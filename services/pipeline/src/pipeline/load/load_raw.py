import os
from supabase import create_client, Client
from datetime import datetime, timezone
from dotenv import load_dotenv
import logging

load_dotenv()

# Logging client for tracking successful data loads and debugging failures.
LOG = logging.getLogger(__name__)

def load_raw_cities(supabase_client: Client, data: dict):
    """
    Inserts raw city geocoding responses into raw_table using the Supabase Python Client.
    
    Uniqueness Rule:
        The raw_table must have a unique constraint on city to ensure that running the loader
        multiple times for the same location performs an upsert instead of inserting duplicates.
    """

    if (
        not supabase_client
        or not (isinstance(supabase_client, Client))
    ):
        LOG.warning("Invalid or missing Supabase client provided.")
        raise ValueError("A valid Supabase client instance is required to load data.")


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
            "extracted_at": retrieve_date,  
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

    if (
        not supabase_client
        or not (isinstance(supabase_client, Client))
    ):
        LOG.warning("Invalid or missing Supabase client provided.")
        raise ValueError("A valid Supabase client instance is required to load data.")

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
    request_params = data.get("request_params") or {}
    start = request_params.get("start")
    end = request_params.get("end")

    # Inserts a record to the DB
    try: 
        record = {
            "city": city,
            "target_date": target_date,
            "data": payload,
            "start": start,
            "end": end,
            "extracted_at": retrieve_date
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