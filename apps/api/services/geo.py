"""
services/geo.py — Expand IATA airport/city codes to full city names.

Used for display everywhere a flight route shows (master list, flights page,
export): a stored 3-letter code like ALG / CDG / NYC becomes 'Algiers' /
'Paris' / 'New York'. Raw codes stay in the DB (needed for matching/dedup);
only the presentation is expanded.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

# Metropolitan IATA CITY codes (cover several airports) that the airport
# database does not carry — the ones travellers actually see on tickets.
_METRO: dict[str, str] = {
    "NYC": "New York", "LON": "London", "PAR": "Paris", "MIL": "Milan",
    "ROM": "Rome", "TYO": "Tokyo", "OSA": "Osaka", "MOW": "Moscow",
    "WAS": "Washington", "CHI": "Chicago", "BJS": "Beijing", "SHA": "Shanghai",
    "SEL": "Seoul", "JKT": "Jakarta", "BUE": "Buenos Aires", "RIO": "Rio de Janeiro",
    "SAO": "Sao Paulo", "STO": "Stockholm", "BER": "Berlin", "DUS": "Dusseldorf",
    "TSA": "Taipei", "TPE": "Taipei", "BKK": "Bangkok", "KUL": "Kuala Lumpur",
    "DXB": "Dubai", "JED": "Jeddah", "RUH": "Riyadh", "DOH": "Doha",
    "YTO": "Toronto", "YMQ": "Montreal", "DFW": "Dallas",
}

_IATA: dict | None = None


def _airports() -> dict:
    global _IATA
    if _IATA is None:
        try:
            import airportsdata
            _IATA = airportsdata.load("IATA")
        except Exception as exc:  # library/data missing → codes stay unexpanded
            logger.warning("airportsdata unavailable, IATA codes not expanded: %s", exc)
            _IATA = {}
    return _IATA


def city_name(value) -> str:
    """
    Return the full city name for a 3-letter IATA code; otherwise return the
    value unchanged (it is already a city name, or an unknown code).
    """
    if value is None:
        return value
    s = str(value).strip()
    if len(s) != 3 or not s.isalpha():
        return s                      # already a city name / not a code
    key = s.upper()
    if key in _METRO:
        return _METRO[key]
    entry = _airports().get(key)
    if entry and entry.get("city"):
        return entry["city"]
    return s                          # unknown code — leave as-is
