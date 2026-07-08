"""
services/consolidation_service.py — Consolidation orchestrator.

Entry point: ``run_consolidation(event_id, run_id, user_id, supabase)``

Consolidation pipeline:
  1. Load all mapped files for the event
  2. Parse raw rows and create source_records
  3. Separate registration records from FCM records
  4. Run the matching engine to link FCM → registration participants
  5. Upsert participants (non-destructive: skip locked fields)
  6. Detect DUPLICATE_EMAIL exceptions
  7. Run the full exception detector
  8. Mark all processed files as 'processed'
  9. Update the consolidation_run with final status and stats
 10. Write a summary entry to the change_log
"""

from __future__ import annotations

import logging
import uuid
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Optional

from rapidfuzz import fuzz
from supabase import Client

from services import exception_service
from services.audit_service import log_change
from services.file_service import download_and_parse_file, get_mapped_files_for_event
from services.mapping_service import apply_mapping, normalise_fields, parse_and_insert_source_records

logger = logging.getLogger(__name__)

# Thresholds for name-matching confidence
SCORE_CERTAIN_THRESHOLD  = 95.0   # email match + high name similarity
SCORE_PROBABLE_THRESHOLD = 75.0   # no email match but strong name match


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

class ParticipantRecord:
    """Lightweight in-memory representation of a (potential) participant."""

    def __init__(self, source_record_id: str, normalized: dict[str, Any]):
        self.source_record_id = source_record_id
        self.normalized = normalized
        self.first_name: str = (normalized.get("first_name") or "").strip()
        self.last_name:  str = (normalized.get("last_name") or "").strip()
        self.email:      str = (normalized.get("email") or "").strip().lower()
        self.company:    str = (normalized.get("company") or "").strip()

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}".strip()


class MatchResult:
    """Outcome of matching a single FCM record against a registration participant."""

    def __init__(
        self,
        fcm_record: ParticipantRecord,
        reg_record: Optional[ParticipantRecord],
        decision: str,  # certain | probable | to_verify | not_found
        score: float,
        signals: dict[str, Any],
    ):
        self.fcm_record  = fcm_record
        self.reg_record  = reg_record
        self.decision    = decision
        self.score       = score
        self.signals     = signals


# ---------------------------------------------------------------------------
# Matching engine
# ---------------------------------------------------------------------------

def _compute_name_score(a: ParticipantRecord, b: ParticipantRecord) -> float:
    """
    Compute a fuzzy name-similarity score between two participant records.

    Uses token_sort_ratio to handle reversed name order (Last, First vs First Last).
    Returns a float in [0, 100].
    """
    score_full = fuzz.token_sort_ratio(a.full_name.lower(), b.full_name.lower())
    # Also try last name only for partial matches
    score_last = fuzz.ratio(a.last_name.lower(), b.last_name.lower())
    return max(score_full, score_last)


def match_sources(
    registrations: list[ParticipantRecord],
    fcm_records: list[ParticipantRecord],
) -> list[MatchResult]:
    """
    Match FCM records against registration records.

    Matching algorithm (in priority order):
    1. **Exact email match** → CERTAIN (score=100)
    2. **No email on one side + high name score ≥ 95** → CERTAIN
    3. **Name score ≥ 75** → PROBABLE
    4. **Name score < 75** → NOT_FOUND

    Parameters
    ----------
    registrations:
        List of ParticipantRecord objects from registration source files.
    fcm_records:
        List of ParticipantRecord objects from FCM source files.

    Returns
    -------
    List of MatchResult — one per FCM record.
    """
    # Build email index for O(1) lookup
    email_index: dict[str, ParticipantRecord] = {}
    for reg in registrations:
        if reg.email:
            email_index[reg.email] = reg

    results: list[MatchResult] = []

    for fcm in fcm_records:
        best_reg: Optional[ParticipantRecord] = None
        best_score = 0.0
        signals: dict[str, Any] = {}

        # Step 1: exact email match
        if fcm.email and fcm.email in email_index:
            best_reg = email_index[fcm.email]
            name_score = _compute_name_score(fcm, best_reg)
            best_score = 100.0
            signals = {"email_match": True, "name_score": name_score}
            decision = "certain"

        else:
            # Step 2–4: name-based fuzzy matching
            signals["email_match"] = False
            for reg in registrations:
                name_score = _compute_name_score(fcm, reg)
                if name_score > best_score:
                    best_score = name_score
                    best_reg = reg
                    signals["name_score"] = name_score
                    signals["company_match"] = (
                        fcm.company.lower() == reg.company.lower()
                        if fcm.company and reg.company
                        else None
                    )

            if best_score >= SCORE_CERTAIN_THRESHOLD:
                decision = "certain"
            elif best_score >= SCORE_PROBABLE_THRESHOLD:
                decision = "probable"
            elif best_reg is not None:
                decision = "to_verify"
            else:
                decision = "not_found"
                best_reg = None

        results.append(
            MatchResult(
                fcm_record=fcm,
                reg_record=best_reg,
                decision=decision,
                score=best_score,
                signals=signals,
            )
        )

    return results


# ---------------------------------------------------------------------------
# Non-destructive merge
# ---------------------------------------------------------------------------

def merge_participant_fields(
    existing: dict[str, Any],
    new_data: dict[str, Any],
    locked_fields: dict[str, Any],
) -> dict[str, Any]:
    """
    Merge new data into an existing participant record, skipping locked fields.

    Rules:
    - Locked fields (``locked_fields[field] == True``) are never overwritten.
    - ``None`` or empty string values in ``new_data`` do not overwrite existing values.
    - Non-locked, non-empty new values are applied.

    Parameters
    ----------
    existing:
        Current participant row from the database.
    new_data:
        Dict of candidate new values.
    locked_fields:
        Dict of ``{field_name: True}`` for locked fields.

    Returns
    -------
    Merged dict ready to be passed to ``supabase.table("participants").update()``.
    """
    merged = existing.copy()
    for field, value in new_data.items():
        if locked_fields.get(field):
            continue  # preserve manually set value
        if value is not None and value != "":
            merged[field] = value
    return merged


# ---------------------------------------------------------------------------
# Duplicate email detector
# ---------------------------------------------------------------------------

def detect_duplicate_emails(
    registrations: list[ParticipantRecord],
    run_id: str,
    event_id: str,
    supabase: Client,
) -> int:
    """
    Detect duplicate email addresses within the registration source records.

    Inserts a DUPLICATE_EMAIL exception for each group of records sharing
    the same email address (when email is not empty).

    Returns
    -------
    Number of exception records inserted.
    """
    from services.exception_service import _insert_exception

    email_groups: dict[str, list[ParticipantRecord]] = defaultdict(list)
    for r in registrations:
        if r.email:
            email_groups[r.email].append(r)

    count = 0
    for email, records in email_groups.items():
        if len(records) > 1:
            names = ", ".join(r.full_name for r in records)
            _insert_exception(
                supabase=supabase,
                run_id=run_id,
                event_id=event_id,
                exception_type="DUPLICATE_EMAIL",
                severity="critical",
                message=f"Email '{email}' appears {len(records)} times in registration data: {names}",
                context_data={
                    "email": email,
                    "occurrences": len(records),
                    "participant_names": names,
                    "source_record_ids": [r.source_record_id for r in records],
                },
            )
            count += 1

    return count


# ---------------------------------------------------------------------------
# Main orchestrator
# ---------------------------------------------------------------------------

async def run_consolidation(
    event_id: str,
    run_id: str,
    user_id: str,
    supabase: Client,
) -> None:
    """
    Orchestrate a full consolidation run for an event.

    This function is designed to run as a FastAPI BackgroundTask.
    All exceptions are caught and surfaced through the run record's ``status``
    field (set to ``failed``) rather than propagating as HTTP errors.

    Steps:
    1. Load mapped files
    2. Parse + insert source_records
    3. Build in-memory participant lists from registration and FCM files
    4. Run matching engine
    5. Upsert participants (non-destructive)
    6. Detect duplicate emails
    7. Run full exception detector
    8. Mark files as processed
    9. Finalise run record

    Parameters
    ----------
    event_id:   UUID of the event.
    run_id:     UUID of the consolidation_run record (already created as 'running').
    user_id:    UUID of the user who triggered the run.
    supabase:   Supabase service-role client.
    """
    logger.info("Consolidation started: run_id=%s event_id=%s", run_id, event_id)

    stats: dict[str, int] = {
        "total_source_records": 0,
        "matched_certain": 0,
        "matched_probable": 0,
        "to_verify": 0,
        "not_found": 0,
        "participants_created": 0,
        "participants_updated": 0,
        "exceptions_count": 0,
    }

    try:
        # ---------------------------------------------------------------
        # 1. Load event metadata (for date incoherence checks)
        # ---------------------------------------------------------------
        event_resp = supabase.table("events").select("start_date, end_date").eq("id", event_id).single().execute()
        event_data = event_resp.data or {}
        event_start = event_data.get("start_date")
        event_end   = event_data.get("end_date")

        # ---------------------------------------------------------------
        # 2. Load mapped files
        # ---------------------------------------------------------------
        mapped_files = get_mapped_files_for_event(supabase, event_id)
        if not mapped_files:
            raise RuntimeError("No mapped files found — consolidation aborted.")

        registrations: list[ParticipantRecord] = []
        fcm_records:   list[ParticipantRecord] = []

        # ---------------------------------------------------------------
        # 3. Parse files, insert source_records, build in-memory lists
        # ---------------------------------------------------------------
        for uploaded_file in mapped_files:
            file_id     = uploaded_file["id"]
            source_type = uploaded_file["source_type"]
            mapping     = uploaded_file.get("column_mapping") or {}

            if not mapping:
                logger.warning("File %s has no column_mapping — skipping.", file_id)
                continue

            df = download_and_parse_file(
                supabase,
                uploaded_file["storage_path"],
                uploaded_file["original_filename"],
            )
            raw_rows = df.to_dict(orient="records")

            # Insert source_records and get their IDs
            inserted_ids = parse_and_insert_source_records(
                supabase=supabase,
                file_id=file_id,
                event_id=event_id,
                df_rows=raw_rows,
                mapping=mapping,
            )
            stats["total_source_records"] += len(inserted_ids)

            # Build ParticipantRecord objects — we need the normalised data
            sr_resp = (
                supabase.table("source_records")
                .select("id, normalized_data")
                .in_("id", inserted_ids)
                .execute()
            )
            for sr in sr_resp.data or []:
                pr = ParticipantRecord(sr["id"], sr.get("normalized_data") or {})
                if source_type == "registration":
                    registrations.append(pr)
                elif source_type == "fcm":
                    fcm_records.append(pr)

        # ---------------------------------------------------------------
        # 4. Upsert participants from registration records
        # ---------------------------------------------------------------
        # Build a quick lookup: email → existing participant_id
        existing_participants: dict[str, str] = {}
        existing_resp = (
            supabase.table("participants")
            .select("id, email, locked_fields")
            .eq("event_id", event_id)
            .execute()
        )
        for p in existing_resp.data or []:
            if p.get("email"):
                existing_participants[p["email"].lower()] = p

        participant_id_map: dict[str, str] = {}  # source_record_id → participant_id

        for reg in registrations:
            nd = reg.normalized

            # Determine if participant already exists
            existing = existing_participants.get(reg.email) if reg.email else None

            if existing:
                # Non-destructive update
                locked = existing.get("locked_fields") or {}
                merged = merge_participant_fields(existing, nd, locked)
                merged["has_flight"] = existing.get("has_flight", False)
                supabase.table("participants").update(merged).eq("id", existing["id"]).execute()
                participant_id = existing["id"]
                stats["participants_updated"] += 1
            else:
                # Create new participant
                participant_id = str(uuid.uuid4())
                new_participant = {
                    "id": participant_id,
                    "event_id": event_id,
                    "first_name": nd.get("first_name") or "",
                    "last_name":  nd.get("last_name") or "",
                    "email":      nd.get("email"),
                    "company":    nd.get("company"),
                    "phone":      nd.get("phone"),
                    "nationality": nd.get("nationality"),
                    "dietary_requirements": nd.get("dietary_requirements"),
                    "completeness_status": "incomplete",
                    "registration_source_id": reg.source_record_id,
                }
                supabase.table("participants").insert(new_participant).execute()
                if reg.email:
                    existing_participants[reg.email] = {"id": participant_id, "email": reg.email, "locked_fields": {}}
                stats["participants_created"] += 1

            participant_id_map[reg.source_record_id] = participant_id

            # Link source_record → participant
            supabase.table("source_records").update({
                "participant_id": participant_id,
                "match_decision": "certain",
                "match_score": 100.0,
                "match_signals": {"source": "registration"},
            }).eq("id", reg.source_record_id).execute()

        # ---------------------------------------------------------------
        # 5. Match FCM records → participants
        # ---------------------------------------------------------------
        match_results = match_sources(registrations, fcm_records)

        for mr in match_results:
            if mr.decision in ("certain", "probable") and mr.reg_record:
                p_id = participant_id_map.get(mr.reg_record.source_record_id)
                if p_id:
                    # Update participant: mark has_flight = True
                    supabase.table("participants").update({
                        "has_flight": True,
                        "fcm_source_id": mr.fcm_record.source_record_id,
                    }).eq("id", p_id).execute()

                    # Link FCM source_record
                    supabase.table("source_records").update({
                        "participant_id": p_id,
                        "match_decision": mr.decision,
                        "match_score": mr.score,
                        "match_signals": mr.signals,
                    }).eq("id", mr.fcm_record.source_record_id).execute()

                    if mr.decision == "certain":
                        stats["matched_certain"] += 1
                    else:
                        stats["matched_probable"] += 1

                        # PROBABLE_MATCH exception for human review
                        from services.exception_service import _insert_exception
                        _insert_exception(
                            supabase=supabase,
                            run_id=run_id,
                            event_id=event_id,
                            exception_type="PROBABLE_MATCH",
                            severity="warning",
                            message=(
                                f"FCM record '{mr.fcm_record.full_name}' was probably matched "
                                f"to participant '{mr.reg_record.full_name}' (score={mr.score:.1f}). "
                                "Please verify."
                            ),
                            source_record_id=mr.fcm_record.source_record_id,
                            participant_id=p_id,
                            context_data=mr.signals,
                        )
                        stats["exceptions_count"] += 1

            elif mr.decision == "to_verify":
                stats["to_verify"] += 1
            else:
                stats["not_found"] += 1

        # ---------------------------------------------------------------
        # 6. Duplicate email detection
        # ---------------------------------------------------------------
        dup_count = detect_duplicate_emails(registrations, run_id, event_id, supabase)
        stats["exceptions_count"] += dup_count

        # ---------------------------------------------------------------
        # 7. Full exception detection
        # ---------------------------------------------------------------
        exc_count = exception_service.detect_all(
            event_id=event_id,
            run_id=run_id,
            supabase=supabase,
            event_start_date=event_start,
            event_end_date=event_end,
        )
        stats["exceptions_count"] += exc_count

        # ---------------------------------------------------------------
        # 8. Update completeness_status on all participants
        # ---------------------------------------------------------------
        _update_completeness_statuses(event_id, supabase)

        # ---------------------------------------------------------------
        # 9. Mark files as processed
        # ---------------------------------------------------------------
        for f in mapped_files:
            supabase.table("uploaded_files").update({"import_status": "processed"}).eq("id", f["id"]).execute()

        # ---------------------------------------------------------------
        # 10. Finalise run record
        # ---------------------------------------------------------------
        supabase.table("consolidation_runs").update({
            "status": "completed",
            "stats": stats,
            "completed_at": datetime.now(timezone.utc).isoformat(),
        }).eq("id", run_id).execute()

        # Summary change_log entry
        log_change(
            supabase=supabase,
            event_id=event_id,
            user_id=user_id,
            entity_type="consolidation_run",
            entity_id=run_id,
            field_name="status",
            old_value="running",
            new_value="completed",
            reason="import",
        )

        logger.info("Consolidation completed: run_id=%s stats=%s", run_id, stats)

    except Exception as exc:
        logger.error("Consolidation FAILED: run_id=%s: %s", run_id, exc, exc_info=True)
        try:
            supabase.table("consolidation_runs").update({
                "status": "failed",
                "stats": stats,
                "completed_at": datetime.now(timezone.utc).isoformat(),
            }).eq("id", run_id).execute()
        except Exception as update_exc:
            logger.error("Failed to mark run as failed: %s", update_exc)


def _update_completeness_statuses(event_id: str, supabase: Client) -> None:
    """
    Recompute and update ``completeness_status`` for all participants of an event.

    A participant is:
    - ``complete``:   has first_name, last_name, email, AND has_flight
    - ``conflict``:   has exceptions of type DATA_CONFLICT (checked separately)
    - ``incomplete``: otherwise
    """
    try:
        participants = (
            supabase.table("participants")
            .select("id, first_name, last_name, email, has_flight")
            .eq("event_id", event_id)
            .execute()
        )
        for p in participants.data or []:
            if p.get("first_name") and p.get("last_name") and p.get("email") and p.get("has_flight"):
                status_val = "complete"
            else:
                status_val = "incomplete"

            supabase.table("participants").update({
                "completeness_status": status_val
            }).eq("id", p["id"]).execute()
    except Exception as exc:
        logger.warning("Failed to update completeness_status: %s", exc)
