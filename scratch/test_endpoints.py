import httpx
import time

event_id = "3e230f01-dc64-4ca4-89dd-b197a67eada9"
base_url = "https://vo-event-max-api-production.up.railway.app/api"

endpoints = {
    "participants": f"/events/{event_id}/participants?per_page=5",
    "files": f"/events/{event_id}/files",
    "exceptions": f"/events/{event_id}/exceptions"
}

# We need the authorization token or headers?
# Wait, let's check dependencies.py in apps/api to see if auth is required!
# In dependencies.py:
# get_current_user parses the Authorization header or reads supabase session.
# Wait, in development, or if token is not passed, does it allow?
# Let's run the queries and print the response status and content.

for name, path in endpoints.items():
    url = base_url + path
    print(f"Testing {name} at {url}...")
    start = time.time()
    try:
        # In production, we need a valid Authorization header!
        # Wait, how does the frontend authenticate?
        # The frontend uses supabase auth, and passes the Bearer token in the headers!
        # But wait, let's see if we can query it without auth to see if it returns 401/403 or if it hangs,
        # or if we can run it locally with supabase client to see if it is database query issue!
        resp = httpx.get(url, timeout=10.0)
        dur = time.time() - start
        print(f"[{name}] Status: {resp.status_code} | Time: {dur:.2f}s")
        print(f"Response: {resp.text[:200]}\n")
    except Exception as e:
        print(f"[{name}] Failed: {e}\n")
