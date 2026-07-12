"""
routers/files.py — File upload, preview, and column mapping endpoints.

Routes:
  POST  /api/files/upload                  Upload a new source file
  GET   /api/files/{file_id}/preview       Preview columns and sample rows
  POST  /api/files/{file_id}/map-columns   Save column mapping (requires human confirmation)
  GET   /api/events/{event_id}/files       List all files for an event
"""

from __future__ import annotations

import io
import logging
import os
import uuid
from typing import Any

import pandas as pd
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from supabase import Client

import config
from dependencies import get_current_user, get_supabase_client, verify_event_access
from models.schemas import (
    ColumnMappingRequest,
    ColumnMappingResponse,
    FileListItem,
    FilePreviewResponse,
    FileUploadResponse,
    ColumnMappingSuggestion,
    MessageResponse,
)
from services.mapping_service import suggest_mapping, CANONICAL_FIELDS

logger = logging.getLogger(__name__)

router = APIRouter()

ALLOWED_CONTENT_TYPES = {
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/vnd.ms-excel",
    "text/csv",
    "application/csv",
}


def _parse_file_to_dataframe(content: bytes, filename: str) -> pd.DataFrame:
    """
    Parse raw file bytes into a Pandas DataFrame.

    Supports .xlsx, .xls, and .csv files. Raises HTTPException on parse error.

    Parameters
    ----------
    content: Raw file bytes.
    filename: Original filename (used to determine extension).
    """
    ext = os.path.splitext(filename)[1].lower()
    try:
        if ext in (".xlsx", ".xls"):
            df = pd.read_excel(io.BytesIO(content), dtype=str)
        elif ext == ".csv":
            # Try UTF-8 first, fall back to latin-1 for Western European files
            try:
                df = pd.read_csv(io.BytesIO(content), dtype=str, encoding="utf-8")
            except UnicodeDecodeError:
                df = pd.read_csv(io.BytesIO(content), dtype=str, encoding="latin-1")
        else:
            raise HTTPException(
                status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                detail=config.ALLOWED_EXTENSIONS.__str__() + " files only.",
            )
    except HTTPException:
        raise
    except Exception as exc:
        logger.warning("Could not parse file %s: %s", filename, exc)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Could not parse file: {exc}",
        ) from exc

    # Replace NaN with None for clean JSON serialisation
    df = df.where(pd.notnull(df), None)
    return df


def _df_sample(df: pd.DataFrame, n: int) -> list[dict[str, Any]]:
    """Return first ``n`` rows as list-of-dicts, safe for JSON."""
    return df.head(n).to_dict(orient="records")


# ---------------------------------------------------------------------------
# POST /api/files/upload
# ---------------------------------------------------------------------------

@router.post(
    "/files/upload",
    response_model=FileUploadResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Upload a source file for an event",
)
async def upload_file(
    event_id: str = Form(..., description="UUID of the event this file belongs to."),
    source_type: str = Form(..., description="Source type: registration | fcm | email | hotel | transfer | activity | other"),
    file: UploadFile = File(..., description="The file to upload (.xlsx, .xls, .csv). Max 50 MB."),
    current_user: dict[str, Any] = Depends(get_current_user),
    supabase: Client = Depends(get_supabase_client),
) -> FileUploadResponse:
    """
    Upload a raw source file for an event.

    Validation:
    - Extension must be .xlsx, .xls, or .csv
    - File size must not exceed 50 MB
    - event_id must belong to the caller's organisation

    The file is:
    1. Parsed with Pandas to extract columns and sample rows
    2. Uploaded to Supabase Storage at ``{event_id}/{file_id}/{filename}``
    3. Registered in the ``uploaded_files`` table with status ``pending``

    Returns column names and the first 5 rows so the frontend can
    immediately show the column-mapping UI.
    """
    # --- Validate extension ---
    filename: str = file.filename or "upload"
    ext = os.path.splitext(filename)[1].lower()
    if ext not in config.ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"Unsupported file format '{ext}'. Accepted: {sorted(config.ALLOWED_EXTENSIONS)}",
        )

    # --- Read content + size check ---
    content: bytes = await file.read()
    if len(content) > config.MAX_UPLOAD_SIZE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="File exceeds the maximum allowed size of 50 MB.",
        )

    # --- Verify event access ---
    await verify_event_access(event_id, current_user, supabase)

    # --- Parse with Pandas ---
    df = _parse_file_to_dataframe(content, filename)
    columns: list[str] = df.columns.tolist()
    row_count: int = len(df)
    sample_rows = _df_sample(df, 5)

    # --- Upload to Supabase Storage ---
    file_id = str(uuid.uuid4())
    storage_path = f"{event_id}/{file_id}/{filename}"

    try:
        supabase.storage.from_(config.SUPABASE_STORAGE_BUCKET).upload(
            path=storage_path,
            file=content,
            file_options={"content-type": file.content_type or "application/octet-stream"},
        )
    except Exception as exc:
        logger.error("Supabase Storage upload failed for %s: %s", storage_path, exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="File storage upload failed. Please try again.",
        ) from exc

    # --- Register in uploaded_files table ---
    record = {
        "id": file_id,
        "event_id": event_id,
        "original_filename": filename,
        "storage_path": storage_path,
        "source_type": source_type,
        "row_count": row_count,
        "column_count": len(columns),
        "import_status": "pending",
        "imported_by": current_user["id"],
    }
    try:
        supabase.table("uploaded_files").insert(record).execute()
    except Exception as exc:
        logger.error("Failed to register uploaded_file record: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="File uploaded but metadata registration failed.",
        ) from exc

    logger.info(
        "File uploaded: file_id=%s event_id=%s rows=%d cols=%d user=%s",
        file_id, event_id, row_count, len(columns), current_user["id"],
    )

    raw_suggestions = suggest_mapping(columns, sample_rows)
    mapping_suggestions = {
        col: ColumnMappingSuggestion(**sug) for col, sug in raw_suggestions.items()
    }
    canonical_fields_list = sorted(list(CANONICAL_FIELDS))

    return FileUploadResponse(
        file_id=uuid.UUID(file_id),
        original_filename=filename,
        source_type=source_type,
        row_count=row_count,
        column_count=len(columns),
        columns=columns,
        sample_rows=sample_rows,
        import_status="pending",
        mapping_suggestions=mapping_suggestions,
        canonical_fields=canonical_fields_list,
    )


# ---------------------------------------------------------------------------
# GET /api/files/{file_id}/preview
# ---------------------------------------------------------------------------

@router.get(
    "/files/{file_id}/preview",
    response_model=FilePreviewResponse,
    summary="Preview columns and sample rows of an uploaded file",
)
async def preview_file(
    file_id: str,
    current_user: dict[str, Any] = Depends(get_current_user),
    supabase: Client = Depends(get_supabase_client),
) -> FilePreviewResponse:
    """
    Return the column list and first 10 rows of an uploaded file.

    Fetches the file from Supabase Storage, parses it in-memory.
    Does NOT require the file to be in ``mapped`` status.
    """
    # Load the file metadata
    meta_resp = (
        supabase.table("uploaded_files")
        .select("*")
        .eq("id", file_id)
        .single()
        .execute()
    )
    if not meta_resp.data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found.")

    meta = meta_resp.data
    await verify_event_access(meta["event_id"], current_user, supabase)

    # Download from Supabase Storage
    try:
        raw: bytes = supabase.storage.from_(config.SUPABASE_STORAGE_BUCKET).download(
            meta["storage_path"]
        )
    except Exception as exc:
        logger.error("Storage download failed for %s: %s", meta["storage_path"], exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Could not retrieve file from storage.",
        ) from exc

    df = _parse_file_to_dataframe(raw, meta["original_filename"])
    columns = df.columns.tolist()
    sample_rows = _df_sample(df, 10)

    raw_suggestions = suggest_mapping(columns, sample_rows)
    mapping_suggestions = {
        col: ColumnMappingSuggestion(**sug) for col, sug in raw_suggestions.items()
    }
    canonical_fields_list = sorted(list(CANONICAL_FIELDS))

    return FilePreviewResponse(
        file_id=uuid.UUID(file_id),
        columns=columns,
        row_count=len(df),
        sample_rows=sample_rows,
        mapping_suggestions=mapping_suggestions,
        canonical_fields=canonical_fields_list,
    )


# ---------------------------------------------------------------------------
# POST /api/files/{file_id}/map-columns
# ---------------------------------------------------------------------------

@router.post(
    "/files/{file_id}/map-columns",
    response_model=ColumnMappingResponse,
    summary="Save column mapping for a file (requires human confirmation)",
)
async def map_columns(
    file_id: str,
    body: ColumnMappingRequest,
    current_user: dict[str, Any] = Depends(get_current_user),
    supabase: Client = Depends(get_supabase_client),
) -> ColumnMappingResponse:
    """
    Save the column-to-field mapping for an uploaded file.

    **``confirmed`` must be ``true``** — this is a hard gate that enforces
    human review of the mapping before it is persisted. The consolidation
    engine will refuse to process files without a confirmed mapping.

    After a successful call, the file's ``import_status`` transitions from
    ``pending`` → ``mapped``.
    """
    # The Pydantic validator already ensures confirmed=True, but double-check
    if not body.confirmed:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Column mapping must be confirmed by a human reviewer (confirmed=true).",
        )

    # Load file metadata and check event access
    meta_resp = (
        supabase.table("uploaded_files")
        .select("id, event_id, import_status")
        .eq("id", file_id)
        .single()
        .execute()
    )
    if not meta_resp.data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found.")

    meta = meta_resp.data
    await verify_event_access(meta["event_id"], current_user, supabase)

    if meta["import_status"] == "processed":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This file has already been processed. Create a new upload to re-map.",
        )

    # Persist mapping and advance status
    try:
        supabase.table("uploaded_files").update(
            {"column_mapping": body.mapping, "import_status": "mapped"}
        ).eq("id", file_id).execute()
    except Exception as exc:
        logger.error("Failed to save column mapping for file %s: %s", file_id, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to save column mapping.",
        ) from exc

    logger.info(
        "Column mapping saved: file_id=%s user=%s fields=%s",
        file_id, current_user["id"], list(body.mapping.values()),
    )

    return ColumnMappingResponse(
        file_id=uuid.UUID(file_id),
        import_status="mapped",
        mapping=body.mapping,
        message="Column mapping saved. File is ready for consolidation.",
    )


# ---------------------------------------------------------------------------
# GET /api/events/{event_id}/files
# ---------------------------------------------------------------------------

@router.get(
    "/events/{event_id}/files",
    response_model=list[FileListItem],
    summary="List all uploaded files for an event",
)
async def list_event_files(
    event_id: str,
    current_user: dict[str, Any] = Depends(get_current_user),
    supabase: Client = Depends(get_supabase_client),
) -> list[FileListItem]:
    """
    Return all files uploaded for a given event, ordered by upload time descending.

    Includes import status and error information so the frontend can show
    processing state for each file.
    """
    await verify_event_access(event_id, current_user, supabase)

    try:
        result = (
            supabase.table("uploaded_files")
            .select(
                "id, original_filename, source_type, row_count, column_count, "
                "import_status, imported_at, error_message"
            )
            .eq("event_id", event_id)
            .order("imported_at", desc=True)
            .execute()
        )
    except Exception as exc:
        logger.error("Failed to list files for event %s: %s", event_id, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve file list.",
        ) from exc

    return [FileListItem(**row) for row in result.data]


# ---------------------------------------------------------------------------
# DELETE /api/files/{file_id}
# ---------------------------------------------------------------------------

@router.delete(
    "/files/{file_id}",
    response_model=MessageResponse,
    summary="Delete an uploaded file",
)
async def delete_file(
    file_id: str,
    current_user: dict[str, Any] = Depends(get_current_user),
    supabase: Client = Depends(get_supabase_client),
) -> MessageResponse:
    """
    Delete an uploaded file from both database and storage.
    Verifies event access first.
    """
    # Load file metadata
    meta_resp = (
        supabase.table("uploaded_files")
        .select("id, event_id, storage_path")
        .eq("id", file_id)
        .single()
        .execute()
    )
    if not meta_resp.data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found.")

    meta = meta_resp.data
    await verify_event_access(meta["event_id"], current_user, supabase)

    # 1. Delete from Supabase Storage
    try:
        supabase.storage.from_(config.SUPABASE_STORAGE_BUCKET).remove(
            [meta["storage_path"]]
        )
    except Exception as exc:
        logger.warning("Storage deletion failed/skipped for path %s: %s", meta["storage_path"], exc)

    # 2. Delete from database (exceptions, source_records, uploaded_files)
    try:
        supabase.table("exceptions").delete().eq("file_id", file_id).execute()
        supabase.table("source_records").delete().eq("file_id", file_id).execute()
        supabase.table("uploaded_files").delete().eq("id", file_id).execute()
    except Exception as exc:
        logger.error("Database deletion failed for file %s: %s", file_id, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete file records.",
        ) from exc

    logger.info("File deleted: file_id=%s user=%s", file_id, current_user["id"])
    return MessageResponse(message="File deleted successfully.")
