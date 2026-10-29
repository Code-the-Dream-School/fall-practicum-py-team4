import datetime
import json
import logging
import os

from dotenv import load_dotenv
from flatten_json import flatten
from icecream import ic
from supabase import create_client
# from data_contracts import GoldSchema

load_dotenv()

SUPABASE_KEY = os.getenv("SUPABASE_KEY")
SUPABASE_URL = os.getenv("SUPABASE_URL")

if SUPABASE_URL is None or SUPABASE_KEY is None:
    raise RuntimeError("Supabase URL and Key must be set in the environment.")

supabase_client = create_client(SUPABASE_URL, SUPABASE_KEY)

def convert_unix_to_timestamp(unix: int):
    return datetime.datetime.fromtimestamp(unix).isoformat()

def transform_city_data(city_record: dict):
    sup_cities_data = supabase_client.table('gold_cities').select("city").execute().data

    presently_enriched_cities = {
        c['city']for c in sup_cities_data if type(c) == dict
    }

    city_data = city_record['results'][0]
    if not isinstance(city_data, dict):
            raise ValueError("Invalid or empty data payload provided.")

    if city_data['name'] in presently_enriched_cities:
        print("This city record has been enriched.")
        return []
    
    flat_enrich_city = {
        "city_name": city_data['name'],
        "state": city_data['admin1'],
        "lat": city_data['latitude'],
        "lon": city_data['longitude'],
        "population": city_data['population'],
        "elevation": city_data['elevation']
    }

def transform_air_data(air_record: dict):
    city = air_record['city']
    lon = air_record['data']['coord']['lon']
    lat = air_record['data']['coord']['lat']
    retrieve_date = air_record['retrieve_date']

    if not isinstance(air_record, dict):
        raise ValueError("Invalid or empty data payload provided.")

    flat_air_record = [{
            "city": city,
            "country": "",
            "date_time": convert_unix_to_timestamp(l['dt']),
            "co": l['components']['co'],
            "pm2_5": l['components']['pm2_5'],
            "no": l['components']['no'],
            "aqi": l['main']['aqi'],
            "retrieve_date": retrieve_date,
            "sentiment_label": "",
            "running_average": 0.0,
            "city_id": 1,
            "lon": lon,
            "lat": lat
        } for l in air_record['list']]

    sup_air_data = supabase_client.table('gold_air_data').select("date_time", "city_id").execute().data
    presently_enriched_air = {
        (a['date_time'], a['city_id']) for a in sup_air_data if type(a) == dict
    }

    to_enrich_air = [r for r in flat_air_record if (r['date_time'], r['city_id']) not in presently_enriched_air]
    
    if not to_enrich_air:
        print("All records have been enriched.")
        return []
