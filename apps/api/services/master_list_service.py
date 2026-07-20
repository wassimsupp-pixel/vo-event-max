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
from datetime import date, datetime, timedelta
from typing import Any, Optional

from supabase import Client

from services import geo
from services.mapping_service import CANONICAL_FIELDS

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
    "has_flight", "has_hotel", "has_transfer", "has_activities", "updated_at",
]

# Labels for uploaded_files.source_type, used in the "sources used" data-quality
# column — kept in one place so the export and the API agree.
_SOURCE_TYPE_LABELS = {
    "registration": "Inscription", "fcm": "Vols (FCM)", "hotel": "Hébergement",
    "transfer": "Transfert", "activity": "Activité", "email": "Email", "other": "Autre",
    "masterfile": "Fichier maître",
}

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


def _fmt_dt(val: Any) -> str:
    """Format an ISO datetime as 'DD/MM HH:MM' (best effort, returns '' on failure)."""
    if not val:
        return ""
    raw = str(val).replace("Z", "+00:00")
    try:
        d = datetime.fromisoformat(raw)
        return d.strftime("%d/%m %H:%M")
    except ValueError:
        # date only or free text
        return _fmt_date(val)


def _fmt_date(val: Any) -> str:
    """Format an ISO date as 'DD/MM/YYYY' (best effort)."""
    if not val:
        return ""
    raw = str(val).split("T")[0].split(" ")[0].strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(raw, fmt).strftime("%d/%m/%Y")
        except ValueError:
            continue
    return str(val)


def _fetch_in_chunks(supabase: Client, table: str, select: str, col: str, ids: list[str], chunk: int = 100) -> list[dict[str, Any]]:
    """Fetch rows of *table* where *col* IN *ids* (chunked to keep URLs short)."""
    out: list[dict[str, Any]] = []
    for i in range(0, len(ids), chunk):
        part = ids[i : i + chunk]
        if not part:
            continue
        res = supabase.table(table).select(select).in_(col, part).execute()
        out.extend(res.data or [])
    return out


def _paginate(supabase: Client, table: str, select: str, event_id: str, extra_not_null: Optional[str] = None) -> list[dict[str, Any]]:
    """Fetch all rows of *table* for an event (PostgREST caps at 1000 → paginate)."""
    out: list[dict[str, Any]] = []
    offset = 0
    page = 1000
    while True:
        q = supabase.table(table).select(select).eq("event_id", event_id)
        if extra_not_null:
            q = q.not_.is_(extra_not_null, "null")
        res = q.range(offset, offset + page - 1).execute()
        data = res.data or []
        out.extend(data)
        if len(data) < page:
            break
        offset += page
    return out


def _index_by_participant(rows: list[dict[str, Any]], key: str = "participant_id") -> dict[str, list[dict[str, Any]]]:
    out: dict[str, list[dict[str, Any]]] = {}
    for r in rows:
        pid = r.get(key)
        if pid:
            out.setdefault(pid, []).append(r)
    return out


def build_master_rows(supabase: Client, event_id: str) -> list[dict[str, Any]]:
    """
    Return one enriched row per participant merging, for the master list (§6):
      * core participant fields + rich master-file fields (source_records),
      * real flight details (airline, number, route, dep/arr times),
      * real hotel stay (hotel name, check-in / check-out, nights, room type),
      * real transfers (type, route, pickup time),
      * real activities (name, day & time).

    Uses separate queries + Python merge to avoid the ambiguous PostgREST embed
    (participants and source_records have foreign keys in both directions).
    """
    try:
        participants = _paginate(supabase, "participants", ", ".join(CORE_FIELDS), event_id)
        source_rows = _paginate(supabase, "source_records", "participant_id, file_id, normalized_data", event_id, extra_not_null="participant_id")
    except Exception as exc:
        logger.error("Failed to build master rows for %s: %s", event_id, exc)
        return []

    participant_ids = [p["id"] for p in participants]

    # --- Rich source fields, indexed by participant ---
    by_participant: dict[str, list[dict[str, Any]]] = {}
    for sr in source_rows:
        pid = sr.get("participant_id")
        if pid:
            by_participant.setdefault(pid, []).append(sr.get("normalized_data") or {})

    # --- Which source FILE TYPES fed each participant ("sources used", §11 §8) ---
    files_by_p: dict[str, set[str]] = {}
    try:
        file_ids = sorted({sr["file_id"] for sr in source_rows if sr.get("file_id")})
        file_type_by_id: dict[str, str] = {}
        if file_ids:
            for f in _fetch_in_chunks(supabase, "uploaded_files", "id, source_type", "id", file_ids):
                file_type_by_id[f["id"]] = f.get("source_type") or ""
        for sr in source_rows:
            pid = sr.get("participant_id")
            ftype = file_type_by_id.get(sr.get("file_id"))
            if pid and ftype:
                files_by_p.setdefault(pid, set()).add(ftype)
    except Exception as exc:
        logger.warning("Master list source-type enrichment partial for %s: %s", event_id, exc)

    # --- Open exceptions per participant (§11 §8 "Qualité des données") ---
    exceptions_by_p: dict[str, list[dict[str, Any]]] = {}
    try:
        exc_rows = _paginate(supabase, "exceptions", "participant_id, severity, resolved", event_id)
        for e in exc_rows:
            pid = e.get("participant_id")
            if pid and not e.get("resolved"):
                exceptions_by_p.setdefault(pid, []).append(e)
    except Exception as exc:
        logger.warning("Master list exception enrichment partial for %s: %s", event_id, exc)

    # --- Communications (§11 §7) — table may not exist yet (migration 002) ---
    comms_by_p: dict[str, list[dict[str, Any]]] = {}
    try:
        comms = _fetch_in_chunks(supabase, "communications",
                                  "participant_id, type, status, sent_at, updated_at",
                                  "participant_id", participant_ids)
        comms_by_p = _index_by_participant(comms)
    except Exception as exc:
        logger.debug("Communications not available for master list %s: %s", event_id, exc)

    # --- Travel details (best-effort; never block the master list) ---
    flights_by_p: dict[str, list[dict[str, Any]]] = {}
    transfers_by_p: dict[str, list[dict[str, Any]]] = {}
    nights_by_p: dict[str, list[dict[str, Any]]] = {}
    acts_by_p: dict[str, list[dict[str, Any]]] = {}
    hotel_names: dict[str, str] = {}
    activity_info: dict[str, dict[str, Any]] = {}
    try:
        flights = _paginate(supabase, "flights",
                            "participant_id, airline, flight_number, departure_airport, arrival_airport, departure_time, arrival_time, status",
                            event_id)
        flights_by_p = _index_by_participant(flights)

        transfers = _paginate(supabase, "transfers",
                             "participant_id, transfer_type, pickup_location, dropoff_location, pickup_time, vehicle_type, status",
                             event_id)
        transfers_by_p = _index_by_participant(transfers)

        hotels = _paginate(supabase, "hotels", "id, name", event_id)
        hotel_names = {h["id"]: h.get("name") or "" for h in hotels}
        nights = _fetch_in_chunks(supabase, "hotel_nights",
                                  "participant_id, hotel_id, night_date, room_type, status",
                                  "participant_id", participant_ids)
        nights_by_p = _index_by_participant(nights)

        activities = _paginate(supabase, "activities", "id, name, date_time, location", event_id)
        activity_info = {a["id"]: a for a in activities}
        pacts = _fetch_in_chunks(supabase, "participant_activities",
                                 "participant_id, activity_id, status",
                                 "participant_id", participant_ids)
        acts_by_p = _index_by_participant(pacts)
    except Exception as exc:
        logger.warning("Master list travel enrichment partial for %s: %s", event_id, exc)

    rows: list[dict[str, Any]] = []
    for p in participants:
        pid = p["id"]
        row: dict[str, Any] = {k: p.get(k) for k in CORE_FIELDS}
        nds = by_participant.get(pid, [])
        for field in RICH_FIELDS:
            row[field] = _first_non_empty([nd.get(field) for nd in nds])

        # Custom (user-defined) mapping fields: any normalized_data key that is
        # not a canonical field — surfaced so master list / export show them.
        custom: dict[str, Any] = {}
        for nd in nds:
            for k, v in nd.items():
                if k not in CANONICAL_FIELDS and k not in custom and v is not None and str(v).strip() != "":
                    custom[k] = v
        row["custom"] = custom

        # Flights → one line per flight, sorted by departure
        flist = sorted(flights_by_p.get(pid, []), key=lambda f: str(f.get("departure_time") or ""))
        flight_lines = []
        for f in flist:
            dep = geo.city_name(f.get('departure_airport')) or '?'
            arr = geo.city_name(f.get('arrival_airport')) or '?'
            route = f"{dep}→{arr}"
            times = f"{_fmt_dt(f.get('departure_time'))}→{_fmt_dt(f.get('arrival_time'))}".strip("→")
            airline = (f.get("airline") or "").strip()
            num = (f.get("flight_number") or "").strip()
            head = " ".join(x for x in [airline, num] if x)
            cancelled = " (annulé)" if f.get("status") == "cancelled" else ""
            flight_lines.append(f"{head} · {route} · {times}{cancelled}".strip(" ·"))
        row["flight_summary"] = "\n".join(flight_lines)
        row["flight_count"] = len(flist)

        # Outbound / return as their own columns (§11 blocs 2-3). Same positional
        # convention already shown to users on the Flights page (segmentLabel):
        # sorted by departure, the FIRST segment is the outbound leg, the LAST is
        # the return — a direct round trip has exactly two segments either way,
        # and a connecting itinerary's outer legs are still the meaningful ones.
        # Nothing is lost for 3+-segment trips: flight_summary above keeps every
        # leg, this just surfaces the two that matter for a Vol Aller/Retour view.
        def _flight_cols(f: Optional[dict[str, Any]]) -> dict[str, Any]:
            if not f:
                return {"airline": "", "flight_number": "", "departure_airport": "",
                        "arrival_airport": "", "departure_time": "", "arrival_time": "", "status": ""}
            return {
                "airline": f.get("airline") or "",
                "flight_number": f.get("flight_number") or "",
                "departure_airport": geo.city_name(f.get("departure_airport")) or f.get("departure_airport") or "",
                "arrival_airport": geo.city_name(f.get("arrival_airport")) or f.get("arrival_airport") or "",
                "departure_time": _fmt_dt(f.get("departure_time")),
                "arrival_time": _fmt_dt(f.get("arrival_time")),
                "status": f.get("status") or "",
            }
        outbound = flist[0] if flist else None
        inbound = flist[-1] if len(flist) >= 2 else None
        for k, v in _flight_cols(outbound).items():
            row[f"outbound_{k}"] = v
        for k, v in _flight_cols(inbound).items():
            row[f"return_{k}"] = v

        # Hotel nights → check-in / check-out / nights.
        #
        # A participant can have nights across SEVERAL distinct properties (a
        # pre-event villa, then the main conference hotel) — two real, separate
        # bookings. Flattening every night's date into one min/max span mixed
        # them into a single fabricated stay: wrong property name (picked at
        # random), a date range that included nights nobody actually slept
        # (the gap between the two bookings), and a night COUNT that
        # contradicted the span shown. Group by hotel_id first and only ever
        # summarise nights that belong to the SAME property.
        nl = nights_by_p.get(pid, [])
        by_hotel: dict[Any, list[dict]] = {}
        for n in nl:
            if n.get("night_date"):
                by_hotel.setdefault(n.get("hotel_id"), []).append(n)

        if by_hotel:
            # The stay with the most nights is the primary one shown in the
            # scalar columns (earliest check-in breaks a tie) — never a mix.
            stay_groups = sorted(
                by_hotel.values(),
                key=lambda g: (-len(g), min(str(x["night_date"]) for x in g)),
            )
            primary = stay_groups[0]
            night_dates = sorted(str(n["night_date"]) for n in primary)
            row["hotel_name"] = _first_non_empty([hotel_names.get(n.get("hotel_id")) for n in primary]) or ""
            row["hotel_checkin"] = _fmt_date(night_dates[0])
            # Check-out = the morning AFTER the last night slept. hotel_nights
            # stores the nights actually occupied (check-in .. check-out-1), so
            # the departure date is the last night + 1 day (was off by -1).
            try:
                _last = date.fromisoformat(str(night_dates[-1])[:10])
                row["hotel_checkout"] = _fmt_date((_last + timedelta(days=1)).isoformat())
            except Exception:
                row["hotel_checkout"] = _fmt_date(night_dates[-1])
            row["hotel_nights_count"] = len(night_dates)
            row["hotel_room_type"] = _first_non_empty([n.get("room_type") for n in primary]) or ""
            # Additional distinct properties exist: say so rather than dropping
            # them silently — the full detail remains on the hotels page.
            extra = len(stay_groups) - 1
            if extra > 0:
                other_nights = sum(len(g) for g in stay_groups[1:])
                row["hotel_name"] = f"{row['hotel_name']} (+{extra} hébergement(s), {other_nights} nuit(s))"
        else:
            row["hotel_name"] = ""
            row["hotel_checkin"] = ""
            row["hotel_checkout"] = ""
            row["hotel_nights_count"] = 0
            row["hotel_room_type"] = ""

        # Transfers → one line per transfer
        tlist = sorted(transfers_by_p.get(pid, []), key=lambda t: str(t.get("pickup_time") or ""))
        transfer_lines = []
        for tr in tlist:
            route = f"{tr.get('pickup_location') or '?'}→{tr.get('dropoff_location') or '?'}"
            when = _fmt_dt(tr.get("pickup_time"))
            veh = (tr.get("vehicle_type") or "").strip()
            typ = (tr.get("transfer_type") or "").strip()
            transfer_lines.append(" · ".join(x for x in [typ, route, when, veh] if x))
        row["transfer_summary"] = "\n".join(transfer_lines)
        row["transfer_count"] = len(tlist)

        # Transfert Arrivée / Transfert Retour as their own columns (§11 bloc 5).
        # Bucketed the same way the extraction step already classifies a
        # transfer's direction (consolidation_service: transfer_type starting
        # with "depart" is the return leg, everything else is arrival) — so a
        # transfer imported as "Departure"/"Retour"/"Départ" always lands on the
        # same side here as it did when it was created.
        arr_bucket = [t for t in tlist if not str(t.get("transfer_type") or "").lower().startswith("depart")]
        ret_bucket = [t for t in tlist if str(t.get("transfer_type") or "").lower().startswith("depart")]

        def _transfer_cols(t: Optional[dict[str, Any]]) -> dict[str, Any]:
            if not t:
                return {"type": "", "route": "", "time": "", "vehicle": "", "status": ""}
            return {
                "type": t.get("transfer_type") or "",
                "route": f"{t.get('pickup_location') or '?'}→{t.get('dropoff_location') or '?'}",
                "time": _fmt_dt(t.get("pickup_time")),
                "vehicle": t.get("vehicle_type") or "",
                "status": t.get("status") or "",
            }
        # Earliest arrival transfer (the first leg of the trip), latest return
        # transfer (the last leg) — the representative one when several exist;
        # the rest stay visible in transfer_summary above.
        for k, v in _transfer_cols(arr_bucket[0] if arr_bucket else None).items():
            row[f"transfer_arrival_{k}"] = v
        for k, v in _transfer_cols(ret_bucket[-1] if ret_bucket else None).items():
            row[f"transfer_return_{k}"] = v

        # Activities → name · day & time, chronological (was insertion order).
        alist = sorted(acts_by_p.get(pid, []),
                       key=lambda pa: str((activity_info.get(pa.get("activity_id"), {}) or {}).get("date_time") or ""))
        act_lines = []
        act_details: list[dict[str, Any]] = []
        for pa in alist:
            info = activity_info.get(pa.get("activity_id"), {})
            name = (info.get("name") or "").strip()
            when = _fmt_dt(info.get("date_time"))
            if name:
                act_lines.append(f"{name}{(' · ' + when) if when else ''}")
                act_details.append({
                    "name": name, "when": when,
                    "location": info.get("location") or "", "status": pa.get("status") or "",
                })
        row["activities_summary"] = "\n".join(act_lines)
        row["activities_count"] = len(act_lines)

        # Activité 1 / Activité 2 as their own columns (§11 bloc 6). A 3rd+
        # activity is not dropped — it stays in activities_summary above.
        for slot in (1, 2):
            d = act_details[slot - 1] if len(act_details) >= slot else None
            row[f"activity_{slot}_name"] = d["name"] if d else ""
            row[f"activity_{slot}_when"] = d["when"] if d else ""
            row[f"activity_{slot}_location"] = d["location"] if d else ""
            row[f"activity_{slot}_status"] = d["status"] if d else ""

        # Communications (§11 bloc 7) — best-effort, table optional (migration 002).
        clist = comms_by_p.get(pid, [])
        confirmations = [c for c in clist if c.get("type") == "confirmation"]
        sent_confirmations = [c for c in confirmations if c.get("status") == "sent"]
        row["comm_confirmation_prepared"] = len(confirmations) > 0
        row["comm_confirmation_sent"] = len(sent_confirmations) > 0
        row["comm_sent_date"] = _fmt_date(
            max((c.get("sent_at") for c in sent_confirmations if c.get("sent_at")), default="")
        ) if sent_confirmations else ""
        row["comm_needs_update"] = any(c.get("status") == "outdated" for c in clist)
        latest = max(clist, key=lambda c: str(c.get("updated_at") or ""), default=None)
        row["comm_last_activity"] = (
            f"{latest.get('type') or ''} · {_fmt_date(latest.get('updated_at'))}".strip(" ·")
            if latest else ""
        )

        # Data quality (§11 bloc 8) — computed from what is already known about
        # this row; nothing here is invented, only summarised.
        missing_fields = [
            label for field, label in (
                ("first_name", "prénom"), ("email", "email"), ("phone", "téléphone"),
                ("nationality", "nationalité"), ("dietary_requirements", "régime"),
            ) if not str(row.get(field) or "").strip()
        ]
        open_excs = exceptions_by_p.get(pid, [])
        has_critical = any(e.get("severity") == "critical" for e in open_excs)
        is_conflict = row.get("completeness_status") == "conflict"
        row["dq_complete"] = row.get("completeness_status") == "complete" and not open_excs
        row["dq_missing_fields"] = ", ".join(missing_fields)
        row["dq_open_exceptions"] = len(open_excs)
        row["dq_conflict"] = is_conflict
        row["dq_priority"] = (
            "critique" if (has_critical or is_conflict)
            else "attention" if (open_excs or missing_fields)
            else "ok"
        )
        row["dq_sources_used"] = ", ".join(
            _SOURCE_TYPE_LABELS.get(t, t) for t in sorted(files_by_p.get(pid, set()))
        )
        row["dq_last_updated"] = _fmt_date(row.get("updated_at"))
        if is_conflict:
            row["dq_action_needed"] = "Arbitrer le conflit de données"
        elif has_critical:
            row["dq_action_needed"] = "Résoudre l'exception critique"
        elif missing_fields:
            row["dq_action_needed"] = f"Compléter : {', '.join(missing_fields)}"
        elif open_excs:
            row["dq_action_needed"] = "Vérifier les exceptions ouvertes"
        else:
            row["dq_action_needed"] = ""

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
            # Plausibility guard: a passport EXPIRY realistically falls within a
            # window around today. Values outside it are almost certainly a birth
            # date or a mis-mapped column bleeding in — not a real expiry — so we
            # ignore them instead of raising a false "expired" alert.
            if not (today.year - 12 <= d.year <= today.year + 15):
                return None
            if d < today:
                return "expired"
            if (d - today).days < 183:
                return "expiring"
            return "ok"
        except ValueError:
            continue
    return None


def build_analysis(supabase: Client, event_id: str, include_ai_summary: bool = False) -> dict[str, Any]:
    """
    Data-quality analysis over the master list: a weighted quality score,
    per-dimension breakdown, distributions (region / category), and concrete
    recommendations (all computed WITHOUT AI, so it is fast). The AI narrative
    is generated only when ``include_ai_summary`` is set — off by default so the
    dashboard never waits on a slow model.
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
    without_activities = sum(1 for r in rows if not r.get("has_activities"))
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
    rec("info", "participant(s) sans activité inscrite.", without_activities)
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
        "without_activities": without_activities,
        "conflicts": conflicts,
        "passport_expired": passport_expired,
        "passport_expiring": passport_expiring,
        "by_region": by_region,
        "by_category": by_category,
        "recommendations": recommendations,
        "ai_summary": _ai_summary(total, quality_score, dimensions, recommendations) if include_ai_summary else None,
    }
    return analysis


def _ai_summary(total: int, score: int, dimensions: dict, recs: list[dict]) -> Optional[str]:
    from services import ai_service
    if not ai_service.ai_available() or total == 0:
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
        # Opt-in only (ai_summary=True): the page already rendered without it, so
        # this is a deliberate, awaited request. 40s lets the reasoning model
        # finish (~28s); still bounded so it can never hang indefinitely.
        return ai_service.ai_text(prompt, timeout_s=40.0)
    except Exception as exc:
        logger.warning("AI quality summary failed: %s", exc)
        return None
