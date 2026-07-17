"""
routers/flights.py — Flight management endpoints.
"""

from __future__ import annotations

import logging
from typing import Any
from fastapi import APIRouter, Depends, HTTPException, status
from supabase import Client

from dependencies import get_current_user, get_supabase_client, verify_event_access
from models.schemas import FlightResponse, FlightUpdate, MessageResponse
from services.audit_service import log_change

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get(
    "/events/{event_id}/flights",
    response_model=list[FlightResponse],
    summary="List all flights for an event",
)
async def list_flights(
    event_id: str,
    current_user: dict[str, Any] = Depends(get_current_user),
    supabase: Client = Depends(get_supabase_client),
) -> list[FlightResponse]:
    """
    List all flights for an event with passenger details.
    """
    await verify_event_access(event_id, current_user, supabase)

    response = (
        supabase.table("flights")
        .select("*, participants(first_name, last_name)")
        .eq("event_id", event_id)
        .execute()
    )

    results = []
    for row in response.data:
        part = row.get("participants")
        part_name = f"{part['first_name']} {part['last_name']}" if part else None
        item = row.copy()
        item.pop("participants", None)
        item["participant_name"] = part_name
        results.append(FlightResponse(**item))

    return results


@router.patch(
    "/flights/{flight_id}",
    response_model=FlightResponse,
    summary="Update flight details",
)
async def update_flight(
    flight_id: str,
    body: FlightUpdate,
    current_user: dict[str, Any] = Depends(get_current_user),
    supabase: Client = Depends(get_supabase_client),
) -> FlightResponse:
    """
    Update details of a flight segment. Logs to audit trail.
    """
    # Load existing
    existing = supabase.table("flights").select("*").eq("id", flight_id).single().execute()
    if not existing.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Flight not found.",
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
                entity_type="flight",
                entity_id=flight_id,
                field_name=field,
                old_value=old_val,
                new_value=new_val_str,
                reason="manual_edit",
            )

    result = supabase.table("flights").update(payload).eq("id", flight_id).execute()
    return FlightResponse(**result.data[0])


@router.post(
    "/events/{event_id}/flights/extract",
    response_model=MessageResponse,
    summary="Extract flights from FCM data",
)
async def extract_flights(
    event_id: str,
    current_user: dict[str, Any] = Depends(get_current_user),
    supabase: Client = Depends(get_supabase_client),
) -> MessageResponse:
    """
    Scan mapped FCM source records linked to participants and extract flight details.
    """
    await verify_event_access(event_id, current_user, supabase, write=True)

    fcm_files = (
        supabase.table("uploaded_files")
        .select("id")
        .eq("event_id", event_id)
        .eq("source_type", "fcm")
        .execute()
    )

    if not fcm_files.data:
        return MessageResponse(message="No FCM files imported yet.")

    file_ids = [f["id"] for f in fcm_files.data]

    records = (
        supabase.table("source_records")
        .select("*")
        .in_("file_id", file_ids)
        .not_.is_("participant_id", "null")
        .execute()
    )

    extracted_count = 0
    for record in records.data:
        part_id = record["participant_id"]
        data = record["normalized_data"] or record["raw_data"]

        flight_num = data.get("flight_number") or data.get("passenger_flight")
        dep_apt = data.get("departure_airport") or data.get("departure")
        arr_apt = data.get("arrival_airport") or data.get("arrival")

        if not flight_num or not dep_apt or not arr_apt:
            continue

        dep_date = data.get("departure_date") or "2025-11-10"
        dep_time = data.get("departure_time") or "00:00"
        arr_date = data.get("arrival_date") or "2025-11-10"
        arr_time = data.get("arrival_time") or "00:00"

        dep_ts = f"{dep_date}T{dep_time}:00Z" if "T" not in str(dep_date) else dep_date
        arr_ts = f"{arr_date}T{arr_time}:00Z" if "T" not in str(arr_date) else arr_date

        pnr = data.get("pnr_code") or data.get("pnr")
        airline = data.get("airline")
        baggage = data.get("baggage_info") or data.get("baggage")

        flight_payload = {
            "event_id": event_id,
            "participant_id": part_id,
            "flight_number": str(flight_num).strip().upper(),
            "departure_airport": str(dep_apt).strip().upper(),
            "arrival_airport": str(arr_apt).strip().upper(),
            "departure_time": dep_ts,
            "arrival_time": arr_ts,
            "pnr_code": pnr,
            "airline": airline,
            "baggage_info": baggage,
            "status": "confirmed",
        }

        # Check existing
        exist_check = (
            supabase.table("flights")
            .select("id")
            .eq("participant_id", part_id)
            .eq("flight_number", flight_payload["flight_number"])
            .execute()
        )

        if exist_check.data:
            supabase.table("flights").update(flight_payload).eq("id", exist_check.data[0]["id"]).execute()
        else:
            supabase.table("flights").insert(flight_payload).execute()

        supabase.table("participants").update({"has_flight": True}).eq("id", part_id).execute()
        extracted_count += 1

    return MessageResponse(message=f"Successfully extracted {extracted_count} flight records.")
