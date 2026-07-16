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


def _looks_numeric(v: Any) -> bool:
    """True if the value is (or looks like) a plain number."""
    if v is None:
        return False
    s = str(v).strip()
    if s == "":
        return False
    try:
        float(s.replace(",", ".").replace(" ", ""))
        return True
    except ValueError:
        return False


def _detect_header_row(df0: pd.DataFrame, max_scan: int = 8) -> int:
    """
    Find the row that best looks like the header among the first ``max_scan``
    rows of a header-less DataFrame. Handles files whose real column names sit
    on the 2nd/3rd row (section banners above them, e.g. the LivaNova masterfile).

    Heuristic: the header is the row with the most distinct, non-numeric,
    non-empty text cells. Ties prefer the earliest row.
    """
    best_idx, best_score = 0, -1.0
    limit = min(max_scan, len(df0))
    for i in range(limit):
        cells = df0.iloc[i].tolist()
        labels = {
            str(c).strip().lower()
            for c in cells
            if c is not None and str(c).strip() != "" and not _looks_numeric(c)
        }
        score = float(len(labels))
        if score > best_score:
            best_score, best_idx = score, i
    return best_idx


def _promote_header(df0: pd.DataFrame, header_idx: int) -> pd.DataFrame:
    """Use row ``header_idx`` as the column names; data is everything below it.
    Blank/duplicate column names are cleaned so mappings stay stable."""
    header = df0.iloc[header_idx].tolist()
    cols: list[str] = []
    seen: dict[str, int] = {}
    for j, c in enumerate(header):
        name = str(c).strip() if (c is not None and str(c).strip() != "") else f"Colonne {j + 1}"
        if name in seen:
            seen[name] += 1
            name = f"{name} ({seen[name]})"
        else:
            seen[name] = 0
        cols.append(name)
    data = df0.iloc[header_idx + 1:].copy()
    data.columns = cols
    return data.reset_index(drop=True)


def _read_raw_no_header(raw: bytes, ext: str) -> pd.DataFrame:
    """Read the file with NO header row (every row is data), for header detection."""
    if ext in (".xlsx", ".xls"):
        return pd.read_excel(io.BytesIO(raw), dtype=str, header=None)
    # CSV: auto-detect delimiter, encoding fallback
    try:
        return pd.read_csv(io.BytesIO(raw), dtype=str, header=None, sep=None, engine="python", encoding="utf-8")
    except UnicodeDecodeError:
        return pd.read_csv(io.BytesIO(raw), dtype=str, header=None, sep=None, engine="python", encoding="latin-1")


def read_tabular(raw: bytes, filename: str) -> pd.DataFrame:
    """
    Parse raw .xlsx/.xls/.csv bytes into a DataFrame, auto-detecting the header
    row (supports files whose real headers are not on the first line). Shared by
    the upload endpoint and the consolidation pipeline so column names — and thus
    the saved mapping — stay identical across both.
    """
    ext = os.path.splitext(filename)[1].lower()
    if ext not in (".xlsx", ".xls", ".csv"):
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"Unsupported file extension: {ext}",
        )
    df0 = _read_raw_no_header(raw, ext)
    if df0.empty:
        return df0
    header_idx = _detect_header_row(df0)
    df = _promote_header(df0, header_idx)
    df = df.where(pd.notnull(df), None)
    return df


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

    try:
        return read_tabular(raw, original_filename)
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Failed to parse file %s: %s", original_filename, exc)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Could not parse file '{original_filename}': {exc}",
        ) from exc


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
