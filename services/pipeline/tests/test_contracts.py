"""pipeline.contracts follows the function signatures in data_contracts.py."""

import inspect
import json
from datetime import datetime, timezone
from unittest.mock import Mock

import psycopg
import pytest
import requests

import data_contracts as dc
from pipeline import contracts
from pipeline.extract import geocoding as geo
from pipeline.extract import open_meteo
from pipeline.transform.locations import to_gold_locations

NOW = datetime(2026, 10, 19, 20, tzinfo=timezone.utc)
CANDIDATES = {
    "london": [{"name": "London", "country": "GB", "lat": 51.5, "lon": -0.12},
               {"name": "London", "country": "CA", "lat": 42.98, "lon": -81.24}],
    "new york,US": [{"name": "New York", "country": "US", "state": "New York", "lat": 40.71, "lon": -74.01}],
    "charlotte,NC,US": [{"name": "Charlotte", "country": "US", "state": "North Carolina", "lat": 35.23, "lon": -80.84}],
}


def reply(body, status=200):
    result = requests.Response()
    result.status_code = status
    result._content = json.dumps(body).encode()
    result._content_consumed = True
    return result


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    monkeypatch.setenv("OPENWEATHER_API_KEY", "test-only-key")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setattr(geo, "utc_now", lambda: NOW)
    monkeypatch.setattr(contracts, "utc_now", lambda: NOW)
    monkeypatch.setattr(requests, "get", Mock(side_effect=AssertionError("Live HTTP forbidden")))
    monkeypatch.setattr(psycopg, "connect", Mock(side_effect=AssertionError("Live DB forbidden")))


@pytest.mark.parametrize("name", ["geocodes", "get_unix", "extract"])
def test_signatures_match_data_contracts(name):
    assert inspect.signature(getattr(contracts, name)) == inspect.signature(getattr(dc, name))


def test_get_unix():
    assert contracts.get_unix("15:00", "01/01/2020") == int(datetime(2020, 1, 1, 15, tzinfo=timezone.utc).timestamp())
    assert contracts.get_unix("1200", "10/19/2026") == int(datetime(2026, 10, 19, 12, tzinfo=timezone.utc).timestamp())
    for bad in (("25:00", "01/01/2020"), ("12:00", "2020-01-01"), (None, "01/01/2020")):
        with pytest.raises(ValueError):
            contracts.get_unix(*bad)


def test_geocodes_accepts_names_country_state_and_zip(monkeypatch):
    def get(url, params, **_):
        if url.endswith("/zip"):
            return reply({"zip": "28202", "name": "Charlotte", "lat": 35.22, "lon": -80.84, "country": "US"})
        return reply(CANDIDATES[params["q"]])
    monkeypatch.setattr(requests, "get", Mock(side_effect=get))
    result = contracts.geocodes(["London", "new york, us", "charlotte, nc, us", "28202"])
    assert result == {
        "london": {"lat": 51.5, "lon": -0.12, "country": "gb"},  # no country: provider's top result
        "new york, us": {"lat": 40.71, "lon": -74.01, "country": "us"},
        "charlotte, nc, us": {"lat": 35.23, "lon": -80.84, "country": "us"},
        "28202": {"lat": 35.22, "lon": -80.84, "country": "us"},
    }


@pytest.mark.parametrize("cities", [[], None, [""], ["a, b, c, d"]])
def test_geocodes_requires_city_values(cities):
    with pytest.raises(ValueError):
        contracts.geocodes(cities)


def payload(hours):
    return {"coord": {"lon": -80.84, "lat": 35.23}, "list": [{
        "dt": int(datetime(2026, 10, 18, h, tzinfo=timezone.utc).timestamp()),
        "main": {"aqi": 2.0},
        "components": dict(dc.raw_data["list"][0]["components"]),
    } for h in hours]}


def test_extract_history_daily_returns_raw_contract_records(monkeypatch):
    get = Mock(return_value=reply(payload(range(24))))
    monkeypatch.setattr(requests, "get", get)
    records = contracts.extract(35.23, -80.84, "/history", "10/18/2026", "10/18/2026", True, "15:00")
    raw = dc.RawAirTrackerData.model_validate(records[0])
    assert len(records) == 1 and len(raw.list) == 1
    assert datetime.fromtimestamp(raw.list[0].dt, tz=timezone.utc).hour == 15
    assert raw.request_params.start == int(datetime(2026, 10, 18, tzinfo=timezone.utc).timestamp())
    assert raw.request_params.end == int(datetime(2026, 10, 19, tzinfo=timezone.utc).timestamp())
    assert raw.retrieve_date == "2026-10-19"
    assert get.call_args.kwargs["params"]["appid"] == "test-only-key"


def test_extract_hourly_current_and_forecast(monkeypatch):
    get = Mock(return_value=reply(payload(range(24))))
    monkeypatch.setattr(requests, "get", get)
    assert len(contracts.extract(35.23, -80.84, "/history", "10/18/2026", "10/18/2026", daily=False)[0]["list"]) == 24
    current = contracts.extract(35.23, -80.84)
    assert get.call_args.args[0].endswith("/data/2.5/air_pollution") and len(current[0]["list"]) == 24
    assert "request_params" not in current[0]
    contracts.extract(35.23, -80.84, "/forecast", daily=False)
    assert get.call_args.args[0].endswith("/air_pollution/forecast")


def test_extract_history_without_dates_returns_empty_like_the_contract(caplog):
    assert contracts.extract(35.23, -80.84, "/history") == []
    assert "start and end dates must be specified" in caplog.text


def test_extract_clamps_to_openweather_archive_start(monkeypatch):
    get = Mock(return_value=reply(payload([12])))
    monkeypatch.setattr(requests, "get", get)
    contracts.extract(35.23, -80.84, "/history", "01/01/2020", "01/01/2026")
    assert get.call_args.kwargs["params"]["start"] == int(datetime(2020, 11, 27, tzinfo=timezone.utc).timestamp())
    with pytest.raises(ValueError):
        contracts.extract(35.23, -80.84, "/nope")


def test_parse_input_reads_the_contract_example():
    settings = contracts.parse_input(dc.input, NOW)
    assert settings.cities == ["new york", "london", "seoul", "jakarta"]
    assert settings.start == datetime(2020, 1, 1, tzinfo=timezone.utc)
    assert settings.end == datetime(2026, 1, 2, tzinfo=timezone.utc)
    assert settings.daily is True and settings.time_of_day == "15:00"
    with pytest.raises(ValueError, match="date_range"):
        contracts.parse_input({"cities": ["x"], "date_range": "01/01/2020"}, NOW)


def test_open_meteo_raw_and_gold_locations_match_contract(monkeypatch):
    monkeypatch.setattr(requests, "get", Mock(return_value=reply(dc.raw_mateo)))
    raw = open_meteo.fetch_location("Paris")
    dc.RawOpenMateo.model_validate(raw)
    gold = to_gold_locations(raw)
    assert gold == dc.golden_mateo
    dc.GoldenMateo.model_validate(gold)


def test_open_meteo_no_match_and_incomplete_rows(monkeypatch):
    monkeypatch.setattr(requests, "get", Mock(return_value=reply({"generationtime_ms": 0.1})))
    assert open_meteo.fetch_location("Nowhere")["results"] == []
    partial = {"results": [{**dc.raw_mateo["results"][0], "population": None}]}
    assert to_gold_locations(partial) == {"locations": []}
