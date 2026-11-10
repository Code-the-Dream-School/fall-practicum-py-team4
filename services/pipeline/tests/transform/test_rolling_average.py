import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock
from pipeline.transform.rolling_average import add_rolling_average, fetch_historical_readings


@pytest.mark.unit
def test_rolling_average_warm_up_and_calculation():
    """Verifies the warm-up period behavior"""
    base_time = datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc)
    
    readings = []
    for i in range(8):
        readings.append({
            "date_time": base_time + timedelta(days=i),
            "aqi": 10.0 if i < 7 else 20.0
        })

    enriched = add_rolling_average(readings, field="aqi")

    for i in range(7):
        assert enriched[i]["aqi_rolling_7d"] == 0, f"Row {i} should be 0 during warm-up"

    assert enriched[7]["aqi_rolling_7d"] is not None


@pytest.mark.unit
def test_rolling_average_math_accuracy():
    """Verifies mathematical precision"""
    base_time = datetime(2026, 10, 1, 0, 0, tzinfo=timezone.utc)
    
    readings = [
        {"date_time": base_time + timedelta(days=i), "aqi": 10.0} 
        for i in range(8)
    ]

    enriched = add_rolling_average(readings, field="aqi")
    assert enriched[7]["aqi_rolling_7d"] == 10.0


@pytest.mark.unit
def test_rolling_average_handles_unsorted_input():
    """Verifies sorting and ordering"""
    base_time = datetime(2026, 10, 1, 0, 0, tzinfo=timezone.utc)
    
    readings = [
        {"date_time": base_time + timedelta(days=2), "aqi": 15.0},
        {"date_time": base_time + timedelta(days=0), "aqi": 5.0},
        {"date_time": base_time + timedelta(days=1), "aqi": 10.0},
    ]

    enriched = add_rolling_average(readings, field="aqi")
    assert enriched[0]["date_time"] == base_time + timedelta(days=0)


@pytest.mark.unit
def test_rolling_average_raises_on_duplicates():
    """Verifies error handling and data integrity"""
    base_time = datetime(2026, 10, 1, 0, 0, tzinfo=timezone.utc)
    readings = [
        {"date_time": base_time, "aqi": 10.0},
        {"date_time": base_time, "aqi": 20.0},
    ]

    with pytest.raises(ValueError, match="Duplicate reading time"):
        add_rolling_average(readings, field="aqi")


@pytest.mark.unit
def test_fetch_historical_readings_success():
    """Verifies successful query construction, timestamp parsing, and combination."""
    base_time = datetime(2026, 11, 9, 12, 0, tzinfo=timezone.utc)
    
    # Mock Supabase client response
    mock_supabase = MagicMock()
    mock_response = MagicMock()
    mock_response.data = [
        {"date_time": "2026-11-08T12:00:00+00:00", "city_id": 1, "aqi": 12.0}
    ]
    mock_supabase.table.return_value.select.return_value.eq.return_value.gte.return_value.lt.return_value.order.return_value.execute.return_value = mock_response

    current_readings = [
        {"date_time": base_time, "city_id": 1, "aqi": 15.0}
    ]

    result = fetch_historical_readings(
        supabase_client=mock_supabase,
        city_id=1,
        current_readings=current_readings,
        city_name="Charlotte",
        table_name="gold_cities"
    )

    # Verify history was parsed into datetime and prepended
    assert len(result) == 2
    assert isinstance(result[0]["date_time"], datetime)
    assert result[0]["aqi"] == 12.0
    assert result[1]["aqi"] == 15.0


@pytest.mark.unit
def test_fetch_historical_readings_empty_input():
    """Verifies empty current readings returns early without querying Supabase."""
    mock_supabase = MagicMock()
    result = fetch_historical_readings(
        supabase_client=mock_supabase,
        city_id=1,
        current_readings=[],
        city_name="Charlotte"
    )
    assert result == []
    mock_supabase.table.assert_not_called()


@pytest.mark.unit
def test_fetch_historical_readings_raises_runtime_error():
    """Verifies Supabase exceptions are caught and wrapped in a RuntimeError."""
    base_time = datetime(2026, 11, 9, 12, 0, tzinfo=timezone.utc)
    mock_supabase = MagicMock()
    
    # Simulate a database crash / exception
    mock_supabase.table.return_value.select.return_value.eq.return_value.gte.return_value.lt.return_value.order.return_value.execute.side_effect = Exception("DB Connection timeout")

    current_readings = [{"date_time": base_time, "city_id": 1, "aqi": 15.0}]

    with pytest.raises(RuntimeError, match="Failed to fetch historical readings for Charlotte"):
        fetch_historical_readings(
            supabase_client=mock_supabase,
            city_id=1,
            current_readings=current_readings,
            city_name="Charlotte"
        )