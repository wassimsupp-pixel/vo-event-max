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


import re as _re

_EMAIL_P = _re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_PHONE_P = _re.compile(r"^[+(]?\d[\d\s().\-]{6,}$")
_FLIGHT_P = _re.compile(r"^[A-Z]{2,3}\s*\d{1,4}[A-Z]?$", _re.IGNORECASE)
_IATA_P = _re.compile(r"^[A-Z]{3}$")
_PNR_P = _re.compile(r"^(?=.*[A-Z])(?=.*\d)[A-Z0-9]{5,7}$")
_TIME_P = _re.compile(r"^\d{1,2}[:hH]\d{2}")
_DATE_P = _re.compile(r"^\d{1,4}[/\-.]\d{1,2}[/\-.]\d{1,4}$")


def _is_blank(v: Any) -> bool:
    """True for empty / NaN / 'nan' / 'none' cells (pandas str-casts NaN to 'nan')."""
    if v is None:
        return True
    try:
        if pd.isna(v):
            return True
    except (TypeError, ValueError):
        pass
    return str(v).strip().lower() in ("", "nan", "none", "nat")


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


def _is_label_like(v: Any) -> bool:
    """True if a cell looks like a HEADER label (short text) rather than data
    (email, phone, date, number, long free text)."""
    if v is None:
        return False
    s = str(v).strip()
    if s == "" or len(s) > 60:
        return False
    if "@" in s or _looks_numeric(s) or _DATE_P.match(s) or _TIME_P.match(s):
        return False
    digits = sum(c.isdigit() for c in s)
    if digits >= max(5, len(s) * 0.5):  # phone-ish / code-ish
        return False
    return True


def _detect_header_row(df0: pd.DataFrame, max_scan: int = 8) -> int:
    """
    Find the row that best looks like the header among the first ``max_scan``
    rows of a header-less DataFrame. Handles files whose real column names sit
    on the 2nd/3rd row (section banners above them, e.g. the LivaNova masterfile).

    Heuristic: the header is the row with the most *label-like* cells (short text,
    not emails/dates/phones/numbers). Ties prefer the earliest row — so a normal
    file keeps row 0, and a data row full of values never beats a real header.
    """
    best_idx, best_score = 0, -1.0
    limit = min(max_scan, len(df0))
    for i in range(limit):
        cells = df0.iloc[i].tolist()
        score = float(sum(1 for c in cells if _is_label_like(c)))
        if score > best_score:
            best_score, best_idx = score, i
    return best_idx


def _infer_column_name(values: list[Any]) -> str | None:
    """Deduce a human column label from the column's DATA when the header is
    blank — e.g. a column full of emails becomes 'Email'. Returns None if no
    confident pattern is found."""
    vals = [str(v).strip() for v in values if not _is_blank(v)]
    if len(vals) < 2:
        return None
    n = len(vals)

    def frac(pred) -> float:
        return sum(1 for v in vals if pred(v)) / n

    if frac(lambda v: _EMAIL_P.match(v)) > 0.6:
        return "Email"
    if frac(lambda v: _DATE_P.match(v)) > 0.6:
        return "Date"
    if frac(lambda v: _TIME_P.match(v)) > 0.6:
        return "Heure"
    if frac(lambda v: _FLIGHT_P.match(v)) > 0.6:
        return "N° de vol"
    if frac(lambda v: _PHONE_P.match(v)) > 0.6:
        return "Téléphone"
    if frac(lambda v: v.isupper() and _IATA_P.match(v)) > 0.6:
        return "Aéroport"
    if frac(lambda v: _PNR_P.match(v)) > 0.6:
        return "Code PNR"
    # Names: mostly 2+ alphabetic words
    if frac(lambda v: len(v.split()) >= 2 and all(p.replace("-", "").replace("'", "").isalpha() for p in v.split())) > 0.6:
        return "Nom complet"
    return None


def _promote_header(df0: pd.DataFrame, header_idx: int) -> pd.DataFrame:
    """Use row ``header_idx`` as the column names; data is everything below it.
    Blank column names are inferred from the column's content; duplicates are
    de-duplicated so mappings stay stable."""
    header = df0.iloc[header_idx].tolist()
    body = df0.iloc[header_idx + 1:]
    cols: list[str] = []
    seen: dict[str, int] = {}
    for j, c in enumerate(header):
        if not _is_blank(c):
            name = str(c).strip()
        else:
            # No header cell → analyse the column's data to find a fitting name.
            col_values = body.iloc[:, j].tolist() if j < body.shape[1] else []
            name = _infer_column_name(col_values) or f"Colonne {j + 1}"
        if name in seen:
            seen[name] += 1
            name = f"{name} ({seen[name]})"
        else:
            seen[name] = 0
        cols.append(name)
    data = body.copy()
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


def read_all_sheets(raw: bytes, filename: str) -> dict[str, "pd.DataFrame"]:
    """
    Parse EVERY sheet of an Excel file into a header-detected DataFrame
    (``{sheet_name: df}``). Used for combined "master files" that spread info
    across sheets (participants / hotel / transfers…). CSV → a single sheet.
    """
    ext = os.path.splitext(filename)[1].lower()
    if ext == ".csv":
        return {"CSV": read_tabular(raw, filename)}
    if ext not in (".xlsx", ".xls"):
        raise HTTPException(status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail=f"Unsupported file extension: {ext}")
    raw_sheets = pd.read_excel(io.BytesIO(raw), dtype=str, header=None, sheet_name=None)
    out: dict[str, pd.DataFrame] = {}
    for name, df0 in raw_sheets.items():
        if df0 is None or df0.empty:
            continue
        try:
            df = _promote_header(df0, _detect_header_row(df0))
            df = df.where(pd.notnull(df), None)
            if len(df.columns) > 0 and len(df) > 0:
                out[str(name)] = df
        except Exception as exc:
            logger.warning("Sheet '%s' could not be parsed, skipping: %s", name, exc)
    return out


def _download_bytes(supabase: Client, storage_path: str) -> bytes:
    try:
        return supabase.storage.from_(config.SUPABASE_STORAGE_BUCKET).download(storage_path)
    except Exception as exc:
        logger.error("Storage download failed for %s: %s", storage_path, exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Failed to retrieve file from storage: {storage_path}",
        ) from exc


def download_all_sheets(supabase: Client, storage_path: str, original_filename: str) -> dict[str, "pd.DataFrame"]:
    """Download from Storage and parse every sheet (see ``read_all_sheets``)."""
    raw = _download_bytes(supabase, storage_path)
    try:
        return read_all_sheets(raw, original_filename)
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Failed to parse sheets of %s: %s", original_filename, exc)
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f"Could not parse file '{original_filename}': {exc}") from exc


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
