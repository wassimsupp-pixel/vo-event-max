"""
routers/event_grouping.py — Suggest and merge look-alike events (org-level).

GET  /org/event-merge-suggestions   read-only clusters of similar events
POST /events/merge                  merge a confirmed cluster into one event
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from pydantic import BaseModel
from supabase import Client

from dependencies import get_current_user, get_supabase_client
from services import event_grouping_service, consolidation_service

logger = logging.getLogger(__name__)

router = APIRouter()

# Roles allowed to merge events (destructive). Mirrors the app's staff roles.
_MERGE_ROLES = {"admin", "pm", "project_manager", "manager", "owner"}


class EventGroupEvent(BaseModel):
    id: str
    name: str
    start_date: Optional[str] = None
    location_city: Optional[str] = None
    participant_count: int = 0


class EventGroupSuggestion(BaseModel):
    canonical_event_id: str
    events: list[EventGroupEvent]
    ai_confirmed: Optional[bool] = None
    min_similarity: float


class MergeEventsRequest(BaseModel):
    canonical_event_id: str
    merge_event_ids: list[str]


class MergeEventsResponse(BaseModel):
    merged: int
    reassigned_tables: int
    canonical_event_id: str
    message: str


@router.get(
    "/org/event-merge-suggestions",
    response_model=list[EventGroupSuggestion],
    summary="Clusters of look-alike events in the org (read-only)",
)
async def event_merge_suggestions(
    current_user: dict[str, Any] = Depends(get_current_user),
    supabase: Client = Depends(get_supabase_client),
) -> list[EventGroupSuggestion]:
    org_id = current_user.get("org_id")
    if not org_id:
        return []
    groups = event_grouping_service.suggest_event_groups(supabase, org_id)
    return [EventGroupSuggestion(**g) for g in groups]


def _org_event_ids(supabase: Client, org_id: str) -> set[str]:
    try:
        res = (
            supabase.table("events")
            .select("id, projects!inner(org_id)")
            .eq("projects.org_id", org_id)
            .execute()
        )
        return {e["id"] for e in (res.data or [])}
    except Exception as exc:
        logger.error("Failed to load org event ids: %s", exc)
        return set()


@router.post(
    "/events/merge",
    response_model=MergeEventsResponse,
    summary="Merge look-alike events into one canonical event",
)
async def merge_events_endpoint(
    body: MergeEventsRequest,
    background_tasks: BackgroundTasks,
    current_user: dict[str, Any] = Depends(get_current_user),
    supabase: Client = Depends(get_supabase_client),
) -> MergeEventsResponse:
    if (current_user.get("role") or "").lower() not in _MERGE_ROLES:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only a manager/admin can merge events.",
        )
    org_id = current_user.get("org_id")
    if not org_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="No organization.")

    # Every event in the operation must belong to the caller's org.
    all_ids = {body.canonical_event_id, *body.merge_event_ids}
    owned = _org_event_ids(supabase, org_id)
    if not all_ids.issubset(owned):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="One or more events are not in your organization.",
        )
    if not body.merge_event_ids or body.canonical_event_id in body.merge_event_ids and len(all_ids) < 2:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Nothing to merge.")

    result = event_grouping_service.merge_events(supabase, body.canonical_event_id, body.merge_event_ids)

    # Re-consolidate the canonical event so people that now co-exist there get
    # de-duplicated by the normal pipeline.
    background_tasks.add_task(
        consolidation_service.start_and_run_consolidation,
        event_id=body.canonical_event_id,
        user_id=current_user["id"],
        supabase=supabase,
    )

    return MergeEventsResponse(
        merged=result.get("merged", 0),
        reassigned_tables=result.get("reassigned_tables", 0),
        canonical_event_id=body.canonical_event_id,
        message=f"{result.get('merged', 0)} événement(s) fusionné(s). Reconsolidation en cours.",
    )
