import os
from supabase import create_client

SUPABASE_URL = "https://mmbkfinzqsxczdjvhrge.supabase.co"
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")

if not SUPABASE_KEY:
    # Let's read from the local .env file in apps/api
    with open("apps/api/.env", "r") as f:
        for line in f:
            if line.startswith("SUPABASE_SERVICE_ROLE_KEY="):
                SUPABASE_KEY = line.split("=", 1)[1].strip().strip('"').strip("'")
            elif line.startswith("SUPABASE_URL="):
                SUPABASE_URL = line.split("=", 1)[1].strip().strip('"').strip("'")

print("Connecting to:", SUPABASE_URL)
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# 1. List events
events = supabase.table("events").select("*").execute()
print("\n--- EVENTS ---")
for e in events.data:
    print(f"ID: {e['id']} | Name: {e['name']} | ProjectID: {e['project_id']}")

# 2. List uploaded files
files = supabase.table("uploaded_files").select("*").execute()
print("\n--- UPLOADED FILES ---")
for f in files.data:
    print(f"ID: {f['id']} | EventID: {f['event_id']} | Filename: {f['original_filename']} | Status: {f['import_status']} | Type: {f['source_type']}")
