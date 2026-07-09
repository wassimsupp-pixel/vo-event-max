"""
routers/events.py — Event management endpoints.

Routes:
  POST   /api/events               Create a new event
  GET    /api/events/{event_id}    Get event details
  PATCH  /api/events/{event_id}    Update event metadata
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from supabase import Client

from dependencies import get_current_user, get_supabase_client, require_role, verify_event_access
from models.schemas import EventCreate, EventResponse, EventUpdate, MessageResponse, ProjectCreate, ProjectResponse

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post(
    "/projects",
    response_model=ProjectResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new project",
)
async def create_project(
    body: ProjectCreate,
    current_user: dict[str, Any] = Depends(require_role(["admin", "pm"])),
    supabase: Client = Depends(get_supabase_client),
) -> ProjectResponse:
    """
    Create a new project inside the organization.
    """
    org_id = current_user["org_id"]
    user_id = current_user["id"]
    payload = {
        "org_id": org_id,
        "name": body.name,
        "client_name": body.client_name,
        "created_by": user_id,
    }
    try:
        result = supabase.table("projects").insert(payload).execute()
    except Exception as exc:
        logger.error("Failed to create project: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create project.",
        ) from exc

    return ProjectResponse(**result.data[0])


@router.get(
    "/projects",
    response_model=list[ProjectResponse],
    summary="List all projects in the organization",
)
async def list_projects(
    current_user: dict[str, Any] = Depends(get_current_user),
    supabase: Client = Depends(get_supabase_client),
) -> list[ProjectResponse]:
    """
    List all projects for the caller's organization.
    """
    org_id = current_user["org_id"]
    try:
        res = (
            supabase.table("projects")
            .select("*")
            .eq("org_id", org_id)
            .execute()
        )
    except Exception as exc:
        logger.error("Failed to list projects: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve projects.",
        ) from exc

    return [ProjectResponse(**row) for row in res.data]



@router.post(
    "/events",
    response_model=EventResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new event",
)
async def create_event(
    body: EventCreate,
    current_user: dict[str, Any] = Depends(require_role(["admin", "pm"])),
    supabase: Client = Depends(get_supabase_client),
) -> EventResponse:
    """
    Create a new event inside a project.

    Only ``admin`` and ``pm`` roles can create events. The project must belong
    to the caller's organisation (enforced by RLS on the Supabase side via the
    service-role client + manual org_id check).
    """
    # Verify the project belongs to the caller's org
    org_id: str = current_user["org_id"]
    proj_check = (
        supabase.table("projects")
        .select("id")
        .eq("id", str(body.project_id))
        .eq("org_id", org_id)
        .single()
        .execute()
    )
    if not proj_check.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found or access denied.",
        )

    payload = body.model_dump(mode="json", exclude_none=True)
    try:
        result = supabase.table("events").insert(payload).execute()
    except Exception as exc:
        logger.error("Failed to create event: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create event.",
        ) from exc

    return EventResponse(**result.data[0])


@router.get(
    "/events/{event_id}",
    response_model=EventResponse,
    summary="Get event details",
)
async def get_event(
    event_id: str,
    current_user: dict[str, Any] = Depends(get_current_user),
    supabase: Client = Depends(get_supabase_client),
) -> EventResponse:
    """
    Retrieve details for a single event.

    Raises HTTP 404 if the event does not exist or belongs to a different org
    (no information leakage about other tenants' events).
    """
    event = await verify_event_access(event_id, current_user, supabase)
    return EventResponse(**event)


@router.patch(
    "/events/{event_id}",
    response_model=EventResponse,
    summary="Update event metadata",
)
async def update_event(
    event_id: str,
    body: EventUpdate,
    current_user: dict[str, Any] = Depends(require_role(["admin", "pm"])),
    supabase: Client = Depends(get_supabase_client),
) -> EventResponse:
    """
    Partially update an event's metadata (name, dates, location, etc.).

    Only ``admin`` and ``pm`` roles may update events.
    """
    await verify_event_access(event_id, current_user, supabase)

    updates = body.model_dump(mode="json", exclude_none=True)
    if not updates:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No fields provided for update.",
        )

    try:
        result = (
            supabase.table("events")
            .update(updates)
            .eq("id", event_id)
            .execute()
        )
    except Exception as exc:
        logger.error("Failed to update event %s: %s", event_id, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update event.",
        ) from exc

    if not result.data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found.")

    return EventResponse(**result.data[0])


@router.get(
    "/events",
    response_model=list[EventResponse],
    summary="List all events in the organization",
)
async def list_events(
    current_user: dict[str, Any] = Depends(get_current_user),
    supabase: Client = Depends(get_supabase_client),
) -> list[EventResponse]:
    """
    List all events for the caller's organization.
    """
    org_id = current_user["org_id"]
    try:
        res = (
            supabase.table("events")
            .select("*, projects!inner(org_id)")
            .eq("projects.org_id", org_id)
            .execute()
        )
    except Exception as exc:
        logger.error("Failed to list events: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve events.",
        ) from exc

    return [EventResponse(**row) for row in res.data]

