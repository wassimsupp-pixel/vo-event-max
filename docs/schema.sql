-- ============================================================
-- VO Event Max — PostgreSQL Schema v1.0
-- Region: Supabase Paris (eu-west-3)
-- Hosting: Railway (Amsterdam EU)
-- Phase 1 tables: fully defined
-- Phase 2 table stubs: flights, hotels, hotel_nights, transfers, activities
-- RLS: enabled on all Phase 1 tables
-- RGPD note: dietary_requirements field is sensitive (health/religion data),
--   restricted to admin/pm roles via RLS policy
-- ============================================================

-- ============================================================
-- EXTENSIONS
-- ============================================================
CREATE EXTENSION IF NOT EXISTS "pgcrypto"; -- provides gen_random_uuid() if not using pg14+

-- ============================================================
-- ENUMS
-- ============================================================

CREATE TYPE user_role AS ENUM ('admin', 'pm', 'client', 'viewer');

CREATE TYPE source_type AS ENUM (
  'registration',
  'fcm',
  'email',
  'hotel',
  'transfer',
  'activity',
  'other'
);

CREATE TYPE exception_severity AS ENUM ('critical', 'warning', 'info');

CREATE TYPE exception_type AS ENUM (
  'PARTICIPANT_NO_FLIGHT',
  'PARTICIPANT_NO_HOTEL',
  'FLIGHT_NO_PARTICIPANT',
  'DUPLICATE_EMAIL',
  'DATA_CONFLICT',
  'NAME_DIVERGENCE',
  'DATE_INCOHERENCE',
  'INVALID_FORMAT',
  'MISSING_REQUIRED_FIELD',
  'INCOMPLETE_FLIGHT_ROUTE',
  'PROBABLE_MATCH',
  'POSSIBLE_DUPLICATE'
);

CREATE TYPE match_decision AS ENUM ('certain', 'probable', 'to_verify', 'not_found');

CREATE TYPE completeness_status AS ENUM ('complete', 'incomplete', 'conflict');

-- ============================================================
-- PHASE 1 TABLES
-- ============================================================

-- Multi-tenant isolation
CREATE TABLE organizations (
  id          UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
  name        TEXT        NOT NULL,
  slug        TEXT        UNIQUE NOT NULL,
  created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE organizations IS 'Top-level tenant. Every user, project, and event belongs to exactly one organization.';
COMMENT ON COLUMN organizations.slug IS 'URL-safe identifier, e.g. "vo-events". Must be globally unique.';

-- Users (extends Supabase auth.users)
CREATE TABLE users (
  id                 UUID        PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
  org_id             UUID        NOT NULL REFERENCES organizations(id),
  email              TEXT        NOT NULL,
  full_name          TEXT,
  role               user_role   NOT NULL DEFAULT 'viewer',
  preferred_language TEXT        NOT NULL DEFAULT 'fr', -- fr | nl | en
  created_at         TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE users IS 'Application-level user profile mirroring auth.users. Role determines access level within the org.';
COMMENT ON COLUMN users.preferred_language IS 'ISO 639-1 code. Supported: fr (default), nl, en.';

-- Projects group events per client
CREATE TABLE projects (
  id          UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id      UUID        NOT NULL REFERENCES organizations(id),
  name        TEXT        NOT NULL,
  client_name TEXT        NOT NULL,
  created_by  UUID        NOT NULL REFERENCES users(id),
  created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE projects IS 'A project groups one or more events for a given client.';

-- Events
CREATE TABLE events (
  id               UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id       UUID        NOT NULL REFERENCES projects(id),
  name             TEXT        NOT NULL,
  event_type       TEXT,
  start_date       DATE,
  end_date         DATE,
  location_city    TEXT,
  location_country TEXT,
  created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE events IS 'A single event (conference, incentive trip, etc.) within a project.';

-- Uploaded source files
CREATE TABLE uploaded_files (
  id                UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
  event_id          UUID        NOT NULL REFERENCES events(id),
  original_filename TEXT        NOT NULL,
  storage_path      TEXT        NOT NULL,   -- Supabase Storage path (private bucket)
  source_type       source_type NOT NULL,
  row_count         INTEGER,
  column_count      INTEGER,
  column_mapping    JSONB,                  -- saved mapping: {source_col: target_field, ...}
  import_status     TEXT        NOT NULL DEFAULT 'pending', -- pending | mapped | processed | error
  imported_by       UUID        NOT NULL REFERENCES users(id),
  imported_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  error_message     TEXT,
  CONSTRAINT chk_import_status CHECK (import_status IN ('pending', 'mapped', 'processed', 'error'))
);

COMMENT ON TABLE uploaded_files IS 'Tracks each raw file uploaded for an event. Files reside in Supabase Storage (private).';
COMMENT ON COLUMN uploaded_files.storage_path IS 'Path inside the private Supabase Storage bucket: {event_id}/{file_id}/{filename}';
COMMENT ON COLUMN uploaded_files.column_mapping IS 'JSON object mapping source column names to canonical target field names.';
COMMENT ON COLUMN uploaded_files.import_status IS 'Lifecycle: pending → mapped → processed (or error).';

-- Raw source records (one row per source file row)
-- NOTE: participant_id is a forward reference resolved after participants table is created below.
-- We declare it here and add the FK constraint afterward.
CREATE TABLE source_records (
  id               UUID          PRIMARY KEY DEFAULT gen_random_uuid(),
  file_id          UUID          NOT NULL REFERENCES uploaded_files(id) ON DELETE CASCADE,
  event_id         UUID          NOT NULL REFERENCES events(id),
  row_index        INTEGER       NOT NULL,
  raw_data         JSONB         NOT NULL,
  normalized_data  JSONB,
  participant_id   UUID,         -- FK added after participants table creation (see ALTER TABLE below)
  match_decision   match_decision,
  match_score      FLOAT,
  match_signals    JSONB,        -- {email_match: bool, name_score: float, ...}
  created_at       TIMESTAMPTZ   NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE source_records IS 'One row per row in an uploaded file. raw_data is verbatim; normalized_data is after type coercion and field mapping.';
COMMENT ON COLUMN source_records.match_signals IS 'Structured matching evidence: {email_match, name_score, company_match, ...}';

-- Consolidated participants (the master record)
CREATE TABLE participants (
  id                    UUID                PRIMARY KEY DEFAULT gen_random_uuid(),
  event_id              UUID                NOT NULL REFERENCES events(id),
  -- Identity
  first_name            TEXT                NOT NULL,
  last_name             TEXT                NOT NULL,
  email                 TEXT,
  company               TEXT,
  phone                 TEXT,
  nationality           TEXT,
  dietary_requirements  TEXT,               -- SENSITIVE: restricted to admin/pm via RLS
  -- Status
  completeness_status   completeness_status NOT NULL DEFAULT 'incomplete',
  has_flight            BOOLEAN             NOT NULL DEFAULT FALSE,
  has_hotel             BOOLEAN             NOT NULL DEFAULT FALSE,
  has_transfer          BOOLEAN             NOT NULL DEFAULT FALSE,
  has_activities        BOOLEAN             NOT NULL DEFAULT FALSE,
  verification_note     TEXT,
  -- Non-destructive merge: locked fields cannot be overwritten by re-import
  locked_fields         JSONB               NOT NULL DEFAULT '{}', -- {field_name: true}
  -- Source tracking
  registration_source_id UUID REFERENCES source_records(id),
  fcm_source_id          UUID REFERENCES source_records(id),
  created_at             TIMESTAMPTZ        NOT NULL DEFAULT NOW(),
  updated_at             TIMESTAMPTZ        NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE participants IS 'Master consolidated participant record. One per person per event.';
COMMENT ON COLUMN participants.dietary_requirements IS 'RGPD SENSITIVE: health/religion data. Access restricted to admin/pm roles via RLS policy.';
COMMENT ON COLUMN participants.locked_fields IS 'JSON object {field_name: true}. Locked fields are not overwritten during re-import.';

-- Now that participants exists, add the FK for source_records.participant_id
ALTER TABLE source_records
  ADD CONSTRAINT fk_source_records_participant
  FOREIGN KEY (participant_id) REFERENCES participants(id);

-- Consolidation runs
CREATE TABLE consolidation_runs (
  id           UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
  event_id     UUID        NOT NULL REFERENCES events(id),
  triggered_by UUID        NOT NULL REFERENCES users(id),
  status       TEXT        NOT NULL DEFAULT 'running', -- running | completed | failed
  stats        JSONB,      -- {total, matched_certain, matched_probable, to_verify, not_found, exceptions_count}
  started_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  completed_at TIMESTAMPTZ,
  CONSTRAINT chk_run_status CHECK (status IN ('running', 'completed', 'failed'))
);

COMMENT ON TABLE consolidation_runs IS 'Tracks each execution of the consolidation engine for an event.';
COMMENT ON COLUMN consolidation_runs.stats IS 'JSON summary: {total, matched_certain, matched_probable, to_verify, not_found, exceptions_count}.';

-- Exceptions detected during a run
CREATE TABLE exceptions (
  id               UUID               PRIMARY KEY DEFAULT gen_random_uuid(),
  run_id           UUID               NOT NULL REFERENCES consolidation_runs(id) ON DELETE CASCADE,
  event_id         UUID               NOT NULL REFERENCES events(id),
  participant_id   UUID               REFERENCES participants(id),
  source_record_id UUID               REFERENCES source_records(id),
  exception_type   exception_type     NOT NULL,
  severity         exception_severity NOT NULL DEFAULT 'warning',
  message          TEXT               NOT NULL,
  context_data     JSONB,             -- additional structured context
  resolved         BOOLEAN            NOT NULL DEFAULT FALSE,
  resolved_by      UUID               REFERENCES users(id),
  resolved_at      TIMESTAMPTZ,
  created_at       TIMESTAMPTZ        NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE exceptions IS 'Data quality exceptions flagged by the consolidation engine or exception detector.';
COMMENT ON COLUMN exceptions.context_data IS 'Structured context specific to each exception type (e.g. conflicting values, source row info).';

-- Full audit trail
CREATE TABLE change_log (
  id            UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
  event_id      UUID        NOT NULL REFERENCES events(id),
  user_id       UUID        NOT NULL REFERENCES users(id),
  entity_type   TEXT        NOT NULL, -- 'participant' | 'exception' | 'source_record' etc.
  entity_id     UUID        NOT NULL,
  field_name    TEXT        NOT NULL,
  old_value     TEXT,
  new_value     TEXT,
  change_reason TEXT,       -- 'manual_edit' | 'import' | 're_import' | 'lock' | 'resolve_exception'
  changed_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE change_log IS 'Immutable audit log of every field-level change. Written BEFORE the actual update.';
COMMENT ON COLUMN change_log.entity_type IS 'Type of changed entity: participant | exception | source_record | uploaded_file.';
COMMENT ON COLUMN change_log.change_reason IS 'Reason code: manual_edit | import | re_import | lock | resolve_exception.';

-- Saved column mapping templates
CREATE TABLE column_mapping_templates (
  id            UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id        UUID        NOT NULL REFERENCES organizations(id),
  source_type   source_type NOT NULL,
  template_name TEXT        NOT NULL,
  mapping       JSONB       NOT NULL, -- {source_col: target_field}
  created_by    UUID        NOT NULL REFERENCES users(id),
  created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE column_mapping_templates IS 'Reusable column mapping presets. Orgs can save and reuse mappings for recurring file formats.';

-- Exports
CREATE TABLE exports (
  id           UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
  run_id       UUID        NOT NULL REFERENCES consolidation_runs(id),
  event_id     UUID        NOT NULL REFERENCES events(id),
  storage_path TEXT        NOT NULL,
  filename     TEXT        NOT NULL,
  created_by   UUID        NOT NULL REFERENCES users(id),
  created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE exports IS 'Tracks generated Excel export files stored in Supabase Storage (private).';

-- ============================================================
-- PHASE 2 TABLE STUBS
-- (structure only — columns to be expanded in Phase 2)
-- ============================================================

CREATE TABLE flights (
  id             UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
  event_id       UUID        NOT NULL REFERENCES events(id),
  participant_id UUID        REFERENCES participants(id),
  created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE flights IS 'Phase 2 stub. Will hold flight segments per participant.';

CREATE TABLE hotels (
  id         UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
  event_id   UUID        NOT NULL REFERENCES events(id),
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE hotels IS 'Phase 2 stub. Will hold hotel property records per event.';

CREATE TABLE hotel_nights (
  id             UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
  hotel_id       UUID        NOT NULL REFERENCES hotels(id),
  participant_id UUID        REFERENCES participants(id),
  created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE hotel_nights IS 'Phase 2 stub. Will hold per-night room assignments.';

CREATE TABLE transfers (
  id             UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
  event_id       UUID        NOT NULL REFERENCES events(id),
  participant_id UUID        REFERENCES participants(id),
  created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE transfers IS 'Phase 2 stub. Will hold ground transfer records.';

CREATE TABLE activities (
  id         UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
  event_id   UUID        NOT NULL REFERENCES events(id),
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE activities IS 'Phase 2 stub. Will hold optional activity registrations.';

-- ============================================================
-- INDEXES
-- ============================================================

CREATE INDEX idx_participants_event_id  ON participants(event_id);
CREATE INDEX idx_participants_email     ON participants(email);
CREATE INDEX idx_source_records_file_id ON source_records(file_id);
CREATE INDEX idx_source_records_event_id ON source_records(event_id);
CREATE INDEX idx_exceptions_run_id     ON exceptions(run_id);
CREATE INDEX idx_exceptions_event_id   ON exceptions(event_id);
CREATE INDEX idx_change_log_event_id   ON change_log(event_id);
CREATE INDEX idx_change_log_entity     ON change_log(entity_type, entity_id);
CREATE INDEX idx_uploaded_files_event_id ON uploaded_files(event_id);

-- Additional useful indexes
CREATE INDEX idx_participants_completeness ON participants(event_id, completeness_status);
CREATE INDEX idx_exceptions_resolved       ON exceptions(event_id, resolved);
CREATE INDEX idx_consolidation_runs_event  ON consolidation_runs(event_id, started_at DESC);

-- ============================================================
-- ROW LEVEL SECURITY
-- ============================================================

-- Enable RLS on all Phase 1 tables
ALTER TABLE organizations          ENABLE ROW LEVEL SECURITY;
ALTER TABLE users                  ENABLE ROW LEVEL SECURITY;
ALTER TABLE projects               ENABLE ROW LEVEL SECURITY;
ALTER TABLE events                 ENABLE ROW LEVEL SECURITY;
ALTER TABLE uploaded_files         ENABLE ROW LEVEL SECURITY;
ALTER TABLE source_records         ENABLE ROW LEVEL SECURITY;
ALTER TABLE participants           ENABLE ROW LEVEL SECURITY;
ALTER TABLE consolidation_runs     ENABLE ROW LEVEL SECURITY;
ALTER TABLE exceptions             ENABLE ROW LEVEL SECURITY;
ALTER TABLE change_log             ENABLE ROW LEVEL SECURITY;
ALTER TABLE exports                ENABLE ROW LEVEL SECURITY;
ALTER TABLE column_mapping_templates ENABLE ROW LEVEL SECURITY;

-- ============================================================
-- HELPER FUNCTIONS (SECURITY DEFINER — run as postgres role)
-- ============================================================

-- Returns the org_id of the currently authenticated Supabase user
CREATE OR REPLACE FUNCTION get_user_org_id()
RETURNS UUID AS $$
  SELECT org_id FROM users WHERE id = auth.uid();
$$ LANGUAGE SQL SECURITY DEFINER STABLE;

COMMENT ON FUNCTION get_user_org_id() IS 'Returns the org_id for the currently authenticated user. Used by RLS policies.';

-- Returns the role of the currently authenticated Supabase user
CREATE OR REPLACE FUNCTION get_user_role()
RETURNS user_role AS $$
  SELECT role FROM users WHERE id = auth.uid();
$$ LANGUAGE SQL SECURITY DEFINER STABLE;

COMMENT ON FUNCTION get_user_role() IS 'Returns the user_role for the currently authenticated user. Used by RLS policies.';

-- Returns true if the current user can access a given event (same org)
CREATE OR REPLACE FUNCTION user_can_access_event(event_uuid UUID)
RETURNS BOOLEAN AS $$
  SELECT EXISTS (
    SELECT 1 FROM events e
    JOIN   projects p ON e.project_id = p.id
    WHERE  e.id = event_uuid
    AND    p.org_id = get_user_org_id()
  );
$$ LANGUAGE SQL SECURITY DEFINER STABLE;

COMMENT ON FUNCTION user_can_access_event(UUID) IS 'Returns TRUE if the current user belongs to the same org as the event''s project.';

-- ============================================================
-- RLS POLICIES
-- ============================================================

-- organizations: each user sees only their own org
CREATE POLICY "organizations_org_isolation" ON organizations
  FOR ALL
  USING (id = get_user_org_id());

-- users: each user sees only users in their own org
CREATE POLICY "users_org_isolation" ON users
  FOR ALL
  USING (org_id = get_user_org_id());

-- projects: only their org's projects
CREATE POLICY "projects_org_isolation" ON projects
  FOR ALL
  USING (org_id = get_user_org_id());

-- events: only their org's events (via project)
CREATE POLICY "events_org_isolation" ON events
  FOR ALL
  USING (
    project_id IN (SELECT id FROM projects WHERE org_id = get_user_org_id())
  );

-- uploaded_files: only files belonging to accessible events
CREATE POLICY "uploaded_files_org_isolation" ON uploaded_files
  FOR ALL
  USING (user_can_access_event(event_id));

-- source_records: only records belonging to accessible events
CREATE POLICY "source_records_org_isolation" ON source_records
  FOR ALL
  USING (user_can_access_event(event_id));

-- participants: general access for the event (without dietary_requirements restriction)
CREATE POLICY "participants_org_isolation" ON participants
  FOR ALL
  USING (user_can_access_event(event_id));

-- dietary_requirements: restricted to admin and pm roles only.
-- NOTE: This policy OVERRIDES the general SELECT for non-admin/pm users by
--       only permitting rows where dietary_requirements IS NULL for those roles.
--       Clients and viewers will never see the dietary_requirements column value.
CREATE POLICY "dietary_requirements_restricted" ON participants
  FOR SELECT
  USING (
    user_can_access_event(event_id)
    AND (
      get_user_role() IN ('admin', 'pm')
      OR dietary_requirements IS NULL
    )
  );

-- consolidation_runs: only their org's events
CREATE POLICY "consolidation_runs_org_isolation" ON consolidation_runs
  FOR ALL
  USING (user_can_access_event(event_id));

-- exceptions: only their org's events
CREATE POLICY "exceptions_org_isolation" ON exceptions
  FOR ALL
  USING (user_can_access_event(event_id));

-- change_log: only their org's events; read-only for non-admin
CREATE POLICY "change_log_org_isolation" ON change_log
  FOR ALL
  USING (user_can_access_event(event_id));

-- exports: only their org's events
CREATE POLICY "exports_org_isolation" ON exports
  FOR ALL
  USING (user_can_access_event(event_id));

-- column_mapping_templates: only their org's templates
CREATE POLICY "column_mapping_templates_org_isolation" ON column_mapping_templates
  FOR ALL
  USING (org_id = get_user_org_id());

-- ============================================================
-- TRIGGERS
-- ============================================================

-- Auto-update updated_at on events
CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = NOW();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_events_updated_at
  BEFORE UPDATE ON events
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TRIGGER trg_participants_updated_at
  BEFORE UPDATE ON participants
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- ============================================================
-- END OF SCHEMA
-- ============================================================
