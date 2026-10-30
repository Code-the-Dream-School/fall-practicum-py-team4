import pytest
from datetime import datetime, timedelta
from pipeline.transform.rolling_average import add_rolling_average


def test_rolling_average_warm_up_and_calculation():
    """Verifies the warm-up period behavior"""
    from datetime import timezone
    base_time = datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc)
    
    readings = []
    for i in range(8):
        readings.append({
            "date_time": base_time + timedelta(days=i),
            "aqi": 10.0 if i < 7 else 20.0
        })

    enriched = add_rolling_average(readings, field="aqi")

    for i in range(7):
        assert enriched[i]["aqi_rolling_7d"] is 0, f"Row {i} should be 0 during warm-up"

    assert enriched[7]["aqi_rolling_7d"] is not None


def test_rolling_average_math_accuracy():
    """Verifies mathematical precision"""
    from datetime import timezone
    base_time = datetime(2026, 10, 1, 0, 0, tzinfo=timezone.utc)
    
    readings = [
        {"date_time": base_time + timedelta(days=i), "aqi": 10.0} 
        for i in range(8)
    ]

    enriched = add_rolling_average(readings, field="aqi")
    assert enriched[7]["aqi_rolling_7d"] == 10.0


def test_rolling_average_handles_unsorted_input():
    """Verifies sorting and ordering"""
    from datetime import timezone
    base_time = datetime(2026, 10, 1, 0, 0, tzinfo=timezone.utc)
    
    readings = [
        {"date_time": base_time + timedelta(days=2), "aqi": 15.0},
        {"date_time": base_time + timedelta(days=0), "aqi": 5.0},
        {"date_time": base_time + timedelta(days=1), "aqi": 10.0},
    ]

    enriched = add_rolling_average(readings, field="aqi")
    assert enriched[0]["date_time"] == base_time + timedelta(days=0)


def test_rolling_average_raises_on_duplicates():
    """Verifies error handling and data integrity"""
    from datetime import timezone
    base_time = datetime(2026, 10, 1, 0, 0, tzinfo=timezone.utc)
    readings = [
        {"date_time": base_time, "aqi": 10.0},
        {"date_time": base_time, "aqi": 20.0},
    ]

    with pytest.raises(ValueError, match="Duplicate reading time"):
        add_rolling_average(readings, field="aqi")