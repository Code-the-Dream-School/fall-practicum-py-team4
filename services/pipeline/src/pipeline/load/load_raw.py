import os
from supabase import create_client, Client
from datetime import datetime, timezone
from dotenv import load_dotenv
import logging

load_dotenv()

# Logging client for tracking successful data loads and debugging failures.
LOG = logging.getLogger(__name__)

# Initialize Supabase client
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    raise RuntimeError("Missing SUPABASE_URL or SUPABASE_KEY in environment variables.")

supabase_client: Client = create_client(SUPABASE_URL, SUPABASE_KEY)


def load_raw(supabase_client, data, longitude, latitude, hours, date):
    """
    Inserts raw air pollution data and its associated metadata into raw_table
    using the Supabase Python Client.

    Uniqueness Rule:
        The raw_table must have a unique constraint or composite unique index on 
        (date, latitude, longitude) to ensure that running the loader multiple times 
        for the same day and location performs an upsert instead of inserting duplicates.
    """

    # Checks if extract() response exists, is formatted as a dict and has a 'list' key (contains openweather payload). 
    if not data or not isinstance(data, dict) or not data.get("list"):
        LOG.warning("Invalid or empty data payload provided to load_raw for coords: (%s, %s)", latitude, longitude)
        raise ValueError("Invalid or empty data payload provided to load_raw.")

    # Inserts a record to the DB
    try: 
        record = {
            "longitude": longitude,
            "latitude": latitude,
            "hours": hours,
            "date": date,
            "data": data
        }

        # Upsert, so it ensures running twice creates no duplicates (requires unique index on date, latitude, longitude)
        response = supabase_client.table("raw_table").upsert(
            record, 
            on_conflict="date,latitude,longitude"
        ).execute()

        LOG.info("Successfully loaded raw air pollution data for date %s at (%s, %s)", date, latitude, longitude)
        return response

    # raises an error if the record failed to insert/upsert to the DB    
    except Exception as e:
        LOG.error("Failed to insert raw data into Supabase for date %s at (%s, %s): %s", date, latitude, longitude, e)
        raise RuntimeError(f"Failed to insert raw data into Supabase: {e}") from e