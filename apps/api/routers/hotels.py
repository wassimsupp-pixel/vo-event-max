"""
routers/hotels.py — Hotels and Rooming List management endpoints.
"""

from __future__ import annotations

import logging
from typing import Any
from fastapi import APIRouter, Depends, HTTPException, status
from supabase import Client

from dependencies import get_current_user, get_supabase_client, verify_event_access
from models.schemas import (
    HotelResponse,
    HotelCreate,
    HotelUpdate,
    HotelNightResponse,
    HotelNightCreate,
    HotelNightUpdate,
    MessageResponse,
)
from services.audit_service import log_change

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get(
    "/events/{event_id}/hotels",
    response_model=list[HotelResponse],
    summary="List all hotels for an event",
)
async def list_hotels(
    event_id: str,
    current_user: dict[str, Any] = Depends(get_current_user),
    supabase: Client = Depends(get_supabase_client),
) -> list[HotelResponse]:
    """
    List hotels configured for an event.
    """
    await verify_event_access(event_id, current_user, supabase)

    response = (
        supabase.table("hotels")
        .select("*")
        .eq("event_id", event_id)
        .execute()
    )

    return [HotelResponse(**row) for row in response.data]


@router.post(
    "/events/{event_id}/hotels",
    response_model=HotelResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Add a new hotel property to an event",
)
async def create_hotel(
    event_id: str,
    body: HotelCreate,
    current_user: dict[str, Any] = Depends(get_current_user),
    supabase: Client = Depends(get_supabase_client),
) -> HotelResponse:
    """
    Add a hotel property to an event.
    """
    await verify_event_access(event_id, current_user, supabase)

    payload = body.model_dump()
    payload["event_id"] = event_id

    result = supabase.table("hotels").insert(payload).execute()
    return HotelResponse(**result.data[0])


@router.patch(
    "/hotels/{hotel_id}",
    response_model=HotelResponse,
    summary="Update hotel property details",
)
async def update_hotel(
    hotel_id: str,
    body: HotelUpdate,
    current_user: dict[str, Any] = Depends(get_current_user),
    supabase: Client = Depends(get_supabase_client),
) -> HotelResponse:
    """
    Update hotel metadata. Logs to audit trail.
    """
    existing = supabase.table("hotels").select("*").eq("id", hotel_id).single().execute()
    if not existing.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Hotel not found.",
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
                entity_type="hotel",
                entity_id=hotel_id,
                field_name=field,
                old_value=old_val,
                new_value=new_val_str,
                reason="manual_edit",
            )

    result = supabase.table("hotels").update(payload).eq("id", hotel_id).execute()
    return HotelResponse(**result.data[0])


@router.get(
    "/events/{event_id}/hotels/rooming",
    response_model=list[HotelNightResponse],
    summary="List rooming list nights for an event",
)
async def list_rooming_list(
    event_id: str,
    current_user: dict[str, Any] = Depends(get_current_user),
    supabase: Client = Depends(get_supabase_client),
) -> list[HotelNightResponse]:
    """
    Get all night room allocations for an event.
    """
    await verify_event_access(event_id, current_user, supabase)

    # Fetch hotels for this event
    hotels_res = supabase.table("hotels").select("id").eq("event_id", event_id).execute()
    hotel_ids = [h["id"] for h in hotels_res.data]

    if not hotel_ids:
        return []

    # Select room allocations
    response = (
        supabase.table("hotel_nights")
        .select("*, hotels(name), participants(first_name, last_name)")
        .in_("hotel_id", hotel_ids)
        .execute()
    )

    results = []
    for row in response.data:
        part = row.get("participants")
        part_name = f"{part['first_name']} {part['last_name']}" if part else None
        h_info = row.get("hotels")
        hotel_name = h_info["name"] if h_info else None

        item = row.copy()
        item.pop("participants", None)
        item.pop("hotels", None)
        item["participant_name"] = part_name
        item["hotel_name"] = hotel_name
        results.append(HotelNightResponse(**item))

    return results


@router.post(
    "/events/{event_id}/hotels/rooming",
    response_model=HotelNightResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Assign a hotel night to a participant",
)
async def assign_rooming_night(
    event_id: str,
    body: HotelNightCreate,
    current_user: dict[str, Any] = Depends(get_current_user),
    supabase: Client = Depends(get_supabase_client),
) -> HotelNightResponse:
    """
    Assign a rooming night to a participant.
    """
    await verify_event_access(event_id, current_user, supabase)

    # Verify participant is in event
    part = (
        supabase.table("participants")
        .select("id")
        .eq("id", str(body.participant_id))
        .eq("event_id", event_id)
        .single()
        .execute()
    )
    if not part.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Participant not found in this event.",
        )

    # Verify hotel belongs to event
    hotel = (
        supabase.table("hotels")
        .select("id")
        .eq("id", str(body.hotel_id))
        .eq("event_id", event_id)
        .single()
        .execute()
    )
    if not hotel.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Hotel not found in this event.",
        )

    payload = body.model_dump()

    # Unique check: participant cannot have duplicate nights
    exist = (
        supabase.table("hotel_nights")
        .select("id")
        .eq("participant_id", str(body.participant_id))
        .eq("night_date", str(body.night_date))
        .execute()
    )
    if exist.data:
        # Update existing
        result = (
            supabase.table("hotel_nights")
            .update({"hotel_id": str(body.hotel_id), "room_type": body.room_type, "status": body.status})
            .eq("id", exist.data[0]["id"])
            .execute()
        )
    else:
        result = supabase.table("hotel_nights").insert(payload).execute()

    # Update participant has_hotel status
    supabase.table("participants").update({"has_hotel": True}).eq("id", str(body.participant_id)).execute()

    return HotelNightResponse(**result.data[0])


@router.patch(
    "/hotels/rooming/{rooming_id}",
    response_model=HotelNightResponse,
    summary="Update rooming night details",
)
async def update_rooming_night(
    rooming_id: str,
    body: HotelNightUpdate,
    current_user: dict[str, Any] = Depends(get_current_user),
    supabase: Client = Depends(get_supabase_client),
) -> HotelNightResponse:
    """
    Update room status or type for a night.
    """
    existing = (
        supabase.table("hotel_nights")
        .select("*, hotels(event_id)")
        .eq("id", rooming_id)
        .single()
        .execute()
    )
    if not existing.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Rooming night not found.",
        )

    event_id = existing.data["hotels"]["event_id"]
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
                entity_type="hotel_night",
                entity_id=rooming_id,
                field_name=field,
                old_value=old_val,
                new_value=new_val_str,
                reason="manual_edit",
            )

    result = supabase.table("hotel_nights").update(payload).eq("id", rooming_id).execute()
    return HotelNightResponse(**result.data[0])


@router.delete(
    "/hotels/rooming/{rooming_id}",
    response_model=MessageResponse,
    summary="Delete rooming assignment for a night",
)
async def delete_rooming_night(
    rooming_id: str,
    current_user: dict[str, Any] = Depends(get_current_user),
    supabase: Client = Depends(get_supabase_client),
) -> MessageResponse:
    """
    Delete a single night allocation.
    """
    existing = (
        supabase.table("hotel_nights")
        .select("*, hotels(event_id)")
        .eq("id", rooming_id)
        .single()
        .execute()
    )
    if not existing.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Rooming night not found.",
        )

    event_id = existing.data["hotels"]["event_id"]
    await verify_event_access(event_id, current_user, supabase)

    supabase.table("hotel_nights").delete().eq("id", rooming_id).execute()
    return MessageResponse(message="Successfully deleted rooming night allocation.")
