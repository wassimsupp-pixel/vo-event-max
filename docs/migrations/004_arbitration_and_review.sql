-- ============================================================================
-- Migration 004 — AI match arbitration queue + "review new formats" mapping gate
-- ============================================================================
-- Run this in the Supabase SQL editor. It is idempotent (safe to re-run).
--
-- Adds:
--   1. match_candidates  — the arbitration queue. Pairs of participants that
--      MIGHT be the same person, scored deterministically, arbitrated by the
--      AI (fusionner / separer / incertain), and resolved by a human in the
--      dedicated review dashboard.
--   2. uploaded_files.import_status = 'review' — a new lifecycle state used the
--      FIRST time a brand-new file format (never-seen column layout) is
--      uploaded, so its auto-built mapping can be confirmed once and then
--      memorised (recognised formats stay 100% automatic).
--
-- Until this migration is applied the application degrades gracefully:
--   - mapping stays fully automatic (no 'review' state is ever set), and
--   - match arbitration is skipped (the table simply isn't there).
-- ============================================================================

-- 1. Arbitration queue ------------------------------------------------------
CREATE TABLE IF NOT EXISTS match_candidates (
    id                  UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    event_id            UUID        NOT NULL REFERENCES events(id) ON DELETE CASCADE,
    run_id              UUID        REFERENCES consolidation_runs(id) ON DELETE SET NULL,
    -- The two participants that might be the same person. participant_a is the
    -- one that gets merged INTO participant_b when a human confirms "fusionner".
    participant_a_id    UUID        REFERENCES participants(id) ON DELETE CASCADE,
    participant_b_id    UUID        REFERENCES participants(id) ON DELETE CASCADE,
    -- Snapshots so the dashboard renders even if a row later changes/merges.
    name_a              TEXT,
    name_b              TEXT,
    details_a           JSONB,
    details_b           JSONB,
    deterministic_score REAL,       -- rapidfuzz similarity 0-100
    ai_recommendation   TEXT,       -- 'fusionner' | 'separer' | 'incertain'
    ai_justification    TEXT,
    ai_confidence       REAL,       -- 0-100
    human_decision      TEXT,       -- 'fusionner' | 'separer' | NULL (pending)
    status              TEXT        NOT NULL DEFAULT 'pending', -- 'pending' | 'resolved'
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    resolved_at         TIMESTAMPTZ,
    CONSTRAINT chk_mc_status CHECK (status IN ('pending', 'resolved'))
);

COMMENT ON TABLE match_candidates IS
    'Ambiguous participant pairs (score ~78-93) arbitrated by the AI and resolved by a human in the match-review dashboard.';

CREATE INDEX IF NOT EXISTS idx_match_candidates_event_status
    ON match_candidates (event_id, status);

-- One open candidate per unordered participant pair (avoids re-queuing the same
-- ambiguity on every consolidation run).
CREATE UNIQUE INDEX IF NOT EXISTS uq_match_candidates_open_pair
    ON match_candidates (
        event_id,
        LEAST(participant_a_id, participant_b_id),
        GREATEST(participant_a_id, participant_b_id)
    )
    WHERE status = 'pending';

-- The API uses the Supabase service-role key, which bypasses RLS. Enable RLS so
-- the table is never exposed through the public anon key; the backend still has
-- full access. (No public policy is added on purpose.)
ALTER TABLE match_candidates ENABLE ROW LEVEL SECURITY;

-- 2. 'review' import status -------------------------------------------------
ALTER TABLE uploaded_files DROP CONSTRAINT IF EXISTS chk_import_status;
ALTER TABLE uploaded_files ADD CONSTRAINT chk_import_status
    CHECK (import_status IN ('pending', 'mapped', 'processed', 'error', 'review'));

COMMENT ON COLUMN uploaded_files.import_status IS
    'Lifecycle: pending -> (review ->) mapped -> processed (or error). ''review'' = a brand-new format awaiting one-time mapping confirmation.';

-- 3. Per-column mapping report ----------------------------------------------
-- Feeds the review screen: {column: {field, confidence(0-100), source
-- (heuristic|ai|custom), needs_split}}. Lets the UI show the LLM's confidence on
-- AI-mapped columns and flag merged-name columns ("Nom complet" -> split).
ALTER TABLE uploaded_files ADD COLUMN IF NOT EXISTS mapping_report JSONB;

COMMENT ON COLUMN uploaded_files.mapping_report IS
    'Per-column mapping metadata for the review UI (confidence, source, needs_split).';
