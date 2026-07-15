"""
routers/participants.py — Participant management endpoints.

Routes:
  GET   /api/events/{event_id}/participants          Paginated + filtered participant list
  GET   /api/participants/{participant_id}            Full participant detail
  PATCH /api/participants/{participant_id}            Update a single field (with change_log)
  POST  /api/participants/{participant_id}/lock/{field}    Lock a field
  POST  /api/participants/{participant_id}/unlock/{field}  Unlock a field
"""

from __future__ import annotations

import logging
import math
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from supabase import Client

from dependencies import get_current_user, get_supabase_client, verify_event_access
from models.schemas import (
    MessageResponse,
    ParticipantListItem,
    ParticipantListResponse,
    ParticipantResponse,
    ParticipantUpdate,
    ParticipantLookupItem,
)
from services.audit_service import log_change

logger = logging.getLogger(__name__)

router = APIRouter()

# Fields that are always selected for the detail view
PARTICIPANT_FULL_SELECT = (
    "id, event_id, first_name, last_name, email, company, phone, nationality, "
    "dietary_requirements, completeness_status, has_flight, has_hotel, has_transfer, "
    "has_activities, verification_note, locked_fields, registration_source_id, "
    "fcm_source_id, created_at, updated_at"
)

# Fields returned in list view (no dietary_requirements)
PARTICIPANT_LIST_SELECT = (
    "id, event_id, first_name, last_name, email, company, "
    "completeness_status, has_flight, has_hotel, has_transfer, has_activities"
)

# Fields that may NOT be updated via the API (system-managed)
IMMUTABLE_FIELDS = {"id", "event_id", "created_at", "updated_at", "registration_source_id", "fcm_source_id"}


def _strip_dietary(participant: dict, role: str) -> dict:
    """
    Remove dietary_requirements from the participant dict for non-admin/pm roles.

    This is an application-layer enforcement layered on top of the RLS policy.
    """
    if role not in ("admin", "pm"):
        participant = participant.copy()
        participant.pop("dietary_requirements", None)
    return participant


# ---------------------------------------------------------------------------
# GET /api/events/{event_id}/participants
# ---------------------------------------------------------------------------

@router.get(
    "/events/{event_id}/participants",
    response_model=ParticipantListResponse,
    summary="List participants for an event (paginated + filtered)",
)
async def list_participants(
    event_id: str,
    page: int = Query(1, ge=1, description="Page number (1-indexed)."),
    page_size: int = Query(50, ge=1, le=200, description="Results per page (max 200)."),
    status_filter: Optional[str] = Query(None, alias="status", description="Filter by completeness_status: complete | incomplete | conflict"),
    has_flight: Optional[bool] = Query(None, description="Filter by flight status."),
    has_hotel: Optional[bool] = Query(None, description="Filter by hotel status."),
    has_transfer: Optional[bool] = Query(None, description="Filter by transfer status."),
    search: Optional[str] = Query(None, description="Substring search on first_name, last_name, email, company, phone."),
    current_user: dict[str, Any] = Depends(get_current_user),
    supabase: Client = Depends(get_supabase_client),
) -> ParticipantListResponse:
    """
    Return a paginated, filterable list of participants for an event.

    Filters:
    - ``status``: completeness_status value
    - ``has_flight``, ``has_hotel``: boolean flags
    - ``search``: case-insensitive substring match on name / email (ilike)

    Note: dietary_requirements is NOT returned in the list view for any role.
    Use the detail endpoint to retrieve it (admin/pm only).
    """
    await verify_event_access(event_id, current_user, supabase)

    offset = (page - 1) * page_size

    # Build query
    q = (
        supabase.table("participants")
        .select(PARTICIPANT_LIST_SELECT, count="exact")
        .eq("event_id", event_id)
    )

    if status_filter:
        q = q.eq("completeness_status", status_filter)
    if has_flight is not None:
        q = q.eq("has_flight", has_flight)
    if has_hotel is not None:
        q = q.eq("has_hotel", has_hotel)
    if has_transfer is not None:
        q = q.eq("has_transfer", has_transfer)
    if search:
        # Multi-column case-insensitive search: name, email, company and phone
        # (feedback §9 — search must not be limited to the email address).
        pattern = f"%{search}%"
        q = q.or_(
            f"first_name.ilike.{pattern},last_name.ilike.{pattern},"
            f"email.ilike.{pattern},company.ilike.{pattern},phone.ilike.{pattern}"
        )

    q = q.order("last_name").order("first_name").range(offset, offset + page_size - 1)

    try:
        result = q.execute()
    except Exception as exc:
        logger.error("Failed to list participants for event %s: %s", event_id, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve participant list.",
        ) from exc

    total = result.count or 0
    total_pages = max(1, math.ceil(total / page_size))

    items = [ParticipantListItem(**row) for row in (result.data or [])]

    return ParticipantListResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )


@router.get(
    "/events/{event_id}/participants/lookup",
    response_model=list[ParticipantLookupItem],
    summary="Get minimal participant info for select dropdowns (non-paginated)",
)
async def lookup_participants(
    event_id: str,
    current_user: dict[str, Any] = Depends(get_current_user),
    supabase: Client = Depends(get_supabase_client),
) -> list[ParticipantLookupItem]:
    """
    Get a minimal lookup list of participants for dropdowns.
    Always verifies event access first.
    """
    await verify_event_access(event_id, current_user, supabase)

    all_items = []
    page_size = 1000
    offset = 0

    while True:
        try:
            res = (
                supabase.table("participants")
                .select("id, first_name, last_name, completeness_status")
                .eq("event_id", event_id)
                .order("last_name")
                .order("first_name")
                .range(offset, offset + page_size - 1)
                .execute()
            )
            data = res.data or []
            all_items.extend(data)
            if len(data) < page_size:
                break
            offset += page_size
        except Exception as exc:
            logger.error("Failed to lookup participants: %s", exc)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to retrieve participant list.",
            ) from exc

    return [ParticipantLookupItem(**row) for row in all_items]


# ---------------------------------------------------------------------------
# GET /api/participants/{participant_id}
# ---------------------------------------------------------------------------

@router.get(
    "/participants/{participant_id}",
    response_model=ParticipantResponse,
    summary="Get full participant detail",
)
async def get_participant(
    participant_id: str,
    current_user: dict[str, Any] = Depends(get_current_user),
    supabase: Client = Depends(get_supabase_client),
) -> ParticipantResponse:
    """
    Retrieve the full record for a single participant.

    dietary_requirements is only populated for ``admin`` and ``pm`` roles.
    For ``client`` and ``viewer`` roles, the field will be ``null`` in the response.
    """
    try:
        result = (
            supabase.table("participants")
            .select(PARTICIPANT_FULL_SELECT)
            .eq("id", participant_id)
            .single()
            .execute()
        )
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Participant not found.") from exc

    if not result.data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Participant not found.")

    participant = result.data

    # Verify event access (org isolation)
    await verify_event_access(participant["event_id"], current_user, supabase)

    # RGPD: strip dietary data for non-admin/pm
    role: str = current_user.get("role", "viewer")
    participant = _strip_dietary(participant, role)

    return ParticipantResponse(**participant)


# ---------------------------------------------------------------------------
# PATCH /api/participants/{participant_id}
# ---------------------------------------------------------------------------

@router.patch(
    "/participants/{participant_id}",
    response_model=ParticipantResponse,
    summary="Update a single participant field",
)
async def update_participant(
    participant_id: str,
    body: ParticipantUpdate,
    current_user: dict[str, Any] = Depends(get_current_user),
    supabase: Client = Depends(get_supabase_client),
) -> ParticipantResponse:
    """
    Update a single field on a participant record.

    Rules:
    - ``dietary_requirements`` can only be updated by ``admin`` / ``pm``
    - System fields (``id``, ``event_id``, ``created_at``, etc.) cannot be updated
    - The change is written to ``change_log`` BEFORE the update is applied
    - If ``lock=true``, the field is added to ``locked_fields``
    """
    user_role: str = current_user.get("role", "viewer")

    # Guard: dietary_requirements is RGPD-sensitive
    if body.field == "dietary_requirements" and user_role not in ("admin", "pm"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admin and pm roles may update dietary_requirements.",
        )

    # Guard: immutable system fields
    if body.field in IMMUTABLE_FIELDS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Field '{body.field}' cannot be modified via the API.",
        )

    # Load existing participant
    try:
        existing_resp = (
            supabase.table("participants")
            .select(PARTICIPANT_FULL_SELECT)
            .eq("id", participant_id)
            .single()
            .execute()
        )
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Participant not found.") from exc

    if not existing_resp.data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Participant not found.")

    existing = existing_resp.data
    await verify_event_access(existing["event_id"], current_user, supabase)

    old_value = existing.get(body.field)

    # Write to change_log BEFORE making the update
    log_change(
        supabase=supabase,
        event_id=existing["event_id"],
        user_id=current_user["id"],
        entity_type="participant",
        entity_id=participant_id,
        field_name=body.field,
        old_value=str(old_value) if old_value is not None else None,
        new_value=str(body.value) if body.value is not None else None,
        reason=body.reason,
    )

    # Build update payload
    updates: dict[str, Any] = {body.field: body.value}

    if body.lock:
        locked_fields: dict = existing.get("locked_fields") or {}
        locked_fields[body.field] = True
        updates["locked_fields"] = locked_fields

    # Apply update
    try:
        result = (
            supabase.table("participants")
            .update(updates)
            .eq("id", participant_id)
            .execute()
        )
    except Exception as exc:
        logger.error("Failed to update participant %s: %s", participant_id, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update participant.",
        ) from exc

    updated = result.data[0]
    updated = _strip_dietary(updated, user_role)
    return ParticipantResponse(**updated)


# ---------------------------------------------------------------------------
# POST /api/participants/{participant_id}/lock/{field}
# ---------------------------------------------------------------------------

@router.post(
    "/participants/{participant_id}/lock/{field}",
    response_model=MessageResponse,
    summary="Lock a participant field against re-import overwrites",
)
async def lock_field(
    participant_id: str,
    field: str,
    current_user: dict[str, Any] = Depends(get_current_user),
    supabase: Client = Depends(get_supabase_client),
) -> MessageResponse:
    """
    Add ``field`` to the participant's ``locked_fields``.

    Locked fields retain their manually-set values when the consolidation
    engine re-runs — new imports cannot overwrite them.
    """
    if field in IMMUTABLE_FIELDS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Field '{field}' is a system field and cannot be locked.",
        )

    existing_resp = (
        supabase.table("participants")
        .select("id, event_id, locked_fields")
        .eq("id", participant_id)
        .single()
        .execute()
    )
    if not existing_resp.data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Participant not found.")

    existing = existing_resp.data
    await verify_event_access(existing["event_id"], current_user, supabase)

    locked_fields: dict = existing.get("locked_fields") or {}
    locked_fields[field] = True

    log_change(
        supabase=supabase,
        event_id=existing["event_id"],
        user_id=current_user["id"],
        entity_type="participant",
        entity_id=participant_id,
        field_name=f"locked_fields.{field}",
        old_value="false",
        new_value="true",
        reason="lock",
    )

    supabase.table("participants").update({"locked_fields": locked_fields}).eq("id", participant_id).execute()

    return MessageResponse(message=f"Field '{field}' is now locked for participant {participant_id}.")


# ---------------------------------------------------------------------------
# POST /api/participants/{participant_id}/unlock/{field}
# ---------------------------------------------------------------------------

@router.post(
    "/participants/{participant_id}/unlock/{field}",
    response_model=MessageResponse,
    summary="Unlock a participant field to allow re-import overwrites",
)
async def unlock_field(
    participant_id: str,
    field: str,
    current_user: dict[str, Any] = Depends(get_current_user),
    supabase: Client = Depends(get_supabase_client),
) -> MessageResponse:
    """
    Remove ``field`` from the participant's ``locked_fields``.

    After unlocking, re-imports can overwrite the field value.
    """
    existing_resp = (
        supabase.table("participants")
        .select("id, event_id, locked_fields")
        .eq("id", participant_id)
        .single()
        .execute()
    )
    if not existing_resp.data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Participant not found.")

    existing = existing_resp.data
    await verify_event_access(existing["event_id"], current_user, supabase)

    locked_fields: dict = existing.get("locked_fields") or {}
    was_locked = locked_fields.pop(field, False)

    if not was_locked:
        return MessageResponse(message=f"Field '{field}' was not locked.")

    log_change(
        supabase=supabase,
        event_id=existing["event_id"],
        user_id=current_user["id"],
        entity_type="participant",
        entity_id=participant_id,
        field_name=f"locked_fields.{field}",
        old_value="true",
        new_value="false",
        reason="unlock",
    )

    supabase.table("participants").update({"locked_fields": locked_fields}).eq("id", participant_id).execute()

    return MessageResponse(message=f"Field '{field}' is now unlocked for participant {participant_id}.")
