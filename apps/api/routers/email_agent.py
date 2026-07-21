# -*- coding: utf-8 -*-
"""
email_agent.py
==============
FastAPI router for the AI Email Agent endpoints.
"""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from supabase import Client

from dependencies import get_current_user, get_supabase_client, verify_event_access
from models.schemas import EmailProposalAnalyzeRequest, EmailProposalResponse
from services.email_agent_service import EmailAgentService

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/events/{event_id}/email-agent", response_model=list[EmailProposalResponse])
async def list_proposals(
    event_id: UUID,
    supabase: Client = Depends(get_supabase_client),
    current_user: dict[str, Any] = Depends(get_current_user),
) -> list[dict[str, Any]]:
    """List all AI parsed email proposals for a specific event."""
    await verify_event_access(str(event_id), current_user, supabase)
    service = EmailAgentService(supabase)
    return await service.list_proposals(event_id)


@router.post("/events/{event_id}/email-agent/analyze", response_model=EmailProposalResponse)
async def analyze_email(
    event_id: UUID,
    payload: EmailProposalAnalyzeRequest,
    supabase: Client = Depends(get_supabase_client),
    current_user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    """Parse a new incoming email and generate AI update proposals."""
    await verify_event_access(str(event_id), current_user, supabase, write=True)
    service = EmailAgentService(supabase)
    return await service.analyze_email(
        event_id=event_id,
        sender=payload.sender,
        subject=payload.subject,
        body=payload.body
    )


@router.post("/email-agent/{proposal_id}/apply")
async def apply_proposal(
    proposal_id: UUID,
    supabase: Client = Depends(get_supabase_client),
    current_user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, str]:
    """Approve and apply AI proposed updates to the participant profile."""
    service = EmailAgentService(supabase)
    proposal = await service.get_proposal(proposal_id)
    if not proposal:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Email proposal not found.")
    await verify_event_access(str(proposal["event_id"]), current_user, supabase, write=True)

    success = await service.apply_proposal(proposal_id, UUID(current_user["id"]))
    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Failed to apply email proposal. Check if it is pending and has an associated participant."
        )
    return {"status": "success", "message": "Email proposal applied successfully."}


@router.post("/email-agent/{proposal_id}/reject")
async def reject_proposal(
    proposal_id: UUID,
    supabase: Client = Depends(get_supabase_client),
    current_user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, str]:
    """Reject and dismiss an AI email update proposal."""
    service = EmailAgentService(supabase)
    proposal = await service.get_proposal(proposal_id)
    if not proposal:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Email proposal not found.")
    await verify_event_access(str(proposal["event_id"]), current_user, supabase, write=True)

    success = await service.reject_proposal(proposal_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Failed to reject email proposal."
        )
    return {"status": "success", "message": "Email proposal rejected."}
