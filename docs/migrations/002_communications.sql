-- Migration 002 — communications (participant confirmations & tracking)
-- Feedback §13 + "Lettre individuelle — Confirmation participant".
-- Run this once in Supabase → SQL Editor.

CREATE TABLE IF NOT EXISTS communications (
  id             UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
  event_id       UUID        NOT NULL REFERENCES events(id),
  participant_id UUID        REFERENCES participants(id),
  -- 'confirmation' (individual attendee confirmation), 'update' (change notice), ...
  type           TEXT        NOT NULL DEFAULT 'confirmation',
  -- 'email' or 'letter'
  channel        TEXT        NOT NULL DEFAULT 'email',
  subject        TEXT,
  body           TEXT,
  -- lifecycle: draft → ready → sent ; 'outdated' when underlying data changed after send
  status         TEXT        NOT NULL DEFAULT 'draft',
  generated_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  sent_at        TIMESTAMPTZ,
  created_by     UUID        REFERENCES users(id),
  created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_communications_event       ON communications(event_id);
CREATE INDEX IF NOT EXISTS idx_communications_participant ON communications(participant_id);
CREATE INDEX IF NOT EXISTS idx_communications_status      ON communications(event_id, status);

ALTER TABLE communications ENABLE ROW LEVEL SECURITY;

-- Same org-isolation pattern as the other event-scoped tables.
DROP POLICY IF EXISTS "communications_org_isolation" ON communications;
CREATE POLICY "communications_org_isolation" ON communications
  FOR ALL
  USING (user_can_access_event(event_id));
