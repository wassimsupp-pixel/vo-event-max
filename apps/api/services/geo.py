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


def place_name(value) -> str:
    """
    Expand a 3-letter IATA code to a readable name:
      - a metropolitan CITY code (NYC, LON, PAR…) → the city name;
      - an AIRPORT code (CDG, JFK…) → the full airport name
        ('Charles de Gaulle International Airport').
    Anything that is not a code (already a city name, unknown code) is returned
    unchanged.
    """
    if value is None:
        return value
    s = str(value).strip()
    if len(s) != 3 or not s.isalpha():
        return s                      # already a name / not a code
    key = s.upper()
    if key in _METRO:                 # city/metro code → city name
        return _METRO[key]
    entry = _airports().get(key)
    if entry:                         # airport code → airport name (city fallback)
        return entry.get("name") or entry.get("city") or s
    return s                          # unknown code — leave as-is


# Backwards-compatible alias.
city_name = place_name
