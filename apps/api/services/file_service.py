"""
services/file_service.py — File download and DataFrame loading helpers.

Provides utilities to retrieve files from Supabase Storage and parse them into
Pandas DataFrames for use by the consolidation pipeline.
"""

from __future__ import annotations

import io
import logging
import os
from typing import Any

import pandas as pd
from fastapi import HTTPException, status
from supabase import Client

import config

logger = logging.getLogger(__name__)


def download_and_parse_file(
    supabase: Client,
    storage_path: str,
    original_filename: str,
) -> pd.DataFrame:
    """
    Download a file from Supabase Storage and parse it into a Pandas DataFrame.

    Parameters
    ----------
    supabase:
        Supabase client (service-role).
    storage_path:
        Path inside the Supabase Storage bucket.
    original_filename:
        Original filename (used to determine extension and encoding fallback).

    Returns
    -------
    DataFrame with raw string values. NaN replaced with ``None``.

    Raises
    ------
    HTTPException 502
        If the storage download fails.
    HTTPException 422
        If the file cannot be parsed.
    """
    try:
        raw: bytes = supabase.storage.from_(config.SUPABASE_STORAGE_BUCKET).download(
            storage_path
        )
    except Exception as exc:
        logger.error("Storage download failed for %s: %s", storage_path, exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Failed to retrieve file from storage: {storage_path}",
        ) from exc

    ext = os.path.splitext(original_filename)[1].lower()
    try:
        if ext in (".xlsx", ".xls"):
            df = pd.read_excel(io.BytesIO(raw), dtype=str)
        elif ext == ".csv":
            # sep=None + python engine auto-detects the delimiter (',' or ';').
            try:
                df = pd.read_csv(io.BytesIO(raw), dtype=str, encoding="utf-8", sep=None, engine="python")
            except UnicodeDecodeError:
                df = pd.read_csv(io.BytesIO(raw), dtype=str, encoding="latin-1", sep=None, engine="python")
        else:
            raise HTTPException(
                status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                detail=f"Unsupported file extension: {ext}",
            )
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Failed to parse file %s: %s", original_filename, exc)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Could not parse file '{original_filename}': {exc}",
        ) from exc

    df = df.where(pd.notnull(df), None)
    return df


def get_mapped_files_for_event(supabase: Client, event_id: str) -> list[dict[str, Any]]:
    """
    Load all ``mapped`` (and ``processed``) uploaded_file records for an event.

    Returns
    -------
    List of uploaded_file row dicts, ordered by upload time ascending so that
    registration files (typically uploaded first) are processed before FCM files.
    """
    try:
        result = (
            supabase.table("uploaded_files")
            .select("id, event_id, original_filename, storage_path, source_type, column_mapping, import_status")
            .eq("event_id", event_id)
            .in_("import_status", ["mapped", "processed"])
            .order("imported_at")
            .execute()
        )
    except Exception as exc:
        logger.error("Failed to load mapped files for event %s: %s", event_id, exc)
        return []

    return result.data or []
