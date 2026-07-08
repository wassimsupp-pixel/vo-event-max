"""
services/mapping_service.py — Column mapping and data normalisation.

Responsibilities:
  - Apply a saved column mapping to raw row data
  - Normalise field values (trim whitespace, parse dates, lower-case emails)
  - Parse and insert source_records rows from a mapped file
"""

from __future__ import annotations

import logging
import re
import uuid
from datetime import date
from typing import Any, Optional

from supabase import Client

logger = logging.getLogger(__name__)

# Canonical target field names that the rest of the system expects
CANONICAL_FIELDS = {
    "first_name", "last_name", "email", "company", "phone",
    "nationality", "dietary_requirements",
    "departure_date", "return_date", "flight_number",
    "hotel_name", "check_in_date", "check_out_date",
    "transfer_type", "activity_name",
}

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_DATE_FORMATS = ["%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d", "%m/%d/%Y", "%d.%m.%Y"]


def apply_mapping(raw_row: dict[str, Any], mapping: dict[str, str]) -> dict[str, Any]:
    """
    Apply a column mapping to a single raw data row.

    Parameters
    ----------
    raw_row:
        Dict with source column names as keys.
    mapping:
        Dict of ``{source_column: target_field}``.

    Returns
    -------
    Dict with canonical target field names as keys. Unmapped columns are dropped.
    """
    result: dict[str, Any] = {}
    for source_col, target_field in mapping.items():
        if target_field in CANONICAL_FIELDS and source_col in raw_row:
            result[target_field] = raw_row[source_col]
    return result


def normalise_fields(mapped_row: dict[str, Any]) -> dict[str, Any]:
    """
    Normalise field values in a mapped row.

    Normalisation steps:
    - Strip leading/trailing whitespace from all string values
    - Lower-case email addresses
    - Attempt to parse date strings into ISO-8601 (YYYY-MM-DD) format
    - Replace empty strings with ``None``

    Parameters
    ----------
    mapped_row:
        Dict with canonical target field names (output of ``apply_mapping``).

    Returns
    -------
    Dict with normalised values. Invalid values are preserved as-is (exception
    detection in ``exception_service`` will flag them).
    """
    normalised: dict[str, Any] = {}
    for field, value in mapped_row.items():
        if isinstance(value, str):
            value = value.strip()
            if value == "":
                value = None
            elif field == "email":
                value = value.lower()
            elif field.endswith("_date"):
                value = _parse_date(value) or value  # keep original if parse fails
        normalised[field] = value
    return normalised


def _parse_date(raw: str) -> Optional[str]:
    """
    Attempt to parse a date string using several common formats.

    Returns the date in ISO-8601 (``YYYY-MM-DD``) format on success, or
    ``None`` if no format matched.
    """
    from datetime import datetime as dt
    for fmt in _DATE_FORMATS:
        try:
            return dt.strptime(raw, fmt).date().isoformat()
        except ValueError:
            continue
    return None


def parse_and_insert_source_records(
    supabase: Client,
    file_id: str,
    event_id: str,
    df_rows: list[dict[str, Any]],
    mapping: dict[str, str],
) -> list[str]:
    """
    Parse raw DataFrame rows, apply mapping + normalisation, and bulk-insert
    into the ``source_records`` table.

    Parameters
    ----------
    supabase:
        Supabase client.
    file_id:
        UUID of the uploaded_file this data originates from.
    event_id:
        UUID of the event.
    df_rows:
        List of raw row dicts from the DataFrame (``df.to_dict(orient="records")``).
    mapping:
        Column mapping from the uploaded_file record.

    Returns
    -------
    List of inserted source_record UUIDs.
    """
    records_to_insert: list[dict[str, Any]] = []

    for i, raw_row in enumerate(df_rows):
        mapped = apply_mapping(raw_row, mapping)
        normalised = normalise_fields(mapped)
        record_id = str(uuid.uuid4())
        records_to_insert.append(
            {
                "id": record_id,
                "file_id": file_id,
                "event_id": event_id,
                "row_index": i,
                "raw_data": raw_row,
                "normalized_data": normalised,
            }
        )

    # Batch insert in chunks to avoid Supabase request size limits
    chunk_size = 200
    inserted_ids: list[str] = []
    for chunk_start in range(0, len(records_to_insert), chunk_size):
        chunk = records_to_insert[chunk_start : chunk_start + chunk_size]
        try:
            result = supabase.table("source_records").insert(chunk).execute()
            inserted_ids.extend(row["id"] for row in result.data)
        except Exception as exc:
            logger.error(
                "Failed to insert source_records chunk [%d:%d] for file %s: %s",
                chunk_start, chunk_start + chunk_size, file_id, exc,
            )
            raise

    logger.info(
        "Inserted %d source_records for file_id=%s event_id=%s",
        len(inserted_ids), file_id, event_id,
    )
    return inserted_ids
