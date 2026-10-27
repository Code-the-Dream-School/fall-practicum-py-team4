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

def load_raw_cities(supabase_client: Client, data: dict):
    """
    Inserts raw city geocoding responses into raw_table using the Supabase Python Client.
    
    Uniqueness Rule:
        The raw_table must have a unique constraint on city to ensure that running the loader
        multiple times for the same location performs an upsert instead of inserting duplicates.
    """

    # Checks if data exists and is formatted as a dict. 
    if (
        not data
        or not isinstance(data, dict)
        or 'payload' not in data
    ):
        LOG.warning("Invalid or empty data payload provided to load_raw")
        raise ValueError("Invalid or empty data payload provided to load_raw.")

    # parameter extraction
    city = data.get("city")
    retrieve_date = data.get("retrieve_date")
    
    # Inserts a record to the DB
    try: 
        record = {
            "city": city,
            "payload": data['payload'],
            "retrieve_date": retrieve_date,  
        }

        # Upsert, so it ensures running twice creates no duplicates (unique index on city)
        response = supabase_client.table("raw_cities").upsert(
            record, 
            on_conflict="city"
        ).execute()

        LOG.info("Successfully loaded geocoding info for %s", city)
        return response

    # raises an error if the record failed to insert/upsert to the DB    
    except Exception as e:
        LOG.error("Failed to insert raw data into Supabase for %s: %s", city, e)
        raise RuntimeError(f"Failed to insert raw data into Supabase: {e}") from e


def load_raw_air_pollution(supabase_client: Client, data: dict):
    """
    Inserts raw air pollution data and its associated metadata into raw_table
    using the Supabase Python Client.
    
    Uniqueness Rule:
        The raw_table must have a unique constraint or composite unique index on
        (city and target_date) to ensure that running the loader multiple times
        for the location and day performs an upsert instead of inserting duplicates.
    """

    # Checks if extract() response exists, is formatted as a dict and has a 'list' key (contains openweather payload). 
    if (
        not data
        or not isinstance(data, dict)
        or 'data' not in data
    ):
        LOG.warning("Invalid or empty data payload provided to load_raw")
        raise ValueError("Invalid or empty data payload provided to load_raw.")


    # Extract payload
    city = data.get('city')
    payload = data.get("data")
    retrieve_date = data.get("retrieve_date")
    target_date = data.get("target_date")
    start = data.get("start")
    end = data.get("end")

    # Inserts a record to the DB
    try: 
        record = {
            "city": city,
            # should we store this as a timestamp? or keep it as a string for human reading?
            "target_date": target_date,
            "data": payload,
            # should the extract function take care of this date? or should the load function do it?
            "start": start,
            "end": end,
            "retrieve_date": retrieve_date
        }

        # Upsert, so it ensures running twice creates no duplicates (requires unique index on city and target_date)
        response = supabase_client.table("raw_air_pollution").upsert(
            record, 
            on_conflict="city, target_date"
        ).execute()

        LOG.info("Successfully loaded raw air pollution data for %s at date %s", city, target_date)
        return response

    # raises an error if the record failed to insert/upsert to the DB    
    except Exception as e:
        LOG.error("Failed to insert raw data into Supabase for %s at date %s: %s", city, target_date, e)
        raise RuntimeError(f"Failed to insert raw data into Supabase: {e}") from e