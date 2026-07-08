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
"""

from __future__ import annotations

import logging
import re
import uuid
from typing import Any, Optional

from supabase import Client

logger = logging.getLogger(__name__)

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_DATE_RE  = re.compile(r"^\d{4}-\d{2}-\d{2}$")  # ISO 8601


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
) -> None:
    """
    Insert a single exception record into the ``exceptions`` table.

    Parameters
    ----------
    supabase:         Supabase client.
    run_id:           UUID of the consolidation run that generated this exception.
    event_id:         UUID of the event.
    exception_type:   One of the exception_type enum values.
    severity:         ``critical`` | ``warning`` | ``info``.
    message:          Human-readable description of the exception.
    participant_id:   Optional UUID of the related participant.
    source_record_id: Optional UUID of the related source record.
    context_data:     Optional JSON-serialisable dict with structured context.
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
    try:
        supabase.table("exceptions").insert(record).execute()
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

    Calls each specialised detector in turn and returns the total number of
    exceptions inserted.

    Parameters
    ----------
    event_id:         UUID of the event.
    run_id:           UUID of the consolidation run.
    supabase:         Supabase client.
    event_start_date: ISO-8601 date string of the event start (optional, for DATE_INCOHERENCE).
    event_end_date:   ISO-8601 date string of the event end (optional, for DATE_INCOHERENCE).

    Returns
    -------
    Total number of exception records inserted.
    """
    total = 0
    total += _detect_participant_no_flight(event_id, run_id, supabase)
    total += _detect_flight_no_participant(event_id, run_id, supabase)
    total += _detect_missing_required_fields(event_id, run_id, supabase)
    total += _detect_invalid_formats(event_id, run_id, supabase)
    total += _detect_date_incoherence(event_id, run_id, supabase, event_start_date, event_end_date)
    total += _detect_data_conflicts(event_id, run_id, supabase)
    logger.info("Exception detection complete: %d exceptions for event %s run %s", total, event_id, run_id)
    return total


# ---------------------------------------------------------------------------
# Individual detectors
# ---------------------------------------------------------------------------

def _detect_participant_no_flight(event_id: str, run_id: str, supabase: Client) -> int:
    """
    PARTICIPANT_NO_FLIGHT — participants with has_flight=False.

    These participants are registered but have no flight assignment, which is
    an operational gap that must be resolved before the event.
    """
    try:
        result = (
            supabase.table("participants")
            .select("id, first_name, last_name, email")
            .eq("event_id", event_id)
            .eq("has_flight", False)
            .execute()
        )
    except Exception as exc:
        logger.error("PARTICIPANT_NO_FLIGHT query failed: %s", exc)
        return 0

    count = 0
    for p in result.data or []:
        name = f"{p.get('first_name', '')} {p.get('last_name', '')}".strip()
        _insert_exception(
            supabase=supabase,
            run_id=run_id,
            event_id=event_id,
            exception_type="PARTICIPANT_NO_FLIGHT",
            severity="warning",
            message=f"Participant '{name}' ({p.get('email', 'no email')}) has no flight record.",
            participant_id=p["id"],
            context_data={"participant_name": name, "email": p.get("email")},
        )
        count += 1

    logger.debug("PARTICIPANT_NO_FLIGHT: %d exceptions", count)
    return count


def _detect_flight_no_participant(event_id: str, run_id: str, supabase: Client) -> int:
    """
    FLIGHT_NO_PARTICIPANT — FCM source records not linked to any participant.

    These flight records exist in the FCM file but could not be matched to
    a participant. They may represent guests not in the registration list.
    """
    try:
        result = (
            supabase.table("source_records")
            .select("id, normalized_data, file_id")
            .eq("event_id", event_id)
            .is_("participant_id", "null")
            # We join via uploaded_files.source_type = 'fcm'
            .execute()
        )
    except Exception as exc:
        logger.error("FLIGHT_NO_PARTICIPANT query failed: %s", exc)
        return 0

    # Filter to only FCM-origin records by checking their file's source_type
    # (We load file IDs in bulk to minimise queries)
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
        )
        count += 1

    logger.debug("FLIGHT_NO_PARTICIPANT: %d exceptions", count)
    return count


def _detect_missing_required_fields(event_id: str, run_id: str, supabase: Client) -> int:
    """
    MISSING_REQUIRED_FIELD — participants where first_name, last_name, or email is absent.

    While first_name and last_name are NOT NULL in the schema, their normalised
    counterparts in source_records may be empty. Detect any participant whose
    key identity fields are incomplete.
    """
    try:
        result = (
            supabase.table("participants")
            .select("id, first_name, last_name, email")
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
        if not p.get("email"):      missing.append("email")

        if missing:
            _insert_exception(
                supabase=supabase,
                run_id=run_id,
                event_id=event_id,
                exception_type="MISSING_REQUIRED_FIELD",
                severity="critical" if "last_name" in missing else "warning",
                message=f"Participant {p['id']} is missing required fields: {', '.join(missing)}.",
                participant_id=p["id"],
                context_data={"missing_fields": missing},
            )
            count += 1

    logger.debug("MISSING_REQUIRED_FIELD: %d exceptions", count)
    return count


def _detect_invalid_formats(event_id: str, run_id: str, supabase: Client) -> int:
    """
    INVALID_FORMAT — source records with unparseable dates or invalid emails.

    Scans normalised_data in source_records for values that failed normalisation
    (e.g. a date field that still contains a non-ISO string after normalisation).
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
) -> int:
    """
    DATE_INCOHERENCE — departure_date < arrival_date or dates outside event window.

    Only evaluated when event start/end dates are provided.
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
            )
            count += 1

    logger.debug("DATE_INCOHERENCE: %d exceptions", count)
    return count


def _detect_data_conflicts(event_id: str, run_id: str, supabase: Client) -> int:
    """
    DATA_CONFLICT — same participant has conflicting values between registration and FCM.

    Compares the ``company`` field between the registration source record and the
    FCM source record for each participant that has both. Extend to other fields
    as needed.
    """
    try:
        # Load participants that have both a registration and FCM source
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

    conflict_fields = ["company", "nationality", "phone"]
    count = 0

    for p in result.data:
        reg_data = sr_map.get(p["registration_source_id"], {})
        fcm_data = sr_map.get(p["fcm_source_id"], {})
        conflicts: list[dict] = []

        for field in conflict_fields:
            reg_val = reg_data.get(field)
            fcm_val = fcm_data.get(field)
            if reg_val and fcm_val and reg_val.strip().lower() != fcm_val.strip().lower():
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
            )
            count += 1

    logger.debug("DATA_CONFLICT: %d exceptions", count)
    return count
