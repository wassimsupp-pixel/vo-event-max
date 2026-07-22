# -*- coding: utf-8 -*-
"""
deletion_service.py
===================
Cascade deletion of events and projects.

Most foreign keys to ``events(id)`` in the schema do **not** declare
``ON DELETE CASCADE``, so a raw ``DELETE`` on the event row would fail with a
foreign-key violation. This service deletes all dependent rows in dependency
order (children first) before removing the event itself.

Deletion order for an event
---------------------------
1. Junction/grandchild tables keyed by participant/activity/hotel ids
   (``participant_activities``, ``hotel_nights``).
2. Event-scoped tables referencing participants / runs / source_records
   (``exceptions``, ``exports``, ``email_proposals``, ``flights``,
   ``transfers``, ``change_log``).
3. ``consolidation_runs`` (referenced by exceptions/exports, now gone).
4. ``activities`` and ``hotels`` (their junction rows are gone).
5. Break the circular FK between ``participants`` and ``source_records``: null
   ``participants.registration_source_id`` / ``fcm_source_id`` so source_records
   can go first.
6. ``source_records`` (participant links nulled, exceptions gone).
7. ``participants``.
8. Storage objects, then ``uploaded_files``.
9. The ``events`` row itself.
"""

from __future__ import annotations

import logging

from supabase import Client

import config

logger = logging.getLogger(__name__)

# Keep `IN (...)` id-lists small: PostgREST rejects over-long request URLs
# (a 1000-UUID list ≈ 37 KB → 400 "Bad Request"). 100 keeps URLs well under limits.
_CHUNK = 100


def _ids(supabase: Client, table: str, filter_col: str, filter_val: str) -> list[str]:
    """Return ALL ``id`` values of rows in *table* matching filter.

    PostgREST caps a single response at ~1000 rows, so we must paginate — a
    partial id list would leave rows behind and break FK-ordered deletes.
    """
    ids: list[str] = []
    page_size = 1000
    offset = 0
    while True:
        res = (
            supabase.table(table)
            .select("id")
            .eq(filter_col, filter_val)
            .range(offset, offset + page_size - 1)
            .execute()
        )
        data = res.data or []
        ids.extend(row["id"] for row in data)
        if len(data) < page_size:
            break
        offset += page_size
    return ids


def _delete_in(supabase: Client, table: str, col: str, ids: list[str], chunk_size: int = _CHUNK) -> None:
    """Delete rows of *table* where *col* is in *ids* (chunked, no-op if empty)."""
    for i in range(0, len(ids), chunk_size):
        chunk = ids[i : i + chunk_size]
        supabase.table(table).delete().in_(col, chunk).execute()


def _remove_event_storage(supabase: Client, event_id: str) -> None:
    """Best-effort removal of Storage objects for an event's uploaded files."""
    res = (
        supabase.table("uploaded_files")
        .select("storage_path")
        .eq("event_id", event_id)
        .execute()
    )
    paths = [row["storage_path"] for row in (res.data or []) if row.get("storage_path")]
    if not paths:
        return
    try:
        supabase.storage.from_(config.SUPABASE_STORAGE_BUCKET).remove(paths)
    except Exception as exc:  # storage cleanup is best-effort; never block the DB delete
        logger.warning("Storage removal during event delete failed: %s", exc)


def delete_event(supabase: Client, event_id: str) -> None:
    """Delete an event and every row that depends on it (see module docstring)."""
    eid = str(event_id)

    # Parent ids needed for junction tables that have no event_id column.
    participant_ids = _ids(supabase, "participants", "event_id", eid)
    activity_ids = _ids(supabase, "activities", "event_id", eid)
    hotel_ids = _ids(supabase, "hotels", "event_id", eid)

    # 1. Junction / grandchild tables
    _delete_in(supabase, "participant_activities", "participant_id", participant_ids)
    _delete_in(supabase, "participant_activities", "activity_id", activity_ids)
    _delete_in(supabase, "hotel_nights", "participant_id", participant_ids)
    _delete_in(supabase, "hotel_nights", "hotel_id", hotel_ids)

    # 2. Event-scoped tables referencing participants / runs / source_records
    for table in ("exceptions", "exports", "email_proposals", "flights", "transfers", "change_log"):
        supabase.table(table).delete().eq("event_id", eid).execute()

    # 3. Consolidation runs (referenced by exceptions/exports, now removed)
    supabase.table("consolidation_runs").delete().eq("event_id", eid).execute()

    # 4. Activities & hotels (their junction rows are gone)
    supabase.table("activities").delete().eq("event_id", eid).execute()
    supabase.table("hotels").delete().eq("event_id", eid).execute()

    # 5. Break the circular FK between participants and source_records:
    #    participants reference source_records (registration_source_id /
    #    fcm_source_id) AND source_records reference participants
    #    (participant_id). Null the participant→source links (nullable columns)
    #    so source_records can be deleted before participants.
    supabase.table("participants").update(
        {"registration_source_id": None, "fcm_source_id": None}
    ).eq("event_id", eid).execute()

    # 6/7. Delete source_records and participants in small id-batches. Both tables
    #      are targets of foreign keys, so Postgres re-checks referencing columns
    #      per deleted row — a single bulk DELETE can exceed the DB statement
    #      timeout on large events. Chunking keeps each statement short.
    source_record_ids = _ids(supabase, "source_records", "event_id", eid)
    logger.info("Deleting %d source_records for event %s", len(source_record_ids), eid)
    _delete_in(supabase, "source_records", "id", source_record_ids, chunk_size=100)

    logger.info("Deleting %d participants for event %s", len(participant_ids), eid)
    _delete_in(supabase, "participants", "id", participant_ids, chunk_size=100)

    # 8. Storage objects, then uploaded_files
    _remove_event_storage(supabase, eid)
    supabase.table("uploaded_files").delete().eq("event_id", eid).execute()

    # 9. The event itself
    supabase.table("events").delete().eq("id", eid).execute()

    logger.info("Deleted event %s and all dependent data", eid)


def _null_participant_source_refs_for(supabase: Client, source_ids: list[str]) -> None:
    """Null participants.registration_source_id / fcm_source_id pointing at *source_ids*."""
    for i in range(0, len(source_ids), 100):
        chunk = source_ids[i : i + 100]
        supabase.table("participants").update({"registration_source_id": None}).in_("registration_source_id", chunk).execute()
        supabase.table("participants").update({"fcm_source_id": None}).in_("fcm_source_id", chunk).execute()


def delete_file_cascade(supabase: Client, file_id: str) -> None:
    """
    Delete an uploaded file and its source_records robustly, handling the same
    pitfalls as event deletion: PostgREST's 1000-row cap (paginate ids), the
    circular participants<->source_records FK (null the participant links first),
    exceptions referencing the records, and statement timeouts (chunk deletes).
    """
    fid = str(file_id)
    source_ids = _ids(supabase, "source_records", "file_id", fid)
    logger.info("Deleting file %s with %d source_records", fid, len(source_ids))

    # 1. Break participant -> source_records references
    _null_participant_source_refs_for(supabase, source_ids)
    # 2. Exceptions referencing these source records
    _delete_in(supabase, "exceptions", "source_record_id", source_ids, chunk_size=100)
    # 3. Source records themselves (chunked by id to stay under the statement timeout)
    _delete_in(supabase, "source_records", "id", source_ids, chunk_size=100)
    # 4. The uploaded_files row
    supabase.table("uploaded_files").delete().eq("id", fid).execute()


def delete_project(supabase: Client, project_id: str) -> None:
    """Delete a project and every event (with all their data) under it."""
    pid = str(project_id)
    event_ids = _ids(supabase, "events", "project_id", pid)
    for eid in event_ids:
        delete_event(supabase, eid)
    supabase.table("projects").delete().eq("id", pid).execute()
    logger.info("Deleted project %s and %d event(s)", pid, len(event_ids))
