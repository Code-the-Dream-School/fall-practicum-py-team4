from datetime import datetime, timedelta, timezone

import pytest

from pipeline.transform.rolling_average import add_rolling_aqi

T0 = datetime(2026, 10, 1, tzinfo=timezone.utc)


def daily(aqis):
    return [{"date_time": T0 + timedelta(days=i), "aqi": aqi} for i, aqi in enumerate(aqis)]


def test_daily_sample_rows_null_until_seven_days_then_window_mean():
    rows = add_rolling_aqi(daily([1, 2, 3, 4, 5, 1, 2, 3, 4]))
    values = [row["aqi_rolling_7d"] for row in rows]
    # Days 0-6 have no full 7 days of history behind them.
    assert values[:7] == [None] * 7
    # Day 7 covers days 1..7 (day 0 is exactly 7 days old and drops out).
    assert values[7] == pytest.approx((2 + 3 + 4 + 5 + 1 + 2 + 3) / 7)
    assert values[8] == pytest.approx((3 + 4 + 5 + 1 + 2 + 3 + 4) / 7)


def test_hourly_rows_use_seven_days_not_seven_rows():
    rows = [{"date_time": T0 + timedelta(hours=h), "aqi": 1 if h < 24 else 3} for h in range(24 * 9)]
    result = add_rolling_aqi(rows)
    at_day_7 = result[24 * 7]
    assert at_day_7["aqi_rolling_7d"] == pytest.approx((23 * 1 + 145 * 3) / 168)
    assert result[-1]["aqi_rolling_7d"] == 3.0
    assert result[24 * 7 - 1]["aqi_rolling_7d"] is None


def test_gaps_average_only_the_readings_present():
    rows = daily([2, 2, 2, 2, 2, 2, 2, 4])
    del rows[3:6]
    result = add_rolling_aqi(rows)
    assert result[-1]["aqi_rolling_7d"] == pytest.approx((2 + 2 + 2 + 4) / 4)


def test_output_is_sorted_and_input_untouched():
    rows = daily([1, 2, 3, 4, 5, 1, 2, 3])[::-1]
    before = [dict(row) for row in rows]
    result = add_rolling_aqi(rows)
    assert rows == before
    assert [row["date_time"] for row in result] == sorted(row["date_time"] for row in rows)
    assert result[-1]["aqi_rolling_7d"] == pytest.approx(20 / 7)
    assert add_rolling_aqi(result) == result


def test_empty_and_invalid_rows():
    assert add_rolling_aqi([]) == []
    with pytest.raises(ValueError, match="Duplicate"):
        add_rolling_aqi(daily([1, 2]) + daily([3]))
    with pytest.raises(ValueError, match="timezone-aware"):
        add_rolling_aqi([{"date_time": datetime(2026, 10, 1), "aqi": 1}])
    with pytest.raises(ValueError, match=r"readings\[0\]"):
        add_rolling_aqi([{"date_time": T0, "aqi": 7}])
    with pytest.raises(ValueError):
        add_rolling_aqi(None)
