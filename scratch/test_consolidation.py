import os
import sys
import asyncio
from supabase import create_client

# Add apps/api to path so we can import services
sys.path.append(os.path.join(os.path.dirname(__file__), "../apps/api"))

from services.consolidation_service import run_consolidation

async def main():
    SUPABASE_URL = "https://mmbkfinzqsxczdjvhrge.supabase.co"
    SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")

    if not SUPABASE_KEY:
        with open("apps/api/.env", "r") as f:
            for line in f:
                if line.startswith("SUPABASE_SERVICE_ROLE_KEY="):
                    SUPABASE_KEY = line.split("=", 1)[1].strip().strip('"').strip("'")
                elif line.startswith("SUPABASE_URL="):
                    SUPABASE_URL = line.split("=", 1)[1].strip().strip('"').strip("'")

    print("Connecting to:", SUPABASE_URL)
    supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

    event_id = "3e230f01-dc64-4ca4-89dd-b197a67eada9"

    # Find or create a user ID
    # Let's query profiles or consolidation_runs to get a valid user_id
    runs_res = supabase.table("consolidation_runs").select("triggered_by").limit(1).execute()
    if runs_res.data:
        user_id = runs_res.data[0]["triggered_by"]
    else:
        # get first user from profiles or users table
        profiles_res = supabase.table("profiles").select("id").limit(1).execute()
        if profiles_res.data:
            user_id = profiles_res.data[0]["id"]
        else:
            user_id = "a4f74fc3-7be8-4920-b934-00c2c9210023" # fallback dummy

    print("Using User ID:", user_id)

    # Let's create a new consolidation run record
    run_res = supabase.table("consolidation_runs").insert({
        "event_id": event_id,
        "triggered_by": user_id,
        "status": "running"
    }).execute()

    run_id = run_res.data[0]["id"]
    print("Created Consolidation Run ID:", run_id)

    try:
        await run_consolidation(event_id, run_id, user_id, supabase)
        print("\nConsolidation run finished successfully!")
        
        # Check status in database
        final_res = supabase.table("consolidation_runs").select("*").eq("id", run_id).execute()
        print("Final status in DB:", final_res.data[0]["status"])
        print("Final stats in DB:", final_res.data[0]["stats"])
    except Exception as e:
        print("\nException raised directly:", e)
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())
