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
from typing import Any

from supabase import Client

import config

logger = logging.getLogger(__name__)

_CHUNK = 1000


def _ids(supabase: Client, table: str, filter_col: str, filter_val: str) -> list[str]:
    """Return the ``id`` values of rows in *table* matching filter."""
    res = supabase.table(table).select("id").eq(filter_col, filter_val).execute()
    return [row["id"] for row in (res.data or [])]


def _delete_in(supabase: Client, table: str, col: str, ids: list[str]) -> None:
    """Delete rows of *table* where *col* is in *ids* (chunked, no-op if empty)."""
    for i in range(0, len(ids), _CHUNK):
        chunk = ids[i : i + _CHUNK]
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

    # 6. Source records (now unreferenced: participant links nulled, exceptions gone)
    supabase.table("source_records").delete().eq("event_id", eid).execute()

    # 7. Participants (the source_records that referenced them are gone)
    supabase.table("participants").delete().eq("event_id", eid).execute()

    # 8. Storage objects, then uploaded_files
    _remove_event_storage(supabase, eid)
    supabase.table("uploaded_files").delete().eq("event_id", eid).execute()

    # 9. The event itself
    supabase.table("events").delete().eq("id", eid).execute()

    logger.info("Deleted event %s and all dependent data", eid)


def delete_project(supabase: Client, project_id: str) -> None:
    """Delete a project and every event (with all their data) under it."""
    pid = str(project_id)
    event_ids = _ids(supabase, "events", "project_id", pid)
    for eid in event_ids:
        delete_event(supabase, eid)
    supabase.table("projects").delete().eq("id", pid).execute()
    logger.info("Deleted project %s and %d event(s)", pid, len(event_ids))
