"""60-day retention window shared by extract, transform and load."""

from datetime import datetime, timedelta, timezone

RETENTION_DAYS = 60
# Extra history pulled so the 7-day rolling AQI is complete on the oldest kept day.
ROLLING_WARMUP_DAYS = 7


def _aware_utc(value: datetime) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("now must be a timezone-aware datetime")
    return value.astimezone(timezone.utc)


def retention_cutoff(now: datetime) -> datetime:
    """Readings at or before this instant are removed from gold."""
    return _aware_utc(now) - timedelta(days=RETENTION_DAYS)


def extraction_window(now: datetime) -> tuple[datetime, datetime]:
    """History request window for every run: 60 kept days plus rolling warm-up.

    Each run re-pulls the full window (one history call per city) so initial
    loads and daily updates follow the same path and loads stay idempotent.
    """
    end = _aware_utc(now)
    return end - timedelta(days=RETENTION_DAYS + ROLLING_WARMUP_DAYS), end


def drop_expired(readings: list[dict], now: datetime) -> list[dict]:
    """Keep only readings newer than the retention cutoff (date_time must be aware)."""
    cutoff = retention_cutoff(now)
    return [reading for reading in readings if reading["date_time"] > cutoff]
