import os
import pytest

from dotenv import load_dotenv
from pipeline.transform.transform_to_gold import *
from supabase import create_client, Client

load_dotenv()

SAMPLE_RAW_CITY_PAYLOAD = {
    'city': 'New York',
    'payload': {
        'generationtime_ms': 0.29575825,
        'results': [{
            'admin1': 'New York',
            'admin1_id': 5128638,
            'country': 'United States',
            'country_code': 'US',
            'country_id': 6252001,
            'elevation': 10.0,
            'feature_code': 'PPL',
            'id': 5128581,
            'latitude': 40.71427,
            'longitude': -74.00597,
            'name': 'New York',
            'population': 8804190,
            'postcodes': [],
            'timezone': 'America/New_York'
        }]
    },
    'retrieve_date': '2026-11-01'
}

SAMPLE_RAW_AIR_PAYLOAD = {
    "city": "new york",
    "target_date": "2025-05-01",
    "data": {
        "coord": {
            "lon": -74.01,
            "lat": 40.71
        },
        "list": [
            {
                "main": {
                    "aqi": 2
                },
                "components": {
                    "co": 207.09,
                    "no": 0.12,
                    "no2": 11.75,
                    "o3": 90.7,
                    "so2": 1.28,
                    "pm2_5": 8.56,
                    "pm10": 10.69,
                    "nh3": 0.82
                },
                "dt": 1746057600
            },
            {
                "main": {
                    "aqi": 2
                },
                "components": {
                    "co": 212.69,
                    "no": 0,
                    "no2": 12.28,
                    "o3": 83.31,
                    "so2": 1.17,
                    "pm2_5": 9.37,
                    "pm10": 11.82,
                    "nh3": 0.84
                },
                "dt": 1746061200
            },
            {
                "main": {
                    "aqi": 2
                },
                "components": {
                    "co": 217.08,
                    "no": 0,
                    "no2": 12.32,
                    "o3": 78.33,
                    "so2": 1.07,
                    "pm2_5": 10.01,
                    "pm10": 12.59,
                    "nh3": 0.82
                },
                "dt": 1746064800
            }
        ]
    },
    "request_params": {
        "start": 1746057600,
        "end": 1746143999
    },
    "retrieve_date": "2026-10-31"
}

SAMPLE_GOLD_CITY = {
    "state": "new york",
    "lat": 40.7143,
    "lon": -74.006,
    "population": 8804190,
    "elevation": 10.0,
    "city": "new york",
    "country": "united states"
}

SAMPLE_GOLD_AIR = [
    {
        "date_time": "2025-04-30T20:00:00",
        "co": 207.09,
        "pm2_5": 8.56,
        "no2": 11.75,
        "aqi": 2,
        "retrieve_date": "2026-10-31",
        "sentiment_label": "",
        "city_id": 1,
        "aqi_rolling_7d": 0.0,
        "pm2_5_rolling_7d": 0.0
    },
    {
        "date_time": "2025-04-30T21:00:00",
        "co": 212.69,
        "pm2_5": 9.37,
        "no2": 12.28,
        "aqi": 2,
        "retrieve_date": "2026-10-31",
        "sentiment_label": "",
        "city_id": 1,
        "aqi_rolling_7d": 0.0,
        "pm2_5_rolling_7d": 0.0
    },
    {
        "date_time": "2025-04-30T22:00:00",
        "co": 217.08,
        "pm2_5": 10.01,
        "no2": 12.32,
        "aqi": 2,
        "retrieve_date": "2026-10-31",
        "sentiment_label": "",
        "city_id": 1,
        "aqi_rolling_7d": 0.0,
        "pm2_5_rolling_7d": 0.0
    }
]

# --- Fixtures ---

@pytest.fixture
def real_supabase_client():
    """Fixture to safely initialize a real Supabase client only for integration tests."""
    load_dotenv()
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_KEY")
    if not url or not key:
        pytest.skip("Supabase credentials not available for integration tests")
    return create_client(url, key)

@pytest.fixture
def load_gold_city(real_supabase_client):
    try:
        response = (
            real_supabase_client.table("gold_cities")
            .upsert(SAMPLE_GOLD_CITY, on_conflict="city")
            .execute()
        )
        log.info('Upserted SAMPLE_GOLD_CITY, ', response.data)
    except Exception as e:
        log.exception('Error: ', e)
        print('Unable to upsert SAMPLE_GOLD_CITY')

@pytest.fixture(autouse=True)
def remove_gold_city(real_supabase_client):
    try:
        response = (
            real_supabase_client.table("gold_cities")
            .delete()
            .eq("city", SAMPLE_GOLD_CITY['city'])
            .execute()
        )
        log.info('Deleted gold city test data, ', response.data)
    except Exception as e:
        log.exception('Error: ', e)
        print('Unable to delete gold city test data')

# --- Tests ---

def test_retrieve_city_id(real_supabase_client, load_gold_city):
    city_id = retrieve_city_id(real_supabase_client, SAMPLE_GOLD_CITY['city'])
    assert city_id > 0

def test_city_id_zero(real_supabase_client):
    city_id = retrieve_city_id(real_supabase_client, SAMPLE_GOLD_CITY['city'])
    assert city_id == 0

def test_transform_city_data():
    flat_city = transform_city_data(SAMPLE_RAW_CITY_PAYLOAD)
    assert flat_city == SAMPLE_GOLD_CITY

def test_invalid_city_record():
    city_record = {"payload": {"results": [[]]}}
    with pytest.raises(ValueError):
        transform_city_data(city_record)

def test_parse_air_data():

    pass
