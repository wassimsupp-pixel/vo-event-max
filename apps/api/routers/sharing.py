"""
routers/sharing.py — Project/event sharing between users.

Routes (managing members requires admin/pm):
  GET    /api/projects/{project_id}/members              List members
  POST   /api/projects/{project_id}/members              Share with an existing user (by email)
  PATCH  /api/projects/{project_id}/members/{member_id}  Change access level / event scope
  DELETE /api/projects/{project_id}/members/{member_id}  Revoke access
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from supabase import Client

from dependencies import get_supabase_client, require_role

logger = logging.getLogger(__name__)

router = APIRouter()

_MIGRATION_HINT = (
    "Sharing is not enabled yet: run docs/migrations/003_sharing.sql "
    "in the Supabase SQL editor."
)


class MemberCreate(BaseModel):
    email: str = Field(..., description="Email of an EXISTING user of the platform")
    access_level: str = Field("viewer", pattern="^(viewer|editor)$")
    event_ids: Optional[list[str]] = Field(
        None, description="Restrict to these event UUIDs; null = whole project"
    )


class MemberUpdate(BaseModel):
    access_level: Optional[str] = Field(None, pattern="^(viewer|editor)$")
    event_ids: Optional[list[str]] = Field(
        None, description="New event restriction; empty list = whole project"
    )


def _get_project_or_404(supabase: Client, project_id: str, org_id: str) -> dict[str, Any]:
    try:
        res = (
            supabase.table("projects")
            .select("id, org_id, name")
            .eq("id", project_id)
            .eq("org_id", org_id)
            .single()
            .execute()
        )
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found.") from exc
    if not res.data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found.")
    return res.data


def _sharing_table_guard(exc: Exception) -> None:
    if "42P01" in str(exc) or "project_members" in str(exc):
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=_MIGRATION_HINT) from exc


@router.get("/projects/{project_id}/members", summary="List project members")
async def list_members(
    project_id: str,
    current_user: dict[str, Any] = Depends(require_role(["admin", "pm"])),
    supabase: Client = Depends(get_supabase_client),
) -> list[dict[str, Any]]:
    _get_project_or_404(supabase, project_id, current_user["org_id"])
    try:
        res = (
            supabase.table("project_members")
            .select("id, user_id, access_level, event_ids, created_at, users(email, full_name, role)")
            .eq("project_id", project_id)
            .execute()
        )
    except Exception as exc:
        _sharing_table_guard(exc)
        logger.error("Failed to list project members: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to list members.") from exc

    members = []
    for row in res.data or []:
        u = row.pop("users", None) or {}
        row["email"] = u.get("email")
        row["full_name"] = u.get("full_name")
        row["user_role"] = u.get("role")
        members.append(row)
    return members


@router.post(
    "/projects/{project_id}/members",
    status_code=status.HTTP_201_CREATED,
    summary="Share a project with an existing user",
)
async def add_member(
    project_id: str,
    body: MemberCreate,
    current_user: dict[str, Any] = Depends(require_role(["admin", "pm"])),
    supabase: Client = Depends(get_supabase_client),
) -> dict[str, Any]:
    _get_project_or_404(supabase, project_id, current_user["org_id"])

    email = body.email.strip().lower()
    try:
        ures = (
            supabase.table("users")
            .select("id, email, full_name, role")
            .eq("org_id", current_user["org_id"])
            .ilike("email", email)
            .execute()
        )
    except Exception as exc:
        logger.error("User lookup failed: %s", exc)
        raise HTTPException(status_code=500, detail="User lookup failed.") from exc

    target = (ures.data or [None])[0]
    if not target:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No existing user with this email. (Invitation links come later.)",
        )
    if target["id"] == current_user["id"]:
        raise HTTPException(status_code=400, detail="You already have access to this project.")

    payload = {
        "project_id": project_id,
        "user_id": target["id"],
        "access_level": body.access_level,
        "event_ids": body.event_ids or None,
        "invited_by": current_user["id"],
    }
    try:
        res = (
            supabase.table("project_members")
            .upsert(payload, on_conflict="project_id,user_id")
            .execute()
        )
    except Exception as exc:
        _sharing_table_guard(exc)
        logger.error("Failed to add project member: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to add member.") from exc

    row = (res.data or [payload])[0]
    row["email"] = target["email"]
    row["full_name"] = target.get("full_name")
    return row


@router.patch("/projects/{project_id}/members/{member_id}", summary="Update a member's access")
async def update_member(
    project_id: str,
    member_id: str,
    body: MemberUpdate,
    current_user: dict[str, Any] = Depends(require_role(["admin", "pm"])),
    supabase: Client = Depends(get_supabase_client),
) -> dict[str, Any]:
    _get_project_or_404(supabase, project_id, current_user["org_id"])
    patch: dict[str, Any] = {}
    if body.access_level is not None:
        patch["access_level"] = body.access_level
    if body.event_ids is not None:
        patch["event_ids"] = body.event_ids or None   # [] → whole project
    if not patch:
        raise HTTPException(status_code=400, detail="Nothing to update.")
    try:
        res = (
            supabase.table("project_members")
            .update(patch)
            .eq("id", member_id)
            .eq("project_id", project_id)
            .execute()
        )
    except Exception as exc:
        _sharing_table_guard(exc)
        logger.error("Failed to update project member: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to update member.") from exc
    if not res.data:
        raise HTTPException(status_code=404, detail="Member not found.")
    return res.data[0]


@router.delete(
    "/projects/{project_id}/members/{member_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Revoke a member's access",
)
async def remove_member(
    project_id: str,
    member_id: str,
    current_user: dict[str, Any] = Depends(require_role(["admin", "pm"])),
    supabase: Client = Depends(get_supabase_client),
) -> None:
    _get_project_or_404(supabase, project_id, current_user["org_id"])
    try:
        supabase.table("project_members").delete().eq("id", member_id).eq("project_id", project_id).execute()
    except Exception as exc:
        _sharing_table_guard(exc)
        logger.error("Failed to remove project member: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to remove member.") from exc
