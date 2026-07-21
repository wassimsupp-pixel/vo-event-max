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
    await verify_event_access(event_id, current_user, supabase, write=True)

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
    await verify_event_access(event_id, current_user, supabase, write=True)

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
    await verify_event_access(event_id, current_user, supabase, write=True)

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
    await verify_event_access(event_id, current_user, supabase, write=True)

    # Fetch all flights for this event
    flights_res = (
        supabase.table("flights")
        .select("id, participant_id, arrival_time, departure_time, flight_number")
        .eq("event_id", event_id)
        .execute()
    )

    if not flights_res.data:
        return MessageResponse(message="No flight records found to group.")

    # The flights table holds every segment of a trip (outbound AND return)
    # with no direction marker (mirrors the flights page's own "Aller/Retour"
    # heuristic: earliest departure = outbound). A shuttle pickup is only
    # needed for the OUTBOUND arrival at the event — treating every segment
    # as an "arrival" also books a bogus BRU-airport-to-hotel shuttle for a
    # participant's return flight landing back home, days later. Keep only
    # each participant's earliest-departing flight.
    earliest_by_participant: dict[str, dict[str, Any]] = {}
    for flight in flights_res.data:
        part_id = flight.get("participant_id")
        if not part_id:
            continue
        dep = flight.get("departure_time") or ""
        current = earliest_by_participant.get(part_id)
        if current is None or dep < (current.get("departure_time") or ""):
            earliest_by_participant[part_id] = flight
    outbound_flights = list(earliest_by_participant.values())

    if not outbound_flights:
        return MessageResponse(message="No flight records found to group.")

    # Preserve transfers that came from an imported transfer file. Those rows are
    # NOT linked to a flight (flight_id IS NULL), whereas calculated shuttles always
    # carry a flight_id. If a participant already has a file-imported transfer, we
    # keep it as-is and never overwrite it with a computed shuttle.
    existing_res = (
        supabase.table("transfers")
        .select("participant_id, flight_id")
        .eq("event_id", event_id)
        .execute()
    )
    imported_participants = {
        row["participant_id"]
        for row in (existing_res.data or [])
        if row.get("participant_id") and not row.get("flight_id")
    }

    # Parse and group by window
    grouped_transfers = 0
    preserved_imported = 0
    # Group flights by rounded arrival time window
    # We round to nearest block of window_minutes
    for flight in outbound_flights:
        part_id = flight["participant_id"]
        if not part_id:
            continue

        # This participant already has a real transfer from the imported file —
        # keep it, do not compute (and do not duplicate) a shuttle for them.
        if part_id in imported_participants:
            preserved_imported += 1
            continue

        arr_time_str = flight["arrival_time"]
        try:
            arr_dt = datetime.fromisoformat(arr_time_str.replace("Z", "+00:00"))
        except Exception:
            continue

        # Round arrival time up to the next slot on a fixed grid anchored to
        # midnight (minutes-since-midnight), not to the arrival's own clock
        # hour. Anchoring to "own hour" (previous behaviour) only produced a
        # genuine window_minutes-wide bucket when window_minutes evenly
        # divides 60 (30 or 60): for 90/120 ("1h30"/"2 heures" in the UI) it
        # silently collapsed back to hourly buckets shifted by a fixed
        # offset — two flights only 20 minutes apart could land in shuttle
        # slots a full hour apart. A single midnight-anchored grid gives
        # consistent window_minutes-wide buckets for every slot size.
        minutes_since_midnight = arr_dt.hour * 60 + arr_dt.minute
        rounded_minutes = (minutes_since_midnight // window_minutes + 1) * window_minutes
        day_start = arr_dt.replace(hour=0, minute=0, second=0, microsecond=0)
        pickup_dt = day_start + timedelta(minutes=rounded_minutes)
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

    if preserved_imported:
        return MessageResponse(
            message=(
                f"Successfully auto-grouped {grouped_transfers} passengers into shuttle windows. "
                f"{preserved_imported} imported transfer(s) were kept as-is."
            )
        )
    return MessageResponse(message=f"Successfully auto-grouped {grouped_transfers} passengers into shuttle windows.")
