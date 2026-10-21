"""Flatten an enriched GoldSchema record into rows for the Supabase gold_table.

gold_table (checked 2026-10-20) has one row per reading and its own column
names. risk_score and five pollutants (no, o3, so2, pm10, nh3) have no
column yet, so they are not sent; T4AIR-22 owns adding them.
"""

from collections.abc import Mapping
from datetime import date, datetime, time, timezone
from typing import Any

# Contract path -> gold_table column. id is assigned by the database.
GOLD_TABLE_COLUMNS = {
    "coordinates.lon": "longitude",
    "coordinates.lat": "latitude",
    "city": "city",
    "country": "country",
    "readings[].components.co": "co",
    "readings[].components.pm2_5": "pm2_5",
    "readings[].components.no2": "no2",
    "readings[].date_time": "date",
    "retrieve_date": "retrieve_date",
    "readings[].aqi": "aqi",
    "readings[].aqi_category": "sentiment_label",
    "readings[].aqi_rolling_7d": "running_average",
}


def _iso(value: Any) -> str:
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).isoformat()
    # retrieve_date is a date in the contract and timestamptz in the table.
    day = date.fromisoformat(value) if isinstance(value, str) else value
    return datetime.combine(day, time(), tzinfo=timezone.utc).isoformat()


def to_gold_rows(record: Mapping[str, Any]) -> list[dict[str, Any]]:
    """One gold_table row per reading of an enriched record (see enrich_gold_record)."""
    coordinates = record["coordinates"]
    shared = {
        "longitude": coordinates["lon"],
        "latitude": coordinates["lat"],
        "city": record["city"],
        "country": record.get("country"),
        "retrieve_date": _iso(record["retrieve_date"]),
    }
    return [{
        **shared,
        "co": reading["components"]["co"],
        "pm2_5": reading["components"]["pm2_5"],
        "no2": reading["components"]["no2"],
        "date": _iso(reading["date_time"]),
        "aqi": reading["aqi"],
        "sentiment_label": reading["aqi_category"],
        "running_average": reading["aqi_rolling_7d"],
    } for reading in record["readings"]]
