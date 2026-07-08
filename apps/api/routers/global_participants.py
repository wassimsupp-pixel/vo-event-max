"""
routers/global_participants.py — Cross-event participant history endpoints.
"""

from __future__ import annotations

import logging
from typing import Any
from fastapi import APIRouter, Depends, HTTPException, Query, status
from supabase import Client

from dependencies import get_current_user, get_supabase_client
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

    # Fetch all participants with matching email in this organization
    # Join via events -> projects to ensure org isolation!
    response = (
        supabase.table("participants")
        .select("*, events!inner(name, start_date, projects!inner(org_id))")
        .ilike("email", email.strip())
        .eq("events.projects.org_id", org_id)
        .execute()
    )

    if not response.data:
        return []

    # Group by exact email
    grouped: dict[str, dict[str, Any]] = {}
    for row in response.data:
        p_email = row["email"].lower().strip()
        first_name = row["first_name"]
        last_name = row["last_name"]
        full_name = f"{first_name} {last_name}"
        
        event_info = row.get("events")
        event_name = event_info["name"] if event_info else "Unknown Event"
        event_date = event_info["start_date"] if event_info else None
        dietary = row.get("dietary_requirements")

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
