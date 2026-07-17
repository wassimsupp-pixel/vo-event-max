-- ============================================================
-- 003_sharing.sql — Project/event sharing between users
--
-- Run this in the Supabase SQL editor (like 002_communications.sql).
--
-- A project_members row grants one user access to one project:
--   access_level 'viewer' → read-only (dashboard, master list, reports)
--   access_level 'editor' → can also import files, map, consolidate, edit
--   event_ids NULL        → the WHOLE project (every event)
--   event_ids [...]       → only the listed events of that project
--
-- org admin/pm keep implicit full access to all org projects (staff);
-- 'client' / 'viewer' users only see what is shared with them.
-- ============================================================

CREATE TABLE IF NOT EXISTS project_members (
  id           UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id   UUID        NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  user_id      UUID        NOT NULL REFERENCES users(id)    ON DELETE CASCADE,
  access_level TEXT        NOT NULL DEFAULT 'viewer'
               CHECK (access_level IN ('viewer', 'editor')),
  event_ids    UUID[],     -- NULL = all events of the project
  invited_by   UUID        REFERENCES users(id),
  created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (project_id, user_id)
);

CREATE INDEX IF NOT EXISTS idx_project_members_user    ON project_members(user_id);
CREATE INDEX IF NOT EXISTS idx_project_members_project ON project_members(project_id);

COMMENT ON TABLE project_members IS 'Sharing: grants a user access to a project (optionally restricted to specific events).';
COMMENT ON COLUMN project_members.event_ids IS 'NULL = whole project; otherwise only these event UUIDs are accessible.';
