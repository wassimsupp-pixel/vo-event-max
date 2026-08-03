"""
services/chatbot_service.py — Project-scoped conversational assistant (client
Feedback V1 §7, "Assistant conversationnel lié au projet").

Design rule, straight from the brief: *"Le chatbot doit répondre uniquement sur
base des données du projet et indiquer lorsqu'une information n'est pas
disponible"* — it must never invent. That constraint drives the whole shape of
this module, so it is worth stating what was deliberately NOT done:

  We do NOT dump the master list into a prompt and let a model write prose about
  it. A model asked to phrase "how many people have no flight" from a blob of
  rows will, sooner or later, produce a plausible wrong number — and the
  organizer has no way to tell that answer apart from a right one.

The model therefore never states a fact. It does two other things instead —
it *chooses* what to look up, and it *phrases* what was found — and the
lookup itself is always real code hitting Postgres.

Three tiers, tried in order:

  1. INTENTS (``_INTENTS``) — the canonical questions, matched by keyword.
     Instant, offline, no model in the path at all.
  2. QUERY PLANNER (``_plan_query``) — for everything else. The model
     translates the question into a STRUCTURED FILTER SPEC (JSON: fields,
     operators, values, optional grouping). That spec is validated against a
     field/operator allowlist and executed by ``_execute_plan`` over rows read
     from the database. This is what lets it answer combinations it has never
     seen — "les Belges sans transfert", "répartition par société", "qui a un
     vol mais pas d'hôtel ni d'activité" — without anyone hard-coding them.
     A model that invents a field name produces an invalid spec, which is
     rejected, not executed.
  3. Refusal — explicit, listing what the assistant can do. Never a guess.

Phrasing: once the facts are computed, the model may write the sentence, but
``_numbers_are_grounded`` then checks that every number in its answer actually
appears in the computed facts. If one does not, the generated text is thrown
away and a deterministic template is used instead. So the worst case of a
phrasing model going astray is a blander sentence — never a wrong figure.

Conversation history is passed to the planner so follow-ups work ("et parmi
eux, combien sont français ?"); it is context for choosing the query, never a
source of facts.

If no AI provider is reachable, tier 1 still answers and tier 2 degrades to a
refusal that says so — the assistant gets less capable, it does not break.
"""

from __future__ import annotations

import json
import logging
import re
import unicodedata
from datetime import date
from typing import Any, Optional

from rapidfuzz import fuzz
from supabase import Client

from services import ai_service

logger = logging.getLogger(__name__)

# Rows returned inline with an answer. The full list always lives behind the
# matching app page (named in `references`) — the chat is a shortcut, not a
# replacement for the master list.
_MAX_ROWS = 50

# Below this rapidfuzz score a name in a question is not considered a match to
# any participant; the assistant says it cannot find them rather than answering
# about the closest stranger.
_NAME_MATCH_MIN = 80

_PARTICIPANT_COLS = (
    "id, first_name, last_name, email, company, phone, nationality, "
    "dietary_requirements, completeness_status, has_flight, has_hotel, "
    "has_transfer, has_activities"
)

_STAFF_ROLES = ("admin", "pm")


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------

def _norm(s: Any) -> str:
    """Lowercase, accent-stripped — for keyword routing and name matching."""
    t = str(s or "").strip().lower()
    t = "".join(c for c in unicodedata.normalize("NFD", t) if unicodedata.category(c) != "Mn")
    return " ".join(t.split())


def _full_name(p: dict) -> str:
    return f"{p.get('first_name') or ''} {p.get('last_name') or ''}".strip()


def _fetch_participants(supabase: Client, event_id: str) -> list[dict]:
    """All participants for the event (paginated — PostgREST caps at 1000)."""
    out: list[dict] = []
    offset = 0
    while True:
        resp = (
            supabase.table("participants")
            .select(_PARTICIPANT_COLS)
            .eq("event_id", event_id)
            .order("last_name")
            .order("first_name")
            .range(offset, offset + 999)
            .execute()
        )
        rows = resp.data or []
        out.extend(rows)
        if len(rows) < 1000:
            break
        offset += 1000
    return out


def _strip_dietary(rows: list[dict], user_role: str) -> list[dict]:
    """dietary_requirements is RGPD-sensitive and restricted to admin/pm
    everywhere else in the app (routers/participants.py::_strip_dietary). The
    assistant must not become a side channel around that."""
    if user_role in _STAFF_ROLES:
        return rows
    return [{k: v for k, v in r.items() if k != "dietary_requirements"} for r in rows]


def _people_rows(people: list[dict], *, extra: tuple[str, ...] = ()) -> list[dict]:
    """Compact tabular rows for display: identity + whichever flags matter."""
    rows = []
    for p in people[:_MAX_ROWS]:
        row = {"id": p["id"], "nom": _full_name(p), "email": p.get("email") or "—"}
        for key in extra:
            row[key] = p.get(key)
        rows.append(row)
    return rows


def _count_phrase(n: int, singular: str, plural: str) -> str:
    return f"{n} {singular}" if n <= 1 else f"{n} {plural}"


def _find_participant(people: list[dict], name: str) -> tuple[Optional[dict], list[dict]]:
    """Resolve a name from a question to one participant.

    Returns ``(match, ambiguous)``. When several people score within a hair of
    each other (real homonyms — common on large events), we return no match and
    the candidate list, so the assistant asks instead of picking one.
    """
    target = _norm(name)
    if not target:
        return None, []
    scored = sorted(
        ((fuzz.token_set_ratio(target, _norm(_full_name(p))), p) for p in people),
        key=lambda t: -t[0],
    )
    if not scored or scored[0][0] < _NAME_MATCH_MIN:
        return None, []
    best_score = scored[0][0]
    tied = [p for s, p in scored if s >= best_score - 2]
    if len(tied) > 1:
        return None, tied[:10]
    return scored[0][1], []


# ---------------------------------------------------------------------------
# Intent handlers — each one is a real query; nothing here is generated.
# Signature: (event_id, params, supabase, user_role) -> dict
# ---------------------------------------------------------------------------

def _coverage_gap(
    people: list[dict], flag: str, label_sing: str, label_plur: str, page: str
) -> dict:
    missing = [p for p in people if not p.get(flag)]
    total = len(people)
    n = len(missing)
    if n == 0:
        answer = f"Aucun participant dans ce cas : les {total} participants ont {label_sing}."
    else:
        answer = (
            f"{_count_phrase(n, 'participant n’a', 'participants n’ont')} pas "
            f"{label_plur} (sur {total})."
        )
        if n > _MAX_ROWS:
            answer += f" Les {_MAX_ROWS} premiers sont listés ci-dessous."
    return {
        "answer": answer,
        "rows": _people_rows(missing),
        "references": [f"Master list — champ « {flag} » ({total} participants)", page],
    }


def _intent_without_flight(event_id, params, supabase, user_role):
    people = _fetch_participants(supabase, event_id)
    return _coverage_gap(people, "has_flight", "un vol", "de vol enregistré", "Page Vols")


def _intent_without_hotel(event_id, params, supabase, user_role):
    people = _fetch_participants(supabase, event_id)
    return _coverage_gap(people, "has_hotel", "un hébergement", "d’hébergement", "Page Gestion des hébergements")


def _intent_without_transfer(event_id, params, supabase, user_role):
    people = _fetch_participants(supabase, event_id)
    return _coverage_gap(people, "has_transfer", "un transfert", "de transfert", "Page Transferts")


def _intent_without_activity(event_id, params, supabase, user_role):
    people = _fetch_participants(supabase, event_id)
    return _coverage_gap(people, "has_activities", "une activité", "d’activité inscrite", "Page Activités")


def _intent_flight_no_transfer(event_id, params, supabase, user_role):
    """The client's example question — a cross-check no single page shows."""
    people = _fetch_participants(supabase, event_id)
    hits = [p for p in people if p.get("has_flight") and not p.get("has_transfer")]
    n = len(hits)
    if n == 0:
        answer = "Aucun participant n’a de vol sans transfert : la couverture est complète de ce côté."
    else:
        answer = (
            f"{_count_phrase(n, 'participant a', 'participants ont')} un vol mais "
            f"aucun transfert — ils arrivent sans prise en charge prévue."
        )
        if n > _MAX_ROWS:
            answer += f" Les {_MAX_ROWS} premiers sont listés ci-dessous."
    return {
        "answer": answer,
        "rows": _people_rows(hits, extra=("has_flight", "has_transfer")),
        "references": ["Master list — champs « has_flight » et « has_transfer »", "Page Transferts"],
    }


_PROFILE_FIELD_LABELS = {
    "email": "email",
    "phone": "téléphone",
    "nationality": "nationalité",
    "company": "société",
    "dietary_requirements": "régime alimentaire",
}


def _intent_participant_missing_info(event_id, params, supabase, user_role):
    people = _fetch_participants(supabase, event_id)
    match, ambiguous, asked = _resolve_participant(people, params)
    if not match:
        return _no_participant(asked, ambiguous)

    fields = [f for f in _PROFILE_FIELD_LABELS if f in match]
    missing = [f for f in fields if not str(match.get(f) or "").strip()]
    gaps = []
    for flag, label in (("has_flight", "vol"), ("has_hotel", "hébergement"),
                        ("has_transfer", "transfert"), ("has_activities", "activité")):
        if not match.get(flag):
            gaps.append(label)

    name = _full_name(match)
    parts = []
    if missing:
        parts.append("champs vides : " + ", ".join(_PROFILE_FIELD_LABELS[f] for f in missing))
    if gaps:
        parts.append("aucun " + ", aucun ".join(gaps))
    answer = (
        f"Il ne manque rien pour « {name} » : profil complet et tous les services rattachés."
        if not parts else
        f"Pour « {name} » — " + " ; ".join(parts) + "."
    )
    return {
        "answer": answer,
        "rows": _strip_dietary([{
            "id": match["id"], "nom": name, "email": match.get("email") or "—",
            "champs_manquants": ", ".join(_PROFILE_FIELD_LABELS[f] for f in missing) or "—",
            "services_manquants": ", ".join(gaps) or "—",
        }], user_role),
        "references": [f"Fiche participant — {name}"],
    }


def _intent_participant_detail(event_id, params, supabase, user_role):
    people = _fetch_participants(supabase, event_id)
    match, ambiguous, asked = _resolve_participant(people, params)
    if not match:
        return _no_participant(asked, ambiguous)
    name = _full_name(match)
    services = [lbl for flag, lbl in (("has_flight", "vol"), ("has_hotel", "hébergement"),
                                      ("has_transfer", "transfert"), ("has_activities", "activité"))
                if match.get(flag)]
    return {
        "answer": (
            f"« {name} » — statut « {match.get('completeness_status') or 'inconnu'} », "
            f"services rattachés : {', '.join(services) if services else 'aucun'}."
        ),
        "rows": _strip_dietary([match], user_role),
        "references": [f"Fiche participant — {name}"],
    }


def _intent_participant_exceptions(event_id, params, supabase, user_role):
    people = _fetch_participants(supabase, event_id)
    match, ambiguous, asked = _resolve_participant(people, params)
    if not match:
        return _no_participant(asked, ambiguous)
    name = _full_name(match)
    resp = (
        supabase.table("exceptions")
        .select("exception_type, severity, message, created_at")
        .eq("event_id", event_id)
        .eq("participant_id", match["id"])
        .eq("resolved", False)
        .order("severity")
        .execute()
    )
    excs = resp.data or []
    if not excs:
        answer = f"« {name} » n’est signalé dans aucune exception non résolue."
    else:
        answer = (
            f"« {name} » est signalé dans "
            f"{_count_phrase(len(excs), 'exception non résolue', 'exceptions non résolues')}."
        )
    return {
        "answer": answer,
        "rows": [{"gravité": e["severity"], "type": e["exception_type"], "message": e["message"]}
                 for e in excs[:_MAX_ROWS]],
        "references": [f"Table exceptions — participant {name}", "Page Exceptions & Alertes"],
    }


def _intent_data_conflicts(event_id, params, supabase, user_role):
    resp = (
        supabase.table("exceptions")
        .select("exception_type, severity, message, participant_id, context_data")
        .eq("event_id", event_id)
        .eq("exception_type", "DATA_CONFLICT")
        .eq("resolved", False)
        .execute()
    )
    excs = resp.data or []
    n = len(excs)
    answer = (
        "Aucune contradiction non résolue entre les fichiers importés."
        if n == 0 else
        f"{_count_phrase(n, 'contradiction détectée', 'contradictions détectées')} entre les fichiers importés."
    )
    return {
        "answer": answer,
        "rows": [{"gravité": e["severity"], "message": e["message"]} for e in excs[:_MAX_ROWS]],
        "references": ["Table exceptions — type DATA_CONFLICT", "Page Exceptions & Alertes"],
    }


def _intent_pending_communications(event_id, params, supabase, user_role):
    try:
        resp = (
            supabase.table("communications")
            .select("id, participant_id, subject, status, type")
            .eq("event_id", event_id)
            .neq("status", "sent")
            .execute()
        )
        pending = resp.data or []
    except Exception as exc:
        # The communications migration may not be applied on this deployment.
        logger.warning("Communications lookup failed for event %s: %s", event_id, exc)
        return {
            "answer": "Je n’ai pas accès au suivi des communications sur cet événement — "
                      "la table n’est pas disponible. Je préfère le dire plutôt que de deviner.",
            "rows": [],
            "references": ["Page Communications"],
        }

    people = {p["id"]: _full_name(p) for p in _fetch_participants(supabase, event_id)}
    n = len(pending)
    answer = (
        "Aucune communication en attente : tout ce qui a été préparé a été envoyé."
        if n == 0 else
        f"{_count_phrase(n, 'communication n’a', 'communications n’ont')} pas encore été envoyée."
    )
    return {
        "answer": answer,
        "rows": [{
            "destinataire": people.get(c.get("participant_id"), "—"),
            "objet": c.get("subject") or "—",
            "statut": c.get("status"),
        } for c in pending[:_MAX_ROWS]],
        "references": ["Table communications — statut ≠ envoyé", "Page Communications"],
    }


def _intent_today_actions(event_id, params, supabase, user_role):
    """The client's "quelles actions aujourd'hui ?" — a roll-up of what is
    genuinely actionable, each line backed by a real count."""
    people = _fetch_participants(supabase, event_id)
    total = len(people)
    lines: list[dict] = []

    for flag, label, page in (
        ("has_flight", "sans vol", "Page Vols"),
        ("has_hotel", "sans hébergement", "Page Gestion des hébergements"),
        ("has_transfer", "sans transfert", "Page Transferts"),
    ):
        n = sum(1 for p in people if not p.get(flag))
        if n:
            lines.append({"action": f"Compléter les participants {label}", "nombre": n, "où": page})

    try:
        excs = (
            supabase.table("exceptions")
            .select("severity, context_data")
            .eq("event_id", event_id)
            .eq("resolved", False)
            .execute()
        ).data or []
    except Exception:
        excs = []
    warnings = [e for e in excs if e.get("severity") in ("critical", "warning")]
    systemic = [e for e in excs if (e.get("context_data") or {}).get("systemic_anomaly")]
    if systemic:
        lines.append({
            "action": "Vérifier un mapping de colonnes suspect (anomalie systémique détectée)",
            "nombre": len(systemic), "où": "Page Exceptions & Alertes",
        })
    if warnings:
        lines.append({"action": "Traiter les exceptions critiques / avertissements",
                      "nombre": len(warnings), "où": "Page Exceptions & Alertes"})

    try:
        cands = (
            supabase.table("match_candidates")
            .select("id").eq("event_id", event_id).eq("status", "pending").execute()
        ).data or []
        if cands:
            lines.append({"action": "Valider les fusions de doublons proposées",
                          "nombre": len(cands), "où": "Page Fusions à vérifier"})
    except Exception:
        pass

    answer = (
        f"Rien d’urgent sur cet événement : les {total} participants sont complets "
        f"et aucune exception n’est en attente."
        if not lines else
        f"{_count_phrase(len(lines), 'action prioritaire', 'actions prioritaires')} sur cet événement "
        f"({total} participants au total) :"
    )
    return {"answer": answer, "rows": lines,
            "references": ["Master list", "Table exceptions", "Fusions à vérifier"]}


def _intent_event_overview(event_id, params, supabase, user_role):
    people = _fetch_participants(supabase, event_id)
    total = len(people)
    stats = {
        "participants": total,
        "avec_vol": sum(1 for p in people if p.get("has_flight")),
        "avec_hébergement": sum(1 for p in people if p.get("has_hotel")),
        "avec_transfert": sum(1 for p in people if p.get("has_transfer")),
        "avec_activité": sum(1 for p in people if p.get("has_activities")),
    }
    return {
        "answer": f"L’événement compte {total} participants consolidés.",
        "rows": [stats],
        "references": ["Master list", "Page Tableau de bord"],
    }


def _no_participant(name: str, ambiguous: list[dict]) -> dict:
    """Never answer about the closest stranger — say what happened."""
    if ambiguous:
        names = ", ".join(_full_name(p) for p in ambiguous)
        return {
            "answer": f"Plusieurs participants correspondent à « {name} » : {names}. "
                      f"Précisez le nom complet, je ne veux pas répondre sur la mauvaise personne.",
            "rows": _people_rows(ambiguous),
            "references": ["Master list"],
        }
    return {
        "answer": f"Je ne trouve aucun participant nommé « {name} » sur cet événement. "
                  f"Vérifiez l’orthographe, ou le participant n’a pas encore été importé.",
        "rows": [],
        "references": ["Master list"],
    }


# ---------------------------------------------------------------------------
# Intent registry
# ---------------------------------------------------------------------------

# ORDER IS PRECEDENCE. _keyword_route walks this dict top-down and takes the
# first pattern that matches, so the SPECIFIC intents must come before the
# generic ones they overlap with: "un vol mais aucun transfert" also contains
# "aucun transfert", and listing the generic transfer intent first made that
# question answer the wrong thing entirely. The tests below pin this down —
# a well-meaning reorder will fail them rather than silently regress.
_INTENTS: dict[str, dict[str, Any]] = {
    "participants_with_flight_no_transfer": {
        "fn": _intent_flight_no_transfer,
        "desc": "lister les participants qui ont un vol mais aucun transfert",
        "keywords": [r"vol .*(mais|sans) .*transfert", r"vol.*aucun transfert"],
    },
    "participants_without_flight": {
        "fn": _intent_without_flight,
        "desc": "lister les participants sans vol",
        "keywords": [r"sans vol", r"pas .*de vol", r"aucun vol", r"n.*ont pas .*vol"],
    },
    "participants_without_hotel": {
        "fn": _intent_without_hotel,
        "desc": "lister les participants sans hébergement/hôtel",
        "keywords": [r"sans (hotel|hebergement)", r"pas .*(hotel|hebergement)", r"aucun (hotel|hebergement)"],
    },
    "participants_without_transfer": {
        "fn": _intent_without_transfer,
        "desc": "lister les participants sans transfert",
        "keywords": [r"sans transfert", r"pas .*de transfert", r"aucun transfert"],
    },
    "participants_without_activity": {
        "fn": _intent_without_activity,
        "desc": "lister les participants sans activité",
        "keywords": [r"sans activite", r"pas .*d.activite", r"aucune activite"],
    },
    "participant_missing_info": {
        "fn": _intent_participant_missing_info,
        "desc": "dire quelles informations manquent pour UN participant donné (nécessite son nom)",
        "keywords": [r"(quelles?|quel).*manque.*pour", r"informations? manquantes? pour"],
    },
    "participant_exceptions": {
        "fn": _intent_participant_exceptions,
        "desc": "expliquer pourquoi UN participant donné est signalé en exception (nécessite son nom)",
        "keywords": [r"pourquoi.*(exception|signale)", r"exceptions? (de|pour|du)"],
    },
    "participant_detail": {
        "fn": _intent_participant_detail,
        "desc": "donner la fiche d'UN participant donné (nécessite son nom)",
        "keywords": [r"(fiche|infos?|informations?|donnees?) (de|du|sur|pour)\b"],
    },
    "data_conflicts": {
        "fn": _intent_data_conflicts,
        "desc": "lister les contradictions/conflits entre les fichiers importés",
        "keywords": [r"contradiction", r"conflit", r"incoherence"],
    },
    "pending_communications": {
        "fn": _intent_pending_communications,
        "desc": "lister les participants/clients qui doivent encore recevoir un e-mail",
        "keywords": [r"(mail|email|e-mail|communication).*(pas|encore|attente|envoyer)",
                     r"(doivent|doit).*recevoir"],
    },
    "today_actions": {
        "fn": _intent_today_actions,
        "desc": "résumer les actions à réaliser aujourd'hui sur l'événement",
        "keywords": [r"(actions?|taches?|faire).*(aujourd|jour|prioritaire)", r"que dois.je faire",
                     r"quoi faire"],
    },
    "event_overview": {
        "fn": _intent_event_overview,
        "desc": "donner les chiffres généraux de l'événement (nombre de participants, couverture)",
        "keywords": [r"combien de participants", r"(vue d.ensemble|resume|apercu) .*evenement",
                     r"^combien\b"],
    },
}

SUGGESTED_QUESTIONS = [
    "Quels participants n'ont pas de vol ?",
    "Quels participants n'ont pas encore d'hôtel ?",
    "Quels participants ont un vol mais aucun transfert ?",
    "Quelles sont les contradictions entre les fichiers ?",
    "Quels clients doivent encore recevoir un e-mail ?",
    "Quelles actions doivent être réalisées aujourd'hui ?",
]

CAPABILITIES_FR = [
    "les participants sans vol, sans hébergement, sans transfert ou sans activité",
    "les participants qui ont un vol mais aucun transfert",
    "ce qu'il manque à un participant précis, ou pourquoi il est en exception",
    "les contradictions entre les fichiers importés",
    "les communications qui n'ont pas encore été envoyées",
    "les actions prioritaires du jour et les chiffres généraux de l'événement",
]


# ---------------------------------------------------------------------------
# Routing — the ONLY place the LLM is involved, and it never sees the data
# ---------------------------------------------------------------------------

# Words that carry no filtering meaning of their own. Used to decide whether a
# question is ONLY a canonical question, or a canonical question plus extra
# criteria. Deliberately small: a word missing here just sends the question to
# the planner (right answer, slightly slower), whereas a word wrongly added
# here would let a compound question be answered as if a criterion weren't
# there — a confidently wrong answer, which is the failure we care about.
_FILLER = {
    "quels", "quelles", "quel", "quelle", "que", "qui", "quoi", "combien",
    "participants", "participant", "personnes", "personne", "gens", "clients", "client",
    "ont", "on", "a", "as", "est", "sont", "etre", "doivent", "doit", "avoir",
    "n", "ne", "pas", "plus", "encore", "aucun", "aucune", "sans", "avec",
    "de", "des", "du", "d", "le", "la", "les", "l", "un", "une", "au", "aux",
    "ce", "cet", "cette", "ces", "y", "il", "elle", "ils", "elles", "t", "s",
    "et", "ou", "en", "dans", "sur", "pour", "entre", "par", "moi", "me", "je",
    "tu", "donne", "donnez", "montre", "montrez", "affiche", "liste", "lister",
    "veux", "voudrais", "peux", "peut", "stp", "merci", "svp",
    # domain words already implied by the matched intent itself
    "vol", "vols", "hotel", "hotels", "hebergement", "hebergements",
    "transfert", "transferts", "activite", "activites", "mail", "mails",
    "email", "emails", "e", "fichier", "fichiers", "source", "sources",
    "action", "actions", "aujourd", "hui", "jour", "realisees", "realiser",
    "contradiction", "contradictions", "conflit", "conflits", "exception",
    "exceptions", "information", "informations", "info", "infos", "manque",
    "manquent", "manquantes", "recevoir", "envoyer", "planifie", "renseigne",
    "evenement", "event", "master", "list", "liste",
}


def _leftover_terms(question: str, matched_span: tuple[int, int]) -> list[str]:
    """Meaningful words left once the matched canonical phrase is removed."""
    q = _norm(question)
    rest = q[:matched_span[0]] + " " + q[matched_span[1]:]
    return [
        w for w in re.split(r"[^\w]+", rest)
        if len(w) >= 3 and w not in _FILLER and not w.isdigit()
    ]


def _keyword_route(question: str) -> Optional[str]:
    """Instant, offline routing for canonical phrasings (the suggestion chips
    resolve through here — no AI call, no latency, no provider dependency).

    Returns None when the question carries criteria BEYOND the canonical one:
    "les belges qui n'ont pas de transfert" contains "pas de transfert", but
    answering it with the plain no-transfert list silently drops "belges" and
    hands back a confidently wrong answer. Those go to the planner, which can
    express both conditions.
    """
    q = _norm(question)
    for name, spec in _INTENTS.items():
        for pattern in spec["keywords"]:
            m = re.search(pattern, q)
            if not m:
                continue
            # Per-participant intents legitimately carry a name as extra text.
            if name.startswith("participant_"):
                return name
            if _leftover_terms(question, m.span()):
                return None      # compound question -> let the planner handle it
            return name
    return None


# Capitalised words that open a French question and are NOT someone's name.
# Without this, "Pourquoi Ana Kaya…" yields "Pourquoi Ana" and the lookup
# misses; with it, the name comes out clean for the answer text.
_QUESTION_WORDS = {
    "pourquoi", "quel", "quels", "quelle", "quelles", "que", "quoi", "qui",
    "comment", "combien", "ou", "quand", "est", "il", "elle", "donne",
    "donnez", "dis", "dites", "montre", "montrez", "affiche", "affichez",
    "liste", "listez", "fiche", "infos", "info", "informations", "peux",
    "peut", "je", "tu", "on", "le", "la", "les", "un", "une", "des",
}


def _extract_name(question: str) -> str:
    """Pull a person's name out of a question, for the per-participant intents.

    Quoted forms win, then a connector ("pour X", "de X"), then any run of
    capitalised words that is not a question word. Returns "" when nothing
    looks like a name — callers then fall back to matching the whole question,
    which token_set_ratio handles well (a two-token name fully contained in a
    longer sentence scores at the top, unrelated participants score low).
    """
    m = re.search(r"[«\"']\s*([^»\"']{2,60})\s*[»\"']", question)
    if m:
        return m.group(1).strip()
    m = re.search(
        r"\b(?:pour|de|du|sur|concernant)\s+((?:[A-ZÀ-Ý][\w'’-]+\s*){1,3})",
        question,
    )
    if m:
        return m.group(1).strip()
    tokens = re.findall(r"[A-ZÀ-Ý][\w'’-]+", question)
    kept = [t for t in tokens if _norm(t) not in _QUESTION_WORDS]
    return " ".join(kept[:3]) if kept else ""


def _resolve_participant(people: list[dict], params: dict) -> tuple[Optional[dict], list[dict], str]:
    """Resolve the participant a question is about.

    Falls back to matching against the raw question when no name could be
    extracted — better to let the fuzzy matcher decide than to fail on a
    phrasing the extractor did not anticipate. The third return value is what
    to show the user when nothing matched.
    """
    name = (params.get("participant_name") or "").strip()
    probe = name or (params.get("question") or "")
    match, ambiguous = _find_participant(people, probe)
    display = name or (params.get("question") or "").strip()
    return match, ambiguous, display


_ROUTER_PROMPT = """Tu es un routeur d'intentions. Tu ne réponds JAMAIS à la question.
Tu choisis uniquement l'intention correspondante dans cette liste :

{catalogue}

Question de l'utilisateur : "{question}"

Réponds UNIQUEMENT en JSON strict :
{{"intent": "<nom exact d'une intention de la liste, ou null si aucune ne correspond>",
  "participant_name": "<nom de la personne citée dans la question, ou \\"\\" si aucune>"}}

Si la question ne correspond à AUCUNE intention de la liste, renvoie "intent": null.
N'invente jamais une intention absente de la liste."""


def _llm_route(question: str) -> tuple[Optional[str], str]:
    catalogue = "\n".join(f"- {name} : {spec['desc']}" for name, spec in _INTENTS.items())
    prompt = _ROUTER_PROMPT.format(catalogue=catalogue, question=question.replace('"', "'"))
    try:
        parsed = ai_service.ai_json(prompt, timeout_s=20.0)
    except Exception as exc:
        logger.warning("Chatbot routing call failed: %s", exc)
        return None, ""
    if not isinstance(parsed, dict):
        return None, ""
    intent = parsed.get("intent")
    if intent not in _INTENTS:
        return None, ""
    return intent, str(parsed.get("participant_name") or "").strip()


# ---------------------------------------------------------------------------
# Tier 2 — structured query planner
#
# The model proposes a filter spec; this code validates and runs it. Anything
# the model names that is not on these allowlists is rejected outright, so a
# hallucinated field or operator can never reach the data.
# ---------------------------------------------------------------------------

_PLANNABLE_FIELDS: dict[str, str] = {
    "has_flight": "bool", "has_hotel": "bool", "has_transfer": "bool",
    "has_activities": "bool", "completeness_status": "text",
    "nationality": "text", "company": "text", "email": "text",
    "phone": "text", "first_name": "text", "last_name": "text",
    "dietary_requirements": "text",     # staff only — filtered out below
}
_PLAN_OPS = {
    "is", "is_not", "contains", "not_contains", "is_empty", "is_not_empty", "in",
}
_PLAN_OUTPUTS = {"count", "list", "group"}


def _plannable_for(user_role: str) -> dict[str, str]:
    fields = dict(_PLANNABLE_FIELDS)
    if user_role not in _STAFF_ROLES:
        fields.pop("dietary_requirements", None)   # same RGPD line as everywhere else
    return fields


def _coerce(value: Any, kind: str) -> Any:
    if kind == "bool":
        if isinstance(value, bool):
            return value
        return _norm(value) in {"true", "oui", "yes", "1"}
    return value


def _validate_plan(plan: Any, user_role: str) -> Optional[dict]:
    """Return a safe plan, or None if the model produced anything unexpected.
    Rejecting is always preferable to running a half-understood query."""
    if not isinstance(plan, dict):
        return None
    allowed = _plannable_for(user_role)

    raw_filters = plan.get("filters")
    if raw_filters is None:
        raw_filters = []
    if not isinstance(raw_filters, list):
        return None

    filters = []
    for f in raw_filters:
        if not isinstance(f, dict):
            return None
        field, op = f.get("field"), f.get("op")
        if field not in allowed or op not in _PLAN_OPS:
            return None                       # unknown field/operator -> reject
        value = f.get("value")
        if op == "in":
            if not isinstance(value, list) or not value:
                return None
            value = [str(v) for v in value]
        elif op in ("is_empty", "is_not_empty"):
            value = None
        else:
            value = _coerce(value, allowed[field])
        filters.append({"field": field, "op": op, "value": value})

    output = plan.get("output", "list")
    if output not in _PLAN_OUTPUTS:
        output = "list"
    group_by = plan.get("group_by")
    if output == "group":
        if group_by not in allowed:
            return None
    else:
        group_by = None
    logic = "or" if str(plan.get("logic", "and")).lower() == "or" else "and"

    if not filters and output != "group":
        return None                           # no criteria and no grouping: nothing to run
    return {"filters": filters, "logic": logic, "output": output, "group_by": group_by}


def _matches(person: dict, f: dict) -> bool:
    raw = person.get(f["field"])
    op = f["op"]
    if op == "is_empty":
        return not str(raw or "").strip()
    if op == "is_not_empty":
        return bool(str(raw or "").strip())
    if _PLANNABLE_FIELDS.get(f["field"]) == "bool":
        return bool(raw) == bool(f["value"]) if op == "is" else bool(raw) != bool(f["value"])
    text = _norm(raw)
    if op == "in":
        return any(_norm(v) == text for v in f["value"])
    target = _norm(f["value"])
    if op == "is":
        return text == target
    if op == "is_not":
        return text != target
    if op == "contains":
        return target in text
    if op == "not_contains":
        return target not in text
    return False


def _execute_plan(plan: dict, people: list[dict], user_role: str) -> dict[str, Any]:
    """Run a validated plan over real rows. Pure Python over data already read
    from Postgres — there is no query string to inject into."""
    filters, logic = plan["filters"], plan["logic"]
    if filters:
        test = all if logic == "and" else any
        hits = [p for p in people if test(_matches(p, f) for f in filters)]
    else:
        hits = list(people)

    if plan["output"] == "group":
        field = plan["group_by"]
        buckets: dict[str, int] = {}
        for p in hits:
            key = str(p.get(field) or "—").strip() or "—"
            buckets[key] = buckets.get(key, 0) + 1
        rows = [{field: k, "participants": v}
                for k, v in sorted(buckets.items(), key=lambda kv: -kv[1])]
        return {"kind": "group", "total": len(hits), "rows": rows[:_MAX_ROWS],
                "groups": len(buckets)}

    rows = _strip_dietary(
        [{"id": p["id"], "nom": _full_name(p), "email": p.get("email") or "—",
          **{f["field"]: p.get(f["field"]) for f in filters
             if f["field"] not in ("first_name", "last_name", "email")}}
         for p in hits[:_MAX_ROWS]],
        user_role,
    )
    return {"kind": plan["output"], "total": len(hits), "rows": rows}


_PLAN_PROMPT = """Tu traduis une question en REQUÊTE STRUCTURÉE sur une liste de
participants d'un événement. Tu ne réponds jamais à la question et tu n'inventes
aucune donnée : tu décris seulement quoi chercher.

Champs disponibles (n'en invente aucun autre) :
{fields}

Opérateurs : is, is_not, contains, not_contains, is_empty, is_not_empty, in
Sorties : "count" (combien), "list" (lesquels), "group" (répartition par champ)

{history}Question : "{question}"

Réponds UNIQUEMENT en JSON strict :
{{"filters":[{{"field":"<champ>","op":"<opérateur>","value":<valeur>}}],
  "logic":"and"|"or",
  "output":"count"|"list"|"group",
  "group_by":"<champ ou null>"}}

Règles :
- has_flight / has_hotel / has_transfer / has_activities valent true ou false.
- "sans X" => {{"field":"has_X","op":"is","value":false}}.
- Pour une répartition, mets output="group" et group_by=<champ>, filters peut être vide.
- Si la question ne porte pas sur les participants de cet événement, renvoie
  exactement {{"filters":[],"output":"unsupported"}}."""


def _plan_query(question: str, user_role: str, history: list[dict] | None) -> Optional[dict]:
    fields = "\n".join(f"- {name} ({kind})" for name, kind in _plannable_for(user_role).items())
    hist = ""
    if history:
        recent = [h for h in history if h.get("question")][-3:]
        if recent:
            hist = "Questions précédentes (contexte pour les sous-entendus) :\n" + "\n".join(
                f"- {h['question']}" for h in recent
            ) + "\n\n"
    prompt = _PLAN_PROMPT.format(fields=fields, history=hist, question=question.replace('"', "'"))
    try:
        raw = ai_service.ai_json(prompt, timeout_s=25.0)
    except Exception as exc:
        logger.warning("Chatbot planner call failed: %s", exc)
        return None
    if isinstance(raw, dict) and raw.get("output") == "unsupported":
        return None
    return _validate_plan(raw, user_role)


# ---------------------------------------------------------------------------
# Phrasing — the model may write the sentence, but not the numbers
# ---------------------------------------------------------------------------

def _numbers_are_grounded(text: str, facts: str) -> bool:
    """Every number in a generated answer must appear in the computed facts.
    This is the guard that makes LLM phrasing safe: a model that drifts into
    inventing a count fails this check and its text is discarded."""
    allowed = set(re.findall(r"\d+", facts))
    return all(n in allowed for n in re.findall(r"\d+", text))


_PHRASE_PROMPT = """Tu formules UNE phrase de réponse en français, à partir des
faits ci-dessous UNIQUEMENT. N'ajoute aucun chiffre, nom ou détail absent des
faits. Pas de liste, pas de markdown : une à deux phrases naturelles.

Question : "{question}"
Faits calculés : {facts}

Réponse :"""


def _phrase(question: str, facts: dict, fallback: str) -> str:
    payload = json.dumps(facts, ensure_ascii=False)
    try:
        text = ai_service.ai_text(
            _PHRASE_PROMPT.format(question=question.replace('"', "'"), facts=payload),
            timeout_s=20.0,
        )
    except Exception:
        return fallback
    if not text:
        return fallback
    text = text.strip().strip('"').split("\n")[0].strip()
    if not text or len(text) > 400 or not _numbers_are_grounded(text, payload):
        logger.info("Discarding ungrounded phrasing, using template instead")
        return fallback
    return text


def _answer_by_plan(
    question: str, event_id: str, supabase: Client, user_role: str,
    history: list[dict] | None,
) -> Optional[dict]:
    """Tier 2: plan a query, run it, phrase the result. None when the question
    cannot be expressed as a query over the participant list."""
    plan = _plan_query(question, user_role, history)
    if not plan:
        return None
    people = _fetch_participants(supabase, event_id)
    result = _execute_plan(plan, people, user_role)
    total, shown = result["total"], len(result["rows"])

    if result["kind"] == "group":
        template = (
            f"Répartition sur {total} participant(s), "
            f"{result['groups']} valeur(s) distincte(s)."
        )
        facts = {"participants": total, "groupes": result["groups"],
                 "repartition": result["rows"][:12]}
    else:
        template = f"{total} participant(s) correspondent à cette recherche."
        if total > shown:
            template += f" Les {shown} premiers sont listés ci-dessous."
        facts = {"resultats": total, "affiches": shown,
                 "exemples": [r.get("nom") for r in result["rows"][:8]]}

    return {
        "answer": _phrase(question, facts, template),
        "rows": result["rows"],
        "references": ["Master list — requête composée sur les données de l'événement"],
        "intent": "query_plan",
        "plan": plan,
    }


def answer_question(
    question: str,
    event_id: str,
    supabase: Client,
    user_role: str = "viewer",
    history: list[dict] | None = None,
) -> dict[str, Any]:
    """Answer a project-scoped question from real event data.

    Returns ``{answer, rows, references, intent, answered}``. ``answered`` is
    False when the question falls outside what the data can support — the
    caller shows the refusal as-is; there is deliberately no fallback that
    tries to be helpful by guessing.
    """
    question = (question or "").strip()
    if not question:
        return {
            "answer": "Posez-moi une question sur cet événement.",
            "rows": [], "references": [], "intent": None, "answered": False,
        }

    # Tier 1: canonical questions, matched offline.
    intent = _keyword_route(question)
    name = _extract_name(question) if intent else ""
    if intent is None:
        intent, name = _llm_route(question)

    if intent is None:
        # Tier 2: compose a query for anything the fixed intents don't cover.
        # This is what answers combinations nobody hard-coded.
        try:
            planned = _answer_by_plan(question, event_id, supabase, user_role, history)
        except Exception as exc:
            logger.error("Chatbot planner failed for event %s: %s", event_id, exc, exc_info=True)
            planned = None
        if planned:
            planned.setdefault("rows", [])
            planned.setdefault("references", [])
            planned["answered"] = True
            planned["generated_on"] = date.today().isoformat()
            return planned

        # Tier 3: refuse, and say what IS answerable.
        return {
            "answer": (
                "Je ne peux pas répondre à cette question à partir des données de l'événement. "
                "Je réponds sur : " + " ; ".join(CAPABILITIES_FR) + "."
            ),
            "rows": [], "references": [], "intent": None, "answered": False,
        }

    spec = _INTENTS[intent]
    # `question` rides along so the per-participant handlers can fall back to
    # fuzzy-matching the whole sentence when name extraction came up empty.
    params = {"participant_name": name or _extract_name(question), "question": question}
    try:
        result = spec["fn"](event_id, params, supabase, user_role)
    except Exception as exc:
        logger.error("Chatbot intent %s failed for event %s: %s", intent, event_id, exc, exc_info=True)
        return {
            "answer": "Je n'ai pas pu lire les données pour répondre. Réessayez dans un instant — "
                      "je préfère ne rien affirmer plutôt que de risquer une réponse fausse.",
            "rows": [], "references": [], "intent": intent, "answered": False,
        }

    result.setdefault("rows", [])
    result.setdefault("references", [])
    result["intent"] = intent
    result["answered"] = True
    result["generated_on"] = date.today().isoformat()
    return result
