
from supabase import Client
from datetime import datetime
import logging

# Logging client for tracking successful data loads and debugging failures.
LOG = logging.getLogger(__name__)


def serialize_record(record: dict) -> dict:
    """
    Returns a copy of the record with datetime values converted to ISO 8601 strings,
    since the Supabase client can't JSON-serialize datetime objects.
    """
    return {
        key: value.isoformat() if isinstance(value, datetime) else value
        for key, value in record.items()
    }


def load_gold_cities(supabase_client: Client, data: dict) -> int:
    """
    Inserts gold city responses into gold_cities using the Supabase Python Client.
    Returns 1 to signify successful upsert of 1 row.
    
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

    # Checks if data exists and is formatted as a dict. 
    if (
        not data
        or not isinstance(data, dict)
        or "city" not in data
    ):
        LOG.warning("Invalid or empty data payload provided to load_gold")
        raise ValueError("Invalid or empty data payload provided to load_gold.")
    
    # Inserts a record to the DB
    try: 

        # Upsert, so it ensures running twice creates no duplicates (unique index on city)
        response = supabase_client.table("gold_cities").upsert(
            data,
            on_conflict="city"
        ).execute()
        
        if not response or not response.data:
            LOG.error("Failed to upload gold city data. Supabase response empty.")
            raise IndexError("Supabase response empty")
        
        row = response.data[0]
        if not isinstance(row, dict):
            raise TypeError("Expected Supabase to return a row object.")

        LOG.info("Successfully loaded gold data info for %s", row.get("city"))
        return 1
    
    # raises an error if the record failed to insert/upsert to the DB
    except Exception as e:
        LOG.error("Failed to insert gold data into Supabase for %s: %s", data['city'], e)
        raise RuntimeError(f"Failed to insert gold data into Supabase: {e}") from e


def load_gold_air_data(supabase_client: Client, data: list) -> int:
    """
    Inserts gold air pollution data and its associated metadata into gold_air_data
    using the Supabase Python Client.
    Returns number of rows successfully upserted to Supabase
    
    Uniqueness Rule:
        The gold_table must have a unique constraint or composite unique index on
        (city_id and date_time) to ensure that running the loader multiple times
        for the location and day performs an upsert instead of inserting duplicates.
    """

    if (
        not supabase_client
        or not (isinstance(supabase_client, Client))
    ):
        LOG.warning("Invalid or missing Supabase client provided.")
        raise ValueError("A valid Supabase client instance is required to load data.")

    # Checks if data exists and is formatted as a dict . 
    if (
        not data
        or not isinstance(data, list)
        or not all(isinstance(row, dict) and "date_time" in row for row in data)
        or not all(isinstance(row, dict) and "city_id" in row for row in data)

    ):
        LOG.warning("Invalid or empty data payload provided to load_gold")
        raise ValueError("Invalid or empty data payload provided to load_gold.")

    # Inserts a record to the DB
    try: 
        # Upsert, so it ensures running twice creates no duplicates (requires unique index on city_id and date_time)
        response = supabase_client.table("gold_air_data").upsert(
            [serialize_record(i) for i in data],
            on_conflict="city_id, date_time"
        ).execute()

        if not response or not response.data:
            LOG.error("Failed to upload gold air data. Supabase response empty.")
            raise IndexError("Supabase response empty")

        LOG.info("Successfully loaded %s record(s) of gold air data", len(response.data))
        return len(response.data)

    # raises an error if the record failed to insert/upsert to the DB    
    except Exception as e:
        LOG.error("Failed to insert gold data into Supabase: %s", e)
        raise RuntimeError(f"Failed to insert gold data into Supabase: {e}") from e
