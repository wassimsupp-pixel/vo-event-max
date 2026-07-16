import sys
import os
sys.path.append(os.path.dirname(__file__))

import asyncio
from supabase import create_client
import config
from services.consolidation_service import extract_domain_data_from_sources

def main():
    supabase = create_client(config.SUPABASE_URL, config.SUPABASE_SERVICE_ROLE_KEY)
    
    # Get the latest event
    resp = supabase.table("events").select("id, name").execute()
    if not resp.data:
        print("No events found!")
        return
        
    for event in resp.data:
        event_id = event["id"]
        print(f"Extracting domain data for event: {event['name']} ({event_id})...")
        extract_domain_data_from_sources(event_id, supabase)
        print("Extraction complete!")

if __name__ == "__main__":
    main()
