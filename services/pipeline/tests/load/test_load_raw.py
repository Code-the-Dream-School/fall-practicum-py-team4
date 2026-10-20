import os
import pytest
from datetime import datetime, timezone
from pathlib import Path
from dotenv import load_dotenv
from supabase import create_client
from unittest.mock import MagicMock
from pipeline.extract.openweather_air_pollution import fetch_air_pollution_history
from pipeline.load.load_raw import load_raw

load_dotenv()
supabase = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY"))

# Test Parameters
LAT, LON = 35.22709, -80.84313
TEST_DATE = "2026-10-01"

@pytest.mark.integration
def test_normal_load():
    """Test 1: Test Normal load"""
    record = fetch_air_pollution_history(
        raw_dir = Path("./raw"),
        city = "Charlotte",
        country_code = "US",
        lat = LAT,
        lon = LON,
        start = datetime(2026, 10, 1, 0, 0, tzinfo=timezone.utc),
        end = datetime(2026, 10, 2, 0, 0, tzinfo=timezone.utc),
        run_id = "test_run_normal",
        pipeline_run_id = 1
    ).to_dict()

    response = load_raw(
        supabase_client = supabase,
        data = record['payload'],
        longitude = LON,
        latitude = LAT,
        hours = 24,
        date = TEST_DATE
    )
    assert response is not None

@pytest.mark.integration
def test_load_twice_idempotency():
    """Test 2: Test Idempotency"""
    payload = {
        "coord": {"lat": LAT, "lon": LON},
        "list": [{"dt": 1790812800, "main": {"aqi": 1}, "components": {"co": 100.0}}]
    }

    load_raw(supabase, payload, LON, LAT, 24, TEST_DATE)
    
    response = load_raw(supabase, payload, LON, LAT, 24, TEST_DATE)
    assert response is not None

@pytest.mark.integration
def test_empty_input_raises_error():
    """Test 3: Raises a clear ValueError if input data is empty."""
    with pytest.raises(ValueError, match="Invalid or empty data payload"):
        load_raw(
            supabase_client=supabase,
            data={},
            longitude=LON,
            latitude=LAT,
            hours=24,
            date=TEST_DATE
        )

@pytest.mark.unit
def test_load_raw_mocked():
    # Arrange: Create a mock Supabase client chain
    mock_supabase = MagicMock()
    mock_response = MagicMock()
    mock_response.data = [{"id": 1}]
    
    # Mock the method chaining: client.table().upsert().execute()
    mock_supabase.table.return_value.upsert.return_value.execute.return_value = mock_response

    # Act
    payload = {"list": [{"dt": 1790812800}]}
    response = load_raw(
        supabase_client=mock_supabase,
        data=payload,
        longitude=-80.84313,
        latitude=35.22709,
        hours=24,
        date="2026-10-01"
    )

    # Assert: Verify correct table and upsert arguments were passed
    mock_supabase.table.assert_called_once_with("raw_table")
    mock_supabase.table.return_value.upsert.assert_called_once()
    assert response == mock_response