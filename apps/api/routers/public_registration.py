"""
routers/public_registration.py — Public, unauthenticated event registration form.

Routes:
  GET  /api/public/register/{token}   Event name + open/closed status
  POST /api/public/register/{token}   Submit a registration

No auth: the token in the URL (events.registration_token, an opaque UUID
distinct from the event id) is the only gate. Degrades safely — until
migration 006 is applied, `registration_token` doesn't exist and every
request here 404s; nothing else in the app is affected.

A submission becomes a normal ``source_records`` row (source_type
'registration') under a single per-event "virtual" uploaded_files row, then
triggers a background consolidation run — reusing the existing
import/matching/dedup pipeline entirely rather than a parallel
implementation, exactly like a real uploaded file would.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from supabase import Client

from dependencies import get_supabase_client, is_consolidation_running
from models.schemas import PublicRegistrationInfo, PublicRegistrationSubmit
from services import consolidation_service

logger = logging.getLogger(__name__)

router = APIRouter()

_FORM_FILENAME = "Formulaire d'inscription en ligne"
# Same-email resubmits within this window beyond this count are refused —
# not a real WAF, but stops the obvious double-click / scripted-repeat case
# without needing external rate-limiting infra (no Redis in this stack).
_THROTTLE_WINDOW = timedelta(hours=1)
_THROTTLE_MAX_PER_EMAIL = 3


def _find_event_by_token(supabase: Client, token: str) -> dict[str, Any] | None:
    try:
        resp = (
            supabase.table("events")
            .select("id, name, project_id, registration_open")
            .eq("registration_token", token)
            .single()
            .execute()
        )
    except Exception:
        return None
    return resp.data


def _system_actor(supabase: Client, project_id: str) -> str | None:
    """The project owner stands in as the 'actor' for records a public form
    creates on nobody's behalf — avoids adding a dedicated service user."""
    try:
        resp = supabase.table("projects").select("created_by").eq("id", project_id).single().execute()
        return resp.data["created_by"] if resp.data else None
    except Exception as exc:
        logger.error("Could not resolve system actor for project %s: %s", project_id, exc)
        return None


def _get_or_create_form_file(supabase: Client, event_id: str, imported_by: str | None) -> str:
    existing = (
        supabase.table("uploaded_files")
        .select("id")
        .eq("event_id", event_id)
        .eq("source_type", "registration")
        .eq("original_filename", _FORM_FILENAME)
        .execute()
    )
    if existing.data:
        return existing.data[0]["id"]
    result = (
        supabase.table("uploaded_files")
        .insert({
            "event_id": event_id,
            "original_filename": _FORM_FILENAME,
            "storage_path": f"public-form/{event_id}",
            "source_type": "registration",
            "import_status": "processed",
            "imported_by": imported_by,
            "column_mapping": {},
        })
        .execute()
    )
    return result.data[0]["id"]


@router.get(
    "/public/register/{token}",
    response_model=PublicRegistrationInfo,
    summary="Get event info for the public registration form",
)
async def get_registration_info(
    token: str,
    supabase: Client = Depends(get_supabase_client),
) -> PublicRegistrationInfo:
    event = _find_event_by_token(supabase, token)
    if not event:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Formulaire introuvable.")
    return PublicRegistrationInfo(
        event_id=event["id"],
        event_name=event["name"],
        is_open=bool(event.get("registration_open", True)),
    )


@router.post(
    "/public/register/{token}",
    status_code=status.HTTP_201_CREATED,
    summary="Submit a public registration for an event",
)
async def submit_registration(
    token: str,
    body: PublicRegistrationSubmit,
    background_tasks: BackgroundTasks,
    supabase: Client = Depends(get_supabase_client),
) -> dict[str, str]:
    event = _find_event_by_token(supabase, token)
    if not event:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Formulaire introuvable.")
    if not event.get("registration_open", True):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Les inscriptions sont fermées pour cet événement.")

    event_id = event["id"]

    # Honeypot: a bot fills every field it finds, including this one, hidden
    # from real visitors by CSS. Report success without touching the
    # database so scripted retries don't learn anything from the response.
    if body.website.strip():
        logger.warning("Public registration honeypot triggered for event %s", event_id)
        return {"status": "ok", "message": "Inscription bien reçue. Merci !"}

    system_user_id = _system_actor(supabase, event["project_id"])
    if not system_user_id:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Impossible d'enregistrer l'inscription pour le moment. Réessayez plus tard.",
        )

    try:
        file_id = _get_or_create_form_file(supabase, event_id, system_user_id)
    except Exception as exc:
        logger.error("Failed to get/create public-form file for event %s: %s", event_id, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Impossible d'enregistrer l'inscription pour le moment. Réessayez plus tard.",
        ) from exc

    # Throttle by email within this event's form submissions only.
    since = (datetime.now(timezone.utc) - _THROTTLE_WINDOW).isoformat()
    try:
        recent = (
            supabase.table("source_records")
            .select("raw_data")
            .eq("file_id", file_id)
            .gte("created_at", since)
            .execute()
        )
        recent_count = sum(
            1 for r in (recent.data or [])
            if str((r.get("raw_data") or {}).get("email", "")).strip().lower() == body.email
        )
    except Exception as exc:
        logger.warning("Throttle check failed for event %s, allowing submission: %s", event_id, exc)
        recent_count = 0
    if recent_count >= _THROTTLE_MAX_PER_EMAIL:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Trop de tentatives avec cette adresse email. Réessayez plus tard.",
        )

    raw = body.model_dump(mode="json", exclude={"consent", "website"})
    normalized = {k: v for k, v in raw.items() if v not in (None, "")}

    try:
        count_resp = (
            supabase.table("source_records")
            .select("id", count="exact")
            .eq("file_id", file_id)
            .execute()
        )
        row_index = count_resp.count or 0
        supabase.table("source_records").insert({
            "file_id": file_id,
            "event_id": event_id,
            "row_index": row_index,
            "raw_data": raw,
            "normalized_data": normalized,
        }).execute()
    except Exception as exc:
        logger.error("Failed to insert public registration for event %s: %s", event_id, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Échec de l'enregistrement. Réessayez.",
        ) from exc

    # Merge the new registration into the master list promptly by reusing the
    # existing consolidation pipeline — same matching/dedup/exception logic
    # as any file import, no parallel code path. If a run is already in
    # flight, skip triggering another one (the pipeline wipes and rebuilds
    # from its first step, so two concurrent runs would stomp on each
    # other) — this submission is picked up by the NEXT consolidation,
    # whether that's the next registration or a manual run.
    if not is_consolidation_running(supabase, event_id):
        run_id = str(uuid.uuid4())
        try:
            supabase.table("consolidation_runs").insert({
                "id": run_id,
                "event_id": event_id,
                "triggered_by": system_user_id,
                "status": "running",
            }).execute()
            background_tasks.add_task(
                consolidation_service.run_consolidation,
                event_id=event_id,
                run_id=run_id,
                user_id=system_user_id,
                supabase=supabase,
            )
        except Exception as exc:
            logger.warning("Failed to auto-trigger consolidation after public registration for event %s: %s", event_id, exc)

    return {"status": "ok", "message": "Inscription bien reçue. Merci !"}
