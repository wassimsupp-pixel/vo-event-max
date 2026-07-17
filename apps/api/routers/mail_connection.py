# -*- coding: utf-8 -*-
"""
mail_connection.py
==================
Endpoints to connect a Gmail/Outlook mailbox (OAuth) to the Email Agent and
sync incoming messages into AI proposals.

Routes
------
- GET  /events/{event_id}/mail/status              → per-provider config/connection
- GET  /events/{event_id}/mail/authorize?provider= → returns the consent URL
- GET  /mail/oauth/callback?code=&state=           → OAuth redirect target (no auth)
- POST /events/{event_id}/mail/sync?provider=      → pull inbox → AI proposals
- POST /events/{event_id}/mail/disconnect?provider=→ forget stored tokens
"""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import RedirectResponse
from supabase import Client

import config
from dependencies import get_current_user, get_supabase_client, verify_event_access
from services import mail_connection_service as mail

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/events/{event_id}/mail/status")
async def mail_status(
    event_id: UUID,
    supabase: Client = Depends(get_supabase_client),
    current_user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    """Return which mail providers are configured and connected for this event."""
    await verify_event_access(str(event_id), current_user, supabase)
    return mail.get_status(event_id)


@router.get("/events/{event_id}/mail/authorize")
async def mail_authorize(
    event_id: UUID,
    provider: str = Query(..., description="gmail | outlook"),
    locale: str = Query("fr"),
    supabase: Client = Depends(get_supabase_client),
    current_user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, str]:
    """Return the OAuth consent URL the frontend should redirect the user to."""
    await verify_event_access(str(event_id), current_user, supabase)
    try:
        url = mail.build_authorization_url(provider, event_id, locale)
    except mail.MailConfigError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return {"authorization_url": url}


@router.get("/mail/oauth/callback")
async def mail_oauth_callback(
    code: str | None = Query(None),
    state: str | None = Query(None),
    error: str | None = Query(None),
) -> RedirectResponse:
    """
    OAuth redirect target. Exchanges the code for tokens, then bounces the user
    back to the Communications page with a success/error flag.

    This route is unauthenticated on purpose: the browser arrives here straight
    from the OAuth provider without the app's Bearer token. Safety comes from
    the signed ``state`` (see TODO in the service) and the short-lived code.
    """
    fallback = f"{config.WEB_APP_URL}/fr"
    if error or not code or not state:
        logger.warning("OAuth callback error=%s (code present=%s)", error, bool(code))
        return RedirectResponse(url=f"{fallback}?mail_error={error or 'missing_code'}")

    try:
        decoded = mail.decode_state(state)
        event_id = decoded["event_id"]
        provider = decoded["provider"]
        locale = decoded["locale"]
        mail.exchange_code(provider, code, event_id)
    except Exception as exc:
        logger.error("OAuth token exchange failed: %s", exc)
        return RedirectResponse(url=f"{fallback}?mail_error=exchange_failed")

    dest = (
        f"{config.WEB_APP_URL}/{locale}/events/{event_id}/communications"
        f"?mail_connected={provider}"
    )
    return RedirectResponse(url=dest)


@router.post("/events/{event_id}/mail/sync")
async def mail_sync(
    event_id: UUID,
    provider: str = Query(..., description="gmail | outlook"),
    supabase: Client = Depends(get_supabase_client),
    current_user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    """Pull the most recent inbox messages and turn them into AI proposals."""
    await verify_event_access(str(event_id, write=True), current_user, supabase)
    try:
        return await mail.sync_inbox(provider, event_id, supabase)
    except mail.MailConfigError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post("/events/{event_id}/mail/disconnect")
async def mail_disconnect(
    event_id: UUID,
    provider: str = Query(..., description="gmail | outlook"),
    supabase: Client = Depends(get_supabase_client),
    current_user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, str]:
    """Forget the stored tokens for a provider connection."""
    await verify_event_access(str(event_id, write=True), current_user, supabase)
    mail.disconnect(event_id, provider)
    return {"status": "disconnected", "provider": provider}
