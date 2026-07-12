-- ============================================================
-- VO Event Max — PostgreSQL Schema Expansion (Phase 3: AI Email Agent)
-- ============================================================

CREATE TYPE email_proposal_status AS ENUM ('pending', 'applied', 'rejected');

CREATE TABLE email_proposals (
  id                UUID                  PRIMARY KEY DEFAULT gen_random_uuid(),
  event_id          UUID                  NOT NULL REFERENCES events(id) ON DELETE CASCADE,
  sender            TEXT                  NOT NULL,
  subject           TEXT                  NOT NULL,
  body              TEXT                  NOT NULL,
  received_at       TIMESTAMPTZ           NOT NULL DEFAULT NOW(),
  participant_id    UUID                  REFERENCES participants(id) ON DELETE SET NULL,
  status            email_proposal_status NOT NULL DEFAULT 'pending',
  proposed_changes  JSONB                 NOT NULL DEFAULT '{}'::jsonb, -- e.g. {"dietary_requirements": "Sans Gluten", "company": "LivaNova"}
  ai_explanation    TEXT,
  created_at        TIMESTAMPTZ           NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE email_proposals IS 'Stores raw emails received and parsed by the AI agent with proposed changes for verification.';

-- Indexes for quick routing and filtering
CREATE INDEX idx_email_proposals_event ON email_proposals(event_id);
CREATE INDEX idx_email_proposals_status ON email_proposals(status);
CREATE INDEX idx_email_proposals_part ON email_proposals(participant_id);

-- Row Level Security policies
ALTER TABLE email_proposals ENABLE ROW LEVEL SECURITY;

CREATE POLICY "email_proposals_org_isolation" ON email_proposals
  FOR ALL USING (user_can_access_event(event_id));
