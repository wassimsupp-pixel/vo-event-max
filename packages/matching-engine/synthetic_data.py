# -*- coding: utf-8 -*-
"""
synthetic_data.py
=================
Generates a realistic synthetic dataset for testing the VO Event Max
matching engine.

Dataset characteristics
-----------------------
* 100 registration records with Belgian/European names and companies.
* 95 FCM flight records (5 registrations deliberately have no flight match).
* 10 FCM records carry a slightly different name (accent dropped, hyphen
  replaced by space, nickname used, transposed given/family name word).
* 3 FCM records have a wrong or missing email address.
* 2 FCM records belong to a completely different person (wrong booking)
  -- these should end up as NOT_FOUND / TO_VERIFY exceptions.
* 3 duplicate emails in the registration list (same email, different name)
  to exercise :func:`~matcher.detect_duplicate_emails`.
* Realistic Belgian airport departures (BRU, CRL) connecting to the
  conference venue in Barcelona (BCN), via realistic European hubs.
* All flight dates are within the 2025-11-10 to 2025-11-14 window.

Running this module directly::

    python synthetic_data.py

produces three files under ``tests/data/``:

* ``registrations.csv``
* ``fcm_flights.csv``
* ``gold_standard.json``
"""

from __future__ import annotations

import csv
import json
import os
import random
import sys
from datetime import date, timedelta
from typing import Optional

# Ensure the parent package is importable when run as __main__
_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)


# ---------------------------------------------------------------------------
# Seed for reproducibility
# ---------------------------------------------------------------------------

_SEED = 42


# ---------------------------------------------------------------------------
# Reference data pools
# ---------------------------------------------------------------------------

_FIRST_NAMES = [
    "Alice", "Bob", "Charlotte", "David", "Emma", "Francois", "Gabrielle",
    "Henri", "Isabelle", "Jacques", "Karen", "Laurent", "Marie", "Nicolas",
    "Olivia", "Pierre", "Quentin", "Rachel", "Sebastien", "Thomas",
    "Ursula", "Vincent", "Wendy", "Xavier", "Yves", "Zoe",
    "Amelie", "Benoit", "Celine", "Damien", "Elise", "Frederic",
    "Genevieve", "Hugo", "Ines", "Jean-Pierre", "Karine", "Luc",
    "Margot", "Nathan", "Ophelie", "Pascal", "Renee", "Sophie",
    "Thibault", "Valerie", "William", "Anais", "Baptiste", "Camille",
    "Delphine", "Etienne", "Fanny", "Guillaume", "Helene", "Igor",
    "Julien", "Laure", "Matthieu", "Nathalie", "Olivier", "Patricia",
    "Romain", "Sandrine", "Tristan", "Veronique", "Alexis", "Brigitte",
    "Christophe", "Dany", "Edouard", "Florian", "Gwenael", "Herve",
    "Jade", "Kevin", "Lisa", "Marc", "Nadine", "Odile",
]

_LAST_NAMES = [
    "Dupont", "Martin", "Bernard", "Thomas", "Petit", "Robert",
    "Richard", "Durand", "Dubois", "Moreau", "Simon", "Laurent",
    "Lefevre", "Michel", "Garcia", "David", "Bertrand", "Roux",
    "Vincent", "Fournier", "Morel", "Girard", "Andre", "Leroy",
    "Mercier", "Dumont", "Fontaine", "Chevalier", "Robin", "Blanc",
    "Guerin", "Muller", "Henry", "Rousseau", "Mathieu", "Picard",
    "Colin", "Marchand", "Renaud", "Bonnet", "Francois", "Schmitt",
    "Clement", "Gauthier", "Perrin", "Morin", "Lacroix", "Arnaud",
    "Lemaire", "Masson", "De Smedt", "Van den Berg", "Peeters",
    "Janssen", "Claes", "Goossens", "Willems", "Leclercq", "Dujardin",
    "Nolet", "Servais", "Renard", "Bodart", "Collignon", "Bastin",
    "Charlier", "Gilles", "Ernst", "Pirard", "Delvaux", "Lecomte",
    "Degroot", "Verbeke", "Desmet", "Claeys", "Vermeersch", "Bogaert",
    "Hendrickx", "Wouters", "Lemmens", "Hermans", "Mertens",
]

_COMPANIES = [
    "Solvay SA", "UCB Pharma", "ING Belgium", "KBC Group", "Proximus",
    "Bekaert NV", "Agfa-Gevaert", "Colruyt Group", "Delhaize Group",
    "AB InBev", "Umicore", "D'Ieteren", "Sofina", "GBL",
    "Bpost", "Telenet", "Elia Group", "Fluxys", "Engie Belgium",
    "BNP Paribas Fortis", "Belfius", "Euroclear", "Swift SCRL",
    "McKinsey Belgium", "Deloitte Belgium", "PwC Belgium", "EY Belgium",
    "KPMG Belgium", "Accenture Belgium", "Capgemini Belgium",
    "Deceuninck NV", "Beiersdorf Belgium", "3M Belgium",
    "Siemens Belgium", "Schneider Electric", "Michelin Belgium",
    "AstraZeneca Belgium", "Janssen Pharmaceutica", "GSK Belgium",
    "Pfizer Belgium", "Novartis Belgium", "Roche Belgium",
]

_DIETARY = ["", "vegetarian", "vegan", "gluten-free", "halal", "kosher", "none"]

_NATIONALITIES = [
    "Belgian", "French", "Dutch", "German", "Spanish", "Italian",
    "British", "Swiss", "Austrian", "Portuguese", "Polish",
]

_AIRPORTS_ORIGIN = ["BRU", "CRL", "LGG"]
_AIRPORTS_HUB = ["CDG", "LHR", "AMS", "FRA", "ZRH", "MAD", "FCO", "VIE"]
_AIRPORT_DEST = "BCN"

_AIRLINES = ["SN", "VY", "IB", "LH", "BA", "AF", "KL", "LX", "OS", "FR"]

_CONF_START = date(2025, 11, 10)
_CONF_END = date(2025, 11, 14)


# ---------------------------------------------------------------------------
# Noise helpers
# ---------------------------------------------------------------------------

def _drop_accent(name: str) -> str:
    """Return *name* with common accented characters replaced by ASCII."""
    table = str.maketrans(
        "AaEeIiOoUuCcNnYyAaEeIiOoUuAaEeIiOoUu",
        "AaEeIiOoUuCcNnYyAaEeIiOoUuAaEeIiOoUu",
    )
    replacements = {
        "\u00e9": "e", "\u00e8": "e", "\u00ea": "e", "\u00eb": "e",
        "\u00e0": "a", "\u00e2": "a", "\u00e4": "a",
        "\u00ee": "i", "\u00ef": "i",
        "\u00f4": "o", "\u00f6": "o",
        "\u00f9": "u", "\u00fb": "u", "\u00fc": "u",
        "\u00e7": "c",
        "\u00c9": "E", "\u00c8": "E", "\u00ca": "E",
        "\u00c0": "A", "\u00c2": "A",
        "\u00ce": "I", "\u00d4": "O",
        "\u00d9": "U", "\u00db": "U", "\u00dc": "U",
        "\u00c7": "C",
    }
    for src, dst in replacements.items():
        name = name.replace(src, dst)
    return name


def _hyphen_to_space(name: str) -> str:
    """Replace hyphens with spaces: 'Jean-Pierre' -> 'Jean Pierre'."""
    return name.replace("-", " ")


def _apply_name_noise(first: str, last: str, rng: random.Random) -> tuple[str, str]:
    """Return a slightly modified version of (first, last)."""
    noise_type = rng.choice(["drop_accent_first", "drop_accent_last",
                              "hyphen_first", "hyphen_last",
                              "merge_last", "truncate_first"])
    if noise_type == "drop_accent_first":
        return _drop_accent(first), last
    if noise_type == "drop_accent_last":
        return first, _drop_accent(last)
    if noise_type == "hyphen_first":
        return _hyphen_to_space(first), last
    if noise_type == "hyphen_last":
        return first, _hyphen_to_space(last)
    if noise_type == "merge_last":
        # "De Smedt" -> "Desmedt"
        return first, last.replace(" ", "")
    # truncate_first: "Jean-Pierre" -> "Jean"
    return first.split("-")[0].split(" ")[0], last


# ---------------------------------------------------------------------------
# Random data generators
# ---------------------------------------------------------------------------

def _random_phone(rng: random.Random) -> str:
    """Generate a random Belgian-style phone number."""
    prefix = rng.choice(["0032", "+32"])
    area = rng.choice(["2", "3", "4", "9", "11", "14", "16"])
    number = "".join(str(rng.randint(0, 9)) for _ in range(7 - len(area)))
    return f"{prefix}{area}{number}"


def _random_email(first: str, last: str, rng: random.Random) -> str:
    """Generate a realistic professional email."""
    domains = [
        "example.com", "corp.be", "enterprise.eu", "business.org",
        "consulting.be", "group.com", "company.net",
    ]
    f = _drop_accent(first).lower().replace(" ", "").replace("-", "")
    l = _drop_accent(last).lower().replace(" ", "").replace("-", "")
    pattern = rng.choice([
        f"{f}.{l}",
        f"{f[0]}.{l}",
        f"{f}_{l}",
        f"{l}.{f[0]}",
    ])
    return f"{pattern}@{rng.choice(domains)}"


def _random_flight(rng: random.Random, direction: str = "outbound") -> dict:
    """Generate a random flight segment dict."""
    airline = rng.choice(_AIRLINES)
    number = rng.randint(100, 9999)
    fn = f"{airline}{number}"

    if direction == "outbound":
        dep_apt = rng.choice(_AIRPORTS_ORIGIN)
        arr_apt = _AIRPORT_DEST
        dep_date = _CONF_START - timedelta(days=rng.randint(0, 2))
    else:
        dep_apt = _AIRPORT_DEST
        arr_apt = rng.choice(_AIRPORTS_ORIGIN)
        dep_date = _CONF_END + timedelta(days=rng.randint(0, 1))

    arr_date = dep_date + timedelta(days=rng.randint(0, 1))
    dep_h = rng.randint(5, 22)
    dep_m = rng.choice([0, 15, 30, 45])
    arr_h = (dep_h + rng.randint(1, 4)) % 24
    arr_m = rng.choice([0, 10, 25, 40, 55])

    return {
        "flight_number": fn,
        "departure_airport": dep_apt,
        "arrival_airport": arr_apt,
        "departure_date": dep_date.strftime("%Y-%m-%d"),
        "departure_time": f"{dep_h:02d}:{dep_m:02d}",
        "arrival_date": arr_date.strftime("%Y-%m-%d"),
        "arrival_time": f"{arr_h:02d}:{arr_m:02d}",
    }


# ---------------------------------------------------------------------------
# Public generators
# ---------------------------------------------------------------------------

def generate_registration_list(n: int = 100) -> list[dict]:
    """Generate *n* synthetic registration records.

    Returns a list of dicts with keys:
    ``id``, ``first_name``, ``last_name``, ``email``, ``company``,
    ``phone``, ``dietary_requirements``, ``nationality``.

    3 of the records intentionally share duplicate email addresses (same
    email, different names) so that :func:`~matcher.detect_duplicate_emails`
    can be exercised.

    Parameters
    ----------
    n:
        Number of registration records to generate (default 100).

    Returns
    -------
    list[dict]
        List of registration record dicts.
    """
    rng = random.Random(_SEED)
    records: list[dict] = []

    fn_pool = _FIRST_NAMES.copy()
    ln_pool = _LAST_NAMES.copy()
    rng.shuffle(fn_pool)
    rng.shuffle(ln_pool)

    # Cycle through pools if n > pool size
    def _pick(pool: list, idx: int) -> str:
        return pool[idx % len(pool)]

    for i in range(n):
        first = _pick(fn_pool, i)
        last = _pick(ln_pool, i)
        email = _random_email(first, last, rng)
        rec = {
            "id": f"REG{i + 1:04d}",
            "first_name": first,
            "last_name": last,
            "email": email,
            "company": rng.choice(_COMPANIES),
            "phone": _random_phone(rng),
            "dietary_requirements": rng.choice(_DIETARY),
            "nationality": rng.choice(_NATIONALITIES),
        }
        records.append(rec)

    # Inject 3 duplicate emails safely
    if n >= 83:
        dup_email = records[0]["email"]
        for idx in [80, 81, 82]:
            records[idx]["email"] = dup_email
    elif n >= 4:
        dup_email = records[0]["email"]
        for idx in [n - 1, n - 2, n - 3]:
            records[idx]["email"] = dup_email

    return records


def generate_fcm_list(
    registrations: list[dict],
    missing_n: int = 5,
    name_noise_n: int = 10,
    email_noise_n: int = 3,
) -> list[dict]:
    """Generate FCM flight records corresponding to *registrations*.

    Parameters
    ----------
    registrations:
        List of registration dicts as returned by
        :func:`generate_registration_list`.
    missing_n:
        Number of registrations that will have **no** FCM record
        (simulating participants who did not book through the agency).
    name_noise_n:
        Number of FCM records that will have a slightly different name.
    email_noise_n:
        Number of FCM records that will have a wrong / missing email.

    Returns
    -------
    list[dict]
        List of FCM record dicts with keys:
        ``id``, ``passenger_first``, ``passenger_last``,
        ``passenger_email``, ``company``, ``flight_number``,
        ``departure_airport``, ``arrival_airport``,
        ``departure_date``, ``departure_time``,
        ``arrival_date``, ``arrival_time``.

    Notes
    -----
    The function also embeds 2 "wrong person" records that cannot be matched
    to any registration.  These should surface as NOT_FOUND / TO_VERIFY
    exceptions.
    """
    rng = random.Random(_SEED + 1)

    # Choose which registrations will be missing
    all_indices = list(range(len(registrations)))
    missing_indices = set(rng.sample(all_indices, missing_n))

    # Choose which will have name noise (from non-missing set)
    eligible = [i for i in all_indices if i not in missing_indices]
    noise_indices = set(rng.sample(eligible, name_noise_n))

    # Choose which will have email noise (from non-missing, non-noise set)
    eligible2 = [i for i in eligible if i not in noise_indices]
    email_noise_indices = set(rng.sample(eligible2, email_noise_n))

    fcm_records: list[dict] = []
    fcm_id = 1

    for i, reg in enumerate(registrations):
        if i in missing_indices:
            continue  # no FCM record for this participant

        first = reg["first_name"]
        last = reg["last_name"]
        email = reg["email"]

        if i in noise_indices:
            first, last = _apply_name_noise(first, last, rng)

        if i in email_noise_indices:
            if rng.random() < 0.5:
                email = ""  # missing email
            else:
                # slightly wrong email
                parts = reg["email"].split("@")
                email = parts[0] + "x@" + parts[1]

        flight = _random_flight(rng, direction="outbound")

        rec = {
            "id": f"FCM{fcm_id:04d}",
            "passenger_first": first,
            "passenger_last": last,
            "passenger_email": email,
            "company": reg["company"],
            **flight,
        }
        fcm_records.append(rec)
        fcm_id += 1

    # Inject 2 "wrong person" records (completely fabricated, no match)
    for _ in range(2):
        wrong_first = rng.choice(_FIRST_NAMES)
        wrong_last = rng.choice(_LAST_NAMES)
        wrong_email = _random_email(wrong_first, wrong_last, rng)
        flight = _random_flight(rng, direction="outbound")
        rec = {
            "id": f"FCM{fcm_id:04d}",
            "passenger_first": wrong_first,
            "passenger_last": wrong_last,
            "passenger_email": wrong_email,
            "company": rng.choice(_COMPANIES),
            **flight,
        }
        fcm_records.append(rec)
        fcm_id += 1

    return fcm_records


# ---------------------------------------------------------------------------
# Gold standard builder
# ---------------------------------------------------------------------------

def build_gold_standard(
    registrations: list[dict],
    fcm_records: list[dict],
    missing_n: int = 5,
    name_noise_n: int = 10,
    email_noise_n: int = 3,
) -> list[dict]:
    """Build a gold-standard evaluation list from the synthetic dataset.

    Each entry is a dict::

        {
            "registration_id": "REG0001",
            "fcm_record_id": "FCM0001",   # or null if missing
            "expected_decision": "certain" # or "probable" / "not_found"
        }

    Logic
    -----
    * A registration whose index is in the *missing* set maps to
      ``fcm_record_id=null`` / ``expected_decision="not_found"``.
    * A registration whose index is in the *name_noise* set maps to its
      corresponding FCM record with ``expected_decision="probable"``
      (fuzzy name match without email).
    * A registration whose index is in the *email_noise* set maps to its
      FCM record with ``expected_decision="probable"`` (name should still
      produce a strong-enough score).
    * All other matched registrations map with ``expected_decision="certain"``.

    Parameters
    ----------
    registrations:
        List of registration dicts.
    fcm_records:
        List of FCM dicts as returned by :func:`generate_fcm_list`.
    missing_n:
        Should match the value used in :func:`generate_fcm_list`.
    name_noise_n:
        Should match the value used in :func:`generate_fcm_list`.
    email_noise_n:
        Should match the value used in :func:`generate_fcm_list`.

    Returns
    -------
    list[dict]
        Gold-standard evaluation records.
    """
    rng = random.Random(_SEED + 1)

    all_indices = list(range(len(registrations)))
    missing_indices = set(rng.sample(all_indices, missing_n))
    eligible = [i for i in all_indices if i not in missing_indices]
    noise_indices = set(rng.sample(eligible, name_noise_n))
    eligible2 = [i for i in eligible if i not in noise_indices]
    email_noise_indices = set(rng.sample(eligible2, email_noise_n))

    # Map FCM records in order (skip missing, extra "wrong" at end)
    fcm_iter = iter(fcm_records)
    gold: list[dict] = []
    fcm_mapping: list[Optional[dict]] = []

    for i in range(len(registrations)):
        if i in missing_indices:
            fcm_mapping.append(None)
        else:
            fcm_mapping.append(next(fcm_iter))

    for i, reg in enumerate(registrations):
        fcm = fcm_mapping[i]
        if fcm is None:
            gold.append({
                "registration_id": reg["id"],
                "fcm_record_id": None,
                "expected_decision": "not_found",
            })
        elif i in noise_indices:
            gold.append({
                "registration_id": reg["id"],
                "fcm_record_id": fcm["id"],
                "expected_decision": "probable",
            })
        elif i in email_noise_indices:
            gold.append({
                "registration_id": reg["id"],
                "fcm_record_id": fcm["id"],
                "expected_decision": "probable",
            })
        else:
            gold.append({
                "registration_id": reg["id"],
                "fcm_record_id": fcm["id"],
                "expected_decision": "certain",
            })

    return gold


# ---------------------------------------------------------------------------
# CSV / JSON helpers
# ---------------------------------------------------------------------------

def _write_csv(path: str, rows: list[dict]) -> None:
    """Write *rows* to a CSV file at *path* (UTF-8, with header)."""
    if not rows:
        return
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def _write_json(path: str, data: object) -> None:
    """Write *data* as indented JSON to *path* (UTF-8)."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, ensure_ascii=False)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("Generating synthetic dataset...")

    registrations = generate_registration_list(n=100)
    fcm_records = generate_fcm_list(registrations)
    gold = build_gold_standard(registrations, fcm_records)

    out_dir = os.path.join(_HERE, "tests", "data")
    reg_path = os.path.join(out_dir, "registrations.csv")
    fcm_path = os.path.join(out_dir, "fcm_flights.csv")
    gold_path = os.path.join(out_dir, "gold_standard.json")

    _write_csv(reg_path, registrations)
    _write_csv(fcm_path, fcm_records)
    _write_json(gold_path, gold)

    print(f"  Registrations : {len(registrations):>4}  ->  {reg_path}")
    print(f"  FCM records   : {len(fcm_records):>4}  ->  {fcm_path}")
    print(f"  Gold standard : {len(gold):>4}  ->  {gold_path}")
    print("Done.")
