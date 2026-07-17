"""
routers/consolidation.py — Consolidation run management endpoints.

Routes:
  POST  /api/events/{event_id}/consolidate          Trigger a consolidation run
  GET   /api/events/{event_id}/runs                 List runs for an event
  GET   /api/events/{event_id}/runs/{run_id}        Get run details + exceptions
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from datetime import datetime, timezone
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from supabase import Client

from dependencies import get_current_user, get_supabase_client, require_role, verify_event_access
from models.schemas import (
    ConsolidationRunListItem,
    ConsolidationRunResponse,
    ExceptionResponse,
    ExceptionResolutionRequest,
)
from services import consolidation_service

logger = logging.getLogger(__name__)

router = APIRouter()


# ---------------------------------------------------------------------------
# POST /api/events/{event_id}/consolidate
# ---------------------------------------------------------------------------

@router.post(
    "/events/{event_id}/consolidate",
    response_model=ConsolidationRunResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Trigger a new consolidation run for an event",
)
async def trigger_consolidation(
    event_id: str,
    background_tasks: BackgroundTasks,
    current_user: dict[str, Any] = Depends(require_role(["admin", "pm"])),
    supabase: Client = Depends(get_supabase_client),
) -> ConsolidationRunResponse:
    """
    Create a new consolidation run and start it asynchronously in the background.

    Only ``admin`` and ``pm`` roles can trigger consolidation.

    The run record is created immediately with ``status=running`` and returned
    so the caller can poll ``GET /api/events/{event_id}/runs/{run_id}`` for progress.

    **Prerequisites**: At least one file for this event must have ``import_status=mapped``.
    """
    await verify_event_access(event_id, current_user, supabase, write=True)

    # Check that at least one mapped or processed file exists
    mapped_files = (
        supabase.table("uploaded_files")
        .select("id")
        .eq("event_id", event_id)
        .in_("import_status", ["mapped", "processed"])
        .execute()
    )
    if not mapped_files.data:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                "No mapped files found for this event. "
                "Please upload files and confirm their column mapping before consolidating."
            ),
        )

    # Create the run record
    run_id = str(uuid.uuid4())
    run_record = {
        "id": run_id,
        "event_id": event_id,
        "triggered_by": current_user["id"],
        "status": "running",
    }
    try:
        result = supabase.table("consolidation_runs").insert(run_record).execute()
    except Exception as exc:
        logger.error("Failed to create consolidation_run record: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to initiate consolidation run.",
        ) from exc

    # Run consolidation asynchronously so the response is returned immediately
    background_tasks.add_task(
        consolidation_service.run_consolidation,
        event_id=event_id,
        run_id=run_id,
        user_id=current_user["id"],
        supabase=supabase,
    )

    logger.info("Consolidation run started: run_id=%s event_id=%s user=%s", run_id, event_id, current_user["id"])

    return ConsolidationRunResponse(**result.data[0])


# ---------------------------------------------------------------------------
# GET /api/events/{event_id}/runs
# ---------------------------------------------------------------------------

@router.get(
    "/events/{event_id}/runs",
    response_model=list[ConsolidationRunListItem],
    summary="List consolidation runs for an event",
)
async def list_runs(
    event_id: str,
    current_user: dict[str, Any] = Depends(get_current_user),
    supabase: Client = Depends(get_supabase_client),
) -> list[ConsolidationRunListItem]:
    """
    Return all consolidation runs for an event, newest first.

    All roles can view run history for events they can access.
    """
    await verify_event_access(event_id, current_user, supabase)

    try:
        result = (
            supabase.table("consolidation_runs")
            .select("id, status, started_at, completed_at, stats")
            .eq("event_id", event_id)
            .order("started_at", desc=True)
            .execute()
        )
    except Exception as exc:
        logger.error("Failed to list runs for event %s: %s", event_id, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve consolidation runs.",
        ) from exc

    return [ConsolidationRunListItem(**row) for row in (result.data or [])]


# ---------------------------------------------------------------------------
# GET /api/events/{event_id}/runs/{run_id}
# ---------------------------------------------------------------------------

@router.get(
    "/events/{event_id}/runs/{run_id}",
    summary="Get details and exceptions for a consolidation run",
)
async def get_run(
    event_id: str,
    run_id: str,
    current_user: dict[str, Any] = Depends(get_current_user),
    supabase: Client = Depends(get_supabase_client),
) -> dict[str, Any]:
    """
    Return full details for a single consolidation run, including:
    - Run metadata (status, stats, timestamps)
    - All exceptions generated during the run

    The ``exceptions`` list is ordered by severity (critical first) then by creation time.
    """
    await verify_event_access(event_id, current_user, supabase)

    # Load run
    try:
        run_resp = (
            supabase.table("consolidation_runs")
            .select("*")
            .eq("id", run_id)
            .eq("event_id", event_id)
            .single()
            .execute()
        )
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Consolidation run not found.") from exc

    if not run_resp.data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Consolidation run not found.")

    # Load exceptions for this run
    try:
        exc_resp = (
            supabase.table("exceptions")
            .select("*")
            .eq("run_id", run_id)
            .order("severity")       # critical < warning < info alphabetically — remap in service if needed
            .order("created_at")
            .execute()
        )
    except Exception as exc:
        logger.warning("Failed to load exceptions for run %s: %s", run_id, exc)
        exc_resp_data = []
    else:
        exc_resp_data = exc_resp.data or []

    exceptions = [ExceptionResponse(**row) for row in exc_resp_data]

    return {
        "run": ConsolidationRunResponse(**run_resp.data),
        "exceptions": exceptions,
        "exception_count": len(exceptions),
    }


# ---------------------------------------------------------------------------
# GET /api/events/{event_id}/exceptions
# ---------------------------------------------------------------------------

@router.get(
    "/events/{event_id}/exceptions",
    response_model=list[ExceptionResponse],
    summary="List all unresolved exceptions for an event",
)
async def list_event_exceptions(
    event_id: str,
    current_user: dict[str, Any] = Depends(get_current_user),
    supabase: Client = Depends(get_supabase_client),
) -> list[ExceptionResponse]:
    """
    Return all unresolved exceptions for a given event.
    """
    await verify_event_access(event_id, current_user, supabase)

    try:
        result = (
            supabase.table("exceptions")
            .select("*")
            .eq("event_id", event_id)
            .eq("resolved", False)
            .order("severity")
            .order("created_at")
            .execute()
        )
    except Exception as exc:
        logger.error("Failed to list exceptions for event %s: %s", event_id, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve exceptions.",
        ) from exc

    return [ExceptionResponse(**row) for row in (result.data or [])]


# ---------------------------------------------------------------------------
# POST /api/exceptions/{exception_id}/resolve
# ---------------------------------------------------------------------------

@router.post(
    "/exceptions/{exception_id}/resolve",
    summary="Resolve a data exception",
)
async def resolve_exception(
    exception_id: str,
    body: ExceptionResolutionRequest,
    current_user: dict[str, Any] = Depends(require_role(["admin", "pm"])),
    supabase: Client = Depends(get_supabase_client),
):
    """
    Mark an exception as resolved. If it's a conflict exception and a resolution
    value is provided, update the participant profile and lock the field.
    """
    # 1. Fetch the exception to find event_id and participant_id
    try:
        exc_res = supabase.table("exceptions").select("*").eq("id", exception_id).single().execute()
    except Exception as exc:
        logger.error("Exception not found: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Exception not found.",
        ) from exc

    exception = exc_res.data
    event_id = exception["event_id"]
    participant_id = exception.get("participant_id")
    context_data = exception.get("context_data") or {}

    # Verify event access
    await verify_event_access(event_id, current_user, supabase, write=True)

    # 2. Mark exception as resolved
    try:
        supabase.table("exceptions").update({
            "resolved": True,
            "resolved_by": current_user["id"],
            "resolved_at": datetime.now(timezone.utc).isoformat(),
        }).eq("id", exception_id).execute()
    except Exception as exc:
        logger.error("Failed to update exception: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to resolve exception.",
        ) from exc

    # 3. If it's a conflict resolution (value chosen is not generic "resolved")
    if body.resolution != "resolved" and participant_id:
        field_name = context_data.get("field")
        if field_name:
            try:
                # Get the participant to read their locked_fields
                part_res = supabase.table("participants").select("locked_fields").eq("id", participant_id).single().execute()
                locked_fields = part_res.data.get("locked_fields") or {}
                
                # Add current field to locked_fields list/object
                if isinstance(locked_fields, list):
                    if field_name not in locked_fields:
                        locked_fields.append(field_name)
                elif isinstance(locked_fields, dict):
                    locked_fields[field_name] = True
                else:
                    locked_fields = {field_name: True}

                # Update the participant field value and locked_fields
                payload = {
                    field_name: body.resolution,
                    "locked_fields": locked_fields,
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                }
                supabase.table("participants").update(payload).eq("id", participant_id).execute()
            except Exception as exc:
                logger.error("Failed to update participant during exception resolution: %s", exc)

    return {"status": "ok", "message": "Exception resolved successfully."}
