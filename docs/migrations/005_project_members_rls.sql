-- ============================================================
-- 005_project_members_rls.sql — Enable RLS on project_members
--
-- Run this in the Supabase SQL editor (like 002/003/004).
--
-- Found in the 2026-07-21 security audit: project_members (added in
-- 003_sharing.sql) was created WITHOUT Row Level Security. Every other
-- table in this schema has RLS enabled with an org-scoped policy
-- (see docs/schema.sql's "RLS POLICIES" section) — this one table was
-- missed. It is not currently queried directly from the browser (the
-- frontend only reaches it via the FastAPI backend's service-role client,
-- which bypasses RLS by design), so today's practical exposure is limited
-- to "if anyone ever points an anon/authenticated Supabase client at this
-- table" — but the frontend DOES already talk to Supabase directly with
-- the anon key for auth and the `users` table (apps/web/src/lib/supabase.ts,
-- used in login/page.tsx, settings/page.tsx, Sidebar.tsx), so the same
-- pattern reaching project_members in the future is not far-fetched.
-- This is pure defense-in-depth: the backend's own application-layer
-- checks (dependencies.py's verify_event_access / get_project_membership)
-- already enforce the real authorization and are unaffected by this
-- migration (service-role always bypasses RLS).
--
-- Safe to run at any time: enabling RLS with no matching policy would
-- normally LOCK OUT all non-service-role access, but this migration adds
-- the policy in the same statement batch, so there is no window with RLS
-- enabled and no policy. Uses the exact same get_user_org_id() helper
-- every other org-isolation policy in this schema already uses.
-- ============================================================

ALTER TABLE project_members ENABLE ROW LEVEL SECURITY;

CREATE POLICY "project_members_org_isolation" ON project_members
  FOR ALL
  USING (
    project_id IN (SELECT id FROM projects WHERE org_id = get_user_org_id())
  );

COMMENT ON POLICY "project_members_org_isolation" ON project_members IS
  'Defense-in-depth only: the FastAPI backend uses the service-role key (bypasses RLS) and already enforces real authorization at the application layer via dependencies.py. This policy only matters if a client ever queries this table directly with the anon/authenticated key.';
