"""
services/exception_service.py — Data quality exception detector.

Detects structural, logical, and data-quality issues in consolidated event data
and writes them to the ``exceptions`` table for human review.

Detectable exception types:
  PARTICIPANT_NO_FLIGHT   — participant has no linked flight record
  FLIGHT_NO_PARTICIPANT   — FCM source record not linked to any participant
  DATE_INCOHERENCE        — departure before arrival, or dates outside event window
  INVALID_FORMAT          — unparseable date or invalid email format
  MISSING_REQUIRED_FIELD  — first_name, last_name, or email missing after normalisation
  DATA_CONFLICT           — conflicting values between registration and FCM sources
  PARTICIPANT_NO_HOTEL    — participant has no hotel information
  PARTICIPANT_NO_TRANSFER — participant has no transfer information
  PARTICIPANT_NO_DIETARY  — participant has no dietary-requirements information
  MISSING_CONTACT         — participant has neither an email nor a phone number
"""

from __future__ import annotations

import logging
import re
import uuid
from typing import Any, Optional

from supabase import Client

logger = logging.getLogger(__name__)

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_DATE_RE  = re.compile(r"^\d{4}-\d{2}-\d{2}([T ]\d{2}:\d{2}(:\d{2})?(\.\d+)?([+-]\d{2}:?\d{2}|Z)?)?$")  # ISO 8601 (date, optional time)


def _insert_exception(
    supabase: Client,
    run_id: str,
    event_id: str,
    exception_type: str,
    severity: str,
    message: str,
    participant_id: Optional[str] = None,
    source_record_id: Optional[str] = None,
    context_data: Optional[dict] = None,
    exceptions_list: Optional[list[dict]] = None,
) -> None:
    """
    Insert a single exception record into the ``exceptions`` table (or collect in list).
    """
    record = {
        "id": str(uuid.uuid4()),
        "run_id": run_id,
        "event_id": event_id,
        "exception_type": exception_type,
        "severity": severity,
        "message": message,
        "participant_id": participant_id,
        "source_record_id": source_record_id,
        "context_data": context_data,
        "resolved": False,
    }
    if exceptions_list is not None:
        exceptions_list.append(record)
        return

    # Translate only on direct database insert
    db_record = record.copy()
    if db_record["exception_type"] == "NAME_MISMATCH_BETWEEN_SOURCES":
        db_record["exception_type"] = "DATA_CONFLICT"
        if db_record["context_data"] is None:
            db_record["context_data"] = {}
        else:
            db_record["context_data"] = db_record["context_data"].copy()
        db_record["context_data"]["original_type"] = "NAME_MISMATCH_BETWEEN_SOURCES"

    try:
        supabase.table("exceptions").insert(db_record).execute()
    except Exception as exc:
        logger.error("Failed to insert exception %s: %s", exception_type, exc)


def detect_all(
    event_id: str,
    run_id: str,
    supabase: Client,
    event_start_date: Optional[str] = None,
    event_end_date: Optional[str] = None,
) -> int:
    """
    Run all exception detectors for an event after consolidation.
    """
    exceptions_to_insert: list[dict] = []

    # Which source types were imported for this event? "Missing X" alerts only
    # make sense once the X source file exists — otherwise every participant is
    # flagged as missing X, which is pure noise (feedback §14).
    imported_types: set[str] = set()
    try:
        files = supabase.table("uploaded_files").select("source_type").eq("event_id", event_id).execute()
        imported_types = {f["source_type"] for f in (files.data or []) if f.get("source_type")}
    except Exception as exc:
        logger.warning("Could not load imported source types: %s", exc)

    if "fcm" in imported_types:
        _aggregate_coverage_exception(
            event_id, run_id, supabase, exceptions_to_insert,
            flag="has_flight", exception_type="PARTICIPANT_NO_FLIGHT",
            message_fr="{count} participant(s) n'ont pas encore de vol enregistré — voir la master list (filtre « Sans vol »).",
        )
    _detect_flight_no_participant(event_id, run_id, supabase, exceptions_to_insert)
    _detect_missing_required_fields(event_id, run_id, supabase, exceptions_to_insert)
    _detect_invalid_formats(event_id, run_id, supabase, exceptions_to_insert)
    _detect_date_incoherence(event_id, run_id, supabase, event_start_date, event_end_date, exceptions_to_insert)
    _detect_data_conflicts(event_id, run_id, supabase, exceptions_to_insert)
    # Possible duplicates now go to the "Fusions à vérifier" dashboard
    # (match_candidates) via the consolidation arbitration step — no longer
    # flooded here as exceptions.
    _detect_name_mismatches_between_sources(event_id, run_id, supabase, exceptions_to_insert)
    # Per-participant "missing info in the master list" alerts (feedback §14),
    # gated on the relevant source file having been imported.
    if "hotel" in imported_types:
        _aggregate_coverage_exception(
            event_id, run_id, supabase, exceptions_to_insert,
            flag="has_hotel", exception_type="PARTICIPANT_NO_HOTEL",
            message_fr="{count} participant(s) n'ont pas encore d'hébergement — voir la master list (filtre « Sans hôtel »).",
        )
    if "transfer" in imported_types:
        # The exception_type ENUM has no PARTICIPANT_NO_TRANSFER value — reuse
        # MISSING_REQUIRED_FIELD (context_data carries the specifics).
        _aggregate_coverage_exception(
            event_id, run_id, supabase, exceptions_to_insert,
            flag="has_transfer", exception_type="MISSING_REQUIRED_FIELD",
            message_fr="{count} participant(s) n'ont pas encore de transfert — voir la master list (filtre « Sans transfert »).",
        )
    # Actionable per-participant missing profile fields (email/phone/nationality/
    # dietary) → the "Champs manquants" category with per-field sub-categories.
    _detect_missing_profile_fields(event_id, run_id, supabase, exceptions_to_insert)

    total = len(exceptions_to_insert)
    
    if exceptions_to_insert:
        db_payload = []
        for exc in exceptions_to_insert:
            db_exc = exc.copy()
            if db_exc["exception_type"] == "NAME_MISMATCH_BETWEEN_SOURCES":
                db_exc["exception_type"] = "DATA_CONFLICT"
                if db_exc["context_data"] is None:
                    db_exc["context_data"] = {}
                else:
                    db_exc["context_data"] = db_exc["context_data"].copy()
                db_exc["context_data"]["original_type"] = "NAME_MISMATCH_BETWEEN_SOURCES"
            db_payload.append(db_exc)

        try:
            logger.info("Bulk inserting %d exceptions for event %s run %s...", total, event_id, run_id)
            # Batch in chunks of 100
            for i in range(0, len(db_payload), 100):
                supabase.table("exceptions").insert(db_payload[i:i+100]).execute()
        except Exception as exc:
            logger.error("Failed to bulk insert exceptions: %s", exc)

    logger.info("Exception detection complete: %d exceptions for event %s run %s", total, event_id, run_id)
    return total


# ---------------------------------------------------------------------------
# Individual detectors
# ---------------------------------------------------------------------------

def _aggregate_coverage_exception(
    event_id: str,
    run_id: str,
    supabase: Client,
    exceptions_list: list[dict],
    *,
    flag: str,
    exception_type: str,
    message_fr: str,
) -> int:
    """
    COVERAGE gaps ("no flight / no hotel / no transfer") are NOT per-person
    errors: they get ONE aggregated info card with the count and the list of
    concerned participants — the master-list filters show the detail.
    """
    try:
        result = (
            supabase.table("participants")
            .select("id, first_name, last_name")
            .eq("event_id", event_id)
            .eq(flag, False)
            .execute()
        )
    except Exception as exc:
        logger.error("%s query failed: %s", exception_type, exc)
        return 0

    people = result.data or []
    if not people:
        return 0
    names = [f"{p.get('first_name', '')} {p.get('last_name', '')}".strip() for p in people]
    _insert_exception(
        supabase=supabase,
        run_id=run_id,
        event_id=event_id,
        exception_type=exception_type,
        severity="info",
        message=message_fr.format(count=len(people)),
        participant_id=None,
        context_data={
            "aggregate": True,
            "count": len(people),
            "participant_ids": [p["id"] for p in people[:500]],
            "sample_names": names[:15],
        },
        exceptions_list=exceptions_list,
    )
    return 1


def _detect_flight_no_participant(event_id: str, run_id: str, supabase: Client, exceptions_list: list[dict]) -> int:
    """
    FLIGHT_NO_PARTICIPANT — FCM source records not linked to any participant.
    """
    try:
        result = (
            supabase.table("source_records")
            .select("id, normalized_data, file_id")
            .eq("event_id", event_id)
            .is_("participant_id", "null")
            .execute()
        )
    except Exception as exc:
        logger.error("FLIGHT_NO_PARTICIPANT query failed: %s", exc)
        return 0

    if not result.data:
        return 0

    file_ids = list({r["file_id"] for r in result.data})
    try:
        files_resp = (
            supabase.table("uploaded_files")
            .select("id, source_type")
            .in_("id", file_ids)
            .execute()
        )
        fcm_file_ids = {f["id"] for f in files_resp.data if f["source_type"] == "fcm"}
    except Exception as exc:
        logger.error("Failed to load file types for FLIGHT_NO_PARTICIPANT: %s", exc)
        return 0

    count = 0
    for sr in result.data:
        if sr["file_id"] not in fcm_file_ids:
            continue
        nd: dict = sr.get("normalized_data") or {}
        name = f"{nd.get('first_name', '')} {nd.get('last_name', '')}".strip() or "Unknown"
        _insert_exception(
            supabase=supabase,
            run_id=run_id,
            event_id=event_id,
            exception_type="FLIGHT_NO_PARTICIPANT",
            severity="warning",
            message=f"FCM record for '{name}' could not be matched to any registered participant.",
            source_record_id=sr["id"],
            context_data={"normalized_data": nd},
            exceptions_list=exceptions_list,
        )
        count += 1

    logger.debug("FLIGHT_NO_PARTICIPANT: %d exceptions", count)
    return count


def _detect_missing_required_fields(event_id: str, run_id: str, supabase: Client, exceptions_list: list[dict]) -> int:
    """
    MISSING_REQUIRED_FIELD — participants where the IDENTITY fields first_name or
    last_name are absent (critical). Contact/profile fields (email, phone,
    nationality, dietary) are handled by _detect_missing_profile_fields so they
    land in the actionable "Champs manquants" category.
    """
    try:
        result = (
            supabase.table("participants")
            .select("id, first_name, last_name")
            .eq("event_id", event_id)
            .execute()
        )
    except Exception as exc:
        logger.error("MISSING_REQUIRED_FIELD query failed: %s", exc)
        return 0

    count = 0
    for p in result.data or []:
        missing = []
        if not p.get("first_name"): missing.append("first_name")
        if not p.get("last_name"):  missing.append("last_name")

        if missing:
            _insert_exception(
                supabase=supabase,
                run_id=run_id,
                event_id=event_id,
                exception_type="MISSING_REQUIRED_FIELD",
                severity="critical",
                message=f"Participant {p['id']} is missing required identity fields: {', '.join(missing)}.",
                participant_id=p["id"],
                context_data={"missing_fields": missing},
                exceptions_list=exceptions_list,
            )
            count += 1

    logger.debug("MISSING_REQUIRED_FIELD: %d exceptions", count)
    return count


# Profile fields surfaced in the actionable "Champs manquants" category, each an
# editable field on the participant fiche so the "Ajouter" button can fill it.
_MISSING_PROFILE_FIELDS = ("email", "phone", "nationality", "dietary_requirements")


def _detect_missing_profile_fields(event_id: str, run_id: str, supabase: Client, exceptions_list: list[dict]) -> int:
    """
    MISSING_FIELD ("Champs manquants") — ONE exception per participant that is
    missing any of the actionable profile fields (email, phone, nationality,
    dietary). context_data.missing_fields lets the UI sort each person into the
    right sub-category (Email / Téléphone / Nationalité / Régime), each with an
    "Ajouter" button that opens their fiche. One exception per person (not per
    field) keeps the volume sane.
    """
    try:
        result = (
            supabase.table("participants")
            .select("id, first_name, last_name, email, phone, nationality, dietary_requirements")
            .eq("event_id", event_id)
            .execute()
        )
    except Exception as exc:
        logger.error("MISSING_FIELD query failed: %s", exc)
        return 0

    count = 0
    for p in result.data or []:
        missing = [f for f in _MISSING_PROFILE_FIELDS if not (p.get(f) or "").strip()]
        if not missing:
            continue
        name = f"{p.get('first_name', '')} {p.get('last_name', '')}".strip() or p["id"]
        _insert_exception(
            supabase=supabase,
            run_id=run_id,
            event_id=event_id,
            # ENUM-valid; the "missing_field" category marker lives in context_data.
            exception_type="MISSING_REQUIRED_FIELD",
            severity="info",
            message=f"Fiche de « {name} » incomplète — champ(s) manquant(s) : {', '.join(missing)}.",
            participant_id=p["id"],
            context_data={
                "category": "missing_field",
                "missing_fields": missing,
                "participant_name": name,
            },
            exceptions_list=exceptions_list,
        )
        count += 1

    logger.debug("MISSING_FIELD: %d exceptions", count)
    return count


def _detect_invalid_formats(event_id: str, run_id: str, supabase: Client, exceptions_list: list[dict]) -> int:
    """
    INVALID_FORMAT — source records with unparseable dates or invalid emails.
    """
    date_fields = {"departure_date", "return_date", "check_in_date", "check_out_date"}

    try:
        result = (
            supabase.table("source_records")
            .select("id, normalized_data")
            .eq("event_id", event_id)
            .not_.is_("normalized_data", "null")
            .execute()
        )
    except Exception as exc:
        logger.error("INVALID_FORMAT query failed: %s", exc)
        return 0

    count = 0
    for sr in result.data or []:
        nd: dict = sr.get("normalized_data") or {}
        issues: list[str] = []

        # Check email format
        email = nd.get("email")
        if email and not _EMAIL_RE.match(email):
            issues.append(f"email='{email}' is not a valid email address")

        # Check date fields
        for df in date_fields:
            val = nd.get(df)
            if val and isinstance(val, str) and not _DATE_RE.match(val):
                issues.append(f"{df}='{val}' is not a valid ISO-8601 date")

        if issues:
            _insert_exception(
                supabase=supabase,
                run_id=run_id,
                event_id=event_id,
                exception_type="INVALID_FORMAT",
                severity="warning",
                message=f"Source record {sr['id']} has format issues: {'; '.join(issues)}.",
                source_record_id=sr["id"],
                context_data={"issues": issues, "normalized_data": nd},
                exceptions_list=exceptions_list,
            )
            count += 1

    logger.debug("INVALID_FORMAT: %d exceptions", count)
    return count


def _detect_date_incoherence(
    event_id: str,
    run_id: str,
    supabase: Client,
    event_start: Optional[str],
    event_end: Optional[str],
    exceptions_list: list[dict],
) -> int:
    """
    DATE_INCOHERENCE — departure_date < arrival_date or dates outside event window.
    """
    try:
        result = (
            supabase.table("source_records")
            .select("id, normalized_data")
            .eq("event_id", event_id)
            .not_.is_("normalized_data", "null")
            .execute()
        )
    except Exception as exc:
        logger.error("DATE_INCOHERENCE query failed: %s", exc)
        return 0

    count = 0
    for sr in result.data or []:
        nd: dict = sr.get("normalized_data") or {}
        issues: list[str] = []

        dep = nd.get("departure_date")
        ret = nd.get("return_date")

        # departure must not be after return
        if dep and ret and _DATE_RE.match(dep) and _DATE_RE.match(ret):
            if dep > ret:
                issues.append(f"departure_date ({dep}) is after return_date ({ret})")

        # dates must not fall outside the event window
        if event_start and event_end:
            for field, val in [("departure_date", dep), ("return_date", ret)]:
                if val and _DATE_RE.match(val):
                    if val < event_start or val > event_end:
                        issues.append(
                            f"{field} ({val}) falls outside event window {event_start}–{event_end}"
                        )

        if issues:
            _insert_exception(
                supabase=supabase,
                run_id=run_id,
                event_id=event_id,
                exception_type="DATE_INCOHERENCE",
                severity="warning",
                message=f"Source record {sr['id']} has date issues: {'; '.join(issues)}.",
                source_record_id=sr["id"],
                context_data={"issues": issues},
                exceptions_list=exceptions_list,
            )
            count += 1

    logger.debug("DATE_INCOHERENCE: %d exceptions", count)
    return count


_LEGAL_SUFFIX_RE = re.compile(
    r"\b(inc|llc|ltd|limited|corp|corporation|co|sa|sas|sarl|gmbh|bv|nv|plc|ag|spa|srl|pty|group|holding|hldg)\b",
    re.I,
)


def _norm_org(v: Any) -> str:
    """Company/organisation name reduced to its meaningful core: no punctuation,
    no legal suffix, no case — 'LivaNova Inc.' == 'LIVANOVA'."""
    s = re.sub(r"[^a-z0-9 ]", " ", str(v or "").lower())
    s = _LEGAL_SUFFIX_RE.sub(" ", s)
    return " ".join(s.split())


def _values_conflict(field: str, a: Any, b: Any) -> bool:
    """
    True only when two source values GENUINELY disagree — formatting differences
    never count. Phones compare on digits / last 9 (so '+1 513 376 1196' ==
    '5133761196'); organisations ignore case, punctuation and legal suffixes.
    """
    sa, sb = str(a or "").strip(), str(b or "").strip()
    if not sa or not sb:
        return False
    if field == "phone":
        na = re.sub(r"\D", "", sa)
        nb = re.sub(r"\D", "", sb)
        if not na or not nb or na == nb:
            return False
        tail = min(len(na), len(nb), 9)
        return na[-tail:] != nb[-tail:]
    if field in ("company", "nationality"):
        ca, cb = _norm_org(sa), _norm_org(sb)
        if not ca or not cb:
            return False
        # One being a prefix/subset of the other ("LivaNova" vs "LivaNova France")
        # is a refinement, not a contradiction.
        return not (ca == cb or ca in cb or cb in ca)
    return sa.lower() != sb.lower()


def _detect_data_conflicts(event_id: str, run_id: str, supabase: Client, exceptions_list: list[dict]) -> int:
    """
    DATA_CONFLICT — same participant has conflicting values between registration and FCM.
    """
    try:
        result = (
            supabase.table("participants")
            .select(
                "id, first_name, last_name, "
                "registration_source_id, fcm_source_id"
            )
            .eq("event_id", event_id)
            .not_.is_("registration_source_id", "null")
            .not_.is_("fcm_source_id", "null")
            .execute()
        )
    except Exception as exc:
        logger.error("DATA_CONFLICT query failed: %s", exc)
        return 0

    if not result.data:
        return 0

    # Load the source records in bulk
    reg_ids = [p["registration_source_id"] for p in result.data]
    fcm_ids = [p["fcm_source_id"] for p in result.data]
    all_ids = list(set(reg_ids + fcm_ids))

    try:
        sr_resp = (
            supabase.table("source_records")
            .select("id, normalized_data")
            .in_("id", all_ids)
            .execute()
        )
        sr_map = {r["id"]: r["normalized_data"] or {} for r in sr_resp.data}
    except Exception as exc:
        logger.error("Failed to load source_records for DATA_CONFLICT: %s", exc)
        return 0

    # `phone` is deliberately NOT a conflict field: a registration form and a
    # travel agency routinely hold two different (both valid) numbers for the same
    # person — mobile vs office, personal vs corporate. That is extra contact
    # info, not a data error, and flagging it produced hundreds of unactionable
    # cards. Both numbers stay visible in the participant's source data.
    # company/nationality are kept: a real divergence there can reveal a WRONG
    # merge, which is genuinely worth a look.
    conflict_fields = ["company", "nationality"]
    count = 0

    for p in result.data:
        reg_data = sr_map.get(p["registration_source_id"], {})
        fcm_data = sr_map.get(p["fcm_source_id"], {})
        conflicts: list[dict] = []

        for field in conflict_fields:
            reg_val = reg_data.get(field)
            fcm_val = fcm_data.get(field)
            if reg_val and fcm_val and _values_conflict(field, reg_val, fcm_val):
                conflicts.append({
                    "field": field,
                    "registration_value": reg_val,
                    "fcm_value": fcm_val,
                })

        if conflicts:
            name = f"{p.get('first_name', '')} {p.get('last_name', '')}".strip()
            _insert_exception(
                supabase=supabase,
                run_id=run_id,
                event_id=event_id,
                exception_type="DATA_CONFLICT",
                severity="warning",
                message=(
                    f"Participant '{name}' has conflicting data between registration and FCM: "
                    + ", ".join(f"{c['field']}: '{c['registration_value']}' vs '{c['fcm_value']}'" for c in conflicts)
                ),
                participant_id=p["id"],
                context_data={"conflicts": conflicts},
                exceptions_list=exceptions_list,
            )
            count += 1

    logger.debug("DATA_CONFLICT: %d exceptions", count)
    return count


def _detect_possible_duplicates(event_id: str, run_id: str, supabase: Client, exceptions_list: list[dict]) -> int:
    """
    POSSIBLE_DUPLICATE — participants with very similar names but different email addresses.
    """
    from rapidfuzz import fuzz

    try:
        result = (
            supabase.table("participants")
            .select("id, first_name, last_name, email, company")
            .eq("event_id", event_id)
            .execute()
        )
    except Exception as exc:
        logger.error("POSSIBLE_DUPLICATE query failed: %s", exc)
        return 0

    participants = result.data or []
    if len(participants) < 2:
        return 0

    count = 0
    for i in range(len(participants)):
        for j in range(i + 1, len(participants)):
            p1 = participants[i]
            p2 = participants[j]

            email1 = (p1.get("email") or "").strip().lower()
            email2 = (p2.get("email") or "").strip().lower()

            if email1 == email2 or not email1 or not email2:
                continue

            name1 = f"{p1.get('first_name') or ''} {p1.get('last_name') or ''}".strip().lower()
            name2 = f"{p2.get('first_name') or ''} {p2.get('last_name') or ''}".strip().lower()

            if not name1 or not name2:
                continue

            score = fuzz.token_sort_ratio(name1, name2)
            if score >= 80:
                name_display1 = f"{p1.get('first_name') or ''} {p1.get('last_name') or ''}".strip()
                name_display2 = f"{p2.get('first_name') or ''} {p2.get('last_name') or ''}".strip()
                
                _insert_exception(
                    supabase=supabase,
                    run_id=run_id,
                    event_id=event_id,
                    exception_type="POSSIBLE_DUPLICATE",
                    severity="warning",
                    message=(
                        f"Potential duplicate participant detected: '{name_display1}' ({email1}) "
                        f"and '{name_display2}' ({email2}) share very similar names (similarity={score:.1f}%)."
                    ),
                    participant_id=p1["id"],
                    context_data={
                        "participant_a_id": p1["id"],
                        "participant_b_id": p2["id"],
                        "name_a": name_display1,
                        "name_b": name_display2,
                        "email_a": email1,
                        "email_b": email2,
                        "score": float(score),
                    },
                    exceptions_list=exceptions_list,
                )
                count += 1

    return count


def _detect_name_mismatches_between_sources(event_id: str, run_id: str, supabase: Client, exceptions_list: list[dict]) -> int:
    """
    NAME_MISMATCH_BETWEEN_SOURCES — same participant has name mismatch between registration and flight source files.
    """
    try:
        result = (
            supabase.table("participants")
            .select("id, first_name, last_name, registration_source_id, fcm_source_id")
            .eq("event_id", event_id)
            .not_.is_("registration_source_id", "null")
            .not_.is_("fcm_source_id", "null")
            .execute()
        )
    except Exception as exc:
        logger.error("NAME_MISMATCH_BETWEEN_SOURCES query failed: %s", exc)
        return 0

    participants = result.data or []
    if not participants:
        return 0

    reg_ids = [p["registration_source_id"] for p in participants]
    fcm_ids = [p["fcm_source_id"] for p in participants]
    all_ids = list(set(reg_ids + fcm_ids))

    try:
        sr_resp = (
            supabase.table("source_records")
            .select("id, normalized_data")
            .in_("id", all_ids)
            .execute()
        )
        sr_map = {r["id"]: r["normalized_data"] or {} for r in sr_resp.data or []}
    except Exception as exc:
        logger.error("Failed to load source_records for NAME_MISMATCH_BETWEEN_SOURCES: %s", exc)
        return 0

    count = 0
    for p in participants:
        reg_data = sr_map.get(p["registration_source_id"], {})
        fcm_data = sr_map.get(p["fcm_source_id"], {})

        reg_first = (reg_data.get("first_name") or "").strip().lower()
        reg_last = (reg_data.get("last_name") or "").strip().lower()
        fcm_first = (fcm_data.get("first_name") or "").strip().lower()
        fcm_last = (fcm_data.get("last_name") or "").strip().lower()

        if (reg_first or reg_last) and (fcm_first or fcm_last):
            if reg_first != fcm_first or reg_last != fcm_last:
                reg_name = f"{reg_data.get('first_name') or ''} {reg_data.get('last_name') or ''}".strip()
                fcm_name = f"{fcm_data.get('first_name') or ''} {fcm_data.get('last_name') or ''}".strip()
                
                _insert_exception(
                    supabase=supabase,
                    run_id=run_id,
                    event_id=event_id,
                    # ENUM-valid name for a registration-vs-FCM name mismatch.
                    exception_type="NAME_DIVERGENCE",
                    severity="warning",
                    message=(
                        f"Name mismatch: registration name is '{reg_name}' "
                        f"but FCM flight record name is '{fcm_name}'."
                    ),
                    participant_id=p["id"],
                    context_data={
                        "registration_name": reg_name,
                        "fcm_name": fcm_name,
                    },
                    exceptions_list=exceptions_list,
                )
                count += 1

    return count


def _detect_missing_service(
    event_id: str,
    run_id: str,
    supabase: Client,
    exceptions_list: list[dict],
    *,
    flag: str,
    exception_type: str,
    label: str,
    severity: str = "warning",
) -> int:
    """
    Generic per-participant "missing info" detector for a boolean service flag
    (``has_hotel``, ``has_transfer`` …). Flags every participant where the flag
    is False — i.e. that master-list line is missing this information.
    """
    try:
        result = (
            supabase.table("participants")
            .select("id, first_name, last_name, email")
            .eq("event_id", event_id)
            .eq(flag, False)
            .execute()
        )
    except Exception as exc:
        logger.error("%s query failed: %s", exception_type, exc)
        return 0

    count = 0
    for p in result.data or []:
        name = f"{p.get('first_name', '')} {p.get('last_name', '')}".strip()
        _insert_exception(
            supabase=supabase,
            run_id=run_id,
            event_id=event_id,
            exception_type=exception_type,
            severity=severity,
            message=f"Participant '{name}' has no {label} information.",
            participant_id=p["id"],
            context_data={"participant_name": name, "email": p.get("email"), "missing": label},
            exceptions_list=exceptions_list,
        )
        count += 1

    logger.debug("%s: %d exceptions", exception_type, count)
    return count


def _detect_missing_dietary(event_id: str, run_id: str, supabase: Client, exceptions_list: list[dict]) -> int:
    """
    PARTICIPANT_NO_DIETARY — participant has no dietary-requirements information
    recorded in the master list.
    """
    try:
        result = (
            supabase.table("participants")
            .select("id, first_name, last_name, email, dietary_requirements")
            .eq("event_id", event_id)
            .execute()
        )
    except Exception as exc:
        logger.error("PARTICIPANT_NO_DIETARY query failed: %s", exc)
        return 0

    # ONE aggregated info card — a missing dietary preference is a coverage
    # gap, not a per-person error (it would otherwise flood the page with
    # hundreds of cards).
    missing = [p for p in (result.data or []) if not (p.get("dietary_requirements") or "").strip()]
    if not missing:
        return 0
    names = [f"{p.get('first_name', '')} {p.get('last_name', '')}".strip() for p in missing]
    _insert_exception(
        supabase=supabase,
        run_id=run_id,
        event_id=event_id,
        # NOTE: the Postgres exception_type ENUM has no PARTICIPANT_NO_DIETARY
        # value — reuse MISSING_REQUIRED_FIELD with the field in context_data.
        exception_type="MISSING_REQUIRED_FIELD",
        severity="info",
        message=f"{len(missing)} participant(s) n'ont pas d'information de régime alimentaire.",
        participant_id=None,
        context_data={
            "aggregate": True,
            "missing": "dietary_requirements",
            "count": len(missing),
            "participant_ids": [p["id"] for p in missing[:500]],
            "sample_names": names[:15],
        },
        exceptions_list=exceptions_list,
    )
    return 1


def _detect_missing_contact(event_id: str, run_id: str, supabase: Client, exceptions_list: list[dict]) -> int:
    """
    MISSING_CONTACT — participant has neither an email nor a phone number, so
    they cannot be reached for confirmations.
    """
    try:
        result = (
            supabase.table("participants")
            .select("id, first_name, last_name, email, phone")
            .eq("event_id", event_id)
            .execute()
        )
    except Exception as exc:
        logger.error("MISSING_CONTACT query failed: %s", exc)
        return 0

    count = 0
    for p in result.data or []:
        if not p.get("email") and not p.get("phone"):
            name = f"{p.get('first_name', '')} {p.get('last_name', '')}".strip()
            _insert_exception(
                supabase=supabase,
                run_id=run_id,
                event_id=event_id,
                # The exception_type ENUM has no MISSING_CONTACT value.
                exception_type="MISSING_REQUIRED_FIELD",
                severity="warning",
                message=f"Participant '{name}' has no email and no phone number.",
                participant_id=p["id"],
                context_data={"participant_name": name},
                exceptions_list=exceptions_list,
            )
            count += 1

    logger.debug("MISSING_CONTACT: %d exceptions", count)
    return count

