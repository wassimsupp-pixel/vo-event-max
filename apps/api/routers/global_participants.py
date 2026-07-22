"""
routers/global_participants.py — Cross-event participant history endpoints.
"""

from __future__ import annotations

import logging
from typing import Any
from fastapi import APIRouter, Depends, Query
from supabase import Client

from dependencies import STAFF_ROLES, get_current_user, get_project_membership, get_supabase_client
from models.schemas import GlobalParticipantHistoryResponse, GlobalParticipantHistoryItem

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get(
    "/global-participants/history",
    response_model=list[GlobalParticipantHistoryResponse],
    summary="Get cross-event participant profile and dietary preferences history",
)
async def get_participant_history(
    email: str = Query(..., description="Email address of the participant to lookup."),
    current_user: dict[str, Any] = Depends(get_current_user),
    supabase: Client = Depends(get_supabase_client),
) -> list[GlobalParticipantHistoryResponse]:
    """
    Search for a participant across all events in the organization and return their historical profile.
    """
    org_id = current_user.get("org_id", "")
    is_staff = current_user.get("role") in STAFF_ROLES
    user_id = current_user.get("id", "")

    # Fetch all participants with matching email in this organization
    # Join via events -> projects to ensure org isolation!
    response = (
        supabase.table("participants")
        .select("*, events!inner(id, name, start_date, project_id, projects!inner(org_id))")
        .ilike("email", email.strip())
        .eq("events.projects.org_id", org_id)
        .execute()
    )

    if not response.data:
        return []

    # Being in the same org is not enough for a non-staff user: verify_event_access
    # additionally requires a project_members row (and, if it restricts event_ids,
    # that the specific event is listed) before a client/viewer can see an event's
    # data. This endpoint skipped that check entirely, letting a client shared on
    # ONE event pull dietary/history data for every OTHER event in the org that
    # happens to share a participant's email. Same rule, same fallback
    # (__no_table__ = sharing migration not applied yet -> legacy org-wide access),
    # just applied per-event across a multi-row result instead of a single event.
    membership_cache: dict[str, Any] = {}

    def _event_allowed(project_id: str, event_id: str) -> bool:
        if is_staff:
            return True
        if project_id not in membership_cache:
            membership_cache[project_id] = get_project_membership(supabase, project_id, user_id)
        membership = membership_cache[project_id]
        if membership and membership.get("__no_table__"):
            return True
        if not membership:
            return False
        restricted = membership.get("event_ids")
        return not (restricted and event_id not in restricted)

    # Group by exact email
    grouped: dict[str, dict[str, Any]] = {}
    for row in response.data:
        event_info = row.get("events") or {}
        event_id = event_info.get("id", "")
        project_id = event_info.get("project_id", "")
        if not _event_allowed(project_id, event_id):
            continue

        p_email = row["email"].lower().strip()
        first_name = row["first_name"]
        last_name = row["last_name"]
        full_name = f"{first_name} {last_name}"

        event_name = event_info.get("name") or "Unknown Event"
        event_date = event_info.get("start_date")
        # dietary_requirements is RGPD-sensitive and restricted to admin/pm
        # everywhere else in the app (participants.py's _strip_dietary).
        dietary = row.get("dietary_requirements") if is_staff else None

        history_item = GlobalParticipantHistoryItem(
            event_name=event_name,
            event_date=event_date,
            dietary_requirements=dietary,
        )

        if p_email not in grouped:
            grouped[p_email] = {
                "email": p_email,
                "full_name": full_name,
                "history": [],
            }

        grouped[p_email]["history"].append(history_item)

    return [GlobalParticipantHistoryResponse(**val) for val in grouped.values()]
