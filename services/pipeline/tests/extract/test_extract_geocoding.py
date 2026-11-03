from datetime import datetime
from unittest.mock import Mock

import pytest
import requests

from pipeline.extract import geocoding as geo

PAYLOAD = {
    "results": [
        {
            "name": "New York",
            "latitude": 40.7128,
            "longitude": -74.006,
            "country_code": "US",
        }
    ],
    "generationtime_ms": 0.5,
}


@pytest.fixture
def mock_get(monkeypatch):
    response = Mock()
    response.json.return_value = PAYLOAD
    get = Mock(return_value=response)
    monkeypatch.setattr(geo.requests, "get", get)
    return get


def test_successful_geocoding(mock_get):
    result = geo.geocodes("New York")

    assert isinstance(result, dict)
    assert set(result) == {"city", "payload", "retrieve_date"}
    assert result["city"] == "New York"
    assert result["payload"] == PAYLOAD
    datetime.strptime(result["retrieve_date"], "%Y-%m-%d")

    mock_get.assert_called_once_with(
        geo.GEOCODING_URL,
        params={"name": "New York", "count": 1},
        timeout=15,
    )
    mock_get.return_value.raise_for_status.assert_called_once_with()


@pytest.mark.parametrize("city", ["", None])
def test_missing_city(mock_get, city):
    with pytest.raises(ValueError, match="Missing city value"):
        geo.geocodes(city)

    mock_get.assert_not_called()


@pytest.mark.parametrize("payload", [{}, {"results": []}])
def test_location_not_found(mock_get, payload):
    mock_get.return_value.json.return_value = payload

    with pytest.raises(ValueError, match="Could not find"):
        geo.geocodes("Unknown place")


def test_http_error(mock_get):
    mock_get.return_value.raise_for_status.side_effect = (
        requests.HTTPError("HTTP 500")
    )

    with pytest.raises(requests.HTTPError):
        geo.geocodes("New York")

    mock_get.return_value.json.assert_not_called()


def test_connection_failure(mock_get):
    mock_get.side_effect = requests.ConnectionError("test failure")

    with pytest.raises(requests.ConnectionError):
        geo.geocodes("New York")


def test_invalid_json(mock_get):
    mock_get.return_value.json.side_effect = requests.exceptions.JSONDecodeError(
        "Invalid JSON", "not json", 0
    )

    with pytest.raises(requests.exceptions.JSONDecodeError):
        geo.geocodes("New York")