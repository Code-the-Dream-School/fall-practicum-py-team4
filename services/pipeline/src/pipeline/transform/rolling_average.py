"""T4AIR-21: 7-day rolling AQI for one city's gold readings."""

from collections.abc import Mapping
from datetime import datetime, timedelta
from typing import Any

from .category_and_score import aqi_to_category

ROLLING_WINDOW = timedelta(days=7)


def _timestamp(reading: Mapping[str, Any], index: int) -> datetime:
    value = reading.get("date_time") if isinstance(reading, Mapping) else None
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"readings[{index}].date_time must be a timezone-aware datetime")
    return value


def add_rolling_aqi(readings: list[Mapping[str, Any]], window: timedelta = ROLLING_WINDOW) -> list[dict[str, Any]]:
    """Return copies sorted by date_time with aqi_rolling_7d set.

    The value is the mean AQI of every reading in (date_time - window, date_time].
    The window is time-based, so hourly and daily data both cover 7 days.
    Until the city has a full window of history before a reading (its first
    days, or a newly added city) the value is None rather than a partial mean.
    Pass one city's readings only; duplicate timestamps raise ValueError.
    """
    if not isinstance(readings, list):
        raise ValueError("readings must be a list")
    rows = []
    for index, reading in enumerate(readings):
        when = _timestamp(reading, index)
        aqi = reading.get("aqi")
        try:
            aqi_to_category(aqi)
        except ValueError as error:
            raise ValueError(f"readings[{index}]: {error}") from error
        rows.append((when, float(aqi), reading))
    rows.sort(key=lambda row: row[0])
    for previous, current in zip(rows, rows[1:]):
        if previous[0] == current[0]:
            raise ValueError(f"Duplicate reading time {current[0].isoformat()}")

    result = []
    start = 0
    total = 0.0
    first = rows[0][0] if rows else None
    for end, (when, aqi, reading) in enumerate(rows):
        total += aqi
        while rows[start][0] <= when - window:
            total -= rows[start][1]
            start += 1
        complete = first <= when - window
        average = total / (end - start + 1) if complete else None
        result.append({**reading, "aqi_rolling_7d": average})
    return result
