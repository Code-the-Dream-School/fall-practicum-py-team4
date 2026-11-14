import logging
import os
import pytest

from datetime import datetime, timezone
from dotenv import load_dotenv
from supabase import create_client
from pipeline.load.load_gold import serialize_record, load_gold_cities, load_gold_air_data

load_dotenv()

log = logging.getLogger(__name__)

# Name that will never collide with real pipeline data
TEST_CITY = "pytest city"

DATETIME_OBJECT = {
    "date_time": datetime(2025, 5, 1, 0, 0, tzinfo=timezone.utc)
}

SAMPLE_GOLD_CITY = {
    "state": "new york",
    "lat": 40.7143,
    "lon": -74.006,
    "population": 8804190,
    "elevation": 10.0,
    "city": TEST_CITY,
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


def delete_test_city(supabase_client):
    """Deletes TEST_CITY and any gold_air_data rows that point to it."""
    response = (
        supabase_client.table("gold_cities")
        .select("id")
        .eq("city", TEST_CITY)
        .execute()
    )
    city_ids = [row["id"] for row in response.data]
    if city_ids:
        # Air rows first, because they reference gold_cities.id
        supabase_client.table("gold_air_data").delete().in_("city_id", city_ids).execute()
        supabase_client.table("gold_cities").delete().in_("id", city_ids).execute()
    log.info("Deleted test city %s", TEST_CITY)


@pytest.fixture
def cleanup_gold_city(real_supabase_client):
    """For tests that insert the test city themselves: deletes it afterwards."""
    yield
    delete_test_city(real_supabase_client)


@pytest.fixture
def gold_city(real_supabase_client):
    """Inserts the test city, yields its id, then deletes it and its air rows."""
    response = (
        real_supabase_client.table("gold_cities")
        .upsert(SAMPLE_GOLD_CITY, on_conflict="city")
        .execute()
    )
    yield response.data[0]["id"]
    delete_test_city(real_supabase_client)


@pytest.fixture
def gold_air(gold_city):
    """SAMPLE_GOLD_AIR with city_id pointing at the test city."""
    return [{**row, "city_id": gold_city} for row in SAMPLE_GOLD_AIR]


# --- Tests for serialize_record ---

@pytest.mark.unit
def test_serialize_record():
    datetime_string = serialize_record(DATETIME_OBJECT)
    assert datetime_string == {"date_time": "2025-05-01T00:00:00+00:00"}


@pytest.mark.unit
def test_serialize_pass_through():
    serial_city = serialize_record(SAMPLE_GOLD_CITY)
    assert serial_city == SAMPLE_GOLD_CITY


# --- Tests for load_gold_cities ---


@pytest.mark.integration
def test_load_gold_cities(real_supabase_client, cleanup_gold_city):
    """Test load of cleaned city data"""
    response = load_gold_cities(real_supabase_client, SAMPLE_GOLD_CITY)
    assert response == 1


@pytest.mark.integration
def test_load_gold_cities_idempotency(real_supabase_client, cleanup_gold_city):
    """Test idempotency of load_gold_cities"""
    load_gold_cities(real_supabase_client, SAMPLE_GOLD_CITY)
    response = load_gold_cities(real_supabase_client, SAMPLE_GOLD_CITY)
    assert response == 1


@pytest.mark.integration
def test_empty_load_gold_cities(real_supabase_client):
    """Test an empty set passing into load_gold_cities raises ValueError"""
    with pytest.raises(ValueError, match="Invalid or empty data payload"):
        load_gold_cities(real_supabase_client, data={})


# --- Tests for load_gold_air_data ---


@pytest.mark.integration
def test_load_gold_air_data(real_supabase_client, gold_air):
    """Test load of cleaned air data"""
    response = load_gold_air_data(real_supabase_client, gold_air)
    assert response == 1


@pytest.mark.integration
def test_load_gold_air_data_idempotency(real_supabase_client, gold_air):
    """Test idempotency of load_gold_air_data"""
    load_gold_air_data(real_supabase_client, gold_air)
    response = load_gold_air_data(real_supabase_client, gold_air)
    assert response == 1


@pytest.mark.integration
def test_empty_load_gold_air_data(real_supabase_client):
    """Test an empty set passing into load_gold_cities raises ValueError"""
    with pytest.raises(ValueError, match="Invalid or empty data payload"):
        load_gold_air_data(real_supabase_client, data=[{}])
