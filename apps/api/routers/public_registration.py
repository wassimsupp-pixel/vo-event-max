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
'registration') under a single per-event "virtual" uploaded_files row.
consolidation_service.run_consolidation has a matching branch that reads
these back directly (there's no real document in Storage to parse for this
"file"). A successful submit then fires a real OS thread (see
_trigger_background_consolidation below) that runs start_and_run_consolidation
so the new participant lands in the master list within seconds, without the
visitor's browser waiting on it — see that function's docstring for why a
plain FastAPI BackgroundTask isn't used here.
"""

from __future__ import annotations

import asyncio
import logging
import threading
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from supabase import Client

from dependencies import get_supabase_client
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


def _run_consolidation_in_thread(event_id: str, user_id: str) -> None:
    """Executed inside the dedicated thread started by
    _trigger_background_consolidation. Builds its own Supabase client (a
    request-scoped one shouldn't be assumed safe to reuse once the request
    that created it has returned) and its own asyncio event loop (threads
    don't have one by default) to run the same consolidation path a mapped
    Excel upload uses."""
    try:
        from dependencies import _build_supabase_client
        thread_supabase = _build_supabase_client()
        asyncio.run(consolidation_service.start_and_run_consolidation(event_id, user_id, thread_supabase))
    except Exception:
        logger.exception("Background consolidation thread failed for event %s", event_id)


def _trigger_background_consolidation(event_id: str, user_id: str) -> None:
    """Fire-and-forget on a real OS thread, deliberately NOT FastAPI's
    BackgroundTasks: a real submission measured ~58s end to end (2026-07-26)
    because BackgroundTasks awaits the consolidation coroutine on the same
    event loop that still has to flush this request's response, and
    run_consolidation makes many synchronous (blocking) Supabase calls on
    that loop. A plain thread runs fully independently, so the visitor sees
    "Merci !" immediately while the master list updates in the background.
    start_and_run_consolidation no-ops if a run is already fresh for this
    event, so concurrent submissions don't pile up overlapping runs."""
    threading.Thread(target=_run_consolidation_in_thread, args=(event_id, user_id), daemon=True).start()


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

    _trigger_background_consolidation(event_id, system_user_id)
    return {"status": "ok", "message": "Inscription bien reçue. Merci !"}
