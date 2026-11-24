from collections.abc import Mapping
from datetime import datetime, timedelta
from typing import Any
from supabase import Client

ROLLING_WINDOW = timedelta(days=7)
LOOKBACK_BUFFER = timedelta(hours=2)


def get_timestamp(reading: Mapping[str, Any], index: int) -> datetime:
    """
    Extracts and validates a timezone-aware datetime object from a reading.
    """
    value = reading.get("date_time") if isinstance(reading, Mapping) else None
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"readings[{index}].date_time must be a timezone-aware datetime")
    return value


def fetch_historical_readings(
    supabase_client: Client,
    city_id: int,
    current_readings: list[Mapping[str, Any]],
    city_name: str,
    table_name: str = "gold_air_data",
) -> list[dict[str, Any]]:
    """
    Queries Supabase for readings within 7 days before and 7 days after the
    incoming batch so both current and downstream rolling averages update cleanly.
    """
    if not current_readings:
        return []

    timestamps = [get_timestamp(r, i) for i, r in enumerate(current_readings)]
    batch_start = min(timestamps)
    batch_end = max(timestamps)
    current_ts_set = set(timestamps)

    window_start = batch_start - ROLLING_WINDOW - LOOKBACK_BUFFER
    window_end = batch_end + ROLLING_WINDOW

    try:
        response = (
            supabase_client.table(table_name)
            .select("*")
            .eq("city_id", city_id)
            .gte("date_time", window_start.isoformat())
            .lte("date_time", window_end.isoformat())
            .order("date_time", desc=False)
            .execute()
        )
    except Exception as e:
        raise RuntimeError(f"Failed to fetch historical readings for {city_name}: {e}") from e

    historical_rows = response.data or []

    # Parse database timestamps and exclude rows being replaced by current_readings
    base_keys = set(current_readings[0].keys())

    parsed_history = []
    for row in historical_rows:
        dt_val = row.get("date_time")
        if isinstance(dt_val, str):
            dt_val = datetime.fromisoformat(dt_val.replace("Z", "+00:00"))
            row["date_time"] = dt_val
        if dt_val not in current_ts_set:
            parsed_history.append({k: row.get(k) for k in base_keys})

    return parsed_history + [dict(r) for r in current_readings]


def add_rolling_average(
    readings: list[Mapping[str, Any]],
    field: str,
    window: timedelta = ROLLING_WINDOW,
    boundary_tolerance: timedelta = timedelta(hours=1),
    min_readings: int = 1,
) -> list[dict[str, Any]]:
    """
    Calculates a 7-day rolling average for a specified field in each reading.
    Returns 0 until the active window spans at least (window - boundary_tolerance)
    and contains at least min_readings points.
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
    required_span = max(timedelta(0), window - boundary_tolerance)
    first = rows[0][0] if rows else None

    for end, (when, val, reading) in enumerate(rows):
        total += val
        while rows[start][0] <= when - window:
            total -= rows[start][1]
            start += 1

        window_count = end - start + 1
        time_span = when - first
        complete = time_span >= required_span and window_count >= min_readings
        average = round(total / window_count, 2) if complete else 0

        result.append({**reading, f"{field}_rolling_7d": average})

    return result