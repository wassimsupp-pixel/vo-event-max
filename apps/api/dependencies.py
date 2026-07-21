"""
dependencies.py — FastAPI dependency-injection helpers.

Provides:
  - get_supabase_client()  : Supabase service-role client
  - get_current_user()     : JWT verification → user dict
  - require_role()         : Role-based access control factory
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from functools import lru_cache
from typing import Any

import httpx
from fastapi import Depends, Header, HTTPException, status
from supabase import Client, create_client

import config

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Supabase client
# ---------------------------------------------------------------------------

@lru_cache(maxsize=1)
def _build_supabase_client() -> Client:
    """
    Build (and cache) a Supabase client using the service-role key.

    The service-role key bypasses Row Level Security — it is intentionally
    used server-side so the API can enforce its own access checks before
    calling Supabase. Never expose this key to the frontend.
    """
    if not config.SUPABASE_URL or not config.SUPABASE_SERVICE_ROLE_KEY:
        raise RuntimeError(
            "SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be set in environment."
        )
    return create_client(config.SUPABASE_URL, config.SUPABASE_SERVICE_ROLE_KEY)


def get_supabase_client() -> Client:
    """
    FastAPI dependency: returns the shared Supabase service-role client.

    Usage::

        @router.get("/example")
        async def example(supabase: Client = Depends(get_supabase_client)):
            ...
    """
    return _build_supabase_client()


# ---------------------------------------------------------------------------
# Current user (JWT verification)
# ---------------------------------------------------------------------------

async def get_current_user(
    authorization: str = Header(..., description="Bearer <Supabase JWT>"),
    supabase: Client = Depends(get_supabase_client),
) -> dict[str, Any]:
    """
    FastAPI dependency: verify a Supabase JWT and return the authenticated user dict.

    Extracts the Bearer token from the Authorization header, calls the Supabase
    auth API to verify it, then loads the user profile from the ``users`` table
    (including their role and org_id).

    Raises
    ------
    HTTPException 401
        If the token is missing, malformed, or rejected by Supabase.
    HTTPException 403
        If the user profile does not exist in the ``users`` table.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired authentication token.",
        headers={"WWW-Authenticate": "Bearer"},
    )

    if not authorization.startswith("Bearer "):
        raise credentials_exception

    token = authorization.removeprefix("Bearer ").strip()

    try:
        # Verify the JWT with Supabase Auth
        auth_response = supabase.auth.get_user(token)
        if auth_response is None or auth_response.user is None:
            raise credentials_exception
        supabase_user = auth_response.user
    except Exception as exc:
        logger.warning("JWT verification failed: %s", exc)
        raise credentials_exception from exc

    user_id: str = supabase_user.id

    # Load application-level profile (role, org_id, language)
    try:
        profile_response = (
            supabase.table("users").select("*").eq("id", user_id).single().execute()
        )
    except Exception as exc:
        logger.error("Failed to load user profile for uid=%s: %s", user_id, exc)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User profile not found. Contact your administrator.",
        ) from exc

    if not profile_response.data:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User profile not found. Contact your administrator.",
        )

    return profile_response.data


# ---------------------------------------------------------------------------
# Role-based access control
# ---------------------------------------------------------------------------

def require_role(allowed_roles: list[str]):
    """
    FastAPI dependency factory: assert that the current user has one of the
    specified roles before allowing access.

    Parameters
    ----------
    allowed_roles:
        List of role strings (e.g. ``['admin', 'pm']``).

    Returns
    -------
    A FastAPI dependency function that raises HTTP 403 if the role check fails.

    Usage::

        @router.delete("/participants/{id}")
        async def delete_participant(
            user: dict = Depends(require_role(["admin"])),
        ):
            ...
    """

    async def _check_role(
        current_user: dict[str, Any] = Depends(get_current_user),
    ) -> dict[str, Any]:
        user_role: str = current_user.get("role", "")
        if user_role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access denied. Required roles: {allowed_roles}. Your role: {user_role!r}.",
            )
        return current_user

    return _check_role


# ---------------------------------------------------------------------------
# Event access guard
# ---------------------------------------------------------------------------

#: Roles with implicit full access to every project of their organisation.
STAFF_ROLES = ("admin", "pm")


def get_project_membership(
    supabase: Client,
    project_id: str,
    user_id: str,
) -> dict[str, Any] | None:
    """
    Return the sharing row (project_members) for a user on a project, or None.

    Returns ``{"__no_table__": True}`` when the sharing migration has not been
    run yet, so callers can fall back to legacy org-wide behaviour instead of
    locking every non-staff user out.
    """
    try:
        res = (
            supabase.table("project_members")
            .select("id, access_level, event_ids")
            .eq("project_id", project_id)
            .eq("user_id", user_id)
            .execute()
        )
        return (res.data or [None])[0]
    except Exception as exc:
        # 42P01 = relation does not exist (migration 003 not applied yet)
        if "42P01" in str(exc) or "project_members" in str(exc):
            logger.warning("project_members table missing — sharing not enforced yet.")
            return {"__no_table__": True}
        logger.error("Failed to load project membership: %s", exc)
        return None


async def verify_event_access(
    event_id: str,
    current_user: dict[str, Any],
    supabase: Client,
    write: bool = False,
) -> dict[str, Any]:
    """
    Verify that the current user may access the given event.

    - The event must belong to the user's organisation (404 otherwise, to avoid
      leaking the existence of other organisations' events).
    - ``admin``/``pm`` (staff) have full access to every org event.
    - Other users need a ``project_members`` row for the event's project; if
      that row restricts ``event_ids``, the event must be listed. With
      ``write=True`` the membership must be ``editor`` (403 otherwise).

    Returns the event row if accessible.
    """
    org_id: str = current_user.get("org_id", "")

    try:
        response = (
            supabase.table("events")
            .select("*, projects!inner(org_id)")
            .eq("id", event_id)
            .eq("projects.org_id", org_id)
            .single()
            .execute()
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Event not found.",
        ) from exc

    if not response.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Event not found.",
        )

    event = response.data

    if current_user.get("role") in STAFF_ROLES:
        return event

    membership = get_project_membership(supabase, event.get("project_id", ""), current_user.get("id", ""))
    if membership and membership.get("__no_table__"):
        return event      # migration not applied yet → legacy org-wide access
    if not membership:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Event not found.",
        )
    restricted = membership.get("event_ids")
    if restricted and event_id not in restricted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Event not found.",
        )
    if write and membership.get("access_level") != "editor":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Read-only access: you cannot modify this event.",
        )
    return event


# Runs normally finish in well under 10 minutes; a "running" row older than
# this survived the pipeline's own try/except only because the whole
# process died (e.g. an OOM kill), not a handled failure — treat it as
# stale rather than letting a hard crash permanently block new work.
CONSOLIDATION_STALE_AFTER_SECONDS = 30 * 60


def is_consolidation_running(supabase: Client, event_id: str) -> bool:
    """True if a non-stale consolidation run is currently in flight for this
    event. Shared by trigger_consolidation (refuse a second overlapping run)
    and delete_file (refuse deleting a file mid-run — see files.py for why
    that races into orphaned source_records)."""
    running = (
        supabase.table("consolidation_runs")
        .select("id, started_at")
        .eq("event_id", event_id)
        .eq("status", "running")
        .execute()
    )
    now = datetime.now(timezone.utc)
    for r in running.data or []:
        try:
            started = datetime.fromisoformat(r["started_at"].replace("Z", "+00:00"))
            if (now - started).total_seconds() < CONSOLIDATION_STALE_AFTER_SECONDS:
                return True
        except Exception:
            return True  # unparsable timestamp — be conservative
    return False
