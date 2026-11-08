from datetime import datetime
from unittest.mock import Mock

import pytest
import requests

from pipeline.extract import geocoding as geo

PAYLOAD = {
    "results": [
        {
            "id": 5128581,
            "name": "New York",
            "latitude": 40.7128,
            "longitude": -74.006,
            "elevation": 10.0,
            "feature_code": "PPL",
            "country_code": "US",
            "admin1_id": 5128638,
            "timezone": "America/New_York",
            "population": 8804190,
            "country_id": 6252001,
            "country": "United States",
            "admin1": "New York"
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
    mock_get.return_value.json.return_value = PAYLOAD

    result = geo.geocodes("New York")

    assert isinstance(result, dict)
    assert set(result) == {"city", "payload", "extracted_at"}
    assert result["city"] == "new york"
    assert result["payload"]["results"][0]["name"] == "New York"
    assert result["payload"]["results"][0]["latitude"] == 40.7128
    datetime.strptime(result["extracted_at"], "%Y-%m-%d")

    mock_get.assert_called_once_with(
        geo.GEOCODING_URL,
        params={"name": "new york", "count": 1},
        timeout=15,
    )
    mock_get.return_value.raise_for_status.assert_called_once_with()


@pytest.mark.parametrize("city", ["", None])
def test_missing_city(mock_get, city):
    with pytest.raises(ValueError, match="Missing city value"):
        geo.geocodes(city)

    mock_get.assert_not_called()


@pytest.mark.parametrize("payload", [{"generationtime_ms": 0.0}])
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

def test_invalid_pydantic_schema(mock_get):
    # Missing required fields like 'generationtime_ms' or 'results'
    mock_get.return_value.json.return_value = {"invalid": "schema"}

    with pytest.raises(RuntimeError, match="Open-Meteo response failed Pydantic validation"):
        geo.geocodes("New York")