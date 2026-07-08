-- ============================================================
-- VO Event Max — PostgreSQL Schema Expansion (Phase 2)
-- ============================================================

-- Drop old stubs if they exist
DROP TABLE IF EXISTS participant_activities CASCADE;
DROP TABLE IF EXISTS activities CASCADE;
DROP TABLE IF EXISTS transfers CASCADE;
DROP TABLE IF EXISTS hotel_nights CASCADE;
DROP TABLE IF EXISTS hotels CASCADE;
DROP TABLE IF EXISTS flights CASCADE;

-- 1. FLIGHTS
CREATE TABLE flights (
  id                 UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
  event_id           UUID        NOT NULL REFERENCES events(id) ON DELETE CASCADE,
  participant_id     UUID        REFERENCES participants(id) ON DELETE CASCADE,
  pnr_code           TEXT,
  airline            TEXT,
  flight_number      TEXT        NOT NULL,
  departure_airport  TEXT        NOT NULL,
  arrival_airport    TEXT        NOT NULL,
  departure_time     TIMESTAMPTZ NOT NULL,
  arrival_time       TIMESTAMPTZ NOT NULL,
  baggage_info       TEXT,
  status             TEXT        NOT NULL DEFAULT 'confirmed', -- confirmed | cancelled | changed
  created_at         TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE flights IS 'Holds details of flight segments booked for event participants.';

-- 2. HOTELS
CREATE TABLE hotels (
  id           UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
  event_id     UUID        NOT NULL REFERENCES events(id) ON DELETE CASCADE,
  name         TEXT        NOT NULL,
  address      TEXT,
  city         TEXT,
  contact_info TEXT,
  created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE hotels IS 'Details of hotel properties hosting participants for an event.';

-- 3. HOTEL NIGHTS
CREATE TABLE hotel_nights (
  id             UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
  hotel_id       UUID        NOT NULL REFERENCES hotels(id) ON DELETE CASCADE,
  participant_id UUID        NOT NULL REFERENCES participants(id) ON DELETE CASCADE,
  night_date     DATE        NOT NULL,
  room_type      TEXT        NOT NULL DEFAULT 'single', -- single | double | twin | suite
  status         TEXT        NOT NULL DEFAULT 'confirmed', -- requested | confirmed | cancelled
  created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (participant_id, night_date)
);

COMMENT ON TABLE hotel_nights IS 'Per-night room block reservations for participants.';

-- 4. TRANSFERS
CREATE TABLE transfers (
  id               UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
  event_id         UUID        NOT NULL REFERENCES events(id) ON DELETE CASCADE,
  participant_id   UUID        NOT NULL REFERENCES participants(id) ON DELETE CASCADE,
  transfer_type    TEXT        NOT NULL, -- arrival | departure | activity | other
  flight_id        UUID        REFERENCES flights(id) ON DELETE SET NULL,
  pickup_location  TEXT        NOT NULL,
  dropoff_location TEXT        NOT NULL,
  pickup_time      TIMESTAMPTZ NOT NULL,
  vehicle_type     TEXT, -- bus | taxi | private_car
  status           TEXT        NOT NULL DEFAULT 'scheduled', -- scheduled | completed | cancelled
  created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE transfers IS 'Ground transportation bookings for airport pickups and event shuttles.';

-- 5. ACTIVITIES
CREATE TABLE activities (
  id           UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
  event_id     UUID        NOT NULL REFERENCES events(id) ON DELETE CASCADE,
  name         TEXT        NOT NULL,
  description  TEXT,
  date_time    TIMESTAMPTZ,
  location     TEXT,
  capacity     INTEGER,
  created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE activities IS 'Excursions, dinners, or secondary meetings within the main event.';

-- 6. PARTICIPANT ACTIVITIES
CREATE TABLE participant_activities (
  id             UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
  participant_id UUID        NOT NULL REFERENCES participants(id) ON DELETE CASCADE,
  activity_id    UUID        NOT NULL REFERENCES activities(id) ON DELETE CASCADE,
  status         TEXT        NOT NULL DEFAULT 'registered', -- registered | waitlisted | cancelled
  created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (participant_id, activity_id)
);

COMMENT ON TABLE participant_activities IS 'Registers participants to specific event activities.';

-- ============================================================
-- INDEXES
-- ============================================================
CREATE INDEX idx_flights_participant   ON flights(participant_id);
CREATE INDEX idx_flights_event         ON flights(event_id);
CREATE INDEX idx_hotel_nights_part     ON hotel_nights(participant_id);
CREATE INDEX idx_hotel_nights_date     ON hotel_nights(night_date);
CREATE INDEX idx_transfers_participant ON transfers(participant_id);
CREATE INDEX idx_transfers_pickup      ON transfers(pickup_time);
CREATE INDEX idx_participant_activities_part ON participant_activities(participant_id);

-- ============================================================
-- ROW LEVEL SECURITY (RLS) POLICIES
-- ============================================================
ALTER TABLE flights ENABLE ROW LEVEL SECURITY;
ALTER TABLE hotels ENABLE ROW LEVEL SECURITY;
ALTER TABLE hotel_nights ENABLE ROW LEVEL SECURITY;
ALTER TABLE transfers ENABLE ROW LEVEL SECURITY;
ALTER TABLE activities ENABLE ROW LEVEL SECURITY;
ALTER TABLE participant_activities ENABLE ROW LEVEL SECURITY;

-- Helper check if user can access an event (already defined in schema.sql, reused here)
-- We assume user_can_access_event(UUID) helper exists from schema.sql.

CREATE POLICY "flights_org_isolation" ON flights
  FOR ALL USING (user_can_access_event(event_id));

CREATE POLICY "hotels_org_isolation" ON hotels
  FOR ALL USING (user_can_access_event(event_id));

CREATE POLICY "hotel_nights_org_isolation" ON hotel_nights
  FOR ALL USING (
    hotel_id IN (
      SELECT id FROM hotels WHERE event_id IN (
        SELECT id FROM events WHERE user_can_access_event(id)
      )
    )
  );

CREATE POLICY "transfers_org_isolation" ON transfers
  FOR ALL USING (user_can_access_event(event_id));

CREATE POLICY "activities_org_isolation" ON activities
  FOR ALL USING (user_can_access_event(event_id));

CREATE POLICY "participant_activities_org_isolation" ON participant_activities
  FOR ALL USING (
    activity_id IN (
      SELECT id FROM activities WHERE event_id IN (
        SELECT id FROM events WHERE user_can_access_event(id)
      )
    )
  );
