"""
services/mapping_service.py — Column mapping and data normalisation.

Responsibilities:
  - Apply a saved column mapping to raw row data
  - Normalise field values (trim whitespace, parse dates, lower-case emails)
  - Parse and insert source_records rows from a mapped file
"""

from __future__ import annotations

import logging
import re
import uuid
import unicodedata
from datetime import date
from typing import Any, Optional

from supabase import Client

logger = logging.getLogger(__name__)

# Canonical target field names that the rest of the system expects.
# Extended to mirror the client LivaNova master file (feedback: mapping must be
# modeled on the reference master list).
CANONICAL_FIELDS = {
    "id", "first_name", "last_name", "email", "company", "phone",
    "nationality", "dietary_requirements",
    # Profile (from the master file)
    "attendee_category", "job_title", "region", "function", "language",
    "badge_name", "country",
    # ID / travel document
    "date_of_birth", "passport_number", "passport_expiry",
    # Dietary detail (distinct from dietary_requirements)
    "food_allergy_info",
    # Flights
    "departure_date", "return_date", "flight_number",
    "departure_airport", "arrival_airport", "departure_time", "arrival_time",
    "arrival_date", "departure_city", "departure_country",
    "arrival_city", "arrival_country", "traveler_name", "flight_domestic_intl",
    "pnr_code", "airline", "baggage_info",
    # Hotels
    "hotel_name", "check_in_date", "check_out_date", "room_type",
    "early_checkin", "late_checkout",
    # Transfers
    "transfer_type", "pickup_location", "dropoff_location", "pickup_time", "vehicle_type",
    # Activities
    "activity_name",
    # Logistics flags
    "fast_track", "extra_meetings", "headphones_translation",
}

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_DATE_FORMATS = ["%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d", "%m/%d/%Y", "%d.%m.%Y"]


def apply_mapping(raw_row: dict[str, Any], mapping: dict[str, str]) -> dict[str, Any]:
    """
    Apply a column mapping to a single raw data row.

    Parameters
    ----------
    raw_row:
        Dict with source column names as keys.
    mapping:
        Dict of ``{source_column: target_field}``.

    Returns
    -------
    Dict with canonical target field names as keys. Unmapped columns are dropped.
    """
    result: dict[str, Any] = {}
    for source_col, target_field in mapping.items():
        # Accept canonical fields AND user-defined custom fields (any non-empty
        # target). Custom fields are captured in source_records.normalized_data
        # and shown on the participant fiche; they never become participant
        # columns (the consolidation merge whitelists real columns).
        if target_field and source_col in raw_row:
            result[target_field] = raw_row[source_col]
    return result


def normalise_fields(mapped_row: dict[str, Any]) -> dict[str, Any]:
    """
    Normalise field values in a mapped row.

    Normalisation steps:
    - Strip leading/trailing whitespace from all string values
    - Lower-case email addresses
    - Attempt to parse date strings into ISO-8601 (YYYY-MM-DD) format
    - Replace empty strings with ``None``

    Parameters
    ----------
    mapped_row:
        Dict with canonical target field names (output of ``apply_mapping``).

    Returns
    -------
    Dict with normalised values. Invalid values are preserved as-is (exception
    detection in ``exception_service`` will flag them).
    """
    normalised: dict[str, Any] = {}
    for field, value in mapped_row.items():
        if isinstance(value, str):
            value = value.strip()
            if value == "":
                value = None
            elif field == "email":
                value = value.lower()
            elif field.endswith("_date"):
                value = _parse_date(value) or value  # keep original if parse fails
        normalised[field] = value
    return normalised


def _parse_date(raw: str) -> Optional[str]:
    """
    Attempt to parse a date string using several common formats.

    Returns the date in ISO-8601 (``YYYY-MM-DD``) format on success, or
    ``None`` if no format matched.
    """
    from datetime import datetime as dt
    for fmt in _DATE_FORMATS:
        try:
            return dt.strptime(raw, fmt).date().isoformat()
        except ValueError:
            continue
    return None


import math

def clean_nans(val: Any) -> Any:
    """Recursively replace float('nan') or None equivalents with None."""
    if isinstance(val, dict):
        return {k: clean_nans(v) for k, v in val.items()}
    elif isinstance(val, list):
        return [clean_nans(v) for v in val]
    elif isinstance(val, float):
        if math.isnan(val) or not math.isfinite(val):
            return None
    elif val == "NaN" or val == "nan":
        return None
    elif hasattr(val, "__class__") and val.__class__.__name__ in ("float", "double", "float64"):
        try:
            if math.isnan(float(val)):
                return None
        except (ValueError, TypeError):
            pass
    return val


def parse_and_insert_source_records(
    supabase: Client,
    file_id: str,
    event_id: str,
    df_rows: list[dict[str, Any]],
    mapping: dict[str, str],
) -> list[str]:
    """
    Parse raw DataFrame rows, apply mapping + normalisation, and bulk-insert
    into the ``source_records`` table.

    Parameters
    ----------
    supabase:
        Supabase client.
    file_id:
        UUID of the uploaded_file this data originates from.
    event_id:
        UUID of the event.
    df_rows:
        List of raw row dicts from the DataFrame (``df.to_dict(orient="records")``).
    mapping:
        Column mapping from the uploaded_file record.

    Returns
    -------
    List of inserted source_record UUIDs.
    """
    records_to_insert: list[dict[str, Any]] = []

    for i, raw_row in enumerate(df_rows):
        cleaned_raw_row = clean_nans(raw_row)
        mapped = apply_mapping(cleaned_raw_row, mapping)
        normalised = normalise_fields(mapped)
        cleaned_normalised = clean_nans(normalised)
        
        record_id = str(uuid.uuid4())
        records_to_insert.append(
            {
                "id": record_id,
                "file_id": file_id,
                "event_id": event_id,
                "row_index": i,
                "raw_data": cleaned_raw_row,
                "normalized_data": cleaned_normalised,
            }
        )

    # Batch insert in chunks to avoid Supabase request size limits
    chunk_size = 200
    inserted_ids: list[str] = []
    for chunk_start in range(0, len(records_to_insert), chunk_size):
        chunk = records_to_insert[chunk_start : chunk_start + chunk_size]
        try:
            result = supabase.table("source_records").insert(chunk).execute()
            inserted_ids.extend(row["id"] for row in result.data)
        except Exception as exc:
            logger.error(
                "Failed to insert source_records chunk [%d:%d] for file %s: %s",
                chunk_start, chunk_start + chunk_size, file_id, exc,
            )
            raise

    logger.info(
        "Inserted %d source_records for file_id=%s event_id=%s",
        len(inserted_ids), file_id, event_id,
    )
    return inserted_ids


def _normalize_column_name(col: str) -> str:
    """
    Normalize a column name by lowercasing, stripping accents,
    and removing all spaces, underscores, and special characters.
    """
    col = col.lower()
    # Stripping accents
    col = "".join(
        c for c in unicodedata.normalize("NFD", col)
        if unicodedata.category(c) != "Mn"
    )
    # Removing spaces, punctuation, dashes, underscores
    col = re.sub(r"[\s_\-\/\\(\)\[\]\.\,\:\;]+", "", col)
    return col


SYNONYMS: dict[str, list[str]] = {
    "id": ["id", "idparticipant", "code", "codeparticipant", "registrationcode", "ref", "reference", "participantid"],
    "first_name": ["prenom", "first", "firstname", "givenname", "nom1", "nomdebateme"],
    "last_name": ["nom", "last", "lastname", "surname", "familyname", "nomdefamille"],
    "email": ["email", "mail", "courriel", "adressemail", "emailaddress", "emailadr", "contactemail"],
    "company": ["company", "societe", "compagnie", "entreprise", "organisation", "org", "boite", "employer", "employeur"],
    "phone": ["phone", "telephone", "tel", "gsm", "mobile", "cel", "cellulaire", "contactphone"],
    "nationality": ["nationality", "nationalite", "pays", "citizen", "citizenship", "orig"],
    "dietary_requirements": ["dietaryrequirements", "dietary", "regime", "regimealimentaire", "aliment", "food", "allergy", "allergie"],
    
    # Flights
    "departure_date": ["departuredate", "departdate", "datedepart", "outbounddate", "flightdepdate"],
    "return_date": ["returndate", "dateretour", "inbounddate", "flightretdate"],
    "flight_number": ["flightnumber", "flight", "numvol", "novol", "flightno", "numdevol", "flightcode"],
    "departure_airport": ["departureairport", "departairport", "aeroportdepart", "depapt", "depairp", "origairport", "airportofdeparture"],
    "arrival_airport": ["arrivalairport", "arrivairport", "aeroportarrivee", "arrapt", "arrairp", "destairport"],
    "departure_time": ["departuretime", "departtime", "heuredepart", "flightdeptime", "deptime"],
    "arrival_time": ["arrivaltime", "arrivtime", "heurearrivee", "flightarrtime", "arrtime"],
    "pnr_code": ["pnrcode", "pnr", "codepnr", "bookingref", "recordlocator"],
    "airline": ["airline", "compagnie", "compagnieaerienne", "carrier", "aircarrier"],
    "baggage_info": ["baggageinfo", "baggage", "luggage", "infosbagages", "bags"],
    
    # Hotels
    "hotel_name": ["hotelname", "hotel", "nomhotel", "hebergement", "nomdebergement", "villahotel", "villa", "hotelvilla"],
    "check_in_date": ["checkindate", "checkin", "datecheckin", "dateentree", "entree", "arrivalhotel", "hotelarr"],
    "check_out_date": ["checkoutdate", "checkout", "datecheckout", "datesortie", "sortie", "departurehotel", "hoteldep"],
    "room_type": ["roomtype", "room", "chambre", "typechambre", "roomcategory"],
    
    # Transfers
    "transfer_type": ["transfertype", "shuttletype", "typenavette"],
    # NB: bare "depart"/"arrivee" removed — too greedy, they collided with the
    # flight Depart*/Arrival* columns. Keep only pickup/transfer-specific tokens.
    "pickup_location": ["pickuplocation", "lieupriseencharge", "priseencharge", "pickup", "lieudedepart"],
    "dropoff_location": ["dropofflocation", "destination", "dropoff", "lieudarrivee"],
    "pickup_time": ["pickuptime", "heurepriseencharge", "heurepickup", "heurenavette", "shuttletime"],
    "vehicle_type": ["vehicletype", "vehicle", "vehicule", "car", "bus", "voiture", "typevehicule"],
    
    # Activities
    "activity_name": ["activityname", "activity", "activite", "nomactivite", "excursion", "loisir", "programme"],

    # Profile (LivaNova master file)
    "attendee_category": ["attendeecategory", "category", "categorie", "typeparticipant", "participanttype", "attendeetype"],
    "job_title": ["jobtitle", "title", "titre", "poste", "position", "fonctionposte"],
    "region": ["region", "zone", "area", "geo", "geographie"],
    "function": ["function", "fonction", "role", "department", "departement", "pleasespecifyyourfunction"],
    "language": ["language", "langue", "lang", "preferredlanguage", "languepreferee"],
    "badge_name": ["nameonbadge", "badgename", "nombadge", "nomsurbadge", "badge", "nomsurlebadge"],
    "country": ["country", "countryofresidence", "paysresidence", "paysderesidence"],

    # ID / travel document
    "date_of_birth": ["dateofbirth", "datedenaissance", "birthdate", "dob", "naissance"],
    "passport_number": ["passportnumber", "passport", "numeropasseport", "passeport", "nopasseport", "passportno"],
    "passport_expiry": ["expirydateofpassport", "passportexpiry", "expirationpasseport", "passeportvalidite", "validuntil", "expirydate", "dateexpirationpasseport"],

    # Dietary detail
    "food_allergy_info": ["foodallergyinformation", "foodallergyinfo", "foodallergy", "allergyinformation", "allergies", "allergie", "allergieinfo", "foodrestrictions"],

    # Flights (extra)
    "arrival_date": ["arrivaldate", "datearrivee", "dad", "arrivaldate2", "arrdate", "arrivaldatedad"],
    "departure_city": ["departurecity", "departcity", "villedepart", "citydeparture", "depcity"],
    "departure_country": ["departurecountry", "departcountry", "paysdepart", "depcountry"],
    "arrival_city": ["arrivalcity", "arrivcity", "villearrivee", "arrcity", "destinationcity"],
    "arrival_country": ["arrivalcountry", "paysarrivee", "country2", "arrcountry", "destinationcountry"],
    "traveler_name": ["traveler", "traveller", "nomvoyageur", "passengername", "nomsurbillet"],
    "flight_domestic_intl": ["dominternational", "domintl", "domesticinternational", "domesticintl", "domestic", "international"],

    # Hotels (extra)
    "early_checkin": ["earlycheckin", "earlycheckintime", "earlycheckintimeguaranteed", "checkinanticipe"],
    "late_checkout": ["latecheckout", "latecheckouttime", "latecheckouttimeguaranteed", "checkouttardif"],

    # Logistics flags
    "fast_track": ["fasttrack", "fasttrackarrivals", "fasttrackarrival", "coupefile"],
    "extra_meetings": ["extrameetings", "extrameeting", "reunionssupplementaires", "meetings"],
    "headphones_translation": ["headphonestranslation", "headphones", "casquetraduction", "traduction", "casque"],
}


_FLIGHT_NO_RE = re.compile(r"^[A-Z0-9]{2,3}\s*[0-9]{1,4}[A-Z]?$", re.IGNORECASE)
# Content-pattern detectors used to deduce a field from the DATA when the header
# is missing, generic ("Unnamed: 3"), or misspelled.
_PHONE_RE = re.compile(r"^[+(]?\d[\d\s().\-]{6,}$")
_PNR_RE = re.compile(r"^(?=.*[A-Z])(?=.*\d)[A-Z0-9]{5,7}$")
_IATA_RE = re.compile(r"^[A-Z]{3}$")
_TIME_RE = re.compile(r"^\d{1,2}[:hH]\d{2}")
_PASSPORT_RE = re.compile(r"^(?=.*[A-Z])(?=.*\d)[A-Z0-9]{7,10}$")
# Generic/placeholder header names that carry no meaning → rely on content only.
_GENERIC_HEADER_RE = re.compile(r"^(unnamed|column|col|field|colonne|nan|none|na|n/?a)\d*$")

try:
    from rapidfuzz import fuzz as _fuzz
    _HAS_FUZZ = True
except ImportError:  # pragma: no cover
    _HAS_FUZZ = False


def _fuzzy_name_score(norm_col: str, field: str) -> float:
    """Best fuzzy similarity of a (normalised) column name against a field name
    and its synonyms — tolerates spelling mistakes. Returns a 0..0.85 score."""
    if not _HAS_FUZZ or len(norm_col) < 4:
        return 0.0
    candidates = [_normalize_column_name(field)] + [_normalize_column_name(s) for s in SYNONYMS.get(field, [])]
    best = 0.0
    for cand in candidates:
        if len(cand) < 4:
            continue
        r = _fuzz.ratio(norm_col, cand)
        if r > best:
            best = r
    if best >= 90:
        return 0.85
    if best >= 82:
        return 0.62
    return 0.0


def suggest_mapping(columns: list[str], sample_rows: list[dict]) -> dict[str, dict]:
    """
    Analyze column names and sample data to suggest canonical fields mappings.
    Returns:
    {
      col_name: {
        "suggested_field": Optional[str],
        "confidence": float,
        "alternatives": list[str]
      }
    }
    """
    col_candidates: dict[str, list[tuple[str, float]]] = {}
    for col in columns:
        norm_col = _normalize_column_name(col)

        # 1. Gather non-empty values for content checks
        vals = []
        for row in sample_rows:
            val = row.get(col)
            if val is not None:
                val_str = str(val).strip()
                if val_str != "":
                    vals.append(val_str)
                    
        # A generic/placeholder or empty header carries no meaning → deduce from
        # the data only (feedback: "if no column name, deduce from its content").
        header_absent = norm_col == "" or bool(_GENERIC_HEADER_RE.match(norm_col))

        # Content match indicators
        is_email = is_date = is_flight = False
        is_phone = is_pnr = is_iata = is_time = is_passport = False

        if vals:
            n = len(vals)
            is_email = (sum(1 for v in vals if _EMAIL_RE.match(v)) / n) > 0.5
            is_date = (sum(1 for v in vals if _parse_date(v) is not None) / n) > 0.5
            is_flight = (sum(1 for v in vals if _FLIGHT_NO_RE.match(v)) / n) > 0.5
            # exclude date-like values (e.g. 13-11-2025) that also match the phone shape
            is_phone = (not is_date) and (sum(1 for v in vals if _PHONE_RE.match(v)) / n) > 0.5
            is_pnr = (sum(1 for v in vals if _PNR_RE.match(v)) / n) > 0.5
            is_passport = (sum(1 for v in vals if _PASSPORT_RE.match(v)) / n) > 0.5
            is_iata = (sum(1 for v in vals if v.isupper() and _IATA_RE.match(v)) / n) > 0.5
            is_time = (sum(1 for v in vals if _TIME_RE.match(v)) / n) > 0.5

        # 2. Evaluate name-based scores for each canonical field (skipped when the
        #    header is generic/absent — then only content signals decide).
        field_scores = {}
        for field in CANONICAL_FIELDS:
            score = 0.0
            if not header_absent:
                norm_field = _normalize_column_name(field)
                if norm_col == norm_field:
                    score = 0.95
                else:
                    for syn in SYNONYMS.get(field, []):
                        norm_syn = _normalize_column_name(syn)
                        if norm_col == norm_syn:
                            score = max(score, 0.90)
                            break
                        elif norm_col.startswith(norm_syn) or norm_col.endswith(norm_syn) or norm_syn in norm_col:
                            score = max(score, 0.60)
                        elif norm_syn.startswith(norm_col) or norm_col in norm_syn:
                            score = max(score, 0.40)
                    # Fuzzy match to tolerate spelling mistakes in the header
                    score = max(score, _fuzzy_name_score(norm_col, field))
            field_scores[field] = score

        # 3. Content-based adjustments/boosts (strong, mutually-exclusive signals)
        if is_email:
            field_scores["email"] = max(field_scores.get("email", 0.0), 0.95)
            for f in field_scores:
                if f != "email":
                    field_scores[f] *= 0.1
        elif is_flight:
            field_scores["flight_number"] = max(field_scores.get("flight_number", 0.0), 0.95)
            for f in field_scores:
                if f != "flight_number":
                    field_scores[f] *= 0.1
        elif is_phone:
            field_scores["phone"] = max(field_scores.get("phone", 0.0), 0.92)
            for f in field_scores:
                if f != "phone":
                    field_scores[f] *= 0.1
        elif is_date:
            date_fields = {
                "check_in_date", "check_out_date", "departure_date", "return_date",
                "departure_time", "arrival_time", "pickup_time",
                "arrival_date", "date_of_birth", "passport_expiry",
            }
            for f in field_scores:
                if f in date_fields:
                    field_scores[f] = max(field_scores[f], 0.95) if field_scores[f] > 0.0 else 0.5
                else:
                    field_scores[f] *= 0.1

        # 4. Weaker content signals — only *raise* scores (used mainly to deduce
        #    a field for an unnamed/misspelled column; a real header still wins).
        if is_pnr and not is_flight:
            field_scores["pnr_code"] = max(field_scores.get("pnr_code", 0.0), 0.6 if header_absent else 0.5)
        if is_passport and not is_pnr:
            field_scores["passport_number"] = max(field_scores.get("passport_number", 0.0), 0.55 if header_absent else 0.4)
        if is_iata:
            field_scores["departure_airport"] = max(field_scores.get("departure_airport", 0.0), 0.55)
            field_scores["arrival_airport"] = max(field_scores.get("arrival_airport", 0.0), 0.5)
        if is_time and not is_date:
            for f in ("departure_time", "arrival_time", "pickup_time"):
                field_scores[f] = max(field_scores.get(f, 0.0), 0.5)
                    
        # Collect this column's candidate (field, score) pairs; the actual
        # suggestion is decided globally below.
        col_candidates[col] = sorted(
            [(f, s) for f, s in field_scores.items() if s >= 0.1],
            key=lambda x: x[1], reverse=True,
        )

    # 5. Global assignment — give each canonical field to at most ONE column
    #    (the highest-confidence one); other columns fall back to their next
    #    free candidate. Prevents two columns being suggested the same target.
    ranked_cols = sorted(
        columns,
        key=lambda c: (col_candidates[c][0][1] if col_candidates[c] else 0.0),
        reverse=True,
    )
    used_fields: set[str] = set()
    assigned: dict[str, tuple[str, float]] = {}
    for col in ranked_cols:
        for field, score in col_candidates[col]:
            if score >= 0.5 and field not in used_fields:
                assigned[col] = (field, score)
                used_fields.add(field)
                break

    suggestions = {}
    for col in columns:
        cands = col_candidates[col]
        if col in assigned:
            field, score = assigned[col]
            suggestions[col] = {
                "suggested_field": field,
                "confidence": round(score, 2),
                "alternatives": [f for f, s in cands if s >= 0.3 and f != field][:5],
            }
        else:
            suggestions[col] = {
                "suggested_field": None,
                "confidence": 0.0,
                "alternatives": [f for f, s in cands if s >= 0.3][:5],
            }
    return suggestions
