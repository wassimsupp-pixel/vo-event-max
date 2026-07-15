# -*- coding: utf-8 -*-
"""
communications.py
=================
Participant confirmation generation + communication tracking (feedback §13 and
the "Lettre individuelle" module).

Routes:
- POST /api/events/{event_id}/participants/{participant_id}/confirmation/generate
- GET  /api/events/{event_id}/communications
- PATCH /api/communications/{communication_id}
- POST  /api/communications/{communication_id}/send
"""

from __future__ import annotations

import logging
from typing import Any, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from supabase import Client

from dependencies import get_current_user, get_supabase_client, require_role, verify_event_access
from services import confirmation_service

logger = logging.getLogger(__name__)

router = APIRouter()


class CommunicationUpdate(BaseModel):
    subject: Optional[str] = None
    body: Optional[str] = None
    status: Optional[str] = None


@router.post("/events/{event_id}/participants/{participant_id}/confirmation/generate")
async def generate_confirmation(
    event_id: str,
    participant_id: str,
    current_user: dict[str, Any] = Depends(require_role(["admin", "pm"])),
    supabase: Client = Depends(get_supabase_client),
) -> dict[str, Any]:
    """
    Generate an individual confirmation draft from the participant's consolidated
    data and persist it as a `communications` row (status=draft).
    """
    await verify_event_access(event_id, current_user, supabase)

    draft = confirmation_service.generate_confirmation(supabase, participant_id)

    row: Optional[dict[str, Any]] = None
    persisted = False
    try:
        payload = {
            "event_id": event_id,
            "participant_id": participant_id,
            "type": "confirmation",
            "channel": "email",
            "subject": draft["subject"],
            "body": draft["body"],
            "status": "draft",
            "created_by": current_user["id"],
        }
        res = supabase.table("communications").insert(payload).execute()
        row = res.data[0] if res.data else None
        persisted = True
    except Exception as exc:
        # Table may not exist yet (migration not run). Still return the draft so
        # the user can preview it; it just isn't tracked until the table exists.
        logger.warning("Could not persist communication (run migration 002?): %s", exc)

    return {
        "communication": row,
        "persisted": persisted,
        "subject": draft["subject"],
        "body": draft["body"],
        "facts": draft["facts"],
        "missing": draft["missing"],
        "source": draft["source"],
    }


@router.get("/events/{event_id}/communications")
async def list_communications(
    event_id: str,
    current_user: dict[str, Any] = Depends(get_current_user),
    supabase: Client = Depends(get_supabase_client),
) -> list[dict[str, Any]]:
    """Tracking table: all communications for an event with participant names."""
    await verify_event_access(event_id, current_user, supabase)
    try:
        res = (
            supabase.table("communications")
            .select("*, participants(first_name, last_name, email)")
            .eq("event_id", event_id)
            .order("created_at", desc=True)
            .execute()
        )
    except Exception as exc:
        logger.warning("communications list failed (run migration 002?): %s", exc)
        return []

    out = []
    for row in res.data or []:
        part = row.get("participants")
        row["participant_name"] = f"{part['first_name']} {part['last_name']}" if part else None
        out.append(row)
    return out


@router.patch("/communications/{communication_id}")
async def update_communication(
    communication_id: str,
    body: CommunicationUpdate,
    current_user: dict[str, Any] = Depends(require_role(["admin", "pm"])),
    supabase: Client = Depends(get_supabase_client),
) -> dict[str, Any]:
    """Edit a communication's subject/body/status."""
    existing = supabase.table("communications").select("event_id").eq("id", communication_id).single().execute()
    if not existing.data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Communication not found.")
    await verify_event_access(existing.data["event_id"], current_user, supabase)

    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    if not updates:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No fields to update.")
    updates["updated_at"] = "now()"

    res = supabase.table("communications").update(updates).eq("id", communication_id).execute()
    return res.data[0] if res.data else {}


@router.post("/communications/{communication_id}/send")
async def send_communication(
    communication_id: str,
    current_user: dict[str, Any] = Depends(require_role(["admin", "pm"])),
    supabase: Client = Depends(get_supabase_client),
) -> dict[str, Any]:
    """
    Mark a communication as sent. (Actual delivery via the connected mailbox is
    a follow-up; this records the validated send and its timestamp.)
    """
    existing = supabase.table("communications").select("event_id").eq("id", communication_id).single().execute()
    if not existing.data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Communication not found.")
    await verify_event_access(existing.data["event_id"], current_user, supabase)

    res = (
        supabase.table("communications")
        .update({"status": "sent", "sent_at": "now()", "updated_at": "now()"})
        .eq("id", communication_id)
        .execute()
    )
    return res.data[0] if res.data else {}
