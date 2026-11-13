import copy
import logging
import os
import pytest

from datetime import datetime, timezone
from dotenv import load_dotenv
from supabase import create_client, Client
from unittest.mock import MagicMock
from pipeline.load.load_gold import serialize_record, load_gold_cities, load_gold_air_data

load_dotenv()

log = logging.getLogger(__name__)

DATETIME_OBJECT = {
    "datetime": datetime(2025, 5, 1, 0, 0, tzinfo=timezone.utc)
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

SAMPLE_GOLD_CITY_MISSING = {
    "state": "new york",
    "lon": -74.006,
    "population": 8804190,
    "elevation": 10.0,
    "city": "new york",
    "country": "united states"
}

SAMPLE_GOLD_AIR = [
    {
        "date_time": "2025-05-01T00:00:00+00:00",
        "co": 207.09,
        "pm2_5": 8.56,
        "no2": 11.75,
        "aqi": 2,
        "retrieve_date": "2026-10-31",
        "sentiment_label": "Fair",
        "city_id": 1,
        "aqi_rolling_7d": 0.0,
        "pm2_5_rolling_7d": 0.0,
        "llm_response": ""
    },
    {
        "date_time": "2025-05-01T01:00:00+00:00",
        "co": 212.69,
        "pm2_5": 9.37,
        "no2": 12.28,
        "aqi": 2,
        "retrieve_date": "2026-10-31",
        "sentiment_label": "Fair",
        "city_id": 1,
        "aqi_rolling_7d": 0.0,
        "pm2_5_rolling_7d": 0.0,
        "llm_response": ""
    },
    {
        "date_time": "2025-05-01T02:00:00+00:00",
        "co": 217.08,
        "pm2_5": 10.01,
        "no2": 12.32,
        "aqi": 2,
        "retrieve_date": "2026-10-31",
        "sentiment_label": "Fair",
        "city_id": 1,
        "aqi_rolling_7d": 0.0,
        "pm2_5_rolling_7d": 0.0,
        "llm_response": ""
    }
]

SAMPLE_GOLD_AIR_MISSING = [
    {
        "date_time": "2025-05-01T02:00:00+00:00",
        "co": 217.08,
        "pm2_5": 10.01,
        "no2": 12.32,
        "retrieve_date": "2026-10-31",
        "sentiment_label": "Fair",
        "city_id": 1,
        "aqi_rolling_7d": 0.0,
        "pm2_5_rolling_7d": 0.0,
        "llm_response": ""
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


# --- Tests for serialize_record ---


def test_serialize_record():
    datetime_string = serialize_record(DATETIME_OBJECT)
    assert datetime_string == "2025-05-01T00:00:00+00:00"


def test_serialize_pass_through():
    serial_city = serialize_record(SAMPLE_GOLD_CITY)
    assert serial_city == SAMPLE_GOLD_CITY


# --- Tests for load_gold_cities ---


def test_load_gold_cities(real_supabase_client, SAMPLE_GOLD_CITY):
    """Test load of cleaned city data"""
    response = load_gold_cities(real_supabase_client, SAMPLE_GOLD_CITY)
    assert response == 1


def test_load_gold_cities_idempotency(real_supabase_client, SAMPLE_GOLD_CITY):
    """Test idempotency of load_gold_cities"""
    load_gold_cities(real_supabase_client, SAMPLE_GOLD_CITY)
    response = load_gold_cities(real_supabase_client, SAMPLE_GOLD_CITY)
    assert response == 1


def test_empty_load_gold_cities(real_supabase_client):
    """Test an empty set passing into load_gold_cities raises ValueError"""
    with pytest.raises(ValueError, match="Invalid or empty data payload"):
        load_gold_cities(real_supabase_client, data={})


def test_missing_value_gold_cities(real_supabase_client, SAMPLE_GOLD_CITY_MISSING):
    """Test passing missing value into load_gold_cities raises ValueError"""
    with pytest.raises(ValueError, match="Invalid or empty data payload"):
        load_gold_cities(real_supabase_client, SAMPLE_GOLD_CITY_MISSING)


# --- Tests for load_gold_air_data ---


def test_load_gold_air_data(real_supabase_client, SAMPLE_GOLD_CITY):
    """Test load of cleaned city data"""
    response = load_gold_air_data(real_supabase_client, SAMPLE_GOLD_CITY)
    assert response == 1


def test_load_gold_air_data_idempotency(real_supabase_client, SAMPLE_GOLD_CITY):
    """Test idempotency of load_gold_cities"""
    load_gold_air_data(real_supabase_client, SAMPLE_GOLD_CITY)
    response = load_gold_air_data(real_supabase_client, SAMPLE_GOLD_CITY)
    assert response == 1


def test_empty_load_gold_air_data(real_supabase_client):
    """Test an empty set passing into load_gold_cities raises ValueError"""
    with pytest.raises(ValueError, match="Invalid or empty data payload"):
        load_gold_air_data(real_supabase_client, data=[{}])


def test_missing_value_gold_air_data(real_supabase_client, SAMPLE_GOLD_AIR_MISSING):
    """Test passing missing value into load_gold_cities raises ValueError"""
    with pytest.raises(ValueError, match="Invalid or empty data payload"):
        load_gold_air_data(real_supabase_client, SAMPLE_GOLD_AIR_MISSING)
