-- ============================================================================
-- Migration 006 — Public event registration form
-- ============================================================================
-- Run this in the Supabase SQL editor. It is idempotent (safe to re-run).
--
-- Adds a per-event public, unauthenticated registration form:
--   1. events.registration_token — opaque token used in the public form URL
--      (never the raw event UUID, so the link can't be guessed from any
--      other event ID a client might see).
--   2. events.registration_open — lets an admin/pm close the form once
--      registrations should stop, without deleting the link.
--   3. uploaded_files.imported_by becomes nullable — form-originated
--      submissions still record an `imported_by` (the project owner, chosen
--      in code as the "system actor" for these auto-created records), but
--      making the column nullable removes the last blocker to a genuinely
--      unattended write path if that choice ever needs to change.
--
-- Until this migration is applied, the "Lien d'inscription" feature simply
-- doesn't work (404 on the link endpoints); nothing else in the app is
-- affected.
-- ============================================================================

ALTER TABLE events ADD COLUMN IF NOT EXISTS registration_token UUID NOT NULL DEFAULT gen_random_uuid();
ALTER TABLE events ADD COLUMN IF NOT EXISTS registration_open BOOLEAN NOT NULL DEFAULT true;

CREATE UNIQUE INDEX IF NOT EXISTS uq_events_registration_token ON events(registration_token);

COMMENT ON COLUMN events.registration_token IS 'Opaque token for the public registration form URL — never expose the raw event id.';
COMMENT ON COLUMN events.registration_open IS 'When false, the public registration form refuses new submissions.';

ALTER TABLE uploaded_files ALTER COLUMN imported_by DROP NOT NULL;
