-- ============================================================
-- VO Event Max — PostgreSQL User Profile Trigger (Supabase)
-- ============================================================
-- Run this in the Supabase SQL Editor to automate profile creation.
-- Whenever a user signs up via Supabase Auth, this trigger creates
-- a default organization (if none exists) and inserts their profile
-- in the public.users table.

CREATE OR REPLACE FUNCTION public.handle_new_user()
RETURNS trigger AS $$
DECLARE
  default_org_id UUID;
  default_project_id UUID;
  default_event_id UUID;
BEGIN
  -- 1. Get or create default organization
  SELECT id INTO default_org_id FROM public.organizations LIMIT 1;
  IF default_org_id IS NULL THEN
    INSERT INTO public.organizations (name, slug)
    VALUES ('VO Communication Group', 'vo-group')
    RETURNING id INTO default_org_id;
  END IF;

  -- 2. Insert user profile (default first user as admin)
  INSERT INTO public.users (id, org_id, email, full_name, role, preferred_language)
  VALUES (
    new.id,
    default_org_id,
    new.email,
    COALESCE(new.raw_user_meta_data->>'full_name', 'Utilisateur VO'),
    'admin',
    COALESCE(new.raw_user_meta_data->>'preferred_language', 'fr')
  );

  -- 3. Create a default project and event so they have a sandbox ready
  SELECT id INTO default_project_id FROM public.projects WHERE org_id = default_org_id LIMIT 1;
  IF default_project_id IS NULL THEN
    INSERT INTO public.projects (org_id, name, client_name, created_by)
    VALUES (default_org_id, 'LivaNova Meetings', 'LivaNova', new.id)
    RETURNING id INTO default_project_id;
  END IF;

  SELECT id INTO default_event_id FROM public.events WHERE project_id = default_project_id LIMIT 1;
  IF default_event_id IS NULL THEN
    -- Insert default event with a fixed UUID matching the frontend fallback route
    INSERT INTO public.events (id, project_id, name, event_type)
    VALUES ('00000000-0000-0000-0000-000000000003', default_project_id, 'Kick-off Meeting Barcelona', 'meeting')
    ON CONFLICT DO NOTHING;
  END IF;
  
  RETURN new;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- Trigger the function on new user signup
DROP TRIGGER IF EXISTS on_auth_user_created ON auth.users;
CREATE TRIGGER on_auth_user_created
  AFTER INSERT ON auth.users
  FOR EACH ROW EXECUTE FUNCTION public.handle_new_user();
