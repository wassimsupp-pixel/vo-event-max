"""
services/event_grouping_service.py — Detect and merge look-alike events.

Clients often create the same event under several spellings across projects
("INNOVATION SUMMIT ISTANBUL", "2026 GLOBAL INNOVATION SUMMIT",
"026INNOVATIONSUMMIT"…). This module clusters an organisation's events by name
similarity, optionally asks the LLM to confirm each cluster is really one event,
and — only on explicit human confirmation — merges a cluster into one canonical
event (reassigning every child row, then deleting the duplicates).

Nothing here is destructive on its own: ``suggest_event_groups`` is read-only;
``merge_events`` runs only when the user confirms a suggestion.
"""

from __future__ import annotations

import logging
import re
import unicodedata
from typing import Any, Optional

from rapidfuzz import fuzz
from supabase import Client

logger = logging.getLogger(__name__)

# Similarity threshold for two event names to be considered the same event.
SIMILARITY_THRESHOLD = 82
# Above this, the deterministic signal is strong enough to skip the AI check.
AUTO_CONFIRM_THRESHOLD = 92

# Tables carrying an event_id that must follow the merge. Best-effort: a table
# that doesn't exist (not migrated) is skipped.
_EVENT_CHILD_TABLES = (
    "participants", "uploaded_files", "source_records", "flights", "hotels",
    "hotel_nights", "transfers", "activities", "exceptions", "communications",
    "consolidation_runs", "match_candidates",
)

# Generic filler tokens that don't help tell two events apart.
_FILLER = {"the", "le", "la", "les", "global", "annual", "edition", "event", "de", "du"}


def _strip_accents(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))


def _norm_event(name: Optional[str]) -> str:
    """lower + de-accent + drop punctuation, keep spaces; drop pure filler words."""
    s = _strip_accents(str(name or "").lower())
    s = re.sub(r"[^a-z0-9\s]", " ", s)
    toks = [t for t in s.split() if t and t not in _FILLER]
    return " ".join(toks).strip()


def _collapsed(norm: str) -> str:
    """spaceless + digitless form so '026innovationsummit' == 'innovation summit'."""
    return re.sub(r"\d", "", norm).replace(" ", "")


def _similarity(a: str, b: str) -> float:
    """Max of token-set similarity and the collapsed spaceless/digitless ratio."""
    na, nb = _norm_event(a), _norm_event(b)
    if not na or not nb:
        return 0.0
    token = fuzz.token_set_ratio(na, nb)
    collapsed = fuzz.ratio(_collapsed(na), _collapsed(nb))
    return float(max(token, collapsed))


def _cluster(events: list[dict]) -> list[list[int]]:
    """Union-find clustering: connect events whose names are similar enough."""
    n = len(events)
    parent = list(range(n))

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: int, b: int) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    for i in range(n):
        for j in range(i + 1, n):
            if _similarity(events[i]["name"], events[j]["name"]) >= SIMILARITY_THRESHOLD:
                union(i, j)

    groups: dict[int, list[int]] = {}
    for i in range(n):
        groups.setdefault(find(i), []).append(i)
    return [idxs for idxs in groups.values() if len(idxs) >= 2]


def _min_pairwise(events: list[dict]) -> float:
    lo = 100.0
    for i in range(len(events)):
        for j in range(i + 1, len(events)):
            lo = min(lo, _similarity(events[i]["name"], events[j]["name"]))
    return lo


def _ai_confirm(names: list[str]) -> Optional[bool]:
    """Ask the LLM whether these names denote the same event. None on failure."""
    from services import ai_service
    if not ai_service.ai_available():
        return None
    prompt = (
        "Voici plusieurs noms d'événements. Dis s'ils désignent le MÊME événement "
        "(mêmes, à des variantes d'orthographe/ville/année près) ou des événements "
        "DIFFÉRENTS.\n"
        f"Noms : {names}\n"
        'Réponds UNIQUEMENT en JSON : {"same_event": true|false}'
    )
    try:
        data = ai_service.ai_json(prompt, timeout_s=30.0)
        if isinstance(data, dict) and "same_event" in data:
            return bool(data["same_event"])
    except Exception as exc:
        logger.warning("Event-group AI confirm failed: %s", exc)
    return None


def _participant_counts(supabase: Client, event_ids: list[str]) -> dict[str, int]:
    counts: dict[str, int] = {e: 0 for e in event_ids}
    for eid in event_ids:
        try:
            r = supabase.table("participants").select("id", count="exact").eq("event_id", eid).execute()
            counts[eid] = r.count if r.count is not None else len(r.data or [])
        except Exception:
            counts[eid] = 0
    return counts


def suggest_event_groups(supabase: Client, org_id: str, use_ai: bool = True) -> list[dict]:
    """
    Read-only. Return clusters of look-alike events for the org, each with a
    suggested canonical event (the richest one). AI confirms borderline clusters;
    very-high-similarity clusters skip the AI call.
    """
    try:
        res = (
            supabase.table("events")
            .select("id, name, start_date, location_city, project_id, projects!inner(org_id)")
            .eq("projects.org_id", org_id)
            .execute()
        )
    except Exception as exc:
        logger.error("Failed to load events for grouping: %s", exc)
        return []

    events = [
        {"id": e["id"], "name": e.get("name") or "", "start_date": e.get("start_date"),
         "location_city": e.get("location_city")}
        for e in (res.data or [])
    ]
    if len(events) < 2:
        return []

    suggestions: list[dict] = []
    for idxs in _cluster(events):
        members = [events[i] for i in idxs]
        names = [m["name"] for m in members]

        ai_confirmed: Optional[bool] = None
        if _min_pairwise(members) < AUTO_CONFIRM_THRESHOLD and use_ai:
            ai_confirmed = _ai_confirm(names)
            if ai_confirmed is False:
                continue  # AI says these are different events — don't suggest

        counts = _participant_counts(supabase, [m["id"] for m in members])
        for m in members:
            m["participant_count"] = counts.get(m["id"], 0)
        # Canonical = most participants, then the longest (most complete) name.
        canonical = max(members, key=lambda m: (m["participant_count"], len(m["name"])))

        suggestions.append({
            "canonical_event_id": canonical["id"],
            "events": sorted(members, key=lambda m: -m["participant_count"]),
            "ai_confirmed": ai_confirmed,
            "min_similarity": round(_min_pairwise(members), 1),
        })
    return suggestions


def merge_events(supabase: Client, canonical_id: str, merge_ids: list[str]) -> dict:
    """
    Reassign every child row of ``merge_ids`` to ``canonical_id``, then delete the
    merged events. Idempotent-ish and best-effort per table. Returns a small stat
    dict. The caller must have verified org ownership of ALL these events.
    """
    merge_ids = [m for m in merge_ids if m and m != canonical_id]
    if not merge_ids:
        return {"merged": 0, "reassigned_tables": 0}

    reassigned = 0
    for eid in merge_ids:
        for table in _EVENT_CHILD_TABLES:
            try:
                supabase.table(table).update({"event_id": canonical_id}).eq("event_id", eid).execute()
                reassigned += 1
            except Exception as exc:
                logger.warning("Reassign %s (event %s→%s) failed: %s", table, eid, canonical_id, exc)

    deleted = 0
    for eid in merge_ids:
        try:
            supabase.table("events").delete().eq("id", eid).execute()
            deleted += 1
        except Exception as exc:
            logger.error("Delete merged event %s failed (lingering FK?): %s", eid, exc)

    logger.info("Merged %d event(s) into %s (%d table reassignments)", deleted, canonical_id, reassigned)
    return {"merged": deleted, "reassigned_tables": reassigned, "canonical_event_id": canonical_id}
