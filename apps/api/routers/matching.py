"""
routers/matching.py — AI match-arbitration review dashboard.

Surfaces the ambiguous participant pairs the consolidation engine could not
settle on its own (queued in ``match_candidates`` with the AI's recommendation)
and lets a human resolve each one side-by-side: ``fusionner`` merges the two
fiches into one, ``separer`` keeps them apart. Every decision is audited.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from supabase import Client

from dependencies import get_current_user, get_supabase_client, verify_event_access
from services import arbitration_service, consolidation_service
from services.audit_service import log_change

logger = logging.getLogger(__name__)

router = APIRouter()


class MatchCandidate(BaseModel):
    id: str
    event_id: str
    participant_a_id: Optional[str] = None
    participant_b_id: Optional[str] = None
    name_a: Optional[str] = None
    name_b: Optional[str] = None
    details_a: Optional[dict[str, Any]] = None
    details_b: Optional[dict[str, Any]] = None
    deterministic_score: Optional[float] = None
    ai_recommendation: Optional[str] = None
    ai_justification: Optional[str] = None
    ai_confidence: Optional[float] = None
    human_decision: Optional[str] = None
    status: str
    created_at: Optional[str] = None


# Fields the user can pick a side for when merging two fiches.
MERGE_SELECTABLE_FIELDS = ("first_name", "last_name", "email", "phone", "company", "nationality")


class DecisionRequest(BaseModel):
    decision: str  # 'fusionner' | 'separer'
    # Optional per-field choice: {"email": "a@x.com", "phone": "+33..."}. Any
    # field left out keeps the default merge behaviour (the surviving fiche's
    # value, backfilled from the other one when empty).
    keep: Optional[dict[str, Any]] = None


class DecisionResponse(BaseModel):
    id: str
    status: str
    decision: str
    message: str


@router.get(
    "/events/{event_id}/match-candidates",
    response_model=list[MatchCandidate],
    summary="List ambiguous participant pairs awaiting human arbitration",
)
async def list_match_candidates(
    event_id: str,
    include_resolved: bool = False,
    current_user: dict[str, Any] = Depends(get_current_user),
    supabase: Client = Depends(get_supabase_client),
) -> list[MatchCandidate]:
    await verify_event_access(event_id, current_user, supabase)

    try:
        q = (
            supabase.table("match_candidates")
            .select("*")
            .eq("event_id", event_id)
        )
        if not include_resolved:
            q = q.eq("status", "pending")
        res = q.order("deterministic_score", desc=True).execute()
    except Exception as exc:
        # Table not migrated yet — behave as an empty queue rather than 500.
        logger.warning("match_candidates unavailable for event %s: %s", event_id, exc)
        return []

    out: list[MatchCandidate] = []
    for row in res.data or []:
        row = dict(row)
        for k in ("id", "event_id", "participant_a_id", "participant_b_id", "run_id"):
            if row.get(k) is not None:
                row[k] = str(row[k])
        if row.get("created_at") is not None:
            row["created_at"] = str(row["created_at"])
        out.append(MatchCandidate(**{k: row.get(k) for k in MatchCandidate.model_fields}))
    return out


@router.put(
    "/match-candidates/{candidate_id}",
    response_model=DecisionResponse,
    summary="Resolve a match candidate (fusionner / separer)",
)
async def resolve_match_candidate(
    candidate_id: str,
    body: DecisionRequest,
    current_user: dict[str, Any] = Depends(get_current_user),
    supabase: Client = Depends(get_supabase_client),
) -> DecisionResponse:
    decision = (body.decision or "").strip().lower()
    if decision not in ("fusionner", "separer"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="decision must be 'fusionner' or 'separer'.",
        )

    try:
        existing = (
            supabase.table("match_candidates").select("*").eq("id", candidate_id).single().execute()
        )
    except Exception as exc:
        logger.warning("Failed to load candidate %s: %s", candidate_id, exc)
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Candidate not found.")
    if not existing.data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Candidate not found.")

    cand = existing.data
    event_id = cand["event_id"]
    await verify_event_access(event_id, current_user, supabase, write=True)

    if cand.get("status") == "resolved":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This candidate has already been resolved.",
        )

    # Atomically claim the candidate BEFORE merging: two concurrent PUTs for
    # the same candidate_id (double-click "confirmer la fusion") both read
    # status="pending" above and could both proceed — the second one
    # operating on rows the first already repointed/deleted, silently
    # no-op'ing while still logging a misleading "merge" change_log entry
    # and re-marking an already-resolved candidate as resolved. The status
    # column's CHECK constraint only allows 'pending'/'resolved' (no
    # intermediate "claimed" state), so this update writes the FINAL state
    # directly; if the merge below fails, the claim is reverted (back to
    # 'pending') so the operation can still be retried, matching the
    # original fail-and-retry behaviour for the single-request case.
    resolved_at = datetime.now(timezone.utc).isoformat()
    claim = (
        supabase.table("match_candidates")
        .update({"human_decision": decision, "status": "resolved", "resolved_at": resolved_at})
        .eq("id", candidate_id)
        .eq("status", "pending")
        .execute()
    )
    if not claim.data:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This candidate has already been resolved.",
        )

    def _revert_claim() -> None:
        try:
            supabase.table("match_candidates").update({
                "human_decision": None, "status": "pending", "resolved_at": None,
            }).eq("id", candidate_id).execute()
        except Exception as exc:
            logger.warning("Failed to revert candidate %s claim after merge failure: %s", candidate_id, exc)

    merged = False
    if decision == "fusionner":
        loser_id = cand.get("participant_a_id")   # a is merged INTO b
        winner_id = cand.get("participant_b_id")
        if not loser_id or not winner_id:
            _revert_claim()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="One of the participants no longer exists; cannot merge.",
            )
        merged = consolidation_service._merge_participant_into(supabase, loser_id, winner_id)
        if not merged:
            _revert_claim()
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Merge failed. The participants may have changed — refresh and retry.",
            )

        # Apply the user's per-field choices on the surviving fiche. Only the
        # selectable identity fields are writable, and an empty choice is ignored
        # so a merge can never blank a field that had a value.
        if body.keep:
            patch = {
                f: str(v).strip()
                for f, v in body.keep.items()
                if f in MERGE_SELECTABLE_FIELDS and v is not None and str(v).strip()
            }
            if patch:
                try:
                    supabase.table("participants").update(patch).eq("id", winner_id).execute()
                    for _f, _v in patch.items():
                        log_change(
                            supabase=supabase, event_id=event_id, user_id=current_user["id"],
                            entity_type="participant", entity_id=winner_id,
                            field_name=_f, old_value="", new_value=_v, reason="human_arbitration",
                        )
                except Exception as exc:
                    logger.warning("Could not apply merge field choices: %s", exc)
        try:
            log_change(
                supabase=supabase, event_id=event_id, user_id=current_user["id"],
                entity_type="participant", entity_id=winner_id,
                field_name="merge", old_value=loser_id, new_value=winner_id,
                reason="human_arbitration",
            )
        except Exception:
            pass

    # Candidate already atomically marked resolved by the claim above.
    msg = (
        "Fiches fusionnées." if decision == "fusionner"
        else "Fiches conservées séparées."
    )
    return DecisionResponse(id=candidate_id, status="resolved", decision=decision, message=msg)
