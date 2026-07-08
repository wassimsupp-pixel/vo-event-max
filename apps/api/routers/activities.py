"""
routers/activities.py — Activities and Excursions management endpoints.
"""

from __future__ import annotations

import logging
from typing import Any
from fastapi import APIRouter, Depends, HTTPException, status
from supabase import Client

from dependencies import get_current_user, get_supabase_client, verify_event_access
from models.schemas import (
    ActivityResponse,
    ActivityCreate,
    ActivityUpdate,
    ParticipantActivityResponse,
    MessageResponse,
)
from services.audit_service import log_change

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get(
    "/events/{event_id}/activities",
    response_model=list[ActivityResponse],
    summary="List all activities for an event",
)
async def list_activities(
    event_id: str,
    current_user: dict[str, Any] = Depends(get_current_user),
    supabase: Client = Depends(get_supabase_client),
) -> list[ActivityResponse]:
    """
    List activities configured for an event with registration counts.
    """
    await verify_event_access(event_id, current_user, supabase)

    activities_res = (
        supabase.table("activities")
        .select("*")
        .eq("event_id", event_id)
        .execute()
    )

    results = []
    for row in activities_res.data:
        act_id = row["id"]
        # Count registrations
        count_res = (
            supabase.table("participant_activities")
            .select("id", count="exact")
            .eq("activity_id", act_id)
            .eq("status", "registered")
            .execute()
        )
        reg_count = count_res.count or 0
        item = row.copy()
        item["registrations_count"] = reg_count
        results.append(ActivityResponse(**item))

    return results


@router.post(
    "/events/{event_id}/activities",
    response_model=ActivityResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new activity",
)
async def create_activity(
    event_id: str,
    body: ActivityCreate,
    current_user: dict[str, Any] = Depends(get_current_user),
    supabase: Client = Depends(get_supabase_client),
) -> ActivityResponse:
    """
    Create a new activity or excursion for an event.
    """
    await verify_event_access(event_id, current_user, supabase)

    payload = body.model_dump()
    payload["event_id"] = event_id

    result = supabase.table("activities").insert(payload).execute()
    return ActivityResponse(**result.data[0])


@router.patch(
    "/activities/{activity_id}",
    response_model=ActivityResponse,
    summary="Update activity details",
)
async def update_activity(
    activity_id: str,
    body: ActivityUpdate,
    current_user: dict[str, Any] = Depends(get_current_user),
    supabase: Client = Depends(get_supabase_client),
) -> ActivityResponse:
    """
    Update details of an activity. Logs to audit trail.
    """
    existing = supabase.table("activities").select("*").eq("id", activity_id).single().execute()
    if not existing.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Activity not found.",
        )

    event_id = existing.data["event_id"]
    await verify_event_access(event_id, current_user, supabase)

    payload = body.model_dump(exclude_none=True)
    user_id = current_user["id"]

    for field, new_val in payload.items():
        old_val = str(existing.data.get(field) or "")
        new_val_str = str(new_val)
        if old_val != new_val_str:
            log_change(
                supabase=supabase,
                event_id=event_id,
                user_id=user_id,
                entity_type="activity",
                entity_id=activity_id,
                field_name=field,
                old_value=old_val,
                new_value=new_val_str,
                reason="manual_edit",
            )

    result = supabase.table("activities").update(payload).eq("id", activity_id).execute()
    return ActivityResponse(**result.data[0])


@router.delete(
    "/activities/{activity_id}",
    response_model=MessageResponse,
    summary="Delete an activity",
)
async def delete_activity(
    activity_id: str,
    current_user: dict[str, Any] = Depends(get_current_user),
    supabase: Client = Depends(get_supabase_client),
) -> MessageResponse:
    """
    Remove activity record.
    """
    existing = supabase.table("activities").select("*").eq("id", activity_id).single().execute()
    if not existing.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Activity not found.",
        )

    event_id = existing.data["event_id"]
    await verify_event_access(event_id, current_user, supabase)

    supabase.table("activities").delete().eq("id", activity_id).execute()
    return MessageResponse(message="Successfully deleted activity.")


@router.get(
    "/activities/{activity_id}/participants",
    response_model=list[ParticipantActivityResponse],
    summary="List all participants registered for an activity",
)
async def list_activity_participants(
    activity_id: str,
    current_user: dict[str, Any] = Depends(get_current_user),
    supabase: Client = Depends(get_supabase_client),
) -> list[ParticipantActivityResponse]:
    """
    Get the registered roster for an activity, including dietary_requirements.
    Restricts dietary_requirements column values to admin/pm roles in the response dictionary.
    """
    # Verify activity access
    existing = supabase.table("activities").select("*").eq("id", activity_id).single().execute()
    if not existing.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Activity not found.",
        )

    event_id = existing.data["event_id"]
    await verify_event_access(event_id, current_user, supabase)

    response = (
        supabase.table("participant_activities")
        .select("*, participants(first_name, last_name, dietary_requirements)")
        .eq("activity_id", activity_id)
        .execute()
    )

    results = []
    user_role = current_user.get("role", "")
    for row in response.data:
        part = row.get("participants")
        part_name = f"{part['first_name']} {part['last_name']}" if part else None
        
        # Hide dietary requirements for viewers/clients
        dietary = None
        if part and user_role in ("admin", "pm"):
            dietary = part.get("dietary_requirements")

        item = row.copy()
        item.pop("participants", None)
        item["participant_name"] = part_name
        item["dietary_requirements"] = dietary
        results.append(ParticipantActivityResponse(**item))

    return results


@router.post(
    "/activities/{activity_id}/register",
    response_model=ParticipantActivityResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a participant to an activity",
)
async def register_participant(
    activity_id: str,
    participant_id: str,
    current_user: dict[str, Any] = Depends(get_current_user),
    supabase: Client = Depends(get_supabase_client),
) -> ParticipantActivityResponse:
    """
    Register a participant to an activity slot.
    """
    activity = supabase.table("activities").select("*").eq("id", activity_id).single().execute()
    if not activity.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Activity not found.",
        )

    event_id = activity.data["event_id"]
    await verify_event_access(event_id, current_user, supabase)

    # Check participant exists
    part = (
        supabase.table("participants")
        .select("id")
        .eq("id", participant_id)
        .eq("event_id", event_id)
        .single()
        .execute()
    )
    if not part.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Participant not found in this event.",
        )

    # Unique check
    exist = (
        supabase.table("participant_activities")
        .select("id")
        .eq("participant_id", participant_id)
        .eq("activity_id", activity_id)
        .execute()
    )

    if exist.data:
        result = (
            supabase.table("participant_activities")
            .update({"status": "registered"})
            .eq("id", exist.data[0]["id"])
            .execute()
        )
    else:
        result = (
            supabase.table("participant_activities")
            .insert({"participant_id": participant_id, "activity_id": activity_id, "status": "registered"})
            .execute()
        )

    # Update participant has_activities flag
    supabase.table("participants").update({"has_activities": True}).eq("id", participant_id).execute()

    return ParticipantActivityResponse(**result.data[0])


@router.delete(
    "/activities/{activity_id}/unregister/{participant_id}",
    response_model=MessageResponse,
    summary="Unregister a participant from an activity",
)
async def unregister_participant(
    activity_id: str,
    participant_id: str,
    current_user: dict[str, Any] = Depends(get_current_user),
    supabase: Client = Depends(get_supabase_client),
) -> MessageResponse:
    """
    Remove participant's registration from an activity slot.
    """
    activity = supabase.table("activities").select("*").eq("id", activity_id).single().execute()
    if not activity.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Activity not found.",
        )

    event_id = activity.data["event_id"]
    await verify_event_access(event_id, current_user, supabase)

    supabase.table("participant_activities").delete().eq("participant_id", participant_id).eq("activity_id", activity_id).execute()
    return MessageResponse(message="Successfully unregistered participant from activity.")
