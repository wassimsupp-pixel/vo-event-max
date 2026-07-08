"""
routers/transfers.py — Transfers and Ground Transportation endpoints.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any
from fastapi import APIRouter, Depends, HTTPException, Query, status
from supabase import Client

from dependencies import get_current_user, get_supabase_client, verify_event_access
from models.schemas import (
    TransferResponse,
    TransferCreate,
    TransferUpdate,
    MessageResponse,
)
from services.audit_service import log_change

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get(
    "/events/{event_id}/transfers",
    response_model=list[TransferResponse],
    summary="List all transfers for an event",
)
async def list_transfers(
    event_id: str,
    current_user: dict[str, Any] = Depends(get_current_user),
    supabase: Client = Depends(get_supabase_client),
) -> list[TransferResponse]:
    """
    List transfers booked for an event.
    """
    await verify_event_access(event_id, current_user, supabase)

    response = (
        supabase.table("transfers")
        .select("*, participants(first_name, last_name), flights(flight_number)")
        .eq("event_id", event_id)
        .execute()
    )

    results = []
    for row in response.data:
        part = row.get("participants")
        part_name = f"{part['first_name']} {part['last_name']}" if part else None
        fl = row.get("flights")
        flight_num = fl["flight_number"] if fl else None

        item = row.copy()
        item.pop("participants", None)
        item.pop("flights", None)
        item["participant_name"] = part_name
        item["flight_number"] = flight_num
        results.append(TransferResponse(**item))

    return results


@router.post(
    "/events/{event_id}/transfers",
    response_model=TransferResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a ground transfer booking",
)
async def create_transfer(
    event_id: str,
    body: TransferCreate,
    current_user: dict[str, Any] = Depends(get_current_user),
    supabase: Client = Depends(get_supabase_client),
) -> TransferResponse:
    """
    Create a ground transfer.
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

    payload = body.model_dump()
    payload["event_id"] = event_id

    result = supabase.table("transfers").insert(payload).execute()

    # Update participant has_transfer flag
    supabase.table("participants").update({"has_transfer": True}).eq("id", str(body.participant_id)).execute()

    return TransferResponse(**result.data[0])


@router.patch(
    "/transfers/{transfer_id}",
    response_model=TransferResponse,
    summary="Update transfer details",
)
async def update_transfer(
    transfer_id: str,
    body: TransferUpdate,
    current_user: dict[str, Any] = Depends(get_current_user),
    supabase: Client = Depends(get_supabase_client),
) -> TransferResponse:
    """
    Update transfer booking. Logs to audit trail.
    """
    existing = supabase.table("transfers").select("*").eq("id", transfer_id).single().execute()
    if not existing.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Transfer not found.",
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
                entity_type="transfer",
                entity_id=transfer_id,
                field_name=field,
                old_value=old_val,
                new_value=new_val_str,
                reason="manual_edit",
            )

    result = supabase.table("transfers").update(payload).eq("id", transfer_id).execute()
    return TransferResponse(**result.data[0])


@router.delete(
    "/transfers/{transfer_id}",
    response_model=MessageResponse,
    summary="Delete a transfer booking",
)
async def delete_transfer(
    transfer_id: str,
    current_user: dict[str, Any] = Depends(get_current_user),
    supabase: Client = Depends(get_supabase_client),
) -> MessageResponse:
    """
    Remove transfer record.
    """
    existing = supabase.table("transfers").select("*").eq("id", transfer_id).single().execute()
    if not existing.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Transfer not found.",
        )

    event_id = existing.data["event_id"]
    await verify_event_access(event_id, current_user, supabase)

    supabase.table("transfers").delete().eq("id", transfer_id).execute()
    return MessageResponse(message="Successfully deleted transfer booking.")


@router.post(
    "/events/{event_id}/transfers/group",
    response_model=MessageResponse,
    summary="Auto-group arrivals into shuttle windows",
)
async def auto_group_shuttles(
    event_id: str,
    window_minutes: int = Query(60, ge=15, le=180, description="Size of transfer grouping window in minutes."),
    pickup_location: str = Query("BRU airport", description="Where to pick up passengers."),
    dropoff_location: str = Query("Conference Hotel", description="Where to drop off passengers."),
    vehicle_type: str = Query("Shuttle Bus", description="Vehicle type assignment."),
    current_user: dict[str, Any] = Depends(get_current_user),
    supabase: Client = Depends(get_supabase_client),
) -> MessageResponse:
    """
    Auto-groups all arrivals (using flight departure/arrival information) into shuttle slots.
    For flights arriving inside each window_minutes block, it schedules a single transfer
    pickup slot at the end of the window.
    """
    await verify_event_access(event_id, current_user, supabase)

    # Fetch all flights for this event
    flights_res = (
        supabase.table("flights")
        .select("id, participant_id, arrival_time, flight_number")
        .eq("event_id", event_id)
        .execute()
    )

    if not flights_res.data:
        return MessageResponse(message="No flight records found to group.")

    # Parse and group by window
    grouped_transfers = 0
    # Group flights by rounded arrival time window
    # We round to nearest block of window_minutes
    for flight in flights_res.data:
        part_id = flight["participant_id"]
        if not part_id:
            continue

        arr_time_str = flight["arrival_time"]
        try:
            arr_dt = datetime.fromisoformat(arr_time_str.replace("Z", "+00:00"))
        except Exception:
            continue

        # Round arrival time to nearest window block (e.g. hourly)
        # Window timestamp is the top of the hour or the end of the slot
        rounded_minutes = (arr_dt.minute // window_minutes + 1) * window_minutes
        pickup_dt = arr_dt.replace(minute=0, second=0, microsecond=0) + timedelta(minutes=rounded_minutes)
        pickup_ts = pickup_dt.isoformat()

        # Check if transfer already exists for this participant & flight_id
        exist = (
            supabase.table("transfers")
            .select("id")
            .eq("participant_id", part_id)
            .eq("flight_id", flight["id"])
            .execute()
        )

        payload = {
            "event_id": event_id,
            "participant_id": part_id,
            "transfer_type": "arrival",
            "flight_id": flight["id"],
            "pickup_location": pickup_location,
            "dropoff_location": dropoff_location,
            "pickup_time": pickup_ts,
            "vehicle_type": vehicle_type,
            "status": "scheduled",
        }

        if exist.data:
            supabase.table("transfers").update(payload).eq("id", exist.data[0]["id"]).execute()
        else:
            supabase.table("transfers").insert(payload).execute()

        supabase.table("participants").update({"has_transfer": True}).eq("id", part_id).execute()
        grouped_transfers += 1

    return MessageResponse(message=f"Successfully auto-grouped {grouped_transfers} passengers into shuttle windows.")
