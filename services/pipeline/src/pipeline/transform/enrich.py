"""Add the derived gold fields to a GoldSchema-shaped record from T4AIR-16."""

from collections.abc import Mapping
from datetime import datetime
from typing import Any

from pipeline.retention import drop_expired

from .category_and_score import add_category_and_score
from .rolling_average import add_rolling_aqi


def enrich_gold_record(record: Mapping[str, Any], now: datetime | None = None) -> dict[str, Any]:
    """Return a copy with aqi_category, risk_score and aqi_rolling_7d on each reading.

    The rolling average is computed over every reading passed in (including
    the warm-up days). When `now` is given, readings at or before the 60-day
    retention cutoff are dropped afterwards. The input is never modified.
    """
    if not isinstance(record, Mapping):
        raise ValueError("gold record must be a mapping")
    readings = add_rolling_aqi(add_category_and_score(record.get("readings")))
    if now is not None:
        readings = drop_expired(readings, now)
    return {**record, "readings": readings}
