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


def load_raw(supabase_client: Client, data: dict):
    """
    Inserts raw air pollution data and its associated metadata into raw_table
    using the Supabase Python Client.
    
    Uniqueness Rule:
        The raw_table must have a unique constraint or composite unique index on
        (date, latitude, longitude) to ensure that running the loader multiple times
        for the same day and location performs an upsert instead of inserting duplicates.
    """

    # Checks if extract() response exists, is formatted as a dict and has a 'list' key (contains openweather payload). 
    if (
        not data
        or not isinstance(data, dict)
        or not data.get("payload", {}).get("list")
    ):
        LOG.warning("Invalid or empty data payload provided to load_raw")
        raise ValueError("Invalid or empty data payload provided to load_raw.")

    # parameter extraction
    city = data.get("city")
    country_code = data.get("country_code")
    longitude = data.get("lon")
    latitude = data.get("lat")

    start = data.get("start")
    if isinstance(start, str):
        start = datetime.fromisoformat(start.replace("Z", "+00:00"))

    end = data.get("end")
    if isinstance(end, str):
        end = datetime.fromisoformat(end.replace("Z", "+00:00"))

    hours = int((end - start).total_seconds() / 3600)
    date = start.strftime("%Y-%m-%d")

    # Extract payload
    payload = data.get("payload")

    # Inserts a record to the DB
    try: 
        record = {
            "city": city,
            "country_code": country_code,
            "longitude": longitude,
            "latitude": latitude,
            "start": start.isoformat(),
            "end": end.isoformat(),
            "hours": hours,
            "date": date,
            "data": payload
        }

        # Upsert, so it ensures running twice creates no duplicates (requires unique index on date, latitude, longitude)
        response = supabase_client.table("raw_table").upsert(
            record, 
            on_conflict="date,latitude,longitude"
        ).execute()

        LOG.info("Successfully loaded raw air pollution data for %s at date %s", city, date)
        return response

    # raises an error if the record failed to insert/upsert to the DB    
    except Exception as e:
        LOG.error("Failed to insert raw data into Supabase for %s at date %s: %s", city, date, e)
        raise RuntimeError(f"Failed to insert raw data into Supabase: {e}") from e