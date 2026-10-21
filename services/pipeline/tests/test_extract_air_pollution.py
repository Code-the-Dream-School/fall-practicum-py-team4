import json
from datetime import datetime, timezone

import pytest
import requests

from pipeline.contracts import extract
from pipeline.extract import openweather_http as http
from pipeline.extract.openweather_http import (
    ConfigurationError,
    OpenWeatherError,
)

FAKE_KEY = "fake-key-123"
START = datetime(2025, 1, 1, tzinfo=timezone.utc)
END = datetime(2025, 1, 2, tzinfo=timezone.utc)

GOOD_PAYLOAD = {
    "coord": {"lon": -74.006, "lat": 40.7128},
    "list": [
        {
            "dt": 1735689600,
            "main": {"aqi": 2},
            "components": {
                "co": 230.3,
                "no": 0.1,
                "no2": 5.2,
                "o3": 60.1,
                "so2": 1.2,
                "pm2_5": 8.5,
                "pm10": 10.2,
                "nh3": 0.5,
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

    def iter_content(self, chunk_size):
        yield self.body


def good_response(payload=GOOD_PAYLOAD):
    return FakeResponse(200, json.dumps(payload).encode())


def use_fake_responses(monkeypatch, *responses):
    calls = []
    queue = list(responses)

    def fake_get(url, **kwargs):
        calls.append({"url": url, **kwargs})
        if not queue:
            pytest.fail("Unexpected HTTP request")
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
    monkeypatch.setattr(http.time, "sleep", lambda seconds: None)


def run_extract(**changes):
    args = {
        "latitude": 40.7128,
        "longitude": -74.006,
        "endpoint": "/history",
        "start_date": START,
        "end_date": END,
        "daily": False,
    }
    args.update(changes)
    return extract(**args)


def test_successful_extract(monkeypatch):
    calls = use_fake_responses(monkeypatch, good_response())

    result = run_extract()

    assert isinstance(result, list)
    assert len(result) == 1
    record = result[0]
    assert record["coord"] == GOOD_PAYLOAD["coord"]
    assert record["list"] == GOOD_PAYLOAD["list"]
    assert record["request_params"] == {
        "start": int(START.timestamp()),
        "end": int(END.timestamp()),
    }
    datetime.strptime(record["retrieve_date"], "%Y-%m-%d")

    assert len(calls) == 1
    assert calls[0]["url"] == (
        http.BASE_URL + "/data/2.5/air_pollution/history"
    )
    assert calls[0]["params"] == {
        "lat": 40.7128,
        "lon": -74.006,
        "start": int(START.timestamp()),
        "end": int(END.timestamp()),
        "appid": FAKE_KEY,
    }


def test_empty_measurements(monkeypatch):
    payload = {"coord": GOOD_PAYLOAD["coord"], "list": []}
    use_fake_responses(monkeypatch, good_response(payload))

    result = run_extract()

    assert len(result) == 1
    assert result[0]["coord"] == payload["coord"]
    assert result[0]["list"] == []


def test_invalid_endpoint(monkeypatch):
    calls = use_fake_responses(monkeypatch)

    with pytest.raises(ValueError, match="endpoint"):
        run_extract(endpoint="/invalid")

    assert calls == []


def test_reversed_date_range(monkeypatch):
    calls = use_fake_responses(monkeypatch)

    with pytest.raises(ValueError, match="start_date"):
        run_extract(start_date=END, end_date=START)

    assert calls == []


@pytest.mark.parametrize("missing_date", ["start_date", "end_date"])
def test_history_requires_both_dates(monkeypatch, missing_date):
    calls = use_fake_responses(monkeypatch)

    result = run_extract(**{missing_date: None})

    assert result == []
    assert calls == []


@pytest.mark.parametrize("key", [None, "", "   "])
def test_missing_or_blank_api_key(monkeypatch, key):
    if key is None:
        monkeypatch.delenv("OPENWEATHER_API_KEY", raising=False)
    else:
        monkeypatch.setenv("OPENWEATHER_API_KEY", key)
    calls = use_fake_responses(monkeypatch)

    with pytest.raises(ConfigurationError):
        run_extract()

    assert calls == []


@pytest.mark.parametrize("value", ["abc", "0", "-5"])
def test_bad_timeout_setting(monkeypatch, value):
    monkeypatch.setenv("OPENWEATHER_TIMEOUT_SECONDS", value)
    calls = use_fake_responses(monkeypatch)

    with pytest.raises(ConfigurationError):
        run_extract()

    assert calls == []


@pytest.mark.parametrize("status", [429, 500])
def test_http_error_fails_after_retries(monkeypatch, status):
    calls = use_fake_responses(
        monkeypatch,
        FakeResponse(status),
        FakeResponse(status),
        FakeResponse(status),
    )

    with pytest.raises(OpenWeatherError):
        run_extract()

    assert len(calls) == 3


def test_connection_error_fails_after_retries(monkeypatch):
    calls = use_fake_responses(
        monkeypatch,
        requests.ConnectionError("no connection"),
        requests.ConnectionError("no connection"),
        requests.ConnectionError("no connection"),
    )

    with pytest.raises(OpenWeatherError):
        run_extract()

    assert len(calls) == 3


def test_invalid_json(monkeypatch):
    use_fake_responses(monkeypatch, FakeResponse(200, b"not json"))

    with pytest.raises(OpenWeatherError, match="invalid JSON"):
        run_extract()


@pytest.mark.parametrize(
    "payload",
    [
        [1, 2, 3],
        {"coord": {}},
        {"list": []},
        {
            "coord": {},
            "list": [{"dt": 1735689600, "main": {"aqi": 2}}],
        },
    ],
)
def test_malformed_payload(monkeypatch, payload):
    use_fake_responses(monkeypatch, good_response(payload))

    with pytest.raises(OpenWeatherError):
        run_extract()
