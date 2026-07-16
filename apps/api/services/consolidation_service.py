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

def fetch_all_source_records(supabase: Client, file_ids: list[str]) -> list[dict]:
    all_data = []
    limit = 1000
    offset = 0
    while True:
        resp = supabase.table("source_records").select("id, normalized_data, raw_data, file_id, event_id, row_index").in_("file_id", file_ids).range(offset, offset + limit - 1).execute()
        data = resp.data or []
        all_data.extend(data)
        if len(data) < limit:
            break
        offset += limit
    return all_data

def fetch_all_hotel_nights(supabase: Client, hotel_ids: list[str]) -> list[dict]:
    all_data = []
    limit = 1000
    offset = 0
    while True:
        resp = supabase.table("hotel_nights").select("id, participant_id, night_date").in_("hotel_id", hotel_ids).range(offset, offset + limit - 1).execute()
        data = resp.data or []
        all_data.extend(data)
        if len(data) < limit:
            break
        offset += limit
    return all_data

def fetch_all_participants(supabase: Client, event_id: str) -> list[dict]:
    all_data = []
    limit = 1000
    offset = 0
    while True:
        resp = supabase.table("participants").select("id, email, locked_fields, nationality").eq("event_id", event_id).range(offset, offset + limit - 1).execute()
        data = resp.data or []
        all_data.extend(data)
        if len(data) < limit:
            break
        offset += limit
    return all_data

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
    if isinstance(locked_fields, list):
        locked_fields = {f: True for f in locked_fields}
    elif not isinstance(locked_fields, dict):
        locked_fields = {}

    for field, value in new_data.items():
        if locked_fields.get(field):
            continue  # preserve manually set value
        if value is not None and value != "":
            merged[field] = value

    # Clean up nationality if it's one of the source type indicators
    src_indicators = {'Formulaire web', 'Assistant', 'Import Excel', 'Email direct'}
    if merged.get("nationality") in src_indicators:
        merged["nationality"] = None

    return merged


# Columns that actually exist on the participants table. normalized_data can
# carry many extra master-file fields (attendee_category, passport_number, …)
# which live in source_records — writing them to participants would fail with
# "column does not exist", so updates are filtered to this whitelist.
_PARTICIPANT_WRITABLE_FIELDS = {
    "first_name", "last_name", "email", "company", "phone", "nationality",
    "dietary_requirements", "completeness_status",
    "has_flight", "has_hotel", "has_transfer", "has_activities",
    "verification_note", "registration_source_id", "fcm_source_id",
}


# ---------------------------------------------------------------------------
# Duplicate email detector
# ---------------------------------------------------------------------------

def detect_duplicate_emails(
    registrations: list[ParticipantRecord],
    run_id: str,
    event_id: str,
    supabase: Client,
    exceptions_list: Optional[list[dict]] = None,
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
                exceptions_list=exceptions_list,
            )
            count += 1

    return count


# ---------------------------------------------------------------------------
# Main orchestrator
# ---------------------------------------------------------------------------

def _name_key(first: Any, last: Any) -> str:
    """Normalised 'first last' key (lowercased, accent-stripped) for deduping the
    same person across files when the email is missing or inconsistent."""
    import unicodedata
    s = f"{first or ''} {last or ''}".strip().lower()
    s = "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")
    return " ".join(s.split())


import re as _re
# Subtotal / label rows that must NOT become participants (e.g. "115 / Total",
# "Percussion facilitator"). Only applied when there is no email to trust.
_ROLE_NOISE = _re.compile(r"\b(total|subtotal|sous[-\s]?total|grand\s*total|facilitator|animateur|organizer|n/?a)\b", _re.I)


def _is_real_person(nd: dict[str, Any]) -> bool:
    """False for parasitic rows (subtotals, job-title labels, fully-empty)."""
    first = (nd.get("first_name") or "").strip()
    last = (nd.get("last_name") or "").strip()
    email = (nd.get("email") or "").strip()
    traveler = (nd.get("traveler_name") or "").strip()
    if not any([first, last, email, traveler]):
        return False           # no identity at all
    if email:
        return True            # a real email → trust it's a person
    combined = f"{first} {last} {traveler}".strip()
    if _re.fullmatch(r"[\d\s/.\-]+", combined):
        return False           # purely numeric (subtotal row)
    if _ROLE_NOISE.search(combined):
        return False           # "… Total", "Percussion facilitator", …
    return True


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
                .eq("file_id", file_id)
                .execute()
            )
            for sr in sr_resp.data or []:
                pr = ParticipantRecord(sr["id"], sr.get("normalized_data") or {})
                # 'masterfile' = one combined file (participants + flights + hotel +
                # transfers + activities). Treat each row as a participant record
                # like a registration; its flight/hotel/etc. columns are extracted
                # afterwards by extract_domain_data_from_sources (runs on all rows).
                if source_type in ("registration", "masterfile"):
                    registrations.append(pr)
                elif source_type == "fcm":
                    fcm_records.append(pr)

        # ---------------------------------------------------------------
        # 4. Upsert participants from registration records
        # ---------------------------------------------------------------
        # Lookups to dedupe the same person across the 10+ files: by email AND
        # by normalised name (so records with a missing/inconsistent email still
        # merge into one participant instead of creating duplicates).
        by_email: dict[str, dict] = {}
        by_name: dict[str, dict] = {}
        existing_data = fetch_all_participants(supabase, event_id)
        for p in existing_data:
            if p.get("email"):
                by_email[p["email"].lower()] = p
            nk = _name_key(p.get("first_name"), p.get("last_name"))
            if nk:
                by_name.setdefault(nk, p)

        participant_id_map: dict[str, str] = {}  # source_record_id → participant_id

        skipped_noise = 0
        for reg in registrations:
            nd = reg.normalized

            # Skip parasitic rows (subtotals, job-title labels, fully-empty) — they
            # must not be created as participants (feedback #4).
            if not _is_real_person(nd):
                skipped_noise += 1
                continue

            email = (nd.get("email") or "").strip().lower() or None
            name_key = _name_key(nd.get("first_name"), nd.get("last_name"))
            full_name = f"{(nd.get('first_name') or '').strip()} {(nd.get('last_name') or '').strip()}".strip()

            # 1) match by email; 2) exact same name; 3) fuzzy same name — unless
            #    emails clearly conflict (two different people sharing a name).
            existing = by_email.get(email) if email else None
            if not existing and name_key:
                cand = by_name.get(name_key)
                if not cand:
                    # Fuzzy: tolerate spelling variants ("Steph" vs "Stephanie").
                    best = 0
                    for k, c in by_name.items():
                        sc = fuzz.token_sort_ratio(name_key, k)
                        if sc > best:
                            best, cand = sc, c
                    if best < 90:
                        cand = None
                if cand:
                    cand_email = (cand.get("email") or "").strip().lower() or None
                    if not email or not cand_email or email == cand_email:
                        existing = cand

            if existing:
                # Non-destructive merge: keep known values, fill the gaps.
                locked = existing.get("locked_fields") or {}
                merged = merge_participant_fields(existing, nd, locked)
                merged["has_flight"] = existing.get("has_flight", False)
                merged["registration_source_id"] = reg.source_record_id
                update_payload = {k: v for k, v in merged.items() if k in _PARTICIPANT_WRITABLE_FIELDS}
                # Log the real field changes so the Change Log is meaningful (feedback #9).
                for f, newv in update_payload.items():
                    oldv = existing.get(f)
                    if str(oldv or "") != str(newv or ""):
                        try:
                            log_change(
                                supabase=supabase, event_id=event_id, user_id=user_id,
                                entity_type="participant", entity_id=existing["id"],
                                field_name=f, old_value=str(oldv or ""), new_value=str(newv or ""),
                                reason="merge",
                            )
                        except Exception:
                            pass
                supabase.table("participants").update(update_payload).eq("id", existing["id"]).execute()
                participant_id = existing["id"]
                # Keep the in-memory record fresh so later files merge onto it too.
                existing.update(update_payload)
                if email:
                    by_email[email] = existing
                if name_key:
                    by_name.setdefault(name_key, existing)
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
                    "locked_fields": {},
                }
                supabase.table("participants").insert(
                    {k: v for k, v in new_participant.items() if k != "locked_fields" or v}
                ).execute()
                if email:
                    by_email[email] = new_participant
                if name_key:
                    by_name.setdefault(name_key, new_participant)
                stats["participants_created"] += 1

            participant_id_map[reg.source_record_id] = participant_id

            # Link source_record → participant
            supabase.table("source_records").update({
                "participant_id": participant_id,
                "match_decision": "certain",
                "match_score": 100.0,
                "match_signals": {"source": "registration"},
            }).eq("id", reg.source_record_id).execute()

        stats["skipped_noise_rows"] = skipped_noise
        if skipped_noise:
            logger.info("Skipped %d parasitic (subtotal/label) rows during consolidation", skipped_noise)

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
        dup_exceptions = []
        dup_count = detect_duplicate_emails(registrations, run_id, event_id, supabase, exceptions_list=dup_exceptions)
        if dup_exceptions:
            try:
                for i in range(0, len(dup_exceptions), 100):
                    supabase.table("exceptions").insert(dup_exceptions[i:i+100]).execute()
            except Exception as exc:
                logger.error("Failed to bulk insert duplicate email exceptions: %s", exc)
        stats["exceptions_count"] += dup_count

        # ---------------------------------------------------------------
        # 6b. Match non-registration source records to participants
        # ---------------------------------------------------------------
        match_non_registration_files_to_participants(event_id, supabase)

        # ---------------------------------------------------------------
        # 6c. Reconcile FCM match stats with reality. Step 5 can report
        #     'not_found' for flight records whose identity is a single
        #     "Traveller" name; step 6b then links them (or creates a client).
        #     Recompute the counters from actual linkage so the dashboard is
        #     accurate: matched_certain + matched_probable = linked, and
        #     not_found = genuinely unlinked flight records.
        # ---------------------------------------------------------------
        try:
            fcm_ids = [f["id"] for f in mapped_files if f.get("source_type") == "fcm"]
            if fcm_ids:
                total_fcm = 0
                linked_fcm = 0
                offset = 0
                while True:
                    res = (
                        supabase.table("source_records")
                        .select("participant_id")
                        .in_("file_id", fcm_ids)
                        .range(offset, offset + 999)
                        .execute()
                    )
                    data = res.data or []
                    total_fcm += len(data)
                    linked_fcm += sum(1 for r in data if r.get("participant_id"))
                    if len(data) < 1000:
                        break
                    offset += 1000
                stats["not_found"] = max(0, total_fcm - linked_fcm)
                stats["to_verify"] = 0
                stats["matched_probable"] = min(stats["matched_probable"], linked_fcm)
                stats["matched_certain"] = max(0, linked_fcm - stats["matched_probable"])
        except Exception as exc:
            logger.warning("Failed to reconcile FCM match stats: %s", exc)

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
        # 8. Extract flights, hotels, transfers, and activities from source records
        # ---------------------------------------------------------------
        extract_domain_data_from_sources(event_id, supabase)

        # ---------------------------------------------------------------
        # 9. Update completeness_status on all participants
        # ---------------------------------------------------------------
        _update_completeness_statuses(event_id, supabase)

        # ---------------------------------------------------------------
        # 10. Mark files as processed
        # ---------------------------------------------------------------
        for f in mapped_files:
            supabase.table("uploaded_files").update({"import_status": "processed"}).eq("id", f["id"]).execute()

        # ---------------------------------------------------------------
        # 11. Finalise run record
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
        # Participants with an unresolved data conflict get status 'conflict'.
        conflict_ids: set[str] = set()
        try:
            conf = (
                supabase.table("exceptions")
                .select("participant_id")
                .eq("event_id", event_id)
                .eq("exception_type", "DATA_CONFLICT")
                .eq("resolved", False)
                .execute()
            )
            conflict_ids = {r["participant_id"] for r in (conf.data or []) if r.get("participant_id")}
        except Exception as exc:
            logger.warning("Failed to load conflict exceptions for completeness: %s", exc)

        participants = (
            supabase.table("participants")
            .select("id, first_name, last_name, email, has_flight")
            .eq("event_id", event_id)
            .execute()
        )
        # Bucket participants by target status, then issue one UPDATE per status
        # (chunked) instead of one UPDATE per participant — avoids N+1 on big events.
        buckets: dict[str, list[str]] = {"conflict": [], "complete": [], "incomplete": []}
        for p in participants.data or []:
            if p["id"] in conflict_ids:
                status_val = "conflict"
            elif p.get("first_name") and p.get("last_name") and p.get("email") and p.get("has_flight"):
                status_val = "complete"
            else:
                status_val = "incomplete"
            buckets[status_val].append(p["id"])

        for status_val, ids in buckets.items():
            for i in range(0, len(ids), 100):
                chunk = ids[i:i + 100]
                if chunk:
                    supabase.table("participants").update(
                        {"completeness_status": status_val}
                    ).in_("id", chunk).execute()
    except Exception as exc:
        logger.warning("Failed to update completeness_status: %s", exc)


def combine_to_iso_timestamp(date_val: Any, time_val: Any, default_date: str = "2025-11-10") -> str:
    import re
    # Clean inputs
    d_str = str(date_val or "").strip()
    t_str = str(time_val or "").strip()
    
    # Check if either is already a full ISO datetime (contains YYYY-MM-DD and THH:MM)
    iso_pattern = re.compile(r"\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}")
    if iso_pattern.search(d_str):
        val = d_str.replace(" ", "T")
        if not val.endswith("Z") and "+" not in val:
            val += "Z"
        return val
    if iso_pattern.search(t_str):
        val = t_str.replace(" ", "T")
        if not val.endswith("Z") and "+" not in val:
            val += "Z"
        return val

    # Extract date (YYYY-MM-DD)
    date_pattern = re.compile(r"(\d{4}[-/]\d{2}[-/]\d{2})|(\d{2}[-/]\d{2}[-/]\d{4})")
    match_d = date_pattern.search(d_str)
    
    target_date = default_date
    if match_d:
        raw_date = match_d.group(0).replace("/", "-")
        parts = raw_date.split("-")
        if len(parts[0]) == 2: # DD-MM-YYYY
            target_date = f"{parts[2]}-{parts[1]}-{parts[0]}"
        else: # YYYY-MM-DD
            target_date = raw_date
            
    # Extract time (HH:MM or HH:MM:SS)
    time_pattern = re.compile(r"(\d{2}:\d{2}(:\d{2})?)")
    match_t = time_pattern.search(t_str) or time_pattern.search(d_str)
    
    target_time = "00:00:00"
    if match_t:
        target_time = match_t.group(1)
        if len(target_time.split(":")) == 2:
            target_time += ":00"
            
    return f"{target_date}T{target_time}Z"


def match_non_registration_files_to_participants(event_id: str, supabase: Client) -> None:
    """
    Match source_records from non-registration files (hotel, transfer, activity)
    to the correct participant based on registration code, email, or name.
    """
    logger.info("Matching non-registration files to participants for event_id=%s", event_id)
    try:
        parts_resp = supabase.table("participants").select("id, first_name, last_name, email, registration_source_id").eq("event_id", event_id).execute()
        participants = parts_resp.data or []
    except Exception as exc:
        logger.error("Failed to load participants for non-registration mapping: %s", exc)
        return

    if not participants:
        return

    reg_sr_ids = [p["registration_source_id"] for p in participants if p.get("registration_source_id")]
    reg_sr_map = {}
    if reg_sr_ids:
        for k in range(0, len(reg_sr_ids), 100):
            chunk = reg_sr_ids[k:k+100]
            try:
                sr_resp = supabase.table("source_records").select("id, normalized_data").in_("id", chunk).execute()
                for sr in sr_resp.data or []:
                    reg_sr_map[sr["id"]] = sr["normalized_data"] or {}
            except Exception as exc:
                logger.error("Failed to load registration source records chunk: %s", exc)

    part_lookup = []
    for p in participants:
        reg_data = reg_sr_map.get(p.get("registration_source_id"), {})
        reg_code = (reg_data.get("id") or reg_data.get("participant_id") or "").strip().lower()
        part_lookup.append({
            "id": p["id"],
            "first_name": (p["first_name"] or "").strip().lower(),
            "last_name": (p["last_name"] or "").strip().lower(),
            "email": (p["email"] or "").strip().lower(),
            "reg_code": reg_code
        })

    try:
        files_resp = supabase.table("uploaded_files").select("id, source_type").eq("event_id", event_id).execute()
        target_files = [f for f in files_resp.data or [] if f["source_type"] in ("fcm", "hotel", "transfer", "activity")]
    except Exception as exc:
        logger.error("Failed to load uploaded files for non-registration matching: %s", exc)
        return

    if not target_files:
        return

    file_ids = [f["id"] for f in target_files]
    try:
        records = fetch_all_source_records(supabase, file_ids)
    except Exception as exc:
        logger.error("Failed to load source records for non-registration matching: %s", exc)
        return

    updates = []
    # Records that match nobody are attached to a NEW participant/client so their
    # info is never orphaned (feedback: every info must belong to a person).
    new_parts: list[dict] = []
    new_by_key: dict[str, str] = {}
    for rec in records:
        normalized = rec.get("normalized_data") or {}
        raw = rec.get("raw_data") or {}

        rec_first = (normalized.get("first_name") or "").strip().lower()
        rec_last = (normalized.get("last_name") or "").strip().lower()
        # Flight/hotel files usually carry the identity as a single "Traveller"
        # field (e.g. "LAI/Chun Chi" = LAST/First, or "First Last"). Derive a
        # name from it when first/last aren't provided separately.
        rec_traveler = (normalized.get("traveler_name") or "").strip().lower()
        if not rec_first and not rec_last and rec_traveler:
            if "/" in rec_traveler:
                a, b = rec_traveler.split("/", 1)
                rec_last, rec_first = a.strip(), b.strip()
            else:
                toks = rec_traveler.split()
                if len(toks) >= 2:
                    rec_first, rec_last = toks[0], " ".join(toks[1:])
                else:
                    rec_last = rec_traveler
        elif not rec_first and " " in rec_last:
            parts = rec_last.split(" ", 1)
            rec_first = parts[0]
            rec_last = parts[1]

        # Order-insensitive matching downstream (token_sort_ratio) tolerates a
        # wrong first/last guess.
        rec_full_name = f"{rec_first} {rec_last}".strip()
        rec_email = (normalized.get("email") or "").strip().lower()
        rec_code = (normalized.get("id") or normalized.get("participant_id") or raw.get("ID Participant") or "").strip().lower()

        matched_id = None

        if rec_code:
            for p in part_lookup:
                if p["reg_code"] == rec_code:
                    matched_id = p["id"]
                    break

        if not matched_id and rec_email:
            for p in part_lookup:
                if p["email"] == rec_email:
                    matched_id = p["id"]
                    break

        if not matched_id and rec_full_name:
            for p in part_lookup:
                p_full = f"{p['first_name']} {p['last_name']}".strip()
                if p_full == rec_full_name:
                    matched_id = p["id"]
                    break

            if not matched_id:
                best_score = 0
                best_p_id = None
                for p in part_lookup:
                    p_full = f"{p['first_name']} {p['last_name']}".strip()
                    if not p_full:
                        continue
                    score = fuzz.token_sort_ratio(rec_full_name, p_full)
                    if score > best_score:
                        best_score = score
                        best_p_id = p["id"]
                if best_score >= 80:
                    matched_id = best_p_id

        # No existing participant matched → create a client so the info is linked.
        if not matched_id and (rec_full_name.strip() or rec_email):
            nk = _name_key(rec_first, rec_last)
            key = rec_email or nk
            matched_id = new_by_key.get(rec_email) or new_by_key.get(nk)
            if not matched_id and key:
                matched_id = str(uuid.uuid4())
                new_parts.append({
                    "id": matched_id,
                    "event_id": event_id,
                    "first_name": (rec_first or "").title(),
                    "last_name": (rec_last or "").title(),
                    "email": rec_email or None,
                    "completeness_status": "incomplete",
                })
                if rec_email:
                    new_by_key[rec_email] = matched_id
                if nk:
                    new_by_key[nk] = matched_id

        if matched_id:
            updates.append({
                "id": rec["id"],
                "file_id": rec["file_id"],
                "event_id": rec["event_id"],
                "row_index": rec["row_index"],
                "raw_data": rec["raw_data"],
                "normalized_data": rec["normalized_data"],
                "participant_id": matched_id
            })

    # Insert the auto-created clients first (source_records reference them).
    if new_parts:
        logger.info("Creating %d client participant(s) from non-registration files", len(new_parts))
        try:
            for i in range(0, len(new_parts), 100):
                supabase.table("participants").insert(new_parts[i:i+100]).execute()
        except Exception as exc:
            logger.error("Failed to insert auto-created participants: %s", exc)

    if updates:
        logger.info("Matching non-registration records: updating %d records with participant_id...", len(updates))
        try:
            for i in range(0, len(updates), 100):
                supabase.table("source_records").upsert(updates[i:i+100]).execute()
        except Exception as exc:
            logger.error("Failed to bulk update participant_id on source_records: %s", exc)


def extract_domain_data_from_sources(event_id: str, supabase: Client) -> None:
    """
    Extract flights, hotels, transfers, and activities from mapped source_records
    and populate the respective domain tables.
    """
    from datetime import date, timedelta
    logger.info("Extracting domain data from sources for event_id=%s", event_id)

    # Load default event date as fallback
    default_date = "2025-11-10"
    try:
        ev_resp = supabase.table("events").select("start_date").eq("id", event_id).single().execute()
        if ev_resp.data and ev_resp.data.get("start_date"):
            default_date = str(ev_resp.data["start_date"])
    except Exception:
        pass

    # Fetch ALL participant-linked source records once (paginated — PostgREST caps
    # at 1000). We extract from every record regardless of the file's source_type
    # so a single combined "masterfile" (flights + hotel + activities in one sheet)
    # is fully exploited, not just type-specific files. The per-domain field guards
    # below simply skip records that don't carry the relevant columns.
    all_records: list[dict] = []
    try:
        _offset = 0
        while True:
            _res = (
                supabase.table("source_records")
                .select("participant_id, normalized_data, raw_data")
                .eq("event_id", event_id)
                .not_.is_("participant_id", "null")
                .range(_offset, _offset + 999)
                .execute()
            )
            _data = _res.data or []
            all_records.extend(_data)
            if len(_data) < 1000:
                break
            _offset += 1000
    except Exception as exc:
        logger.error("Failed to load source records for domain extraction: %s", exc)

    # 1. Flights Extraction (any record exposing flight fields)
    try:
        if all_records:
            # Load existing flights to optimize queries (bulk upsert)
            existing_flights = supabase.table("flights").select("id, participant_id, flight_number").eq("event_id", event_id).execute()
            existing_flights_map = {
                (f["participant_id"], f["flight_number"]): f["id"] for f in (existing_flights.data or [])
            }
            
            flight_payloads = {}
            participants_has_flight = set()

            for record in all_records:
                try:
                    part_id = record["participant_id"]
                    data = record["normalized_data"] or record["raw_data"] or {}
                    
                    flight_num = data.get("flight_number") or data.get("passenger_flight")
                    dep_apt = data.get("departure_airport") or data.get("departure")
                    arr_apt = data.get("arrival_airport") or data.get("arrival")
                    
                    if flight_num and dep_apt and arr_apt:
                        flight_num_clean = str(flight_num).strip().upper()
                        dep_ts = combine_to_iso_timestamp(
                            data.get("departure_date") or data.get("departure_time"),
                            data.get("departure_time"),
                            default_date
                        )
                        arr_ts = combine_to_iso_timestamp(
                            data.get("return_date") or data.get("arrival_date") or data.get("arrival_time"),
                            data.get("arrival_time"),
                            default_date
                        )
                        
                        pnr = data.get("pnr_code") or data.get("pnr")
                        airline = data.get("airline")
                        baggage = data.get("baggage_info") or data.get("baggage")
                        
                        payload = {
                            "id": str(uuid.uuid4()),
                            "event_id": event_id,
                            "participant_id": part_id,
                            "flight_number": flight_num_clean,
                            "departure_airport": str(dep_apt).strip().upper(),
                            "arrival_airport": str(arr_apt).strip().upper(),
                            "departure_time": dep_ts,
                            "arrival_time": arr_ts,
                            "pnr_code": pnr,
                            "airline": airline,
                            "baggage_info": baggage,
                            "status": "confirmed",
                        }
                        
                        # Add primary key ID if it exists to trigger update instead of duplicate insert
                        existing_id = existing_flights_map.get((part_id, flight_num_clean))
                        if existing_id:
                            payload["id"] = existing_id
                            
                        flight_payloads[(part_id, flight_num_clean)] = payload
                        participants_has_flight.add(part_id)
                except Exception as record_exc:
                    logger.warning("Failed to extract flight record: %s", record_exc)
            
            # Bulk upsert flights
            payload_list = list(flight_payloads.values())
            if payload_list:
                for i in range(0, len(payload_list), 100):
                    supabase.table("flights").upsert(payload_list[i:i+100]).execute()
            
            # Bulk update participants
            if participants_has_flight:
                part_ids = list(participants_has_flight)
                for i in range(0, len(part_ids), 50):
                    supabase.table("participants").update({"has_flight": True}).in_("id", part_ids[i:i+50]).execute()

    except Exception as exc:
        logger.error("Failed to extract flights during consolidation: %s", exc)

    # 2. Hotels Extraction (any record exposing hotel fields)
    try:
        if all_records:
            # Load existing hotels
            existing_hotels = supabase.table("hotels").select("id, name").eq("event_id", event_id).execute()
            hotel_map = {h["name"]: h["id"] for h in (existing_hotels.data or [])}
            
            # Load existing nights for all event hotels to avoid duplicate inserts
            existing_nights_map = {}
            if hotel_map:
                existing_nights = fetch_all_hotel_nights(supabase, list(hotel_map.values()))
                existing_nights_map = {
                    (n["participant_id"], n["night_date"]): n["id"] for n in existing_nights
                }
            
            nights_payloads = {}
            participants_has_hotel = set()

            for record in all_records:
                try:
                    part_id = record["participant_id"]
                    data = record["normalized_data"] or record["raw_data"] or {}
                    
                    hotel_name = data.get("hotel_name")
                    if not hotel_name:
                        continue
                    
                    # Check / Create Hotel Property
                    if hotel_name not in hotel_map:
                        new_hotel = supabase.table("hotels").insert({
                            "event_id": event_id,
                            "name": hotel_name
                        }).execute()
                        hotel_id = new_hotel.data[0]["id"]
                        hotel_map[hotel_name] = hotel_id
                    else:
                        hotel_id = hotel_map[hotel_name]
                    
                    check_in_str = data.get("check_in_date")
                    check_out_str = data.get("check_out_date")
                    room_type = data.get("room_type") or "single"
                    
                    if check_in_str and check_out_str:
                        try:
                            ci_clean = str(check_in_str).split("T")[0].split(" ")[0].strip()
                            co_clean = str(check_out_str).split("T")[0].split(" ")[0].strip()
                            check_in = date.fromisoformat(ci_clean)
                            check_out = date.fromisoformat(co_clean)
                            
                            current_date = check_in
                            while current_date < check_out:
                                night_str = current_date.isoformat()
                                payload = {
                                    "id": str(uuid.uuid4()),
                                    "hotel_id": hotel_id,
                                    "participant_id": part_id,
                                    "night_date": night_str,
                                    "room_type": room_type,
                                    "status": "confirmed"
                                }
                                
                                # Add primary key ID if it exists
                                existing_id = existing_nights_map.get((part_id, night_str))
                                if existing_id:
                                    payload["id"] = existing_id
                                    
                                nights_payloads[(part_id, night_str)] = payload
                                current_date += timedelta(days=1)
                            
                            participants_has_hotel.add(part_id)
                        except Exception as e:
                            logger.error("Failed to parse check_in/check_out date for hotel: %s", e)
                except Exception as record_exc:
                    logger.warning("Failed to extract hotel record: %s", record_exc)
            
            # Bulk upsert hotel nights
            payload_list = list(nights_payloads.values())
            if payload_list:
                for i in range(0, len(payload_list), 100):
                    supabase.table("hotel_nights").upsert(payload_list[i:i+100]).execute()
                    
            # Bulk update participants
            if participants_has_hotel:
                part_ids = list(participants_has_hotel)
                for i in range(0, len(part_ids), 50):
                    supabase.table("participants").update({"has_hotel": True}).in_("id", part_ids[i:i+50]).execute()

    except Exception as exc:
        logger.error("Failed to extract hotels during consolidation: %s", exc)

    # 3. Activities Extraction (any record exposing an activity name)
    try:
        if all_records:
            # Load existing activities
            existing_acts = supabase.table("activities").select("id, name").eq("event_id", event_id).execute()
            act_map = {a["name"]: a["id"] for a in (existing_acts.data or [])}
            
            # Load existing participant activity registrations
            existing_regs_map = {}
            if act_map:
                existing_regs = supabase.table("participant_activities").select("id, participant_id, activity_id").in_("activity_id", list(act_map.values())).execute()
                existing_regs_map = {
                    (r["participant_id"], r["activity_id"]): r["id"] for r in (existing_regs.data or [])
                }
                
            reg_payloads = {}
            participants_has_activity = set()

            for record in all_records:
                try:
                    part_id = record["participant_id"]
                    data = record["normalized_data"] or record["raw_data"] or {}
                    
                    act_name = data.get("activity_name")
                    if not act_name:
                        continue
                    
                    # Check / Create Activity
                    if act_name not in act_map:
                        new_act = supabase.table("activities").insert({
                            "event_id": event_id,
                            "name": act_name
                        }).execute()
                        act_id = new_act.data[0]["id"]
                        act_map[act_name] = act_id
                    else:
                        act_id = act_map[act_name]
                    
                    payload = {
                        "id": str(uuid.uuid4()),
                        "participant_id": part_id,
                        "activity_id": act_id,
                        "status": "registered"
                    }
                    
                    # Add primary key ID if it exists
                    existing_id = existing_regs_map.get((part_id, act_id))
                    if existing_id:
                        payload["id"] = existing_id
                        
                    reg_payloads[(part_id, act_id)] = payload
                    participants_has_activity.add(part_id)
                except Exception as record_exc:
                    logger.warning("Failed to extract activity record: %s", record_exc)
            
            # Bulk upsert registrations
            payload_list = list(reg_payloads.values())
            if payload_list:
                for i in range(0, len(payload_list), 100):
                    supabase.table("participant_activities").upsert(payload_list[i:i+100]).execute()
                    
            # Bulk update participants
            if participants_has_activity:
                part_ids = list(participants_has_activity)
                for i in range(0, len(part_ids), 50):
                    supabase.table("participants").update({"has_activities": True}).in_("id", part_ids[i:i+50]).execute()

    except Exception as exc:
        logger.error("Failed to extract activities during consolidation: %s", exc)

    # 4. Transfers Extraction (any record exposing pickup/dropoff)
    try:
        if all_records:
            # Load existing transfers
            existing_trans = supabase.table("transfers").select("id, participant_id, pickup_time").eq("event_id", event_id).execute()
            existing_trans_map = {
                (t["participant_id"], t["pickup_time"]): t["id"] for t in (existing_trans.data or [])
            }
            
            trans_payloads = {}
            participants_has_transfer = set()

            for record in all_records:
                try:
                    part_id = record["participant_id"]
                    data = record["normalized_data"] or record["raw_data"] or {}
                    
                    pickup_loc = data.get("pickup_location") or data.get("pickup")
                    dropoff_loc = data.get("dropoff_location") or data.get("dropoff")
                    
                    if pickup_loc and dropoff_loc:
                        pickup_time_str = combine_to_iso_timestamp(
                            data.get("pickup_time") or data.get("departure_time") or data.get("pickup_date"),
                            data.get("pickup_time") or data.get("departure_time"),
                            default_date
                        )
                        transfer_type = data.get("transfer_type") or "arrival"
                        vehicle_type = data.get("vehicle_type") or "shuttle"
                        
                        payload = {
                            "id": str(uuid.uuid4()),
                            "event_id": event_id,
                            "participant_id": part_id,
                            "transfer_type": transfer_type,
                            "pickup_location": pickup_loc,
                            "dropoff_location": dropoff_loc,
                            "pickup_time": pickup_time_str,
                            "vehicle_type": vehicle_type,
                            "status": "scheduled"
                        }
                        
                        # Add primary key ID if it exists
                        existing_id = existing_trans_map.get((part_id, pickup_time_str))
                        if existing_id:
                            payload["id"] = existing_id
                            
                        trans_payloads[(part_id, pickup_time_str)] = payload
                        participants_has_transfer.add(part_id)
                except Exception as record_exc:
                    logger.warning("Failed to extract transfer record: %s", record_exc)
            
            # Bulk upsert transfers
            payload_list = list(trans_payloads.values())
            if payload_list:
                for i in range(0, len(payload_list), 100):
                    supabase.table("transfers").upsert(payload_list[i:i+100]).execute()
                    
            # Bulk update participants
            if participants_has_transfer:
                part_ids = list(participants_has_transfer)
                for i in range(0, len(part_ids), 50):
                    supabase.table("participants").update({"has_transfer": True}).in_("id", part_ids[i:i+50]).execute()

    except Exception as exc:
        logger.error("Failed to extract transfers during consolidation: %s", exc)
