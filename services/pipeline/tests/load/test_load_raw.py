import os
import pytest
from dotenv import load_dotenv
from supabase import create_client
from unittest.mock import MagicMock
from pipeline.load.load_raw import load_raw_cities, load_raw_air_pollution

load_dotenv()
supabase = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY"))

# Test Parameters
TEST_CITY = 'Charlotte'
TEST_DATE = "2000-01-01"

# Sample payload for load_raw_cities
SAMPLE_CITY_DATA = {
    "id": 4460243,
    "name": "Charlotte",
    "country_code": "US",
    "lat": 35.22709,
    "lon": -80.84313,
    "feature_code": "PPLA2",
    "country_code": "US",
    "admin1_id": 4482348,
    "admin2_id": 4478884,
    "timezone": "America/New_York",
    "population": 911311,
    "postcodes": ['28201', '28202', '28203'],
    "country_id": 6252001,
    "country": "United States",
    "admin1": "North Carolina",
    "admin2": "Mecklenburg County"
}

SAMPLE_POLLUTION_DATA = {
    "list": {
        "coord": {"lon": -80.8431, "lat": 35.2271},
        "list": [
            {
            "dt": 1767225600,
            "main": {"aqi": 2},
            "components": {
                "co": 162.21,
                "no": 0,
                "no2": 5.53,
                "o3": 81.67,
                "so2": 81.67,
                "pm2_5": 3.87,
                "pm10": 4.98,
                "nh3": 1.84,
                }
            }
        ]
    },   
    "retrieve_date": "2026-10-26"
}

@pytest.fixture(autouse=True)
def cleanup_test_data():
    """Fixture to clean up Supabase test data after each integration test runs."""
    yield
    try:
        supabase.table('raw_cities').delete().eq("city", TEST_CITY).execute()
        supabase.table('raw_air_pollution').delete().eq('city', TEST_CITY).eq('target_date', TEST_DATE).execute()
    except Exception as e:
        print(f"Warning: Cleanup failed: {e}")

# --- Tests for load_raw_cities ---

@pytest.mark.integration
def test_normal_load():
    """Test 1: Test Normal load for raw_cities"""
    response = load_raw_cities(
        supabase_client = supabase,
        data = SAMPLE_CITY_DATA,
    )
    assert response is not None
    assert response['city'] == TEST_CITY

@pytest.mark.integration
def test_idempotency_cities():
    """Test 2: Test Idempotency for raw_cities"""
    load_raw_cities(supabase, SAMPLE_CITY_DATA)
    response = load_raw_cities(supabase, SAMPLE_CITY_DATA)
    assert response is not None

@pytest.mark.integration
def test_empty_input_raises_error_cities():
    """Test 3: Raises a clear ValueError if citi input data is empty."""
    with pytest.raises(ValueError, match="Invalid or empty data payload"):
        load_raw_cities(
            supabase_client=supabase,
            data={},
        )

@pytest.mark.unit
def test_load_raw_cities_mocked():
    # Arrange: Create a mock Supabase client chain
    mock_supabase = MagicMock()
    mock_response = MagicMock()
    mock_response.data = [{"id": 1}]
    
    # Mock the method chaining: client.table().upsert().execute()
    mock_supabase.table.return_value.upsert.return_value.execute.return_value = mock_response

    response = load_raw_cities(
        supabase_client=mock_supabase,
        data = SAMPLE_CITY_DATA,
    )

    # Assert: Verify correct table and upsert arguments were passed
    mock_supabase.table.assert_called_once_with('raw_cities')
    mock_supabase.table.return_value.upsert.assert_called_once()
    assert response['city'] == TEST_CITY

# --- Tests for load_raw_air_pollution ---

@pytest.mark.integration
def test_normal_load_pollution():
    """Test 1: Normal load for raw air pollution"""
    response = load_raw_air_pollution(
        supabase_client=supabase,
        data=SAMPLE_POLLUTION_DATA,
        city=TEST_CITY,
        date=TEST_DATE
    )
    assert response is not None
    assert response["city"] == TEST_CITY
    assert response["target_date"] == TEST_DATE


@pytest.mark.integration
def test_load_twice_idempotency_pollution():
    """Test 2: Idempotency for raw air pollution"""
    load_raw_air_pollution(supabase, SAMPLE_POLLUTION_DATA, TEST_CITY, TEST_DATE)
    response = load_raw_air_pollution(supabase, SAMPLE_POLLUTION_DATA, TEST_CITY, TEST_DATE)
    assert response is not None


@pytest.mark.integration
def test_empty_input_raises_error_pollution():
    """Test 3: Raises ValueError if pollution input data is empty."""
    with pytest.raises(ValueError, match="Invalid or empty data payload"):
        load_raw_air_pollution(
            supabase_client=supabase,
            data={},
            city=TEST_CITY,
            date=TEST_DATE
        )


@pytest.mark.unit
def test_load_raw_pollution_mocked():
    """Unit test with mocks for load_raw_air_pollution."""
    mock_supabase = MagicMock()
    mock_response = MagicMock()
    mock_response.data = [{"id": 1}]
    
    mock_supabase.table.return_value.upsert.return_value.execute.return_value = mock_response

    response = load_raw_air_pollution(
        supabase_client=mock_supabase,
        data=SAMPLE_POLLUTION_DATA,
        city=TEST_CITY,
        date=TEST_DATE
    )

    mock_supabase.table.assert_called_once_with("raw_air_pollution")
    mock_supabase.table.return_value.upsert.assert_called_once()
    assert response["city"] == TEST_CITY