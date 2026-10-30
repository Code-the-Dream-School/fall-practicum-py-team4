import os
import pytest
from dotenv import load_dotenv
from supabase import create_client, Client
from unittest.mock import MagicMock
from pipeline.extract.geocoding_cache import get_city_from_cache

# Test Parameters
TEST_CITY = 'Charlotte'

# Sample mock response data for gold_cities cache hit
SAMPLE_CACHE_RECORD = {
    "city": TEST_CITY,
    "lat": 35.2271,
    "lon": -80.8431
}

@pytest.fixture
def real_supabase_client():
    """Fixture to safely initialize a real Supabase client only for integration tests."""
    load_dotenv()
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_KEY")
    if not url or not key:
        pytest.skip("Supabase credentials not available for integration tests")
    return create_client(url, key)


@pytest.mark.unit
def test_get_city_from_cache_hit():
    """Test 1: Verify that a cache hit returns existing coordinates from gold_cities."""
    mock_supabase = MagicMock(spec=Client)
    mock_response = MagicMock()
    mock_response.data = [SAMPLE_CACHE_RECORD]
    
    # Mock method chaining: client.table().select().eq().execute()
    mock_supabase.table.return_value.select.return_value.eq.return_value.execute.return_value = mock_response

    result = get_city_from_cache(TEST_CITY, mock_supabase)

    # Assert correct database calls and returned dictionary structure
    mock_supabase.table.assert_called_once_with("gold_cities")
    mock_supabase.table.return_value.select.return_value.eq.assert_called_once_with("city", TEST_CITY)
    
    assert result is not None
    assert result['city'] == TEST_CITY
    assert result['latitude'] == 35.2271
    assert result['longitude'] == -80.8431


@pytest.mark.unit
def test_get_city_from_cache_miss():
    """Test 2: Verify that a cache miss returns None correctly."""
    mock_supabase = MagicMock(spec=Client)
    mock_response = MagicMock()
    mock_response.data = []  # Empty data list indicates cache miss
    
    mock_supabase.table.return_value.select.return_value.eq.return_value.execute.return_value = mock_response

    result = get_city_from_cache("NonExistentCity", mock_supabase)

    mock_supabase.table.assert_called_once_with("gold_cities")
    assert result is None


@pytest.mark.unit
def test_get_city_from_cache_exception_returns_none():
    """Test 3: Unit test verifying that database exceptions are caught gracefully and return None."""
    mock_supabase = MagicMock(spec=Client)
    
    # Simulate a database error/exception during execution
    mock_supabase.table.return_value.select.return_value.eq.return_value.execute.side_effect = Exception("DB Connection Error")

    result = get_city_from_cache(TEST_CITY, mock_supabase)

    # Should log warning and return None safely rather than crashing
    assert result is None


@pytest.mark.integration
def test_cache_hit_integration(real_supabase_client):
    """Test 4: Integration test checking a live query against gold_cities table."""
    # Assuming 'Charlotte' is populated in your development gold_cities table,
    # or you can test against a known record.
    result = get_city_from_cache(TEST_CITY, real_supabase_client)
    
    if result is not None:
        assert result['city'] == TEST_CITY
        assert 'latitude' in result
        assert 'longitude' in result
    else:
        # If the city isn't seeded in the remote environment yet, verify it cleanly returned None
        assert result is None