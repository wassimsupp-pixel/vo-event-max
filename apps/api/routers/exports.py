"""
routers/exports.py — Export generation and download endpoints.

Routes:
  POST  /api/events/{event_id}/exports          Generate an Excel export
  GET   /api/exports/{export_id}/download       Get a signed download URL
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from supabase import Client

import config
from dependencies import get_current_user, get_supabase_client, verify_event_access
from models.schemas import ExportDownloadResponse, ExportRequest, ExportResponse
from services import export_service

logger = logging.getLogger(__name__)

router = APIRouter()


# ---------------------------------------------------------------------------
# POST /api/events/{event_id}/exports
# ---------------------------------------------------------------------------

@router.post(
    "/events/{event_id}/exports",
    response_model=ExportResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Generate an Excel export for a consolidation run",
)
async def create_export(
    event_id: str,
    body: ExportRequest,
    current_user: dict[str, Any] = Depends(get_current_user),
    supabase: Client = Depends(get_supabase_client),
) -> ExportResponse:
    """
    Generate a multi-sheet Excel workbook for the given consolidation run and
    upload it to Supabase Storage (private bucket).

    Sheets generated:
    1. **Master List** — all participants with colour-coded completeness rows
    2. **Exceptions** — unresolved exceptions from the run
    3. **Summary** — run statistics and metadata
    4. **Change Log** — last 500 change log entries for the event

    The export is stored privately; use ``GET /api/exports/{export_id}/download``
    to obtain a time-limited signed URL.
    """
    await verify_event_access(event_id, current_user, supabase)

    # Verify the run exists and belongs to this event
    run_resp = (
        supabase.table("consolidation_runs")
        .select("id, status")
        .eq("id", str(body.run_id))
        .eq("event_id", event_id)
        .single()
        .execute()
    )
    if not run_resp.data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Consolidation run not found.")
    if run_resp.data["status"] != "completed":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cannot export an incomplete or failed consolidation run.",
        )

    # Generate Excel bytes
    try:
        excel_bytes: bytes = await export_service.generate_excel(
            event_id=event_id,
            run_id=str(body.run_id),
            user_id=current_user["id"],
            supabase=supabase,
        )
    except Exception as exc:
        logger.error("Excel generation failed for event %s run %s: %s", event_id, body.run_id, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate Excel export.",
        ) from exc

    # Upload to Supabase Storage
    export_id = str(uuid.uuid4())
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    filename = f"export_{event_id[:8]}_{timestamp}.xlsx"
    storage_path = f"exports/{event_id}/{export_id}/{filename}"

    try:
        supabase.storage.from_(config.SUPABASE_STORAGE_BUCKET).upload(
            path=storage_path,
            file=excel_bytes,
            file_options={
                "content-type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            },
        )
    except Exception as exc:
        logger.error("Failed to upload export to storage: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Export generated but upload to storage failed.",
        ) from exc

    # Register in exports table
    export_record = {
        "id": export_id,
        "run_id": str(body.run_id),
        "event_id": event_id,
        "storage_path": storage_path,
        "filename": filename,
        "created_by": current_user["id"],
    }
    try:
        result = supabase.table("exports").insert(export_record).execute()
    except Exception as exc:
        logger.error("Failed to register export record: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Export uploaded but metadata registration failed.",
        ) from exc

    logger.info(
        "Export created: export_id=%s event_id=%s run_id=%s user=%s",
        export_id, event_id, body.run_id, current_user["id"],
    )

    return ExportResponse(**result.data[0])


# ---------------------------------------------------------------------------
# GET /api/exports/{export_id}/download
# ---------------------------------------------------------------------------

@router.get(
    "/exports/{export_id}/download",
    response_model=ExportDownloadResponse,
    summary="Get a signed download URL for an export file (valid 1 hour)",
)
async def download_export(
    export_id: str,
    current_user: dict[str, Any] = Depends(get_current_user),
    supabase: Client = Depends(get_supabase_client),
) -> ExportDownloadResponse:
    """
    Return a time-limited (1 hour) signed URL for downloading an export file.

    The file is stored in a private Supabase Storage bucket and cannot be
    accessed directly. The signed URL is single-use in the sense that it
    expires after 3600 seconds.
    """
    # Load export metadata
    try:
        export_resp = (
            supabase.table("exports")
            .select("*")
            .eq("id", export_id)
            .single()
            .execute()
        )
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Export not found.") from exc

    if not export_resp.data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Export not found.")

    export = export_resp.data

    # Verify the caller can access this event's exports
    await verify_event_access(export["event_id"], current_user, supabase)

    # Generate a signed URL (3600 seconds = 1 hour)
    expiry_seconds = 3600
    try:
        signed = supabase.storage.from_(config.SUPABASE_STORAGE_BUCKET).create_signed_url(
            path=export["storage_path"],
            expires_in=expiry_seconds,
        )
        signed_url: str = signed["signedURL"]
    except Exception as exc:
        logger.error("Failed to create signed URL for export %s: %s", export_id, exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to generate download URL.",
        ) from exc

    expires_at = datetime.now(timezone.utc) + timedelta(seconds=expiry_seconds)

    return ExportDownloadResponse(
        export_id=uuid.UUID(export_id),
        signed_url=signed_url,
        expires_at=expires_at,
        filename=export["filename"],
    )
