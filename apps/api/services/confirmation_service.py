# -*- coding: utf-8 -*-
"""
confirmation_service.py
=======================
Generate an individual participant confirmation (email/letter) from the
consolidated event data — feedback §13 + "Lettre individuelle".

Hard rule (from the brief): the confirmation must **never invent** information.
Only fields actually present in the participant's consolidated data are used;
missing data is simply omitted (and flagged to the user separately).
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any, Optional
from uuid import UUID

from supabase import Client

logger = logging.getLogger(__name__)

GEMINI_AVAILABLE = False
try:
    import google.generativeai as genai
    if os.getenv("GEMINI_API_KEY"):
        genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
        GEMINI_AVAILABLE = True
except ImportError:
    pass


def _gather(supabase: Client, participant_id: str) -> dict[str, Any]:
    """Collect the participant's core + consolidated logistics (best-effort)."""
    def safe(fn):
        try:
            return fn().data or []
        except Exception as exc:
            logger.warning("confirmation gather sub-query failed: %s", exc)
            return []

    part_res = (
        supabase.table("participants")
        .select("id, event_id, first_name, last_name, email, company, dietary_requirements")
        .eq("id", participant_id)
        .single()
        .execute()
    )
    participant = part_res.data or {}
    event = {}
    if participant.get("event_id"):
        ev = safe(lambda: supabase.table("events").select("name, location_city, location_country, start_date, end_date").eq("id", participant["event_id"]).execute())
        event = ev[0] if ev else {}

    flights = safe(lambda: supabase.table("flights").select("*").eq("participant_id", participant_id).execute())
    transfers = safe(lambda: supabase.table("transfers").select("*").eq("participant_id", participant_id).execute())
    hotel_nights = safe(lambda: supabase.table("hotel_nights").select("*, hotels(name, city)").eq("participant_id", participant_id).execute())
    activities = safe(lambda: supabase.table("participant_activities").select("*, activities(name)").eq("participant_id", participant_id).execute())

    return {
        "participant": participant,
        "event": event,
        "flights": flights,
        "transfers": transfers,
        "hotel_nights": hotel_nights,
        "activities": activities,
    }


def _facts(data: dict[str, Any]) -> dict[str, Any]:
    """Reduce the raw consolidated data to a clean, present-only fact dict."""
    p = data["participant"]
    ev = data["event"]
    facts: dict[str, Any] = {}

    name = f"{p.get('first_name', '')} {p.get('last_name', '')}".strip()
    if name:
        facts["participant_name"] = name
    if ev.get("name"):
        facts["event_name"] = ev["name"]
    loc = ", ".join([x for x in (ev.get("location_city"), ev.get("location_country")) if x])
    if loc:
        facts["event_location"] = loc
    if ev.get("start_date"):
        facts["event_start_date"] = str(ev["start_date"])
    if ev.get("end_date"):
        facts["event_end_date"] = str(ev["end_date"])

    flights = []
    for f in data["flights"]:
        seg = {k: f[k] for k in ("flight_number", "departure_airport", "arrival_airport", "departure_time", "arrival_time", "status") if f.get(k)}
        if seg:
            flights.append(seg)
    if flights:
        facts["flights"] = flights

    nights = []
    for h in data["hotel_nights"]:
        seg = {}
        if (h.get("hotels") or {}).get("name"):
            seg["hotel"] = h["hotels"]["name"]
        for k in ("night_date", "room_type", "status"):
            if h.get(k):
                seg[k] = h[k]
        if seg:
            nights.append(seg)
    if nights:
        facts["hotel_nights"] = nights

    transfers = []
    for tr in data["transfers"]:
        seg = {k: tr[k] for k in ("pickup_location", "dropoff_location", "pickup_time", "transfer_type") if tr.get(k)}
        if seg:
            transfers.append(seg)
    if transfers:
        facts["transfers"] = transfers

    acts = [a["activities"]["name"] for a in data["activities"] if (a.get("activities") or {}).get("name")]
    if acts:
        facts["activities"] = acts

    if p.get("dietary_requirements"):
        facts["dietary_requirements"] = p["dietary_requirements"]

    return facts


def _template(facts: dict[str, Any]) -> tuple[str, str]:
    """Deterministic fallback confirmation (used when no LLM is available)."""
    name = facts.get("participant_name", "")
    event = facts.get("event_name", "l'événement")
    subject = f"Confirmation de votre participation — {event}" if facts.get("event_name") else "Confirmation de votre participation"

    lines = [f"Bonjour {name},", "", f"Nous confirmons votre participation à {event}.", ""]
    if facts.get("event_location") or facts.get("event_start_date"):
        loc = facts.get("event_location", "")
        dates = facts.get("event_start_date", "")
        if facts.get("event_end_date"):
            dates = f"{dates} → {facts['event_end_date']}"
        lines.append(f"Lieu : {loc}".rstrip(" :"))
        if dates:
            lines.append(f"Dates : {dates}")
        lines.append("")

    if facts.get("flights"):
        lines.append("Vos vols :")
        for f in facts["flights"]:
            route = f"{f.get('departure_airport', '')} → {f.get('arrival_airport', '')}".strip(" →")
            lines.append(f"  - {f.get('flight_number', '')} {route} {f.get('departure_time', '')}".rstrip())
        lines.append("")
    if facts.get("hotel_nights"):
        lines.append("Votre hébergement :")
        for h in facts["hotel_nights"]:
            lines.append(f"  - {h.get('hotel', '')} {h.get('night_date', '')} {h.get('room_type', '')}".rstrip())
        lines.append("")
    if facts.get("transfers"):
        lines.append("Vos transferts :")
        for tr in facts["transfers"]:
            lines.append(f"  - {tr.get('pickup_location', '')} → {tr.get('dropoff_location', '')} {tr.get('pickup_time', '')}".strip(" →"))
        lines.append("")
    if facts.get("activities"):
        lines.append("Vos activités : " + ", ".join(facts["activities"]))
        lines.append("")
    if facts.get("dietary_requirements"):
        lines.append(f"Régime alimentaire noté : {facts['dietary_requirements']}")
        lines.append("")

    lines.append("Pour toute question, n'hésitez pas à nous contacter.")
    lines.append("")
    lines.append("Bien cordialement,")
    lines.append("L'équipe organisation")
    return subject, "\n".join(lines)


def _generate_with_gemini(facts: dict[str, Any]) -> Optional[tuple[str, str]]:
    prompt = f"""
    Rédige un e-mail de confirmation de participation, chaleureux et professionnel, en français.

    Utilise UNIQUEMENT les informations fournies ci-dessous (au format JSON). Règle absolue :
    n'invente JAMAIS une information absente ; si un champ manque, ne le mentionne pas.

    Données du participant :
    {json.dumps(facts, ensure_ascii=False, indent=2)}

    Réponds STRICTEMENT en JSON avec deux champs :
    {{"subject": "...", "body": "..."}}
    Le body est le corps de l'e-mail (texte, sauts de ligne autorisés).
    """
    try:
        model = genai.GenerativeModel("gemini-1.5-flash")
        resp = model.generate_content(prompt)
        text = resp.text.strip()
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0].strip()
        elif "```" in text:
            text = text.split("```")[1].split("```")[0].strip()
        parsed = json.loads(text)
        subject = parsed.get("subject") or "Confirmation de votre participation"
        body = parsed.get("body") or ""
        if not body:
            return None
        return subject, body
    except Exception as exc:
        logger.error("Gemini confirmation generation failed, using template: %s", exc)
        return None


def generate_confirmation(supabase: Client, participant_id: str) -> dict[str, Any]:
    """
    Build a confirmation draft for a participant. Returns
    ``{subject, body, facts, missing, source}`` — never persists.
    """
    data = _gather(supabase, participant_id)
    facts = _facts(data)

    # Which useful blocks are missing (surfaced to the user, never invented)
    missing = [
        key for key in ("flights", "hotel_nights", "transfers")
        if key not in facts
    ]

    result = _generate_with_gemini(facts) if GEMINI_AVAILABLE else None
    if result is None:
        subject, body = _template(facts)
        source = "template"
    else:
        subject, body = result
        source = "gemini"

    return {
        "subject": subject,
        "body": body,
        "facts": facts,
        "missing": missing,
        "source": source,
        "event_id": data["participant"].get("event_id"),
    }
