import json
from datetime import datetime, timezone
from pathlib import Path

import pytest
import requests

from pipeline.extract import openweather_http as http
from pipeline.extract.openweather_air_pollution import fetch_air_pollution_history
from pipeline.extract.openweather_http import (
    ConfigurationError,
    InputError,
    OpenWeatherError,
)

FAKE_KEY = "fake-key-123"
START = datetime(2025, 1, 1, tzinfo=timezone.utc)
END = datetime(2025, 1, 2, tzinfo=timezone.utc)

# a small example of what OpenWeather sends back
GOOD_PAYLOAD = {
    "coord": {"lon": -74.006, "lat": 40.7128},
    "list": [
        {
            "dt": 1735689600,
            "main": {"aqi": 2},
            "components": {
                "co": 230.3, "no": 0.1, "no2": 5.2, "o3": 60.1,
                "so2": 1.2, "pm2_5": 8.5, "pm10": 10.2, "nh3": 0.5,
            },
        }
    ],
}


class FakeResponse:
    def __init__(self, status_code=200, body=b""):
        self.status_code = status_code
        self.body = body
        self.headers = {}

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def iter_content(self, size):
        yield self.body


def good_response(payload=GOOD_PAYLOAD):
    return FakeResponse(200, json.dumps(payload).encode())


def use_fake_responses(monkeypatch, *responses):
    """Replace requests.get. Each call hands back the next response."""
    calls = []
    queue = list(responses)

    def fake_get(url, **kwargs):
        calls.append({"url": url, **kwargs})
        item = queue.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    monkeypatch.setattr(http.requests, "get", fake_get)
    return calls


@pytest.fixture(autouse=True)
def setup(monkeypatch):
    monkeypatch.setenv("OPENWEATHER_API_KEY", FAKE_KEY)
    monkeypatch.delenv("OPENWEATHER_TIMEOUT_SECONDS", raising=False)
    # don't actually wait between retries
    monkeypatch.setattr(http.time, "sleep", lambda seconds: None)


def run_fetch(**changes):
    args = {
        "raw_dir": Path("unused"),
        "city": "New York",
        "country_code": "US",
        "lat": 40.7128,
        "lon": -74.006,
        "start": START,
        "end": END,
        "run_id": "run-1",
        "pipeline_run_id": 1,
    }
    args.update(changes)
    return fetch_air_pollution_history(**args)


# ---- output structure ----

def test_output_structure(monkeypatch):
    use_fake_responses(monkeypatch, good_response())
    payload = run_fetch().payload

    assert "coord" in payload
    row = payload["list"][0]
    assert isinstance(row["dt"], int)
    assert row["main"]["aqi"] in [1, 2, 3, 4, 5]
    assert "pm2_5" in row["components"]
    assert "no2" in row["components"]


def test_to_dict_turns_dates_into_text(monkeypatch):
    use_fake_responses(monkeypatch, good_response())
    result = run_fetch().to_dict()
    assert result["start"] == "2025-01-01T00:00:00Z"
    assert result["end"] == "2025-01-02T00:00:00Z"


def test_request_has_key_and_url(monkeypatch):
    calls = use_fake_responses(monkeypatch, good_response())
    run_fetch()
    assert len(calls) == 1
    assert calls[0]["url"].endswith("/data/2.5/air_pollution/history")
    assert calls[0]["params"]["appid"] == FAKE_KEY


# ---- invalid input (no request should be made) ----

def check_bad_input(monkeypatch, **changes):
    calls = use_fake_responses(monkeypatch)
    with pytest.raises(InputError):
        run_fetch(**changes)
    assert calls == []


@pytest.mark.parametrize("city", ["", "   ", None, "New York,NY"])
def test_bad_city(monkeypatch, city):
    check_bad_input(monkeypatch, city=city)


@pytest.mark.parametrize("lon", [181, -181, "-74", None])
def test_bad_longitude(monkeypatch, lon):
    check_bad_input(monkeypatch, lon=lon)


@pytest.mark.parametrize("number", [0, -1, "1"])
def test_bad_pipeline_run_id(monkeypatch, number):
    check_bad_input(monkeypatch, pipeline_run_id=number)


# ---- bad settings ----

def test_blank_api_key(monkeypatch):
    monkeypatch.setenv("OPENWEATHER_API_KEY", "   ")
    calls = use_fake_responses(monkeypatch)
    with pytest.raises(ConfigurationError):
        run_fetch()
    assert calls == []


@pytest.mark.parametrize("value", ["abc", "0", "-5"])
def test_bad_timeout_setting(monkeypatch, value):
    monkeypatch.setenv("OPENWEATHER_TIMEOUT_SECONDS", value)
    calls = use_fake_responses(monkeypatch)
    with pytest.raises(ConfigurationError):
        run_fetch()
    assert calls == []


# ---- retries running out ----

def test_server_error_retries_then_fails(monkeypatch):
    calls = use_fake_responses(
        monkeypatch, FakeResponse(500), FakeResponse(500), FakeResponse(500))
    with pytest.raises(OpenWeatherError):
        run_fetch()
    assert len(calls) == 3


def test_rate_limit_fails_after_retries(monkeypatch):
    calls = use_fake_responses(
        monkeypatch, FakeResponse(429), FakeResponse(429), FakeResponse(429))
    with pytest.raises(OpenWeatherError):
        run_fetch()
    assert len(calls) == 3


def test_connection_error_fails_after_retries(monkeypatch):
    error = requests.ConnectionError("no connection")
    calls = use_fake_responses(monkeypatch, error, error, error)
    with pytest.raises(OpenWeatherError):
        run_fetch()
    assert len(calls) == 3


# ---- malformed responses ----

def test_response_is_a_list_instead_of_a_dict(monkeypatch):
    use_fake_responses(monkeypatch, FakeResponse(200, b"[1, 2, 3]"))
    with pytest.raises(OpenWeatherError):
        run_fetch()


def test_response_missing_list(monkeypatch):
    use_fake_responses(monkeypatch, good_response({"coord": {}}))
    with pytest.raises(OpenWeatherError):
        run_fetch()


def test_response_missing_coord(monkeypatch):
    use_fake_responses(monkeypatch, good_response({"list": []}))
    with pytest.raises(OpenWeatherError):
        run_fetch()


def test_record_missing_components(monkeypatch):
    bad = {"coord": {}, "list": [{"dt": 1735689600, "main": {"aqi": 2}}]}
    use_fake_responses(monkeypatch, good_response(bad))
    with pytest.raises(OpenWeatherError):
        run_fetch()


@pytest.mark.parametrize("aqi", [0, 6, "2", None])
def test_aqi_must_be_1_to_5(monkeypatch, aqi):
    bad = {
        "coord": {},
        "list": [{"dt": 1735689600, "main": {"aqi": aqi}, "components": {}}],
    }
    use_fake_responses(monkeypatch, good_response(bad))
    with pytest.raises(OpenWeatherError):
        run_fetch()
