"""
services/arbitration_service.py — AI arbitration of ambiguous participant merges.

The deterministic matcher fuses people it is confident about and keeps clearly
different people apart. What is left is the ambiguous middle band (rapidfuzz
name similarity ~78-93): two participant fiches that MIGHT be the same person.

For those, and only those (never on every row — see the fusion-engine spec §7),
we ask the reasoning LLM to arbitrate: ``fusionner`` / ``separer`` / ``incertain``
with a one-line justification and a confidence. Confident "fusionner" verdicts
are merged automatically; everything else is filed as a ``match_candidates`` row
for a human to resolve side-by-side in the review dashboard.

Everything here degrades gracefully: if the AI is unavailable it returns
``incertain`` (→ human review), and if the ``match_candidates`` table has not
been migrated yet, ``create_candidate`` is a no-op that reports failure so the
caller can fall back to the legacy exception path.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Optional

from supabase import Client

from services import ai_service

logger = logging.getLogger(__name__)

# rapidfuzz similarity window that counts as "ambiguous". Below this the two
# people are clearly different; at/above the upper bound the phantom-merge pass
# already fuses obvious duplicates, so we don't re-litigate them here.
AMBIGUOUS_MIN = 78
AMBIGUOUS_MAX = 93

# Hard cap on LLM arbitration calls per consolidation run — bounds latency/cost
# on large events (spec §7: never call the model on every line).
MAX_ARBITRATIONS_PER_RUN = 25

_VALID_DECISIONS = {"fusionner", "separer", "incertain"}


def participant_summary(p: dict) -> dict[str, Any]:
    """A compact, display-and-prompt-friendly snapshot of a participant fiche."""
    return {
        "nom": f"{(p.get('first_name') or '').strip()} {(p.get('last_name') or '').strip()}".strip(),
        "email": (p.get("email") or "").strip() or None,
        "telephone": (p.get("phone") or "").strip() or None,
        "societe": (p.get("company") or "").strip() or None,
        "nationalite": (p.get("nationality") or "").strip() or None,
    }


def arbitrate_pair(a: dict, b: dict, score: float) -> dict[str, Any]:
    """
    Ask the LLM whether two participant fiches are the same person.

    Returns ``{"decision", "justification", "confidence"}``. On any failure the
    decision is ``incertain`` so the pair is routed to mandatory human review
    rather than silently merged or dropped.
    """
    sa, sb = participant_summary(a), participant_summary(b)
    prompt = (
        "Tu dois décider si ces deux fiches représentent la MÊME personne "
        "(participant d'un même événement), en te basant sur le nom, l'email, "
        "le téléphone, la société et la nationalité.\n"
        f"Fiche A : {sa}\n"
        f"Fiche B : {sb}\n"
        f"Score de similarité déterministe du nom : {score:.0f}/100\n\n"
        "Règles : des emails différents et non vides indiquent fortement deux "
        "personnes distinctes ; un même email ou un même téléphone indique "
        "fortement la même personne ; un simple prénom/nom proche ne suffit pas "
        "seul. En cas de réel doute, réponds 'incertain'.\n\n"
        "Réponds UNIQUEMENT en JSON compact, sans texte autour :\n"
        '{"decision": "fusionner" | "separer" | "incertain", '
        '"justification": "une phrase courte", "confiance": 0-100}'
    )
    try:
        data = ai_service.ai_json(prompt, timeout_s=30.0)
    except Exception as exc:  # never let arbitration break a consolidation run
        logger.warning("Arbitration call raised: %s", exc)
        data = None

    if not isinstance(data, dict):
        return {"decision": "incertain", "justification": "Arbitrage IA indisponible.", "confidence": 0.0}

    decision = str(data.get("decision") or "").strip().lower()
    if decision not in _VALID_DECISIONS:
        decision = "incertain"
    try:
        confidence = float(data.get("confiance", data.get("confidence", 0)) or 0)
    except (TypeError, ValueError):
        confidence = 0.0
    confidence = max(0.0, min(100.0, confidence))
    justification = str(data.get("justification") or "").strip()[:500]
    return {"decision": decision, "justification": justification, "confidence": confidence}


def _candidate_exists(supabase: Client, event_id: str, a_id: str, b_id: str) -> bool:
    """True if an OPEN candidate already covers this unordered pair."""
    try:
        res = (
            supabase.table("match_candidates")
            .select("id, participant_a_id, participant_b_id")
            .eq("event_id", event_id)
            .eq("status", "pending")
            .execute()
        )
    except Exception:
        return False
    pair = {a_id, b_id}
    for row in res.data or []:
        if {row.get("participant_a_id"), row.get("participant_b_id")} == pair:
            return True
    return False


def create_candidate(
    supabase: Client,
    event_id: str,
    run_id: Optional[str],
    a: dict,
    b: dict,
    score: float,
    verdict: dict,
) -> bool:
    """
    Insert a pending ``match_candidates`` row. ``a`` is the fiche that would be
    merged INTO ``b`` if confirmed (b is the richer/registered one — the caller
    orders them). Returns False if the table is missing (not migrated yet) or the
    pair is already queued, so the caller can fall back to the legacy path.
    """
    a_id, b_id = a.get("id"), b.get("id")
    if not a_id or not b_id or a_id == b_id:
        return False
    if _candidate_exists(supabase, event_id, a_id, b_id):
        return True  # already surfaced — treat as handled, no fallback needed
    sa, sb = participant_summary(a), participant_summary(b)
    row = {
        "event_id": event_id,
        "run_id": run_id,
        "participant_a_id": a_id,
        "participant_b_id": b_id,
        "name_a": sa["nom"],
        "name_b": sb["nom"],
        "details_a": sa,
        "details_b": sb,
        "deterministic_score": round(float(score), 1),
        "ai_recommendation": verdict.get("decision"),
        "ai_justification": verdict.get("justification"),
        "ai_confidence": round(float(verdict.get("confidence") or 0), 1),
        "status": "pending",
    }
    try:
        supabase.table("match_candidates").insert(row).execute()
        return True
    except Exception as exc:
        # Most likely: the table hasn't been migrated yet. Report failure so the
        # caller keeps the legacy PROBABLE_MATCH exception behaviour.
        logger.warning("Could not insert match_candidate (table missing?): %s", exc)
        return False


def resolve_candidate(supabase: Client, candidate_id: str, decision: str) -> None:
    """Mark a candidate resolved with the human decision. Best-effort."""
    try:
        supabase.table("match_candidates").update({
            "human_decision": decision,
            "status": "resolved",
            "resolved_at": datetime.now(timezone.utc).isoformat(),
        }).eq("id", candidate_id).execute()
    except Exception as exc:
        logger.warning("Failed to mark candidate %s resolved: %s", candidate_id, exc)
