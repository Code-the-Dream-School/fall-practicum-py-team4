import json
import logging
from datetime import datetime, timezone
from unittest.mock import Mock

import pytest

from pipeline.orchestration import lambda_handler as handler


pytestmark = pytest.mark.unit

EVENT = {
    "city": "New York",
    "date": "2025-01-01",
}
CACHED_CITY = {
    "city": "new york",
    "city_id": 7,
    "latitude": 40.7128,
    "longitude": -74.006,
}


@pytest.fixture
def lambda_dependencies(monkeypatch):
    parameter_values = {
        "/app/openweather-key": "test-openweather-key",
        "/app/supabase-url": "https://example.supabase.co",
        "/app/supabase-key": "test-supabase-key",
    }
    ssm = Mock()
    ssm.get_parameter.side_effect = lambda Name, WithDecryption: {
        "Parameter": {"Value": parameter_values[Name]}
    }
    monkeypatch.setattr(handler.boto3, "client", Mock(return_value=ssm))
    monkeypatch.setenv("OPENWEATHER_API_KEY_SSM_PARAMETER", "/app/openweather-key")
    monkeypatch.setenv("SUPABASE_URL_SSM_PARAMETER", "/app/supabase-url")
    monkeypatch.setenv("SUPABASE_KEY_SSM_PARAMETER", "/app/supabase-key")
    supabase = Mock()
    monkeypatch.setattr(handler, "create_client", Mock(return_value=supabase))
    monkeypatch.setattr(
        handler, "get_city_from_cache", Mock(return_value=CACHED_CITY)
    )
    return ssm, supabase


def test_lambda_handler_runs_ingest_stages(lambda_dependencies, monkeypatch, caplog):
    caplog.set_level(logging.INFO)
    _, supabase = lambda_dependencies
    raw_data = {"city": "new york", "payload": {"list": []}}
    current_batch = [
        {
            "date_time": datetime(2025, 1, 1, hour, tzinfo=timezone.utc),
            "aqi": 2,
            "pm2_5": 8.5,
        }
        for hour in range(2)
    ]
    monkeypatch.setattr(handler, "extract", Mock(return_value=raw_data))
    monkeypatch.setattr(handler, "load_raw_air_pollution", Mock(return_value=1))
    monkeypatch.setattr(handler, "transform_air_data", Mock(return_value=current_batch))
    monkeypatch.setattr(
        handler, "fetch_historical_readings", Mock(return_value=current_batch)
    )
    monkeypatch.setattr(
        handler, "add_rolling_average", Mock(side_effect=lambda rows, field: rows)
    )
    monkeypatch.setattr(handler, "load_gold_air_data", Mock(return_value=2))

    result = handler.lambda_handler(EVENT, None)

    assert result == {
        "status": "SUCCESS",
        "city": "new york",
        "date": "2025-01-01",
        "counts": {
            "extract_geocoding": 0,
            "load_raw_cities": 0,
            "transform_cities": 0,
            "load_gold_cities": 0,
            "extract_air_pollution": 1,
            "load_raw_air_pollution": 1,
            "transform_air_records": 2,
            "transform_rolling_records": 2,
            "load_gold_air_records": 2,
        },
    }
    handler.extract.assert_called_once_with("new york", 40.7128, -74.006, "2025-01-01")
    handler.load_raw_air_pollution.assert_called_once_with(supabase, raw_data)
    handler.transform_air_data.assert_called_once_with(raw_data, 7)
    assert [
        call.kwargs["field"] for call in handler.add_rolling_average.call_args_list
    ] == ["aqi", "pm2_5"]
    handler.load_gold_air_data.assert_called_once_with(supabase, current_batch)
    assert json.loads(caplog.records[-1].message)["status"] == "SUCCESS"


def test_cache_miss_loads_and_transforms_city(lambda_dependencies, monkeypatch):
    _, supabase = lambda_dependencies
    monkeypatch.setattr(handler, "get_city_from_cache", Mock(side_effect=[None, CACHED_CITY]))
    city_data = {"city": "new york", "payload": {"results": [{}]}}
    gold_city = {"city": "new york", "lat": 40.7128, "lon": -74.006}
    monkeypatch.setattr(handler, "geocodes", Mock(return_value=city_data))
    monkeypatch.setattr(handler, "load_raw_cities", Mock(return_value=1))
    monkeypatch.setattr(handler, "transform_city_data", Mock(return_value=gold_city))
    monkeypatch.setattr(handler, "load_gold_cities", Mock(return_value=1))
    monkeypatch.setattr(
        handler,
        "extract",
        Mock(return_value={"city": "new york", "payload": {"list": []}}),
    )
    monkeypatch.setattr(handler, "load_raw_air_pollution", Mock(return_value=1))
    monkeypatch.setattr(handler, "transform_air_data", Mock(return_value=[]))

    result = handler.lambda_handler(EVENT, None)

    assert result["counts"]["extract_geocoding"] == 1
    assert result["counts"]["load_raw_cities"] == 1
    assert result["counts"]["transform_cities"] == 1
    assert result["counts"]["load_gold_cities"] == 1
    handler.load_raw_cities.assert_called_once_with(supabase, city_data)
    handler.load_gold_cities.assert_called_once_with(supabase, gold_city)


def test_lambda_handler_logs_stage_and_reraises_failure(lambda_dependencies, monkeypatch, caplog):
    monkeypatch.setattr(handler, "extract", Mock(side_effect=RuntimeError("upstream failed")))

    with pytest.raises(RuntimeError, match="upstream failed"):
        handler.lambda_handler(EVENT, None)

    failure = json.loads(caplog.records[-1].message)
    assert failure["status"] == "FAILED"
    assert failure["failed_stage"] == "extract_air_pollution"
    assert failure["counts"]["extract_air_pollution"] == 0


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("city", ""),
        ("date", "2025-1-1"),
    ],
)
def test_lambda_handler_rejects_invalid_event(lambda_dependencies, field, value):
    event = {**EVENT, field: value}

    with pytest.raises(ValueError):
        handler.lambda_handler(event, None)


def test_lambda_handler_accepts_eventbridge_detail(lambda_dependencies, monkeypatch):
    monkeypatch.setattr(handler, "extract", Mock(return_value={"payload": {"list": []}}))
    monkeypatch.setattr(handler, "load_raw_air_pollution", Mock(return_value=1))
    monkeypatch.setattr(handler, "transform_air_data", Mock(return_value=[]))

    result = handler.lambda_handler({"detail": EVENT}, None)

    assert result["status"] == "SUCCESS"
