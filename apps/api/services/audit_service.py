"""
services/audit_service.py — Change log writer.

All mutations on participant records, exceptions, and files must call
``log_change`` BEFORE applying the actual database update. This provides a
non-repudiation audit trail for RGPD compliance and operational debugging.
"""

from __future__ import annotations

import logging
from typing import Optional

from supabase import Client

logger = logging.getLogger(__name__)


def log_change(
    supabase: Client,
    event_id: str,
    user_id: str,
    entity_type: str,
    entity_id: str,
    field_name: str,
    old_value: Optional[str],
    new_value: Optional[str],
    reason: Optional[str],
) -> None:
    """
    Write a single field-level change entry to the ``change_log`` table.

    This function MUST be called BEFORE the actual database update so that the
    audit record reflects the pre-change state even if the update subsequently
    fails.

    Parameters
    ----------
    supabase:
        Supabase client (service-role).
    event_id:
        UUID of the event this change belongs to.
    user_id:
        UUID of the authenticated user making the change.
    entity_type:
        Type of the changed entity. Canonical values:
        ``participant`` | ``exception`` | ``source_record`` | ``uploaded_file``.
    entity_id:
        UUID of the changed entity row.
    field_name:
        Name of the field that was changed. For nested changes (e.g. locked_fields),
        use dot notation: ``locked_fields.email``.
    old_value:
        String representation of the previous value (``None`` if not applicable).
    new_value:
        String representation of the new value (``None`` if clearing a field).
    reason:
        Short reason code or human-readable explanation.
        Canonical codes: ``manual_edit`` | ``import`` | ``re_import`` | ``lock`` | ``resolve_exception``.

    Raises
    ------
    Does NOT raise. Audit failures are logged as warnings but do not abort
    the caller's operation — data integrity of the primary record takes
    precedence over the audit record in edge failure cases.
    """
    record = {
        "event_id": event_id,
        "user_id": user_id,
        "entity_type": entity_type,
        "entity_id": entity_id,
        "field_name": field_name,
        "old_value": old_value,
        "new_value": new_value,
        "change_reason": reason,
    }
    try:
        supabase.table("change_log").insert(record).execute()
    except Exception as exc:
        # Audit failures should not surface as 500s to the user.
        logger.warning(
            "AUDIT LOG FAILURE — entity=%s/%s field=%s user=%s: %s",
            entity_type, entity_id, field_name, user_id, exc,
        )


def log_bulk_change(
    supabase: Client,
    event_id: str,
    user_id: str,
    entity_type: str,
    entity_id: str,
    changes: dict[str, tuple[Optional[str], Optional[str]]],
    reason: Optional[str],
) -> None:
    """
    Convenience wrapper to write multiple field changes for the same entity in one call.

    Parameters
    ----------
    changes:
        Dict of ``{field_name: (old_value, new_value)}``.

    All other parameters are the same as ``log_change``.
    """
    records = [
        {
            "event_id": event_id,
            "user_id": user_id,
            "entity_type": entity_type,
            "entity_id": entity_id,
            "field_name": field,
            "old_value": old,
            "new_value": new,
            "change_reason": reason,
        }
        for field, (old, new) in changes.items()
    ]
    if not records:
        return
    try:
        supabase.table("change_log").insert(records).execute()
    except Exception as exc:
        logger.warning(
            "AUDIT BULK LOG FAILURE — entity=%s/%s user=%s: %s",
            entity_type, entity_id, user_id, exc,
        )
