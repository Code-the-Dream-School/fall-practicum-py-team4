from collections.abc import Mapping
from datetime import datetime, timedelta
from typing import Any

ROLLING_WINDOW = timedelta(days=7)


def get_timestamp(reading: Mapping[str, Any], index: int) -> datetime:
    """
    Extracts and validates a timezone-aware datetime object from a reading.
    """
    value = reading.get("date_time") if isinstance(reading, Mapping) else None
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"readings[{index}].date_time must be a timezone-aware datetime")
    return value


def add_rolling_average(readings: list[Mapping[str, Any]], field: str, window: timedelta = ROLLING_WINDOW) -> list[dict[str, Any]]:
    """
    Calculates a 7-day rolling average for a specified field in each reading.
    
    This takes a list of readings, sorts them chronologically, and adds 
    an '{field}_rolling_7d' key to every record.

    A time-based window, handles irregular data, missing hourly pings, or API gaps
    gracefully without breaking the math.
    
    Key details:
    - Uses a time-based window (7 days), so it handles hourly or daily data seamlessly.
    - Returns 0 during the initial warm-up period (until the city has a full 7 days of history)
    to avoid showing misleading, partial averages.
    """

    if not isinstance(readings, list):
        raise ValueError("readings must be a list")
    
    rows = []

    for index, reading in enumerate(readings):
        when = get_timestamp(reading, index)
        raw_val = reading.get(field)
        if raw_val is None:
            raise ValueError(f"reading[{index}].{field} is missing")
        rows.append((when, float(raw_val), reading))

    rows.sort(key=lambda row: row[0])

    for previous, current in zip(rows, rows[1:]):
        if previous[0] == current[0]:
            raise ValueError(f"Duplicate reading time {current[0].isoformat()}")

    result = []
    start = 0
    total = 0.0
    first = rows[0][0] if rows else None

    for end, (when, val, reading) in enumerate(rows):
        total += val
        while rows[start][0] <= when - window:
            total -= rows[start][1]
            start += 1
        complete = first <= when - window
        # returning 0 during warm-up period, as agreed with the team
        average = total / (end - start + 1) if complete else 0

        result.append({**reading, f"{field}_rolling_7d": average})

    return result