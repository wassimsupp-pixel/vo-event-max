# Column mapping reference (Feedback V1 — P1.3)

Use this when testing the import flow with the **real client Excel files**. It
lists every canonical field the system understands and the column-header
synonyms the auto-suggester already recognizes. Compare it against the real
headers: anything not covered here is a mapping gap to record and fix.

Source of truth: `apps/api/services/mapping_service.py`
(`CANONICAL_FIELDS` + `SYNONYMS`). Suggestions combine **header-name** matching
(accent-insensitive, punctuation-stripped) with **content** sniffing (emails,
dates, flight numbers).

## How matching works (summary)

- Header names are normalized: lowercased, accents stripped, spaces/punctuation
  removed. `"Prénom"` → `prenom`, `"E-mail Address"` → `emailaddress`.
- Confidence: exact header = 0.95, exact synonym = 0.90, partial (prefix/suffix/
  contains) = 0.40–0.60. A suggestion is only auto-filled at **≥ 0.50**.
- Content boosts override names: a column whose values are >50% emails is forced
  to `email` (0.95); likewise dates → the date fields, `AA1234` patterns →
  `flight_number`.

## Canonical fields & recognized synonyms

### Participant core
| Field | Recognized headers (normalized) |
|-------|--------------------------------|
| `id` | id, idparticipant, code, codeparticipant, registrationcode, ref, reference, participantid |
| `first_name` | prenom, first, firstname, givenname, nom1, nomdebateme |
| `last_name` | nom, last, lastname, surname, familyname, nomdefamille |
| `email` | email, mail, courriel, adressemail, emailaddress, emailadr, contactemail |
| `company` | company, societe, compagnie, entreprise, organisation, org, boite, employer, employeur |
| `phone` | phone, telephone, tel, gsm, mobile, cel, cellulaire, contactphone |
| `nationality` | nationality, nationalite, pays, citizen, citizenship, orig |
| `dietary_requirements` | dietaryrequirements, dietary, regime, regimealimentaire, aliment, food, allergy, allergie |

### Flights (FCM)
| Field | Recognized headers (normalized) |
|-------|--------------------------------|
| `departure_date` | departuredate, datedepart, outbounddate, flightdepdate |
| `return_date` | returndate, dateretour, inbounddate, flightretdate |
| `flight_number` | flightnumber, numvol, novol, flightno, numdevol, flightcode |
| `departure_airport` | departureairport, aeroportdepart, depapt, depairp, origairport |
| `arrival_airport` | arrivalairport, aeroportarrivee, arrapt, arrairp, destairport |
| `departure_time` | departuretime, heuredepart, flightdeptime, deptime, datedepart |
| `arrival_time` | arrivaltime, heurearrivee, flightarrtime, arrtime, datearrivee, retdate |
| `pnr_code` | pnrcode, pnr, codepnr, bookingref, recordlocator |
| `airline` | airline, compagnie, compagnieaerienne, carrier, aircarrier |
| `baggage_info` | baggageinfo, baggage, luggage, infosbagages, bags |

### Hotels
| Field | Recognized headers (normalized) |
|-------|--------------------------------|
| `hotel_name` | hotelname, hotel, nomhotel, hebergement, nomdebergement |
| `check_in_date` | checkindate, checkin, datecheckin, dateentree, entree, arrivalhotel, hotelarr |
| `check_out_date` | checkoutdate, checkout, datecheckout, datesortie, sortie, departurehotel, hoteldep |
| `room_type` | roomtype, room, chambre, typechambre, roomcategory |

### Transfers
| Field | Recognized headers (normalized) |
|-------|--------------------------------|
| `transfer_type` | transfertype, shuttletype, typenavette |
| `pickup_location` | pickuplocation, lieupriseencharge, priseencharge, depart, pickup, lieudedepart |
| `dropoff_location` | dropofflocation, destination, lieuarrivee, arrivee, dropoff, lieudarrivee |
| `pickup_time` | pickuptime, heurepriseencharge, heurepickup, heurenavette, shuttletime |
| `vehicle_type` | vehicletype, vehicle, vehicule, car, bus, voiture, typevehicule |

### Activities
| Field | Recognized headers (normalized) |
|-------|--------------------------------|
| `activity_name` | activityname, activity, activite, nomactivite, excursion, loisir, programme |

## Known ambiguities to watch on real data

- **`compagnie`** is a synonym for both `company` and `airline`. On an FCM flight
  file it should resolve to `airline`; on a registration file, to `company`.
  Verify the auto-suggestion picked the right one and correct if needed.
- **`datedepart`** maps to both `departure_date` and `departure_time`;
  **`datearrivee`/`retdate`** to `arrival_time` / `return_date`. If the real file
  splits date and time into separate columns, confirm each lands correctly.
- **Date parsing** accepts `dd/mm/yyyy`, `dd-mm-yyyy`, `yyyy-mm-dd`, `mm/dd/yyyy`,
  `dd.mm.yyyy`. A `mm/dd` vs `dd/mm` ambiguity (e.g. `03/04/2025`) is resolved by
  format order (European `dd/mm` wins). Spot-check real dates.

## Testing checklist (real files — P1.3/1.4/1.5)

1. Upload each real file via **Sources**; open the mapping screen.
2. For every column, record: real header → suggested field → confidence.
3. Note any column with **no suggestion** or a **wrong** suggestion → add the
   real header to the relevant list in `SYNONYMS` (mapping_service.py) and
   re-test. Document each addition here.
4. Run a consolidation; confirm participant counts and that
   `certain/probable/to_verify/not_found` splits look sane (P1.4). If the real
   data produces many false positives/negatives, revisit the thresholds in
   `packages/matching-engine/matcher.py` (documented in its module docstring).
5. Confirm each exception type appears where expected (P1.5) and the sidebar
   badge count matches the Exceptions page.

> Record every mapping gap and threshold change directly in this file so the
> next import round starts from an accurate baseline.
