# -*- coding: utf-8 -*-
"""
master_list_service.py
======================
Builds the "operational master list": one enriched row per participant that
merges the participant record with the rich fields imported from the source
files (attendee category, job title, region, country, passport, food/allergy …
— modeled on the client master file), plus a data-quality analysis with
recommendations (feedback §6 + §15).
"""

from __future__ import annotations

import logging
import os
from datetime import date, datetime
from typing import Any, Optional

from supabase import Client

logger = logging.getLogger(__name__)

# Rich fields that live in source_records.normalized_data (not participant cols)
RICH_FIELDS = [
    "attendee_category", "job_title", "region", "function", "language",
    "badge_name", "country", "date_of_birth", "passport_number",
    "passport_expiry", "food_allergy_info",
]

# Core participant columns surfaced in the master list
CORE_FIELDS = [
    "id", "first_name", "last_name", "email", "company", "phone", "nationality",
    "dietary_requirements", "completeness_status",
    "has_flight", "has_hotel", "has_transfer", "has_activities",
]

GEMINI_AVAILABLE = False
try:
    import google.generativeai as genai
    if os.getenv("GEMINI_API_KEY"):
        genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
        GEMINI_AVAILABLE = True
except ImportError:
    pass


def _first_non_empty(values: list[Any]) -> Optional[Any]:
    for v in values:
        if v is not None and str(v).strip() != "":
            return v
    return None


def build_master_rows(supabase: Client, event_id: str) -> list[dict[str, Any]]:
    """
    Return one enriched row per participant: core fields + the rich master-file
    fields merged from all of their source records (first non-empty wins).
    """
    try:
        res = (
            supabase.table("participants")
            .select("*, source_records(normalized_data)")
            .eq("event_id", event_id)
            .order("last_name")
            .order("first_name")
            .execute()
        )
    except Exception as exc:
        logger.error("Failed to build master rows for %s: %s", event_id, exc)
        return []

    rows: list[dict[str, Any]] = []
    for p in res.data or []:
        row: dict[str, Any] = {k: p.get(k) for k in CORE_FIELDS}

        # Merge rich fields from the participant's source records
        source_rows = p.get("source_records") or []
        for field in RICH_FIELDS:
            candidates = [sr.get("normalized_data", {}).get(field) for sr in source_rows if sr.get("normalized_data")]
            # dietary lives on the participant already, keep it; others from sources
            row[field] = _first_non_empty(candidates)
        rows.append(row)
    return rows


def _passport_status(expiry: Any) -> Optional[str]:
    """Return 'expired' / 'expiring' (< 6 months) / 'ok' / None from a date-ish value."""
    if not expiry:
        return None
    raw = str(expiry).split("T")[0].split(" ")[0].strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y"):
        try:
            d = datetime.strptime(raw, fmt).date()
            today = date.today()
            if d < today:
                return "expired"
            if (d - today).days < 183:
                return "expiring"
            return "ok"
        except ValueError:
            continue
    return None


def build_analysis(supabase: Client, event_id: str) -> dict[str, Any]:
    """
    Data-quality analysis over the master list: a weighted quality score,
    per-dimension breakdown, distributions (region / category), and concrete
    recommendations. An optional AI narrative summarizes it (feedback §15).
    """
    rows = build_master_rows(supabase, event_id)
    total = len(rows)

    def count_missing(field: str, from_rich: bool = False) -> int:
        n = 0
        for r in rows:
            v = r.get(field)
            if v is None or str(v).strip() == "":
                n += 1
        return n

    missing = {
        "email": count_missing("email"),
        "phone": count_missing("phone"),
        "dietary_requirements": count_missing("dietary_requirements"),
        "passport_number": count_missing("passport_number"),
        "job_title": count_missing("job_title"),
        "region": count_missing("region"),
    }
    without_flight = sum(1 for r in rows if not r.get("has_flight"))
    without_hotel = sum(1 for r in rows if not r.get("has_hotel"))
    without_transfer = sum(1 for r in rows if not r.get("has_transfer"))
    conflicts = sum(1 for r in rows if r.get("completeness_status") == "conflict")

    # Passport validity
    passport_expired = 0
    passport_expiring = 0
    for r in rows:
        st = _passport_status(r.get("passport_expiry"))
        if st == "expired":
            passport_expired += 1
        elif st == "expiring":
            passport_expiring += 1

    # Distributions
    def distribution(field: str) -> dict[str, int]:
        d: dict[str, int] = {}
        for r in rows:
            key = (r.get(field) or "Non renseigné")
            key = str(key).strip() or "Non renseigné"
            d[key] = d.get(key, 0) + 1
        return dict(sorted(d.items(), key=lambda x: x[1], reverse=True))

    by_region = distribution("region")
    by_category = distribution("attendee_category")

    # Quality dimensions (0-100 each), then a weighted overall score
    def pct_present(field: str) -> int:
        if total == 0:
            return 0
        return round(100 * (total - count_missing(field)) / total)

    dimensions = {
        "identite": pct_present("email"),
        "contact": round(100 * (total - sum(1 for r in rows if not r.get("email") and not r.get("phone"))) / total) if total else 0,
        "voyage": round(100 * (total - without_flight) / total) if total else 0,
        "hebergement": round(100 * (total - without_hotel) / total) if total else 0,
        "regime": pct_present("dietary_requirements"),
        "passeport": pct_present("passport_number"),
    }
    weights = {"identite": 0.25, "contact": 0.15, "voyage": 0.2, "hebergement": 0.15, "regime": 0.1, "passeport": 0.15}
    quality_score = round(sum(dimensions[k] * weights[k] for k in dimensions)) if total else 0

    # Rule-based recommendations
    recommendations: list[dict[str, Any]] = []

    def rec(sev: str, text: str, count: int) -> None:
        if count > 0:
            recommendations.append({"severity": sev, "text": text, "count": count})

    rec("warning", "participant(s) sans vol renseigné — à relancer auprès de FCM.", without_flight)
    rec("warning", "participant(s) sans hébergement — vérifier la rooming list.", without_hotel)
    rec("info", "participant(s) sans transfert planifié.", without_transfer)
    rec("info", "participant(s) sans régime alimentaire renseigné.", missing["dietary_requirements"])
    rec("critical", "conflit(s) de données non résolu(s) — à arbitrer dans Exceptions.", conflicts)
    rec("critical", "passeport(s) expiré(s) — bloquant pour le voyage.", passport_expired)
    rec("warning", "passeport(s) expirant dans moins de 6 mois.", passport_expiring)
    rec("info", "participant(s) sans email.", missing["email"])

    analysis = {
        "total": total,
        "quality_score": quality_score,
        "dimensions": dimensions,
        "missing": missing,
        "without_flight": without_flight,
        "without_hotel": without_hotel,
        "without_transfer": without_transfer,
        "conflicts": conflicts,
        "passport_expired": passport_expired,
        "passport_expiring": passport_expiring,
        "by_region": by_region,
        "by_category": by_category,
        "recommendations": recommendations,
        "ai_summary": _ai_summary(total, quality_score, dimensions, recommendations),
    }
    return analysis


def _ai_summary(total: int, score: int, dimensions: dict, recs: list[dict]) -> Optional[str]:
    if not GEMINI_AVAILABLE or total == 0:
        return None
    try:
        prompt = f"""
        Tu es un chef de projet événementiel. Rédige une courte analyse (3-4 phrases,
        en français) de la qualité des données de la master list, avec 2-3 conseils
        d'action priorisés. Base-toi UNIQUEMENT sur ces chiffres, n'invente rien.

        Participants: {total}
        Score qualité global: {score}/100
        Dimensions (%): {dimensions}
        Points d'attention: {[{'quoi': r['text'], 'nombre': r['count']} for r in recs]}
        """
        model = genai.GenerativeModel("gemini-1.5-flash")
        resp = model.generate_content(prompt)
        return resp.text.strip()
    except Exception as exc:
        logger.warning("AI quality summary failed: %s", exc)
        return None
