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

_BOOLEAN_VALUES = {"yes", "no", "oui", "non", "y", "n", "true", "false", "1", "0", "x", "✓", "✗"}

# A bare "Type" header (no synonym recognizes it — SYNONYMS["transfer_type"]
# only lists "transfertype"/"shuttletype"/"typenavette") is how real transfer
# files actually label the arrival/departure column. Left unrecognized, the
# extraction step falls back to "arrival" for every row regardless of what the
# file said — a departure transfer silently became a duplicate arrival one.
# Detecting it from VALUES ("Arrivee"/"Depart"/"Retour"…) rather than from the
# single generic word "Type" avoids colliding with room_type/vehicle_type,
# which use the same header but hold completely different values.
_TRANSFER_DIR_VALUES = {
    "arrivee", "arrival", "arrivees", "arrivals", "arrivee groupe",
    "depart", "departure", "departs", "departures",
    "retour", "return", "retours", "returns",
    "aller", "outbound", "outbound transfer", "inbound", "inbound transfer",
}


def _strip_accents_lower(s: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFD", s.strip().lower())
        if unicodedata.category(c) != "Mn"
    )

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_DATE_FORMATS = ["%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d", "%m/%d/%Y", "%d.%m.%Y"]

# Values that LOOK like data but mean "there is no data here". Travel agencies
# redact PII in their exports (FCM writes "SECURED DATA" in the email and phone
# columns), and rosters are full of "N/A" / "TBC" / "-".
#
# Treating them as real values is actively harmful, not just cosmetic:
#   * the identity engine deduplicates by email, so two different travellers both
#     carrying "secured data" would be merged into ONE fiche;
#   * every one of them raises a bogus "Format invalide" exception.
# Mapping them to None is not a modification of the client's data — it is
# refusing to mistake a redaction marker for a value. The field then shows up
# where it belongs: in "Champs manquants".
_PLACEHOLDER_VALUES = {
    "secured data", "secured", "data secured", "confidential", "confidentiel",
    "masked", "redacted", "hidden", "protected", "private", "restricted",
    "not available", "not provided", "not applicable", "non disponible",
    "non communique", "non communiqué", "n/a", "n.a.", "na", "nil", "none",
    "null", "unknown", "inconnu", "tbc", "tba", "tbd", "to be confirmed",
    "a definir", "à définir", "-", "--", "---", "?", "??", "x", "xx", "xxx",
    "xxxx", "no email", "noemail", "no phone", "sans email", "sans mail",
}

# Deliberately narrow. Only fields where a placeholder does real damage — they
# key the identity engine or trip the format validator — and where no legitimate
# value collides with the list above.
#
# `nationality` is EXCLUDED on purpose: "NA" is the ISO code for Namibia, so
# scrubbing it would silently erase a real nationality. Same reasoning for
# `company` and any free-text note. Better a harmless "N/A" left visible than a
# genuine value destroyed — the engine must never lose client data.
_PLACEHOLDER_SENSITIVE_FIELDS = {
    "email", "phone", "first_name", "last_name", "traveler_name", "badge_name",
}


def is_placeholder(value: Any) -> bool:
    """True when a cell means 'no data' despite being non-empty."""
    s = str(value or "").strip().lower()
    if not s:
        return False
    # Collapse inner whitespace/punctuation noise ("SECURED  DATA", "N / A").
    s = re.sub(r"\s+", " ", s)
    return s in _PLACEHOLDER_VALUES or re.sub(r"[\s./]", "", s) in _PLACEHOLDER_VALUES


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
        # An identifier column must never hold a boolean/form value ("Yes"/"No"):
        # matching on such a shared value collapses everyone onto one participant
        # and contaminates their flights/hotels. Drop it.
        if field in ("id", "participant_id") and str(value or "").strip().lower() in _BOOLEAN_VALUES:
            value = None
        # A redaction marker ("SECURED DATA") or a filler ("N/A") is an ABSENCE
        # of data, not data. Left as-is it would key the identity engine and
        # merge unrelated people. See _PLACEHOLDER_VALUES.
        if field in _PLACEHOLDER_SENSITIVE_FIELDS and is_placeholder(value):
            value = None
        normalised[field] = value
    return normalised


def _parse_date(raw: str) -> Optional[str]:
    """
    Attempt to parse a date string using several common formats.

    Returns the date in ISO-8601 (``YYYY-MM-DD``) format on success, or
    ``None`` if no format matched.
    """
    from datetime import datetime as dt
    raw = str(raw).strip()
    # Drop a trailing time component ("2026-02-09 00:00:00" / "…T00:00:00").
    core = re.split(r"[T ]", raw, maxsplit=1)[0]
    for fmt in _DATE_FORMATS:
        try:
            return dt.strptime(core, fmt).date().isoformat()
        except ValueError:
            continue
    # Last resort: a full ISO datetime with time/zone.
    try:
        return dt.fromisoformat(raw.replace("Z", "+00:00")).date().isoformat()
    except ValueError:
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
    sheet_key: str = "0",
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

        # DETERMINISTIC id per (file, sheet, row): re-consolidations UPSERT the
        # same rows instead of stacking a fresh full copy per run. Stale copies
        # kept pre-repair normalized_data (junk passports…) and inflated every
        # count. participant_id is NOT in the payload, so links survive updates.
        record_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"vo-sr:{file_id}:{sheet_key}:{i}"))
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

    # Batch upsert in chunks to avoid Supabase request size limits
    chunk_size = 200
    inserted_ids: list[str] = []
    for chunk_start in range(0, len(records_to_insert), chunk_size):
        chunk = records_to_insert[chunk_start : chunk_start + chunk_size]
        try:
            result = supabase.table("source_records").upsert(chunk).execute()
            inserted_ids.extend(row["id"] for row in result.data)
        except Exception as exc:
            logger.error(
                "Failed to upsert source_records chunk [%d:%d] for file %s: %s",
                chunk_start, chunk_start + chunk_size, file_id, exc,
            )
            raise

    logger.info(
        "Upserted %d source_records for file_id=%s event_id=%s",
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
    # COMBINED name columns. These MUST land here and not in last_name: the
    # consolidation splits traveler_name into first+last, whereas a value routed
    # to last_name is stored verbatim — which is how "MONTOYA HURTADO/MARÍA"
    # ended up as a surname with no given name on 292 fiches.
    "traveler_name": ["traveler", "traveller", "nomvoyageur", "passengername", "nomsurbillet",
                      "fullname", "name", "nomcomplet", "nomprenom", "prenomnom",
                      "guestname", "attendeename", "participantname", "passenger",
                      "nametravel", "completename", "nometprenom"],
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
        is_phone = is_pnr = is_iata = is_time = is_passport = is_boolean = False
        is_transfer_dir = False

        if vals:
            n = len(vals)
            is_boolean = (sum(1 for v in vals if v.strip().lower() in _BOOLEAN_VALUES) / n) > 0.7
            is_email = (sum(1 for v in vals if _EMAIL_RE.match(v)) / n) > 0.5
            is_date = (sum(1 for v in vals if _parse_date(v) is not None) / n) > 0.5
            is_flight = (sum(1 for v in vals if _FLIGHT_NO_RE.match(v)) / n) > 0.5
            # exclude date-like values (e.g. 13-11-2025) that also match the phone shape
            is_phone = (not is_date) and (sum(1 for v in vals if _PHONE_RE.match(v)) / n) > 0.5
            is_pnr = (sum(1 for v in vals if _PNR_RE.match(v)) / n) > 0.5
            is_passport = (sum(1 for v in vals if _PASSPORT_RE.match(v)) / n) > 0.5
            is_iata = (sum(1 for v in vals if v.isupper() and _IATA_RE.match(v)) / n) > 0.5
            is_time = (sum(1 for v in vals if _TIME_RE.match(v)) / n) > 0.5
            is_transfer_dir = (sum(1 for v in vals if _strip_accents_lower(v) in _TRANSFER_DIR_VALUES) / n) > 0.5

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

        # Header-only scores, kept before the content boosts below so a column
        # whose NAME actually designates the field can outrank one that merely
        # LOOKS like it by content (see the header-priority bonus in step 4b).
        name_scores = dict(field_scores)

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
        elif is_transfer_dir:
            field_scores["transfer_type"] = max(field_scores.get("transfer_type", 0.0), 0.9)
            for f in field_scores:
                if f != "transfer_type":
                    field_scores[f] *= 0.1

        # 4. Weaker content signals — only *raise* scores (used mainly to deduce
        #    a field for an unnamed/misspelled column; a real header still wins).
        if is_pnr and not is_flight:
            field_scores["pnr_code"] = max(field_scores.get("pnr_code", 0.0), 0.6 if header_absent else 0.5)
        if is_passport and not is_pnr:
            field_scores["passport_number"] = max(field_scores.get("passport_number", 0.0), 0.55 if header_absent else 0.4)
        # A 3-uppercase-letter value LOOKS like an IATA airport code, but so do
        # many free-text tokens ("VIP", "N/A", "CEO"). Only map to an airport
        # field when the header has NO other meaning (blank/unnamed) or actually
        # hints at a location — otherwise a Notes/Comment column would pollute
        # the flight data.
        if is_iata and (header_absent or re.search(r"airport|aeroport|dep|arr|from|to|city|ville|origin|destination|vol|flight", norm_col)):
            field_scores["departure_airport"] = max(field_scores.get("departure_airport", 0.0), 0.55)
            field_scores["arrival_airport"] = max(field_scores.get("arrival_airport", 0.0), 0.5)
        if is_time and not is_date:
            for f in ("departure_time", "arrival_time", "pickup_time"):
                field_scores[f] = max(field_scores.get(f, 0.0), 0.5)

        # A Yes/No (boolean) column must never be proposed as an identifier —
        # it would collapse everyone sharing the value onto one participant.
        if is_boolean:
            field_scores["id"] = 0.0
            field_scores["participant_id"] = 0.0

        # 4b. HEADER PRIORITY — a column whose name actually designates the field
        # must outrank a column that only LOOKS like it by content. Without this,
        # a "Conf #" of 9 digits scored 0.92 as a phone (content) and TIED with the
        # real "Telephone" column (0.90 name → 0.92), so the raw column order
        # decided: the confirmation number stole `phone`, the real phone fell into
        # a custom field, and every participant present in two files raised a
        # DATA_CONFLICT on phone.
        for _f, _ns in name_scores.items():
            if _ns >= 0.6 and field_scores.get(_f, 0.0) > 0.0:
                field_scores[_f] = min(1.0, field_scores[_f] + 0.06)

        # Identity-critical date fields require HEADER evidence — they must
        # never be deduced from date-looking content alone, or a leftover date
        # column ("Depart Date6") falls back onto passport_expiry and poisons
        # every participant with fake expired passports.
        _col_l = str(col).lower()

        # A confirmation / booking reference is a bare digit string that matches
        # the phone shape but is NOT a phone number.
        if re.search(r"\b(conf|booking|reserv|dossier|folio|voucher|r[ée]f)", _col_l) and not re.search(
            r"\b(phone|t[ée]l|mobile|gsm|portable)", _col_l
        ):
            field_scores["phone"] = 0.0

        # "Nom de l'hôtel" / "Nom de la chambre" / "Nom compagnie": the generic
        # synonym "nom" ties with the specific field, and the raw column order
        # would decide — putting the HOTEL name into the participant's surname.
        # A header naming another entity is never the person's name.
        if re.search(r"h[oô]tel|chambre|\broom\b|compagnie|airline|agence", _col_l):
            for _pf in ("last_name", "first_name", "traveler_name", "badge_name"):
                field_scores[_pf] = 0.0
        if "passport_expiry" in field_scores and not re.search(r"pass|expir|valid", _col_l):
            field_scores["passport_expiry"] = 0.0
        if "date_of_birth" in field_scores and not re.search(r"birth|dob|naiss|n[ée] le", _col_l):
            field_scores["date_of_birth"] = 0.0

        # An administrative/system metadata header ("Registration Date",
        # "Date d'inscription", "Submission Date"...) must never be
        # content-boosted into a TRAVEL date/time field just because its
        # values happen to look like dates — a leftover registration
        # timestamp is not a flight arrival_date. Genuinely blank/generic
        # headers are exempt: content-only inference must still work for
        # unnamed columns (feedback: "if no column name, deduce from content").
        if not header_absent and _ADMIN_DATE_HDR_RE.search(_col_l):
            for _tf in _TRAVEL_DATE_TIME_FIELDS:
                field_scores[_tf] = 0.0

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


# ---------------------------------------------------------------------------
# Fully automatic mapping (no human step)
# ---------------------------------------------------------------------------

# Canonical fields that hold SEVERAL identities merged in one column and are
# split downstream (first_name + last_name). Flagged as "needs split" so the
# review UI can make the split transparent.
_COMBINED_NAME_FIELDS = {"traveler_name"}
_AI_FORBIDDEN_FIELDS = ("passport_expiry", "date_of_birth", "id", "participant_id")


def ai_refine_mapping_detailed(
    columns: list[str],
    sample_rows: list[dict],
    already_mapped: dict[str, str],
) -> dict[str, dict]:
    """
    Best-effort LLM pass over the columns the heuristics could NOT identify.
    Returns ``{column: {"field": <canonical|None>, "confidence": 0-100,
    "needs_split": bool}}``. Silent no-op ({}) when the AI is unavailable or the
    call fails — the heuristic mapping stands. Identity/sensitive fields stay
    heuristic-only. A field is never assigned to two columns.
    """
    from services import ai_service

    unmapped = [c for c in columns if c not in already_mapped]
    if not unmapped or not ai_service.ai_available():
        return {}
    try:
        free_fields = sorted(CANONICAL_FIELDS - set(already_mapped.values()))
        samples = {
            c: [str(r.get(c) or "")[:40] for r in sample_rows[:3] if r.get(c) not in (None, "")]
            for c in unmapped[:20]
        }
        prompt = (
            "You map spreadsheet columns of an event-management file to canonical fields.\n"
            f"Available fields: {free_fields}\n"
            "Columns with sample values:\n"
            + "\n".join(f"- {c!r}: {v}" for c, v in samples.items())
            + "\n\nFor EACH column give the single best field (or null if none fits), a "
            "confidence 0-100, and needs_split=true when ONE column holds several "
            "identities merged together — e.g. a full name 'Last First', 'Nom Prénom' or "
            "'Last/First' that should be split into first_name + last_name. "
            "Never assign the same field to two columns; if two could match one field, "
            "pick the most likely and set the other to null. Never use 'passport_expiry' "
            "or 'date_of_birth' unless the column NAME clearly says so.\n"
            'Return ONLY JSON: {"columns":[{"column":"...","field":"<field|null>",'
            '"confidence":0-100,"needs_split":true|false}]}'
        )
        # Runs in the background (upload returns instantly), so a reasoning model
        # is fine here. 60s covers a ~28s mapping plus headroom for wide files;
        # heuristics + catch-all already guarantee a complete mapping if it times out.
        data = ai_service.ai_json(prompt, timeout_s=60.0)
        items = data.get("columns") if isinstance(data, dict) else (data if isinstance(data, list) else None)
        if not isinstance(items, list):
            return {}

        out: dict[str, dict] = {}
        used = set(already_mapped.values())
        for it in items:
            if not isinstance(it, dict):
                continue
            col = it.get("column")
            if col not in unmapped:
                continue
            try:
                conf = max(0.0, min(100.0, float(it.get("confidence", 0) or 0)))
            except (TypeError, ValueError):
                conf = 0.0
            entry = {"field": None, "confidence": conf, "needs_split": bool(it.get("needs_split"))}
            field = it.get("field")
            if (
                isinstance(field, str) and field in free_fields
                and field not in used and field not in _AI_FORBIDDEN_FIELDS
            ):
                entry["field"] = field
                used.add(field)
            out[col] = entry
        mapped = {c: d for c, d in out.items() if d["field"]}
        if mapped:
            logger.info("AI mapping resolved %d extra column(s): %s", len(mapped), {c: d["field"] for c, d in mapped.items()})
        return out
    except Exception as exc:
        logger.warning("AI mapping refinement skipped: %s", exc)
        return {}


def ai_refine_mapping(
    columns: list[str],
    sample_rows: list[dict],
    already_mapped: dict[str, str],
) -> dict[str, str]:
    """Back-compat thin wrapper: {column: field} for the columns the LLM mapped."""
    detailed = ai_refine_mapping_detailed(columns, sample_rows, already_mapped)
    return {c: d["field"] for c, d in detailed.items() if d.get("field")}


def _custom_field_key(col: str, used_targets: set[str]) -> Optional[str]:
    """
    Turn a leftover column header into a SAFE custom-field key so its data is
    preserved (never silently dropped). The key is guaranteed non-canonical (so
    it surfaces as a custom column, never overwriting a real field) and unique.
    """
    raw = str(col or "").strip()
    if not raw:
        return None
    low = raw.lower()
    # Nameless / index columns keep their data under a readable generic label.
    if re.fullmatch(r"(unnamed|column|colonne|col)[\s:_\-.]*\d*", low) or re.fullmatch(r"\d+", low):
        raw = "Info"
    key = raw
    # Must not collide with a canonical field name (would populate that field).
    if key in CANONICAL_FIELDS:
        key = f"{raw} (info)"
    base, i = key, 2
    while key in used_targets or key in CANONICAL_FIELDS:
        key = f"{base} ({i})"
        i += 1
    return key


# Word-anchored on purpose: an unanchored "tel" also matches "ho-TEL", which would
# remap the hotel column onto `phone` and wipe the hotel data.
_CONF_HDR_RE = re.compile(r"\b(conf|booking|reserv|dossier|folio|voucher|r[ée]f)", re.I)
_PHONE_HDR_RE = re.compile(r"\b(phone|t[ée]l|mobile|gsm|portable)", re.I)
_HOTEL_HDR_RE = re.compile(r"h[oô]tel", re.I)
# A header naming an ADMINISTRATIVE timestamp — when the person registered/
# submitted the form, not a travel event — must never be mistaken for a
# flight/hotel date just because its values look date-shaped. "Registration
# Date" -> arrival_date fed a fake, weeks-before-the-event arrival into every
# participant from that file (false DATE_INCOHERENCE + DATA_CONFLICT noise).
_ADMIN_DATE_HDR_RE = re.compile(
    r"regist|inscri|submi|soumis|signup|creat|updat|modifi|statut|status|horodat|timestamp", re.I
)
_TRAVEL_DATE_TIME_FIELDS = {
    "arrival_date", "departure_date", "return_date",
    "check_in_date", "check_out_date",
    "arrival_time", "departure_time", "pickup_time",
    "date_of_birth", "passport_expiry",
}
# A transfer file carries no hotel data at all — a column landing on one of
# these is always a mis-mapping, never a legitimate reading. Split by shape:
# check_in_date/check_out_date are genuinely DATE-shaped, so a misplaced one
# belongs on the transfer's own date field. hotel_name is TEXT-shaped — on a
# transfer file it almost always names the pickup/dropoff VENUE, not a date
# (see rule 6 below). room_type/early_checkin/late_checkout have no reliable
# transfer equivalent and are only ever demoted, never redirected.
_HOTEL_DATE_FIELDS = {"check_in_date", "check_out_date"}
_HOTEL_ONLY_FIELDS = {"check_in_date", "check_out_date", "room_type", "hotel_name", "early_checkin", "late_checkout"}
# A bare "Aéroport"/"Airport" header, with no depart/arrivée qualifier, is how
# real transfer files commonly label their sole location column (the
# direction lives in the separate "Type" column instead) — but no synonym in
# SYNONYMS recognizes it (only "aeroportdepart"/"aeroportarrivee" do), so it
# is left as an unmapped custom field by suggest_mapping.
_BARE_AIRPORT_HDR_RE = re.compile(r"^(a[eé]roport|airport)$", re.I)


def repair_stored_mappings(event_id: str, supabase) -> int:
    """
    Self-heal mis-mappings already baked into a file's stored ``column_mapping``.
    Those are reused verbatim on every consolidation, so fixing the heuristics
    alone would never clear them. Repairs:
      1. a confirmation/reference column holding ``phone`` (a "Conf #" of 9 digits
         looked like a phone and stole the field from the real "Telephone"
         column — the cause of the DATA_CONFLICT flood);
      2. gives ``phone`` back to the column actually named phone/téléphone;
      3. a hotel-name column sitting on the participant's name;
      4. a transfer file's direction column ("Type") left unmapped;
      5. an administrative timestamp mapped onto a travel date/time field;
      6. a transfer file's date column mapped onto a hotel-only field;
      7. a transfer file's sole, unqualified "Aéroport" column left unmapped;
      8. a bare "Country"/"Pays" column left on the unused `country` rich
         field when no column maps to `nationality` at all.
    Returns the number of files repaired.
    """
    fixed = 0
    try:
        files = supabase.table("uploaded_files").select("id, source_type, column_mapping").eq("event_id", event_id).execute().data or []
    except Exception as exc:
        logger.warning("Could not load files for mapping repair: %s", exc)
        return 0

    for f in files:
        cm = f.get("column_mapping")
        if not isinstance(cm, dict) or not cm:
            continue
        new = dict(cm)
        changed = False

        # 1. A confirmation / reference column is not a phone number.
        for col, tgt in list(new.items()):
            if tgt == "phone" and _CONF_HDR_RE.search(str(col)) and not _PHONE_HDR_RE.search(str(col)):
                new[col] = str(col)          # keep its data as a custom field
                changed = True

        # 2. Hand `phone` back to the column that actually names it.
        if "phone" not in set(new.values()):
            for col, tgt in list(new.items()):
                if _PHONE_HDR_RE.search(str(col)) and tgt != "phone":
                    new[col] = "phone"
                    changed = True
                    break

        # 3. A hotel-name column must never sit on the person's name.
        for col, tgt in list(new.items()):
            if tgt in ("last_name", "first_name", "traveler_name") and _HOTEL_HDR_RE.search(str(col)):
                new[col] = "hotel_name" if "hotel_name" not in set(new.values()) else str(col)
                changed = True

        # 4. A transfer file's direction column, header-named just "Type" (no
        #    synonym recognizes a bare "Type" — see _TRANSFER_DIR_VALUES), was
        #    left unmapped and fell into the custom-field catch-all. Every
        #    transfer then silently defaulted to "arrival" regardless of what
        #    the file actually said, so a departure transfer duplicated as a
        #    second, wrongly-directioned arrival one. Detect it from the
        #    ALREADY-IMPORTED rows' values, the same way suggest_mapping now
        #    does for new imports.
        if f.get("source_type") == "transfer" and "transfer_type" not in set(new.values()):
            try:
                sample = (
                    supabase.table("source_records")
                    .select("raw_data")
                    .eq("file_id", f["id"])
                    .limit(20)
                    .execute()
                    .data or []
                )
                for col in list(new.keys()):
                    vals = [
                        str(r["raw_data"][col]).strip()
                        for r in sample
                        if r.get("raw_data") and r["raw_data"].get(col) not in (None, "")
                    ]
                    if vals and sum(1 for v in vals if _strip_accents_lower(v) in _TRANSFER_DIR_VALUES) / len(vals) > 0.5:
                        new[col] = "transfer_type"
                        changed = True
                        break
            except Exception as exc:
                logger.warning("Transfer-direction mapping repair failed for file %s: %s", f["id"], exc)

        # 5. An administrative/system metadata column ("Registration Date",
        #    "Registration Time", "Date d'inscription"...) must never sit on
        #    a TRAVEL date/time field — it's when the person registered on
        #    the platform, not a flight/hotel/transfer date. A mapping stored
        #    before this guard existed silently fed a fake arrival_date/
        #    departure_time into every participant from that file, causing
        #    false DATE_INCOHERENCE and DATA_CONFLICT exceptions.
        for col, tgt in list(new.items()):
            if tgt in _TRAVEL_DATE_TIME_FIELDS and _ADMIN_DATE_HDR_RE.search(str(col)):
                new[col] = str(col)          # keep its data as a custom field
                changed = True

        # 6. A transfer file's column landing on a HOTEL-only field is always
        #    wrong — the file has no hotel data. A single ambiguous "Date"
        #    header (direction lives in "Type", not here) got mapped to
        #    check_in_date by mistake once, was "remembered" org-wide, and
        #    silently reapplied verbatim to a real event's real transfer
        #    import: 0 of 600 rows extracted, because check_in_date is never
        #    checked as a date source by the transfer-extraction gate
        #    (2026-07-21 audit).
        #
        #    hotel_name needs a DIFFERENT fix, not the same one: it is
        #    TEXT-shaped, not date-shaped. Reusing the date-column fallback
        #    for it (2026-07-22 regression) stuffed a venue name like "VOAI
        #    Diamond Head Conference Hotel" into departure_date — a
        #    nonsensical, unparseable "date de départ" that fired a fresh
        #    INVALID_FORMAT exception per row — while the real pickup/dropoff
        #    field it should have gone to stayed empty, so transfers kept
        #    failing has_location_signal and the count of "sans transfert"
        #    never moved despite the file being fully imported. On a
        #    transfer, a "Hotel" column almost always names the pickup or
        #    dropoff VENUE, so redirect it there instead.
        if f.get("source_type") == "transfer":
            for col, tgt in list(new.items()):
                if tgt in _HOTEL_DATE_FIELDS:
                    used = set(new.values())
                    for fallback in ("departure_date", "arrival_date"):
                        if fallback not in used:
                            new[col] = fallback
                            changed = True
                            break
                    else:
                        new[col] = str(col)  # keep its data as a custom field
                        changed = True
                elif tgt == "hotel_name":
                    used = set(new.values())
                    for fallback in ("dropoff_location", "pickup_location"):
                        if fallback not in used:
                            new[col] = fallback
                            changed = True
                            break
                    else:
                        new[col] = str(col)  # keep its data as a custom field
                        changed = True
                elif tgt in _HOTEL_ONLY_FIELDS:  # room_type, early_checkin, late_checkout
                    new[col] = str(col)  # no reliable transfer equivalent — demote, don't guess
                    changed = True

        # 6b. The RETROACTIVE case for the bug rule 6 fixes above: a run of
        #     the OLD, broken rule 6 (before this fix existed) already
        #     redirected a transfer file's hotel_name column into
        #     departure_date/arrival_date. That corrupted mapping is now
        #     indistinguishable from a legitimate one by header/target alone
        #     — "departure_date" is a normal, valid transfer field — so rule
        #     6 above never touches it again on rerun: mappings_repaired
        #     stays 0 and "sans transfert" never moves, even after this fix
        #     is deployed and consolidation is relaunched (2026-07-22).
        #     Detect it the same way rule 7 detects a starved location field
        #     below: sample the ACTUAL raw values of whatever column is
        #     mapped to departure_date/arrival_date. A real date column
        #     parses; a leftover venue name never does.
        if f.get("source_type") == "transfer":
            date_cols = [col for col, tgt in new.items() if tgt in ("departure_date", "arrival_date")]
            if date_cols:
                try:
                    sample = (
                        supabase.table("source_records")
                        .select("raw_data")
                        .eq("file_id", f["id"])
                        .limit(20)
                        .execute()
                        .data or []
                    )
                    for col in date_cols:
                        vals = [
                            str(r["raw_data"][col]).strip()
                            for r in sample
                            if r.get("raw_data") and r["raw_data"].get(col) not in (None, "")
                        ]
                        if vals and sum(1 for v in vals if _parse_date(v) is None) / len(vals) > 0.5:
                            used = set(new.values())
                            for fallback in ("dropoff_location", "pickup_location"):
                                if fallback not in used:
                                    new[col] = fallback
                                    changed = True
                                    break
                            else:
                                new[col] = str(col)  # keep its data as a custom field
                                changed = True
                except Exception as exc:
                    logger.warning("Transfer date-column content check failed for file %s: %s", f["id"], exc)

        # 7. That same audit: the file's ONLY location-bearing column (a bare
        #    "Aéroport") was left unmapped for the same reason — no synonym
        #    recognizes an unqualified "Aéroport". Every row then also failed
        #    has_location_signal, on top of the date failure above. A column
        #    being MAPPED to pickup_location/dropoff_location/*_airport is not
        #    enough to skip this: the real file had "Destination" and "Lieu de
        #    Prise en charge" columns mapped correctly, yet EMPTY on all 600
        #    rows — "Aéroport" was the only column actually carrying data. So
        #    sample the already-imported rows and check the mapped location
        #    columns for real values, not just their presence in the mapping.
        if f.get("source_type") == "transfer":
            location_fields = {"pickup_location", "dropoff_location", "departure_airport", "arrival_airport"}
            location_cols = [col for col, tgt in new.items() if tgt in location_fields]
            location_has_data = False
            if location_cols:
                try:
                    sample = (
                        supabase.table("source_records")
                        .select("raw_data")
                        .eq("file_id", f["id"])
                        .limit(20)
                        .execute()
                        .data or []
                    )
                    location_has_data = any(
                        (r.get("raw_data") or {}).get(col) not in (None, "")
                        for r in sample for col in location_cols
                    )
                except Exception as exc:
                    logger.warning("Location-data sampling failed for file %s: %s", f["id"], exc)
                    location_has_data = True  # fail safe: don't touch the mapping on error
            if not location_has_data:
                for col, tgt in list(new.items()):
                    if tgt not in CANONICAL_FIELDS and _BARE_AIRPORT_HDR_RE.match(str(col).strip()):
                        new[col] = "arrival_airport"
                        changed = True
                        break

        # 8. A bare "Country"/"Pays" column is the file's nationality signal
        #    when the column(s) already mapped to `nationality` carry no real
        #    data — a form with no separate nationality field means "Country"
        #    IS the attendee's nationality for travel logistics, confirmed
        #    against a real case: 300/300 participants had real data
        #    ("Turquie", "Japon"...) captured under the `country` rich field,
        #    which the export never even shows, while `nationality` — the
        #    field that actually drives Missing Fields / Data Complete —
        #    stayed empty for every single one (2026-07-21 audit). Checking
        #    DATA, not just mapping presence, matters here too: that same
        #    file's stored mapping already had a stale 'Nationalité' entry
        #    inherited from an earlier org template — a column that doesn't
        #    exist in this file at all — which made a naive "already mapped"
        #    check wrongly skip the repair. A file that genuinely
        #    distinguishes the two (a real, populated "Nationalité" column)
        #    is left untouched.
        nationality_cols = [col for col, tgt in new.items() if tgt == "nationality"]
        nationality_has_data = False
        if nationality_cols:
            try:
                sample = (
                    supabase.table("source_records")
                    .select("raw_data")
                    .eq("file_id", f["id"])
                    .limit(20)
                    .execute()
                    .data or []
                )
                nationality_has_data = any(
                    (r.get("raw_data") or {}).get(col) not in (None, "")
                    for r in sample for col in nationality_cols
                )
            except Exception as exc:
                logger.warning("Nationality-data sampling failed for file %s: %s", f["id"], exc)
                nationality_has_data = True  # fail safe: don't touch the mapping on error
        if not nationality_has_data:
            for col, tgt in list(new.items()):
                if tgt == "country":
                    new[col] = "nationality"
                    changed = True
                    break

        if changed:
            try:
                supabase.table("uploaded_files").update({"column_mapping": new}).eq("id", f["id"]).execute()
                fixed += 1
                logger.info("Repaired stored column_mapping for file %s", f["id"])
            except Exception as exc:
                logger.warning("Mapping repair failed for file %s: %s", f["id"], exc)
    return fixed


def build_mapping_with_report(
    columns: list[str], sample_rows: list[dict]
) -> tuple[dict[str, str], dict[str, dict]]:
    """
    Fully automatic A→Z column mapping PLUS a per-column report for the review UI.

    Confident heuristic suggestions (suggest_mapping >= 0.5) are completed by a
    best-effort AI pass for the ambiguous ones, then a CATCH-ALL preserves EVERY
    remaining data-bearing column as a custom field — so no information is ever
    lost. The report gives, per column: ``{field, confidence(0-100), source
    ('heuristic'|'ai'|'custom'), needs_split}`` so the review screen can show the
    LLM's confidence on AI-mapped columns and flag merged-name columns.
    """
    suggestions = suggest_mapping(columns, sample_rows)
    mapping: dict[str, str] = {}
    report: dict[str, dict] = {}
    for col, s in suggestions.items():
        f = s.get("suggested_field")
        conf = float(s.get("confidence", 0) or 0)
        if f and conf >= 0.5:
            mapping[col] = f
            report[col] = {
                "field": f, "confidence": round(conf * 100), "source": "heuristic",
                "needs_split": f in _COMBINED_NAME_FIELDS,
            }

    # AI pass (with confidence + needs_split) for the columns still unmapped.
    detailed = ai_refine_mapping_detailed(columns, sample_rows, mapping)
    for col, d in detailed.items():
        if d.get("field"):
            mapping[col] = d["field"]
            report[col] = {
                "field": d["field"], "confidence": round(d.get("confidence") or 0),
                "source": "ai", "needs_split": bool(d.get("needs_split")) or d["field"] in _COMBINED_NAME_FIELDS,
            }
        elif d.get("needs_split"):
            # AI flagged a merged column it could not assign to a single field.
            report.setdefault(col, {
                "field": None, "confidence": round(d.get("confidence") or 0),
                "source": "ai", "needs_split": True,
            })

    # CATCH-ALL: every remaining column with data is kept as a custom field, so
    # the master list shows all of its info.
    used_targets: set[str] = set(mapping.values())
    for col in columns:
        if col in mapping:
            continue
        if not any(str(r.get(col) or "").strip() for r in sample_rows):
            continue    # truly empty column — nothing to preserve
        key = _custom_field_key(col, used_targets)
        if key:
            mapping[col] = key
            used_targets.add(key)
            prev = report.get(col, {})
            report[col] = {
                "field": key, "confidence": prev.get("confidence", 0),
                "source": "custom", "needs_split": prev.get("needs_split", False),
            }

    # Guarantee a report entry for every mapped column.
    for col, f in mapping.items():
        report.setdefault(col, {
            "field": f, "confidence": 0, "source": "heuristic",
            "needs_split": f in _COMBINED_NAME_FIELDS,
        })
    return mapping, report


def build_auto_mapping(columns: list[str], sample_rows: list[dict]) -> dict[str, str]:
    """Fully automatic A→Z column mapping (see build_mapping_with_report)."""
    mapping, _ = build_mapping_with_report(columns, sample_rows)
    return mapping
