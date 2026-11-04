import datetime
import logging

from dotenv import load_dotenv
from icecream import ic
from supabase import Client

load_dotenv()

log = logging.getLogger(__name__)

def retrieve_city_id(supabase_client: Client, city: str) -> int:
    response = (
        supabase_client.table("gold_cities")
        .select("id", "city")
        .eq("city", city)
        .execute()
    )
    ic(response.data)
    if not response.data or not isinstance(response.data[0], dict):
        log.warning("Response did not come back with a dictionary")
    elif isinstance(response.data[0], dict):
        id = response.data[0]['id']
        if isinstance(id, int):
            return id
    return 0

def convert_unix_to_timestamp(unix: int) -> str:
    """Takes unix timestamp and returns date/time in iso format"""
    return datetime.datetime.fromtimestamp(unix).isoformat()

def transform_city_data(city_record: dict) -> dict:
    """Takes Supabase client and a record from the raw city table. Converts the payload from the raw data
    and uploads to Supabase gold_city table"""

    city_data = city_record['payload']['results'][0]
    if not isinstance(city_data, dict):
        raise ValueError("Invalid or empty data payload provided.")
    
    flat_enrich_city = {
        "state": city_data['admin1'].lower(),
        "lat": round(city_data['latitude'], 4),
        "lon": round(city_data['longitude'], 4),
        "population": city_data['population'],
        "elevation": city_data['elevation'],
        "city": city_data['name'].lower(),
        "country": city_data['country'].lower()
    }

    return flat_enrich_city

def parse_air_data(air_record: dict, city_id: int) -> list:
    """
    This function is called through transform_air_data. Not called directly by orchestration
    Uses the air_record dictionary and city_id to parse the variables to
    be loaded to the gold_air_data. Returns a list of dicts.
    """
    retrieve_date = air_record['retrieve_date']

    flat_air_record = [{
            "date_time": convert_unix_to_timestamp(l['dt']),
            "co": l['components']['co'],
            "pm2_5": l['components']['pm2_5'],
            "no2": l['components']['no2'],
            "aqi": l['main']['aqi'],
            "retrieve_date": retrieve_date,
            "sentiment_label": "",
            "city_id": city_id,
            "aqi_rolling_7d": 0.0,
            "pm2_5_rolling_7d": 0.0
        } for l in air_record['data']['list']]
    
    return flat_air_record    

def transform_air_data(supabase_client: Client, air_record: dict) -> list:
    """
    Takes Supabase Client and air record from extraction. Returns a list of 
    flat dictionaries by calling the parse function. The Client is
    used to find the city_id from gold_cities database. Returns empty list if
    city_id not found.
    """
    if not isinstance(air_record, dict):
        raise ValueError("Invalid or empty data payload provided.")

    city = air_record['city']
    city_id = retrieve_city_id(supabase_client, city)
    if city_id > 0:
        return parse_air_data(air_record, city_id)
    else:
        log.warning("City Name did not return a valid id. Check spelling.")
    return []
