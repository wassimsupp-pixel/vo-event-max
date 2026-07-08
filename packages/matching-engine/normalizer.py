# -*- coding: utf-8 -*-
"""
normalizer.py
=============
Text normalisation utilities for the VO Event Max matching engine.

All functions are pure (no side-effects) and operate on plain Python strings.
They are deliberately conservative: when in doubt they return an empty string
rather than raising, so callers can safely compare ``bool(value)`` to check
whether a field is usable.
"""

from __future__ import annotations

import re
import unicodedata
from datetime import date
from typing import Optional


# ---------------------------------------------------------------------------
# Email
# ---------------------------------------------------------------------------

def normalize_email(email: str) -> str:
    """Return a canonicalised email address.

    Applies ``str.strip()`` and ``str.lower()``.  Returns an empty string
    when *email* is ``None``, empty, or whitespace-only.

    Parameters
    ----------
    email:
        Raw email string from any source.

    Returns
    -------
    str
        Lowercase, stripped email or ``""`` if the input is falsy.

    Examples
    --------
    >>> normalize_email("  Alice@Example.COM  ")
    'alice@example.com'
    >>> normalize_email(None)
    ''
    """
    if not email:
        return ""
    return str(email).strip().lower()


# ---------------------------------------------------------------------------
# Names
# ---------------------------------------------------------------------------

def normalize_name(name: str) -> str:
    """Return a canonicalised single name component.

    Steps applied in order:

    1. Guard against ``None`` / empty values.
    2. Decompose Unicode to NFD form so combining diacritical marks are
       separated from their base characters.
    3. Strip every character whose Unicode category starts with ``"Mn"``
       (Non-spacing Mark) -- this removes accents, tildes, umlauts, etc.
    4. Re-encode to ASCII, ignoring anything that cannot be represented.
    5. Lowercase and strip surrounding whitespace.

    Parameters
    ----------
    name:
        A single name token (first *or* last name).

    Returns
    -------
    str
        Accent-free, lowercase name or ``""`` if the input is falsy.

    Examples
    --------
    >>> normalize_name("Heloise")
    'heloise'
    >>> normalize_name("  DE SMEDT ")
    'de smedt'
    """
    if not name:
        return ""
    nfd = unicodedata.normalize("NFD", str(name))
    ascii_only = "".join(ch for ch in nfd if unicodedata.category(ch) != "Mn")
    return ascii_only.encode("ascii", "ignore").decode("ascii").lower().strip()


def normalize_full_name(first: str, last: str) -> str:
    """Return a canonicalised full name built from *first* and *last*.

    Each component is passed through :func:`normalize_name` before being
    joined with a single space.  Components that normalise to an empty string
    are omitted, so a missing first or last name still yields a usable result.

    Parameters
    ----------
    first:
        First (given) name.
    last:
        Last (family) name.

    Returns
    -------
    str
        Normalised full name, e.g. ``"jean pierre de smedt"``.

    Examples
    --------
    >>> normalize_full_name("Jean-Pierre", "De Smedt")
    'jean-pierre de smedt'
    >>> normalize_full_name(None, "Muller")
    'muller'
    """
    parts = [normalize_name(p) for p in (first, last)]
    return " ".join(p for p in parts if p)


# ---------------------------------------------------------------------------
# Phone
# ---------------------------------------------------------------------------

def normalize_phone(phone: str) -> str:
    """Return a digit-only phone number string.

    Strips every character that is not an ASCII digit (``0``-``9``).
    Country-code prefixes, spaces, dashes, dots and parentheses are all
    removed.  Returns an empty string when *phone* is ``None`` or falsy.

    Parameters
    ----------
    phone:
        Raw phone string, e.g. ``"+32 (0)2 123 45 67"`` or ``"02-123.45.67"``.

    Returns
    -------
    str
        Digit-only string, e.g. ``"3202123456"`` or ``""``.

    Examples
    --------
    >>> normalize_phone("+32 (0)2 123 45 67")
    '3202123456'
    >>> normalize_phone(None)
    ''
    """
    if not phone:
        return ""
    return re.sub(r"\D", "", str(phone))


# ---------------------------------------------------------------------------
# Dates
# ---------------------------------------------------------------------------

# Ordered list of format strings to try when parsing a raw date string.
_DATE_FORMATS: list[str] = [
    "%d/%m/%Y",   # 31/12/2025   (European day-first slash)
    "%Y-%m-%d",   # 2025-12-31   (ISO 8601)
    "%d-%m-%Y",   # 31-12-2025   (European day-first dash)
    "%m/%d/%Y",   # 12/31/2025   (US month-first slash)
    "%d.%m.%Y",   # 31.12.2025   (European dot-separated)
]


def parse_date(raw: str) -> Optional[date]:
    """Parse a raw date string into a :class:`datetime.date`.

    Tries each format in :data:`_DATE_FORMATS` in order and returns the first
    successful parse.  Returns ``None`` if the string cannot be parsed by any
    known format or if *raw* is ``None`` / empty.

    Parameters
    ----------
    raw:
        Raw date string from any source.

    Returns
    -------
    date or None
        Parsed date, or ``None`` if unparseable.

    Examples
    --------
    >>> parse_date("10/11/2025")
    datetime.date(2025, 11, 10)
    >>> parse_date("2025-11-10")
    datetime.date(2025, 11, 10)
    >>> parse_date("not-a-date")
    """
    if not raw:
        return None
    from datetime import datetime
    raw = str(raw).strip()
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
    return None


# ---------------------------------------------------------------------------
# Flight numbers
# ---------------------------------------------------------------------------

def normalize_flight_number(fn: str) -> str:
    """Return a canonical flight number string.

    Converts to uppercase and removes all whitespace so that ``"SN 123"``,
    ``"sn123"`` and ``"SN123"`` all normalise to ``"SN123"``.

    Parameters
    ----------
    fn:
        Raw flight number string, e.g. ``"sn 123"`` or ``"SN123"``.

    Returns
    -------
    str
        Uppercase, space-free flight number or ``""`` if falsy.

    Examples
    --------
    >>> normalize_flight_number("sn 123")
    'SN123'
    >>> normalize_flight_number("  BA 456  ")
    'BA456'
    """
    if not fn:
        return ""
    return re.sub(r"\s+", "", str(fn).upper())
