import logging

from datetime import datetime, timezone
from dotenv import load_dotenv
from supabase import Client
from typing import Optional

log = logging.getLogger(__name__)

def retrieve_city_id(supabase_client: Client, city: str) -> Optional[int]:
    response = (
        supabase_client.table("gold_cities")
        .select("id", "city")
        .eq("city", city)
        .execute()
    )
    if not response.data or not isinstance(response.data[0], dict):
        log.warning("No city found for %s", city)
        return None
    city_id = response.data[0]['id']
    if isinstance(city_id, int):
        return city_id
    return None

def convert_unix_to_timestamp(unix: int) -> str:
    """Converts a unix timestamp to a UTC 'YYYY-MM-DD HH:MM' string."""
    return datetime.fromtimestamp(unix, timezone.utc).strftime("%Y-%m-%d %H:%M")

def transform_city_data(city_record: dict) -> dict:
    """Takes a raw city record. Enriches the record and returns a dictionary"""

    if not city_record or not isinstance(city_record, dict):
        log.error("Empty or invalid city record.")
        raise ValueError("Empty or invalid city.")

    results = city_record.get("payload", {}).get("results", [])
    if not results or not isinstance(results[0], dict):
        raise ValueError("City record has no results.")
    city_data = results[0]

    city_data_dict = {
        "state": "admin1",
        "lat": "latitude",
        "lon": "longitude",
        "population": "population",
        "elevation": "elevation",
        "city": "name",
        "country": "country"
    }
    flat_enrich_city = {}

    for gold_name, raw_name in city_data_dict.items():
        value = city_data.get(raw_name)
        if isinstance(value, float):
            value = round(value, 4)
        elif isinstance(value, str):
            value = value.lower()
        flat_enrich_city[gold_name] = value

    return flat_enrich_city

def parse_air_data(air_record: dict, city_id: int) -> list[dict]:
    """Flattens each hourly reading in the air record into a row for gold_air_data."""
    retrieve_date = air_record.get("retrieve_date")
    readings = air_record.get("data", {}).get("list", [])

    flat_air_records = []
    for reading in readings:
        if "dt" not in reading:
            log.warning("Skipping reading with no timestamp: %s", reading)
            continue
        components = reading.get("components", {})
        flat_air_records.append({
            "date_time": convert_unix_to_timestamp(reading["dt"]),
            "co": components.get("co"),
            "pm2_5": components.get("pm2_5"),
            "no2": components.get("no2"),
            "aqi": reading.get("main", {}).get("aqi"),
            "retrieve_date": retrieve_date,
            "sentiment_label": "",
            "city_id": city_id,
            "aqi_rolling_7d": 0.0,
            "pm2_5_rolling_7d": 0.0,
        })
    return flat_air_records

def transform_air_data(supabase_client: Client, air_record: dict) -> list[dict]:
    """
    Takes Supabase Client and air record from extraction. Returns a list of 
    flat dictionaries by calling the parse function. The Client is
    used to find the city_id from gold_cities database. Returns empty list if
    city_id not found.
    """
    if not air_record or not isinstance(air_record, dict):
        raise ValueError("Invalid or empty data payload provided.")

    city = air_record.get('city')
    if not city or not isinstance(city, str):
            raise ValueError("Record is missing 'city'.")
    city_id = retrieve_city_id(supabase_client, city.lower())
    if city_id:
        return parse_air_data(air_record, city_id)
    else:
        log.warning("City Name did not return a valid id. Check spelling.")
    return []
