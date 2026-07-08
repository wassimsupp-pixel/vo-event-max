# -*- coding: utf-8 -*-
"""
matching_engine
===============
Public API for the VO Event Max matching engine package.

Import the most-used symbols directly from the package root::

    from matching_engine import match_sources, MatchResult, MatchDecision
    from matching_engine import normalize_email, parse_date
"""

from matcher import (
    MatchDecision,
    MatchResult,
    ParticipantRecord,
    match_sources,
)
from normalizer import (
    normalize_email,
    normalize_full_name,
    normalize_name,
    parse_date,
)

__all__ = [
    "match_sources",
    "MatchResult",
    "MatchDecision",
    "ParticipantRecord",
    "normalize_email",
    "normalize_name",
    "normalize_full_name",
    "parse_date",
]
