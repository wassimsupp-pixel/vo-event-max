# -*- coding: utf-8 -*-
"""
mail_connection_service.py
==========================
OAuth mailbox connection for the Email Agent.

Lets an operator connect a real Gmail or Outlook inbox so incoming participant
emails can be pulled and run through the existing ``EmailAgentService`` (which
produces human-validated update proposals).

Design
------
* OAuth **app** credentials (client id/secret/redirect) come from environment
  variables only (see ``config.py``) — nothing secret is stored in the DB.
* The per-connection access/refresh tokens obtained after consent are kept in a
  process-memory store keyed by ``(event_id, provider)``.

  .. warning::
     In-memory token storage is intentionally simple for this first iteration:
     tokens are lost on restart and not shared across API instances. Before
     production use, persist the refresh token in an encrypted store and add
     CSRF signing to the OAuth ``state`` parameter (TODOs marked below).

* Two providers are supported: ``gmail`` (Gmail REST API) and ``outlook``
  (Microsoft Graph). A provider is "available" only when its client id/secret
  env vars are set, so the feature degrades gracefully when unconfigured.
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import time
from typing import Any, Optional
from uuid import UUID

import httpx
from supabase import Client

import config
from services.email_agent_service import EmailAgentService

logger = logging.getLogger(__name__)

GMAIL = "gmail"
OUTLOOK = "outlook"
SUPPORTED_PROVIDERS = (GMAIL, OUTLOOK)

# OAuth scopes: read-only mailbox access + offline access for a refresh token.
_GMAIL_SCOPES = "https://www.googleapis.com/auth/gmail.readonly"
_OUTLOOK_SCOPES = "offline_access Mail.Read"

# ---------------------------------------------------------------------------
# In-memory token store  (see module warning)
# TODO(prod): replace with an encrypted, persistent store.
# ---------------------------------------------------------------------------
_token_store: dict[tuple[str, str], dict[str, Any]] = {}


class MailConfigError(RuntimeError):
    """Raised when a provider is not configured via environment variables."""


# ---------------------------------------------------------------------------
# Provider configuration helpers
# ---------------------------------------------------------------------------

def _client_creds(provider: str) -> tuple[str, str]:
    if provider == GMAIL:
        return config.GOOGLE_CLIENT_ID, config.GOOGLE_CLIENT_SECRET
    if provider == OUTLOOK:
        return config.MICROSOFT_CLIENT_ID, config.MICROSOFT_CLIENT_SECRET
    raise MailConfigError(f"Unknown mail provider: {provider!r}")


def provider_configured(provider: str) -> bool:
    """True when the provider's OAuth app credentials and redirect are all set."""
    try:
        client_id, client_secret = _client_creds(provider)
    except MailConfigError:
        return False
    return bool(client_id and client_secret and config.MAIL_OAUTH_REDIRECT_URI)


def get_status(event_id: UUID) -> dict[str, Any]:
    """Per-provider configuration + connection status for an event."""
    providers = []
    for provider in SUPPORTED_PROVIDERS:
        providers.append({
            "provider": provider,
            "configured": provider_configured(provider),
            "connected": (str(event_id), provider) in _token_store,
        })
    return {"providers": providers}


# ---------------------------------------------------------------------------
# OAuth state (event/provider/locale round-trip)
# TODO(prod): sign this value to prevent CSRF on the callback.
# ---------------------------------------------------------------------------

def _encode_state(event_id: UUID, provider: str, locale: str) -> str:
    raw = json.dumps({"e": str(event_id), "p": provider, "l": locale}).encode()
    return base64.urlsafe_b64encode(raw).decode()


def decode_state(state: str) -> dict[str, str]:
    raw = base64.urlsafe_b64decode(state.encode())
    data = json.loads(raw)
    return {"event_id": data["e"], "provider": data["p"], "locale": data.get("l", "fr")}


# ---------------------------------------------------------------------------
# Authorization URL
# ---------------------------------------------------------------------------

def build_authorization_url(provider: str, event_id: UUID, locale: str) -> str:
    """Build the provider consent URL the user is redirected to."""
    if not provider_configured(provider):
        raise MailConfigError(
            f"Provider {provider!r} is not configured. Set its OAuth env vars."
        )
    client_id, _ = _client_creds(provider)
    state = _encode_state(event_id, provider, locale)
    params: dict[str, str] = {
        "client_id": client_id,
        "redirect_uri": config.MAIL_OAUTH_REDIRECT_URI,
        "response_type": "code",
        "state": state,
    }
    if provider == GMAIL:
        params.update({
            "scope": _GMAIL_SCOPES,
            "access_type": "offline",
            "prompt": "consent",
        })
        base = "https://accounts.google.com/o/oauth2/v2/auth"
    else:  # OUTLOOK
        params.update({
            "scope": _OUTLOOK_SCOPES,
            "response_mode": "query",
        })
        base = f"https://login.microsoftonline.com/{config.MICROSOFT_TENANT_ID}/oauth2/v2.0/authorize"

    # httpx.QueryParams URL-encodes each value correctly.
    return f"{base}?{httpx.QueryParams(params)}"


# ---------------------------------------------------------------------------
# Token exchange & refresh
# ---------------------------------------------------------------------------

def _token_endpoint(provider: str) -> str:
    if provider == GMAIL:
        return "https://oauth2.googleapis.com/token"
    return f"https://login.microsoftonline.com/{config.MICROSOFT_TENANT_ID}/oauth2/v2.0/token"


def _store_token(event_id: str, provider: str, token: dict[str, Any]) -> None:
    expires_in = int(token.get("expires_in", 3600))
    token["_expires_at"] = time.time() + expires_in - 60  # refresh 1 min early
    # Preserve a previously-issued refresh token if the provider omits it on refresh
    existing = _token_store.get((event_id, provider), {})
    if "refresh_token" not in token and "refresh_token" in existing:
        token["refresh_token"] = existing["refresh_token"]
    _token_store[(event_id, provider)] = token


def exchange_code(provider: str, code: str, event_id: str) -> None:
    """Exchange an authorization code for tokens and store them in memory."""
    client_id, client_secret = _client_creds(provider)
    data = {
        "code": code,
        "client_id": client_id,
        "client_secret": client_secret,
        "redirect_uri": config.MAIL_OAUTH_REDIRECT_URI,
        "grant_type": "authorization_code",
    }
    if provider == OUTLOOK:
        data["scope"] = _OUTLOOK_SCOPES
    resp = httpx.post(_token_endpoint(provider), data=data, timeout=30.0)
    resp.raise_for_status()
    _store_token(event_id, provider, resp.json())
    logger.info("Stored mail token for event=%s provider=%s", event_id, provider)


def _access_token(event_id: str, provider: str) -> str:
    """Return a valid access token, refreshing via refresh_token if expired."""
    token = _token_store.get((event_id, provider))
    if not token:
        raise MailConfigError("Mailbox not connected. Connect the account first.")
    if token.get("_expires_at", 0) > time.time():
        return token["access_token"]

    refresh_token = token.get("refresh_token")
    if not refresh_token:
        raise MailConfigError("Session expired and no refresh token. Reconnect the mailbox.")

    client_id, client_secret = _client_creds(provider)
    data = {
        "refresh_token": refresh_token,
        "client_id": client_id,
        "client_secret": client_secret,
        "grant_type": "refresh_token",
    }
    if provider == OUTLOOK:
        data["scope"] = _OUTLOOK_SCOPES
    resp = httpx.post(_token_endpoint(provider), data=data, timeout=30.0)
    resp.raise_for_status()
    _store_token(event_id, provider, resp.json())
    return _token_store[(event_id, provider)]["access_token"]


# ---------------------------------------------------------------------------
# Message fetching
# ---------------------------------------------------------------------------

def _fetch_gmail_messages(access_token: str, limit: int) -> list[dict[str, str]]:
    headers = {"Authorization": f"Bearer {access_token}"}
    with httpx.Client(timeout=30.0) as client:
        listing = client.get(
            "https://gmail.googleapis.com/gmail/v1/users/me/messages",
            headers=headers,
            params={"maxResults": limit, "q": "in:inbox"},
        )
        listing.raise_for_status()
        ids = [m["id"] for m in listing.json().get("messages", [])]

        messages: list[dict[str, str]] = []
        for mid in ids:
            detail = client.get(
                f"https://gmail.googleapis.com/gmail/v1/users/me/messages/{mid}",
                headers=headers,
                params={"format": "full"},
            )
            detail.raise_for_status()
            messages.append(_parse_gmail_message(detail.json()))
    return messages


def _parse_gmail_message(msg: dict[str, Any]) -> dict[str, str]:
    payload = msg.get("payload", {})
    headers = {h["name"].lower(): h["value"] for h in payload.get("headers", [])}
    sender = headers.get("from", "")
    # Strip a display name: "Sophie <sophie@x.com>" -> "sophie@x.com"
    if "<" in sender and ">" in sender:
        sender = sender[sender.find("<") + 1: sender.find(">")]
    subject = headers.get("subject", "")
    body = _extract_gmail_body(payload) or msg.get("snippet", "")
    return {"sender": sender.strip(), "subject": subject, "body": body}


def _extract_gmail_body(payload: dict[str, Any]) -> str:
    """Best-effort text/plain extraction from a Gmail MIME payload."""
    mime = payload.get("mimeType", "")
    body_data = payload.get("body", {}).get("data")
    if mime == "text/plain" and body_data:
        return _b64url_decode(body_data)
    for part in payload.get("parts", []) or []:
        text = _extract_gmail_body(part)
        if text:
            return text
    return ""


def _b64url_decode(data: str) -> str:
    padding = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(data + padding).decode("utf-8", errors="replace")


def _fetch_outlook_messages(access_token: str, limit: int) -> list[dict[str, str]]:
    headers = {"Authorization": f"Bearer {access_token}"}
    with httpx.Client(timeout=30.0) as client:
        resp = client.get(
            "https://graph.microsoft.com/v1.0/me/mailFolders/inbox/messages",
            headers=headers,
            params={"$top": limit, "$select": "from,subject,body,bodyPreview"},
        )
        resp.raise_for_status()
        messages: list[dict[str, str]] = []
        for m in resp.json().get("value", []):
            sender = (m.get("from", {}) or {}).get("emailAddress", {}).get("address", "")
            body = (m.get("body", {}) or {}).get("content") or m.get("bodyPreview", "")
            messages.append({
                "sender": sender.strip(),
                "subject": m.get("subject", ""),
                "body": body,
            })
    return messages


# ---------------------------------------------------------------------------
# Sync — pull inbox and run each message through the Email Agent
# ---------------------------------------------------------------------------

async def sync_inbox(provider: str, event_id: UUID, supabase: Client) -> dict[str, Any]:
    """
    Fetch the most recent inbox messages and turn each into an AI proposal.

    Returns ``{"synced": <count>, "provider": provider}``. Reuses the existing
    ``EmailAgentService.analyze_email`` so proposals stay human-validated.
    """
    if provider not in SUPPORTED_PROVIDERS:
        raise MailConfigError(f"Unknown mail provider: {provider!r}")

    limit = config.MAIL_SYNC_MAX_MESSAGES

    # The token refresh + message fetch use a synchronous HTTP client; run them
    # in a thread so they don't block the event loop.
    access_token = await asyncio.to_thread(_access_token, str(event_id), provider)
    if provider == GMAIL:
        raw_messages = await asyncio.to_thread(_fetch_gmail_messages, access_token, limit)
    else:
        raw_messages = await asyncio.to_thread(_fetch_outlook_messages, access_token, limit)

    agent = EmailAgentService(supabase)
    synced = 0
    for msg in raw_messages:
        if not msg.get("sender"):
            continue
        try:
            await agent.analyze_email(
                event_id=event_id,
                sender=msg["sender"],
                subject=msg.get("subject", ""),
                body=msg.get("body", ""),
            )
            synced += 1
        except Exception as exc:  # one bad message shouldn't abort the whole sync
            logger.warning("Failed to analyze message from %s: %s", msg.get("sender"), exc)

    return {"synced": synced, "provider": provider}


def disconnect(event_id: UUID, provider: str) -> None:
    """Drop stored tokens for a connection."""
    _token_store.pop((str(event_id), provider), None)
