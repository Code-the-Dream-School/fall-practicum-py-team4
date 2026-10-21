"""Historical extraction using the exact arguments passed by orchestration."""

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .openweather_http import (
    BASE_URL, InputError, OpenWeatherError, coordinate,
    get_json, location_input, utc_now,
)

HISTORY_PATH = "/data/2.5/air_pollution/history"
HISTORY_START = datetime(2020, 11, 27, tzinfo=timezone.utc)


@dataclass(frozen=True)
class RawAirPollutionRecord:
    city: str
    country_code: str | None
    lat: float
    lon: float
    start: datetime
    end: datetime
    run_id: str
    pipeline_run_id: int
    retrieved_at: datetime
    request_params: dict[str, int | float]
    payload: dict[str, Any]
    source: str = "openweather"
    endpoint: str = BASE_URL + HISTORY_PATH
    schema_version: int = 1

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        for key in ("start", "end", "retrieved_at"):
            result[key] = result[key].astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
        return result

    def to_raw_contract(self) -> dict[str, Any]:
        """Shape of `RawAirTrackerData` in data_contracts.py."""
        return {
            "coord": self.payload["coord"],
            "list": self.payload["list"],
            "request_params": {"start": self.request_params["start"], "end": self.request_params["end"]},
            "retrieve_date": self.retrieved_at.astimezone(timezone.utc).date().isoformat(),
            "city": self.city.lower(),
        }


def validate_pollution_payload(payload):
    """Shared check for current, forecast and history responses."""
    if (not isinstance(payload, dict) or not isinstance(payload.get("list"), list)
            or not isinstance(payload.get("coord"), (dict, list))):
        raise OpenWeatherError("Expected air pollution coord and list fields")
    for row in payload["list"]:
        if (not isinstance(row, dict) or type(row.get("dt")) is not int
                or not isinstance(row.get("main"), dict)
                or not isinstance(row.get("components"), dict)):
            raise OpenWeatherError("Malformed air pollution record")
        aqi = row["main"].get("aqi")
        if isinstance(aqi, bool) or not isinstance(aqi, (int, float)) or aqi not in (1, 2, 3, 4, 5):
            raise OpenWeatherError("Invalid OpenWeather AQI")
    return payload


def _aware_utc(value, name):
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise InputError(f"{name} must be a timezone-aware datetime")
    return value.astimezone(timezone.utc)


def fetch_air_pollution_history(
    raw_dir: Path | None, city: str, country_code: str, lat: float, lon: float,
    start: datetime, end: datetime, run_id: str, pipeline_run_id: int,
) -> RawAirPollutionRecord:
    """Return raw data and context for the team's storage and transform layers.

    raw_dir is retained for caller compatibility and may be None. The caller
    chooses the window; orchestration uses pipeline.retention.extraction_window
    (60 retained days plus the rolling-average warm-up).
    """
    city, country_code, _ = location_input(city, country_code)
    lat = coordinate(lat, "lat", -90, 90)
    lon = coordinate(lon, "lon", -180, 180)
    start, end = _aware_utc(start, "start"), _aware_utc(end, "end")
    if not HISTORY_START <= start < end <= utc_now():
        raise InputError("History requires 2020-11-27 <= start < end <= now")
    if not isinstance(run_id, str) or not run_id.strip():
        raise InputError("run_id must be a nonempty string")
    if type(pipeline_run_id) is not int or pipeline_run_id < 1:
        raise InputError("pipeline_run_id must be a positive integer")
    params = {"lat": lat, "lon": lon, "start": int(start.timestamp()), "end": int(end.timestamp())}
    if params["start"] >= params["end"]:
        raise InputError("Historical start and end must fall in different Unix seconds")
    payload = validate_pollution_payload(get_json(HISTORY_PATH, params))
    return RawAirPollutionRecord(
        city=city, country_code=country_code, lat=lat, lon=lon,
        start=start, end=end, run_id=run_id, pipeline_run_id=pipeline_run_id,
        retrieved_at=utc_now(), request_params=params, payload=payload,
    )
