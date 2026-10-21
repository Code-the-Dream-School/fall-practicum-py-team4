"""The functions and input configuration exactly as named in data_contracts.py.

geocodes, get_unix and extract are implemented here on top of the extract
modules. load_raw (T4AIR-15) and transform (T4AIR-16) keep the contract
signatures `load_raw(raw_records: list) -> None` and
`transform(raw_records: list) -> list`; orchestration calls them that way.
"""

import logging
import re
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone

from pipeline.extract.geocoding import geocode_city, geocode_zip
from pipeline.extract.openweather_air_pollution import HISTORY_START, validate_pollution_payload
from pipeline.extract.openweather_http import get_json, utc_now
from pipeline.retention import extraction_window

LOG = logging.getLogger(__name__)

ENDPOINTS = {
    "/": "/data/2.5/air_pollution",
    "/forecast": "/data/2.5/air_pollution/forecast",
    "/history": "/data/2.5/air_pollution/history",
}
_ZIP = re.compile(r"^\d{5}(-\d{4})?$")
_DATE_FORMAT = "%m/%d/%Y"


def _parse_time(value: str) -> time:
    # data_contracts uses both "1200" and "12:00".
    try:
        text = value.strip().replace(":", "")
        if len(text) != 4 or not text.isdigit():
            raise ValueError
        return time(int(text[:2]), int(text[2:]))
    except (AttributeError, ValueError):
        raise ValueError(f"time_of_day must look like '12:00' or '1200', got {value!r}") from None


def _parse_date(value) -> date:
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).date()
    if isinstance(value, date):
        return value
    try:
        return datetime.strptime(value.strip(), _DATE_FORMAT).date()
    except (AttributeError, ValueError):
        raise ValueError(f"Dates must be MM/DD/YYYY, got {value!r}") from None


def _as_utc(value, end_of_day: bool) -> datetime:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            raise ValueError("datetimes must be timezone-aware")
        return value.astimezone(timezone.utc)
    moment = datetime.combine(_parse_date(value), time(), tzinfo=timezone.utc)
    return moment + timedelta(days=1) if end_of_day else moment


def get_unix(time: str, start_date: str) -> int:
    """'15:00' + '01/01/2020' -> Unix seconds for that UTC moment."""
    moment = datetime.combine(_parse_date(start_date), _parse_time(time), tzinfo=timezone.utc)
    return int(moment.timestamp())


def _parse_city(entry: str):
    """'new york' | 'new york, us' | 'charlotte, nc, us' | '28202' -> geocoder call."""
    if not isinstance(entry, str) or not entry.strip():
        raise ValueError("Missing city value; provide a city name or zipcode")
    parts = [part.strip() for part in entry.lower().split(",")]
    if _ZIP.match(parts[0]):
        return lambda: geocode_zip(parts[0], parts[1] if len(parts) > 1 else "US")
    if len(parts) == 1:
        return lambda: geocode_city(None, parts[0], None)
    if len(parts) == 2:
        return lambda: geocode_city(None, parts[0], parts[1])
    if len(parts) == 3:
        return lambda: geocode_city(None, parts[0], parts[2], parts[1])
    raise ValueError(f"Use 'city', 'city, country' or 'city, state, country': {entry!r}")


def geocodes(cities: list) -> dict:
    """Return {city: {"lat": float, "lon": float, "country": str}} per lowercase city or zipcode.

    country (lowercase ISO code) is extra to the contract; gold_table stores it.
    """
    if not isinstance(cities, list) or not cities:
        raise ValueError("Missing city value; the pipeline needs at least one city")
    result = {}
    for entry in cities:
        lookup = _parse_city(entry)
        coords = lookup()
        result[entry.strip().lower()] = {
            "lat": coords.lat, "lon": coords.lon,
            "country": coords.country.lower() if coords.country else None,
        }
    return result


def extract(latitude: float, longitude: float, endpoint='/', start_date=None, end_date=None,
            daily=True, time_of_day='1200') -> list:
    """Return a list of raw records shaped like RawAirTrackerData.

    '/history' needs start_date and end_date (MM/DD/YYYY or aware datetimes);
    without them a message is logged and [] is returned, as in the contract.
    With daily=True only the reading at time_of_day (UTC hour) is kept per day.
    """
    if endpoint not in ENDPOINTS:
        raise ValueError(f"endpoint must be one of {sorted(ENDPOINTS)}")
    if endpoint == "/history" and (start_date is None or end_date is None):
        LOG.error("When using the '/history' endpoint, start and end dates must be specified")
        return []
    params = {"lat": latitude, "lon": longitude}
    request_params = None
    if endpoint == "/history":
        start = max(_as_utc(start_date, end_of_day=False), HISTORY_START)
        end = min(_as_utc(end_date, end_of_day=True), utc_now())
        if start >= end:
            raise ValueError("start_date must be before end_date and after 11/27/2020")
        request_params = {"start": int(start.timestamp()), "end": int(end.timestamp())}
        params.update(request_params)
    payload = validate_pollution_payload(get_json(ENDPOINTS[endpoint], params))
    rows = payload["list"]
    if daily and endpoint != "/":
        hour = _parse_time(time_of_day).hour
        rows = [row for row in rows if datetime.fromtimestamp(row["dt"], tz=timezone.utc).hour == hour]
    record = {
        "coord": payload["coord"],
        "list": rows,
        "retrieve_date": utc_now().date().isoformat(),
    }
    if request_params:
        record["request_params"] = request_params
    return [record]


@dataclass(frozen=True)
class PipelineInput:
    cities: list[str]
    start: datetime
    end: datetime
    daily: bool
    time_of_day: str


def parse_input(config: dict, now: datetime) -> PipelineInput:
    """Read the data_contracts input configuration.

    An empty date_range means the default 60-day window (plus the 7-day rolling
    warm-up). Gold keeps only the last 60 days whatever range is requested.
    """
    cities = config.get("cities") if isinstance(config, dict) else None
    if not isinstance(cities, list) or not cities or not all(isinstance(c, str) and c.strip() for c in cities):
        raise ValueError("Missing city value; set 'cities' to a list of city names or zipcodes")
    date_range = config.get("date_range") or ""
    if date_range:
        try:
            first, last = (part.strip() for part in date_range.split("-"))
        except ValueError:
            raise ValueError("date_range must look like 'MM/DD/YYYY - MM/DD/YYYY'") from None
        start, end = _as_utc(first, end_of_day=False), _as_utc(last, end_of_day=True)
    else:
        start, end = extraction_window(now)
    time_of_day = config.get("time_of_day") or "12:00"
    _parse_time(time_of_day)
    return PipelineInput(
        cities=[city.strip().lower() for city in cities],
        start=start, end=end,
        daily=bool(config.get("daily", True)),
        time_of_day=time_of_day,
    )
