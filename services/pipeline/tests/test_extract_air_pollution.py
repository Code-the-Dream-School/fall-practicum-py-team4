from datetime import datetime, timezone
from unittest.mock import Mock

import pytest
import requests

from pipeline.extract import openweather_air_pollution as air

FAKE_KEY = "fake-key-123"

PAYLOAD = {
    "coord": {"lat": 40.7128, "lon": -74.006},
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


@pytest.fixture
def mock_get(monkeypatch):
    monkeypatch.setenv("OPENWEATHER_API_KEY", FAKE_KEY)
    monkeypatch.setattr(air, "load_dotenv", lambda: None)

    response = Mock(status_code=200)
    response.json.return_value = PAYLOAD
    get = Mock(return_value=response)
    monkeypatch.setattr(air.requests, "get", get)
    return get


def test_successful_extract(mock_get):
    result = air.extract("New York", 40.7128, -74.006, "2025-01-01")

    start = int(
        datetime(2025, 1, 1, tzinfo=timezone.utc).timestamp()
    )
    end = int(
        datetime(2025, 1, 2, tzinfo=timezone.utc).timestamp()
    )

    assert isinstance(result, dict)
    assert set(result) == {
        "city", "target_date", "data", "request_params", "retrieve_date"
    }
    assert result["city"] == "New York"
    assert result["target_date"] == "2025-01-01"
    assert result["data"] == PAYLOAD
    assert result["request_params"] == {"start": start, "end": end}
    datetime.strptime(result["retrieve_date"], "%Y-%m-%d")

    mock_get.assert_called_once_with(
        air.AIR_POLLUTION_URL + "/history",
        params={
            "lat": 40.7128,
            "lon": -74.006,
            "appid": FAKE_KEY,
            "start": start,
            "end": end,
        },
        timeout=30,
    )


def test_invalid_date(mock_get):
    with pytest.raises(ValueError, match="Invalid format"):
        air.extract("New York", 40.7128, -74.006, "not-a-date")

    mock_get.assert_not_called()


@pytest.mark.parametrize("key", [None, ""])
def test_missing_api_key(monkeypatch, mock_get, key):
    if key is None:
        monkeypatch.delenv("OPENWEATHER_API_KEY", raising=False)
    else:
        monkeypatch.setenv("OPENWEATHER_API_KEY", key)

    with pytest.raises(ValueError, match="Missing OPENWEATHER_API_KEY"):
        air.extract("New York", 40.7128, -74.006, "2025-01-01")

    mock_get.assert_not_called()


def test_empty_measurements(mock_get):
    payload = {"coord": PAYLOAD["coord"], "list": []}
    mock_get.return_value.json.return_value = payload

    result = air.extract("New York", 40.7128, -74.006, "2025-01-01")

    assert result["data"] == payload


@pytest.mark.parametrize("status", [401, 429, 500])
def test_http_error(mock_get, status):
    mock_get.return_value.status_code = status

    with pytest.raises(RuntimeError, match=f"HTTP {status}"):
        air.extract("New York", 40.7128, -74.006, "2025-01-01")

    mock_get.return_value.json.assert_not_called()


@pytest.mark.parametrize(
    "error_type", [requests.ConnectionError, requests.Timeout]
)
def test_connection_failure(mock_get, error_type):
    mock_get.side_effect = error_type("test failure")

    with pytest.raises(RuntimeError, match="Could not reach OpenWeather"):
        air.extract("New York", 40.7128, -74.006, "2025-01-01")


def test_invalid_json(mock_get):
    mock_get.return_value.json.side_effect = requests.exceptions.JSONDecodeError(
        "Invalid JSON", "not json", 0
    )

    with pytest.raises(requests.exceptions.JSONDecodeError):
        air.extract("New York", 40.7128, -74.006, "2025-01-01")
