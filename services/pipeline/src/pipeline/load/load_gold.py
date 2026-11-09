import os
from supabase import create_client, Client
from datetime import datetime, timezone
from dotenv import load_dotenv
import logging

load_dotenv()

# Logging client for tracking successful data loads and debugging failures.
LOG = logging.getLogger(__name__)

def load_gold_cities(supabase_client: Client, data: dict):
    """
    Inserts gold city responses into gold_cities using the Supabase Python Client.
    
    Uniqueness Rule:
        The gold_table must have a unique constraint on city to ensure that running the loader
        multiple times for the same location performs an upsert instead of inserting duplicates.
    """

    if (
        not supabase_client
        or not (isinstance(supabase_client, Client))
    ):
        LOG.warning("Invalid or missing Supabase client provided.")
        raise ValueError("A valid Supabase client instance is required to load data.")
    
    # Inserts a record to the DB
    try: 

        # Upsert, so it ensures running twice creates no duplicates (unique index on city)
        response = supabase_client.table("raw_cities").upsert(
            data, 
            on_conflict="city"
        ).execute()

        LOG.info("Successfully loaded geocoding info for %s", data['city'])
        return 1
    # raises an error if the record failed to insert/upsert to the DB
    except Exception as e:
        LOG.error("Failed to insert gold data into Supabase for %s: %s", data['city'], e)
        raise RuntimeError(f"Failed to insert raw data into Supabase: {e}") from e

def load_gold_air_data(supabase_client: Client, data: dict):
    """
    Inserts gold air pollution data and its associated metadata into gold_air_data
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
    pass
