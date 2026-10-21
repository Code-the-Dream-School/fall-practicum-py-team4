import os
import pytest
from dotenv import load_dotenv
from supabase import create_client
from unittest.mock import MagicMock
from pipeline.load.load_raw import load_raw

load_dotenv()
supabase = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY"))

# Test Parameters
LAT, LON = 35.22709, -80.84313
TEST_DATE = "2000-01-01"
TEST_TABLE = "raw_table"

# Realistic sample payload matching your pipeline output structure
SAMPLE_EXTRACTION_DATA = {
    "city": "Charlotte",
    "country_code": "US",
    "lat": LAT,
    "lon": LON,
    "start": "2000-01-01T00:00:00Z",
    "end": "2000-01-02T00:00:00Z",
    "run_id": "test_run_normal",
    "pipeline_run_id": 1,
    "retrieved_at": "2000-01-02T14:48:08.981311Z",
    "request_params": {"lat": LAT, "lon": LON, "start": 946684800, "end": 946771200},
    "payload": {
        "coord": {"lon": LON, "lat": LAT},
        "list": [
            {"dt": 1790812800, "main": {"aqi": 2}, "components": {"co": 155.29, "pm2_5": 12.26}}
        ]
    },
    "source": "openweather",
    "endpoint": "https://api.openweathermap.org/data/2.5/air_pollution/history",
    "schema_version": 1
}

@pytest.fixture(autouse=True)
def cleanup_test_data():
    """Fixture to clean up Supabase test data after each integration test runs."""
    yield
    try:
        supabase.table(TEST_TABLE).delete().eq("date", TEST_DATE).execute()
    except Exception as e:
        print(f"Warning: Cleanup failed: {e}")

@pytest.mark.integration
def test_normal_load():
    """Test 1: Test Normal load"""
    response = load_raw(
        supabase_client = supabase,
        data = SAMPLE_EXTRACTION_DATA,
    )
    assert response is not None

@pytest.mark.integration
def test_load_twice_idempotency():
    """Test 2: Test Idempotency"""
    response = load_raw(supabase, SAMPLE_EXTRACTION_DATA)
    assert response is not None

@pytest.mark.integration
def test_empty_input_raises_error():
    """Test 3: Raises a clear ValueError if input data is empty."""
    with pytest.raises(ValueError, match="Invalid or empty data payload"):
        load_raw(
            supabase_client=supabase,
            data={},
        )

@pytest.mark.unit
def test_load_raw_mocked():
    # Arrange: Create a mock Supabase client chain
    mock_supabase = MagicMock()
    mock_response = MagicMock()
    mock_response.data = [{"id": 1}]
    
    # Mock the method chaining: client.table().upsert().execute()
    mock_supabase.table.return_value.upsert.return_value.execute.return_value = mock_response

    response = load_raw(
        supabase_client=mock_supabase,
        data = SAMPLE_EXTRACTION_DATA,
    )

    # Assert: Verify correct table and upsert arguments were passed
    mock_supabase.table.assert_called_once_with(TEST_TABLE)
    mock_supabase.table.return_value.upsert.assert_called_once()
    assert response == mock_response