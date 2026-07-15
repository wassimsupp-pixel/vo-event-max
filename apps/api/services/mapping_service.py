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
        if target_field in CANONICAL_FIELDS and source_col in raw_row:
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
    "departure_date": ["departuredate", "datedepart", "outbounddate", "flightdepdate"],
    "return_date": ["returndate", "dateretour", "inbounddate", "flightretdate"],
    "flight_number": ["flightnumber", "numvol", "novol", "flightno", "numdevol", "flightcode"],
    "departure_airport": ["departureairport", "aeroportdepart", "depapt", "depairp", "origairport", "airportofdeparture"],
    "arrival_airport": ["arrivalairport", "aeroportarrivee", "arrapt", "arrairp", "destairport"],
    "departure_time": ["departuretime", "heuredepart", "flightdeptime", "deptime", "datedepart"],
    "arrival_time": ["arrivaltime", "heurearrivee", "flightarrtime", "arrtime", "datearrivee", "retdate"],
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
    "pickup_location": ["pickuplocation", "lieupriseencharge", "priseencharge", "depart", "pickup", "lieudedepart"],
    "dropoff_location": ["dropofflocation", "destination", "lieuarrivee", "arrivee", "dropoff", "lieudarrivee"],
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
    "departure_city": ["departurecity", "villedepart", "citydeparture", "depcity"],
    "departure_country": ["departurecountry", "paysdepart", "depcountry"],
    "arrival_city": ["arrivalcity", "villearrivee", "arrcity", "destinationcity"],
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
    suggestions = {}
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
                    
        # Content match indicators
        is_email = False
        is_date = False
        is_flight = False
        
        if vals:
            email_count = sum(1 for v in vals if _EMAIL_RE.match(v))
            is_email = (email_count / len(vals)) > 0.5
            
            date_count = sum(1 for v in vals if _parse_date(v) is not None)
            is_date = (date_count / len(vals)) > 0.5
            
            flight_count = sum(1 for v in vals if _FLIGHT_NO_RE.match(v))
            is_flight = (flight_count / len(vals)) > 0.5
            
        # 2. Evaluate scores for each canonical field
        field_scores = {}
        for field in CANONICAL_FIELDS:
            score = 0.0
            norm_field = _normalize_column_name(field)
            
            # Exact matches
            if norm_col == norm_field:
                score = max(score, 0.95)
            else:
                # Check synonyms
                for syn in SYNONYMS.get(field, []):
                    norm_syn = _normalize_column_name(syn)
                    if norm_col == norm_syn:
                        score = max(score, 0.90)
                        break
                    elif norm_col.startswith(norm_syn) or norm_col.endswith(norm_syn) or norm_syn in norm_col:
                        score = max(score, 0.60)
                    elif norm_syn.startswith(norm_col) or norm_col in norm_syn:
                        score = max(score, 0.40)
            field_scores[field] = score
            
        # 3. Content-based adjustments/boosts
        if is_email:
            field_scores["email"] = max(field_scores.get("email", 0.0), 0.95)
            # de-boost all others
            for f in field_scores:
                if f != "email":
                    field_scores[f] *= 0.1
        elif is_date:
            date_fields = {
                "check_in_date", "check_out_date", "departure_date", "return_date",
                "departure_time", "arrival_time", "pickup_time",
                "arrival_date", "date_of_birth", "passport_expiry",
            }
            for f in field_scores:
                if f in date_fields:
                    if field_scores[f] > 0.0:
                        field_scores[f] = max(field_scores[f], 0.95)
                    else:
                        field_scores[f] = 0.5
                else:
                    field_scores[f] *= 0.1
        elif is_flight:
            field_scores["flight_number"] = max(field_scores.get("flight_number", 0.0), 0.95)
            for f in field_scores:
                if f != "flight_number":
                    field_scores[f] *= 0.1
                    
        # 4. Filter, sort, and format results
        candidates = []
        for field, score in field_scores.items():
            if score >= 0.1:
                candidates.append((field, score))
        candidates.sort(key=lambda x: x[1], reverse=True)
        
        suggested_field = None
        confidence = 0.0
        alternatives = []
        
        if candidates:
            # Check if top candidate meets confidence threshold
            if candidates[0][1] >= 0.5:
                suggested_field = candidates[0][0]
                confidence = round(candidates[0][1], 2)
                # alternatives are other candidates with score >= 0.3
                alternatives = [f for f, s in candidates[1:] if s >= 0.3]
            else:
                suggested_field = None
                confidence = 0.0
                alternatives = [f for f, s in candidates if s >= 0.3]
                
        suggestions[col] = {
            "suggested_field": suggested_field,
            "confidence": confidence,
            "alternatives": alternatives
        }
        
    return suggestions
