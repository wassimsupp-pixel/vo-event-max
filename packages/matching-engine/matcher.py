# -*- coding: utf-8 -*-
"""
matcher.py
==========
Deterministic, scoring-based participant matching engine for VO Event Max.

Design principles
-----------------
* **No generative AI, no ML** -- every decision is explainable and
  reproducible from the scoring table below.
* Conservative thresholds: it is always safer to flag a record for human
  review than to silently merge two unrelated participants.
* Each ``MatchResult`` carries a ``signals`` dict so downstream tools can
  display exactly which signals fired and why a decision was reached.

Scoring table
-------------
+------------------------------------+--------+--------------------+
| Signal                             | Points | Key                |
+====================================+========+====================+
| Email exact normalised match       |    100 | email_exact        |
+------------------------------------+--------+--------------------+
| ID exact match (both non-empty)    |     90 | id_exact           |
+------------------------------------+--------+--------------------+
| Full name exact normalised match   |     80 | name_exact         |
+------------------------------------+--------+--------------------+
| Fuzzy full name (token_sort_ratio) |  <=75  | name_fuzzy         |
+------------------------------------+--------+--------------------+
| Company normalised bonus           |      5 | company_bonus      |
+------------------------------------+--------+--------------------+
| Phone normalised bonus             |      5 | phone_bonus        |
+------------------------------------+--------+--------------------+

Decision thresholds
-------------------
+-------------+----------+----------------------------------------+
| Decision    | Score    | Action                                 |
+=============+==========+========================================+
| CERTAIN     | >= 90    | Auto-merge                             |
+-------------+----------+----------------------------------------+
| PROBABLE    | 70-89    | Merge + flag for review                |
+-------------+----------+----------------------------------------+
| TO_VERIFY   | 50-69    | Put in human review queue              |
+-------------+----------+----------------------------------------+
| NOT_FOUND   | < 50     | Create exception / manual lookup       |
+-------------+----------+----------------------------------------+
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from rapidfuzz.fuzz import ratio

from normalizer import (
    normalize_email,
    normalize_full_name,
    normalize_name,
    normalize_phone,
)


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------

class MatchDecision(Enum):
    """Outcome of a single registration-to-flight-record matching attempt."""

    CERTAIN = "certain"
    """Score >= 90: records can be auto-merged with high confidence."""

    PROBABLE = "probable"
    """Score 70-89: records are merged but flagged for a quick human check."""

    TO_VERIFY = "to_verify"
    """Score 50-69: records must be reviewed by a human before merging."""

    NOT_FOUND = "not_found"
    """Score < 50: no plausible match was found; treat as exception."""


@dataclass
class ParticipantRecord:
    """A single participant record from any source (registration or FCM).

    Attributes
    ----------
    id:
        Optional external identifier (registration ID, booking reference, …).
    first_name:
        Given name as provided by the source.
    last_name:
        Family name as provided by the source.
    email:
        Contact email address (may be empty/None).
    company:
        Employer or organisation (optional).
    phone:
        Contact phone number in any format (optional).
    source:
        Human-readable label for the originating file or system.
    raw_data:
        Verbatim key-value pairs from the source row, preserved for auditing.
    """

    id: Optional[str]
    first_name: str
    last_name: str
    email: Optional[str]
    company: Optional[str] = None
    phone: Optional[str] = None
    source: str = ""
    raw_data: dict = field(default_factory=dict)


@dataclass
class MatchResult:
    """The result of matching one registration against all FCM records.

    Attributes
    ----------
    registration:
        The registration record that was the query.
    flight_record:
        The best-matching FCM record, or ``None`` if no match was found
        (decision == NOT_FOUND).
    score:
        Composite score in the range 0-100+ as defined by the scoring table.
    decision:
        Categorical decision derived from the score.
    signals:
        Dict mapping signal key -> contribution value.  Useful for explaining
        why a score was reached, e.g. ``{"email_exact": 100, "phone_bonus": 5}``.
    conflict_fields:
        List of field names where both records have non-empty values that
        differ after normalisation.  Populated only when a match was found.
    """

    registration: ParticipantRecord
    flight_record: Optional[ParticipantRecord]
    score: float
    decision: MatchDecision
    signals: dict
    conflict_fields: list[str]


# ---------------------------------------------------------------------------
# Internal thresholds
# ---------------------------------------------------------------------------

_THRESHOLD_CERTAIN: float = 90.0
_THRESHOLD_PROBABLE: float = 70.0
_THRESHOLD_TO_VERIFY: float = 50.0


def _decision_from_score(score: float) -> MatchDecision:
    """Map a numeric score to a :class:`MatchDecision`.

    Parameters
    ----------
    score:
        Composite matching score.

    Returns
    -------
    MatchDecision
        Categorical decision.
    """
    if score >= _THRESHOLD_CERTAIN:
        return MatchDecision.CERTAIN
    if score >= _THRESHOLD_PROBABLE:
        return MatchDecision.PROBABLE
    if score >= _THRESHOLD_TO_VERIFY:
        return MatchDecision.TO_VERIFY
    return MatchDecision.NOT_FOUND


# ---------------------------------------------------------------------------
# Core scoring function
# ---------------------------------------------------------------------------

def score_pair(
    reg: ParticipantRecord,
    fcm: ParticipantRecord,
) -> tuple[float, dict]:
    """Compute a matching score between one registration and one FCM record.

    The function applies a set of deterministic signals in order of
    discriminative power.  **Email and ID signals are mutually exclusive with
    name signals** in the sense that the highest applicable primary signal is
    taken -- but bonus signals (company, phone) always stack on top.

    Signal priority
    ~~~~~~~~~~~~~~~
    1. ``email_exact``  -- +100  (strongest single identifier)
    2. ``id_exact``     -- +90   (requires both records to carry an ID)
    3. ``name_exact``   -- +80   (full normalised name equality)
    4. ``name_fuzzy``   -- up to +75  (token_sort_ratio * 0.75)

    Bonus signals (independent, additive):
    5. ``company_bonus`` -- +5
    6. ``phone_bonus``   -- +5

    Parameters
    ----------
    reg:
        Registration record (query side).
    fcm:
        FCM flight record (candidate side).

    Returns
    -------
    tuple[float, dict]
        ``(score, signals)`` where *signals* maps each fired signal key to
        its numeric contribution.

    Notes
    -----
    Scores can technically exceed 100 when both a primary signal and both
    bonus signals fire (e.g. email_exact 100 + company_bonus 5 + phone_bonus 5
    = 110).  Downstream code should use thresholds, not assume a 0-100 range.
    """
    score: float = 0.0
    signals: dict = {}

    # -- Primary signals (take the best one) --------------------------------

    reg_email = normalize_email(reg.email)
    fcm_email = normalize_email(fcm.email)

    if reg_email and fcm_email and reg_email == fcm_email:
        score += 100.0
        signals["email_exact"] = 100.0

    elif reg.id and fcm.id and str(reg.id).strip() == str(fcm.id).strip():
        score += 90.0
        signals["id_exact"] = 90.0

    else:
        reg_full = normalize_full_name(reg.first_name, reg.last_name)
        fcm_full = normalize_full_name(fcm.first_name, fcm.last_name)

        if reg_full and fcm_full:
            if reg_full == fcm_full:
                score += 80.0
                signals["name_exact"] = 80.0
            else:
                reg_first = normalize_name(reg.first_name)
                reg_last = normalize_name(reg.last_name)
                fcm_first = normalize_name(fcm.first_name)
                fcm_last = normalize_name(fcm.last_name)
                
                # Only fuzzy match if both first name and last name have some similarity
                # (prevents matching different family members or same first names)
                if ratio(reg_first, fcm_first) >= 60.0 and ratio(reg_last, fcm_last) >= 60.0:
                    score_ratio = ratio(reg_full, fcm_full)
                    contribution = round(score_ratio * 0.75, 2)
                    score += contribution
                    signals["name_fuzzy"] = score_ratio

    # -- Bonus signals (always evaluated independently) ---------------------

    reg_company = normalize_name(reg.company)
    fcm_company = normalize_name(fcm.company)
    if reg_company and fcm_company and reg_company == fcm_company:
        score += 5.0
        signals["company_bonus"] = 5.0

    reg_phone = normalize_phone(reg.phone)
    fcm_phone = normalize_phone(fcm.phone)
    if reg_phone and fcm_phone and reg_phone == fcm_phone:
        score += 5.0
        signals["phone_bonus"] = 5.0

    return score, signals


# ---------------------------------------------------------------------------
# Conflict detection
# ---------------------------------------------------------------------------

def _detect_conflicts(
    reg: ParticipantRecord,
    fcm: ParticipantRecord,
) -> list[str]:
    """Return the list of fields where normalised values differ.

    Only fields where **both** records carry a non-empty value are considered;
    a missing value on one side is not flagged as a conflict (it is simply
    missing data).

    Parameters
    ----------
    reg:
        Registration record.
    fcm:
        FCM flight record.

    Returns
    -------
    list[str]
        Field names with conflicting values, e.g. ``["email", "phone"]``.
    """
    conflicts: list[str] = []

    # Email
    r_email = normalize_email(reg.email)
    f_email = normalize_email(fcm.email)
    if r_email and f_email and r_email != f_email:
        conflicts.append("email")

    # Company
    r_company = normalize_name(reg.company)
    f_company = normalize_name(fcm.company)
    if r_company and f_company and r_company != f_company:
        conflicts.append("company")

    # Phone
    r_phone = normalize_phone(reg.phone)
    f_phone = normalize_phone(fcm.phone)
    if r_phone and f_phone and r_phone != f_phone:
        conflicts.append("phone")

    return conflicts


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def match_sources(
    registrations: list[ParticipantRecord],
    flight_records: list[ParticipantRecord],
) -> list[MatchResult]:
    """Match every registration against all FCM flight records.

    For each registration the function scores it against every FCM record and
    selects the candidate with the highest score.  If the best score is below
    the NOT_FOUND threshold the registration is returned with
    ``flight_record=None`` and ``decision=NOT_FOUND``.

    The algorithm is **O(R * F)** where R = number of registrations and
    F = number of flight records.  For conference-scale datasets (a few
    thousand records at most) this is perfectly adequate.

    Parameters
    ----------
    registrations:
        List of registration records (one per attendee).
    flight_records:
        List of FCM flight records to search.

    Returns
    -------
    list[MatchResult]
        One :class:`MatchResult` per registration, in the same order as the
        input list.

    Examples
    --------
    >>> regs = [ParticipantRecord(id="1", first_name="Alice",
    ...         last_name="Smith", email="alice@example.com")]
    >>> fcms = [ParticipantRecord(id="A", first_name="Alice",
    ...         last_name="Smith", email="alice@example.com")]
    >>> results = match_sources(regs, fcms)
    >>> results[0].decision
    <MatchDecision.CERTAIN: 'certain'>
    """
    results: list[MatchResult] = []

    for reg in registrations:
        best_score: float = -1.0
        best_signals: dict = {}
        best_fcm: Optional[ParticipantRecord] = None

        for fcm in flight_records:
            s, sigs = score_pair(reg, fcm)
            if s > best_score:
                best_score = s
                best_signals = sigs
                best_fcm = fcm

        if best_score < _THRESHOLD_TO_VERIFY:
            # No usable match -- return a NOT_FOUND record
            results.append(
                MatchResult(
                    registration=reg,
                    flight_record=None,
                    score=max(best_score, 0.0),
                    decision=MatchDecision.NOT_FOUND,
                    signals=best_signals,
                    conflict_fields=[],
                )
            )
        else:
            decision = _decision_from_score(best_score)
            conflicts = _detect_conflicts(reg, best_fcm)
            results.append(
                MatchResult(
                    registration=reg,
                    flight_record=best_fcm,
                    score=best_score,
                    decision=decision,
                    signals=best_signals,
                    conflict_fields=conflicts,
                )
            )

    return results


def detect_duplicate_emails(
    records: list[ParticipantRecord],
) -> list[list[ParticipantRecord]]:
    """Group records that share the same normalised email address.

    Only groups of **two or more** records are returned; unique emails are
    ignored.  This is useful for identifying double-registrations before
    attempting flight matching.

    Parameters
    ----------
    records:
        Any list of :class:`ParticipantRecord` objects.

    Returns
    -------
    list[list[ParticipantRecord]]
        A list of groups, where each group is a list of records sharing the
        same normalised email.

    Examples
    --------
    >>> r1 = ParticipantRecord(id="1", first_name="A", last_name="B",
    ...                        email="dup@example.com")
    >>> r2 = ParticipantRecord(id="2", first_name="C", last_name="D",
    ...                        email="DUP@EXAMPLE.COM")
    >>> detect_duplicate_emails([r1, r2])
    [[r1, r2]]
    """
    from collections import defaultdict

    buckets: dict[str, list[ParticipantRecord]] = defaultdict(list)
    for rec in records:
        key = normalize_email(rec.email)
        if key:  # ignore records with no email
            buckets[key].append(rec)

    return [group for group in buckets.values() if len(group) >= 2]
