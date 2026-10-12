import ast
import copy
import json
import traceback
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock

import psycopg
import pytest
import requests

from pipeline.extract import geocoding as geo
from pipeline.extract import lookup_cache as cache_module
from pipeline.extract import openweather_air_pollution as air
from pipeline.extract import openweather_http as http

NOW = datetime(2026, 10, 12, 12, tzinfo=timezone.utc)
CITY = [{"name": "New York", "country": "US", "state": "New York", "lat": 40.71, "lon": -74.01}]
POLLUTION = {"coord": [40.71, -74.01], "list": [{
    "dt": 1791763200, "main": {"aqi": 2}, "components": {"pm2_5": 8.8}, "extra": "preserve me",
}]}


class MemoryCache:
    def __init__(self):
        self.rows = {}

    def get(self, key, now, ttl, empty_ttl):
        row = self.rows.get(key)
        if row is None:
            return None
        payload, fetched, expires = row
        lifetime = ttl if payload else empty_ttl
        if fetched <= now < min(expires, fetched + timedelta(seconds=lifetime)):
            return copy.deepcopy((payload, fetched))

    def put(self, key, payload, fetched, ttl):
        if ttl > 0:
            self.rows[key] = copy.deepcopy((payload, fetched, fetched + timedelta(seconds=ttl)))


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    monkeypatch.setenv("OPENWEATHER_API_KEY", "test-only-key")
    for key in ("OPENWEATHER_LOOKUP_TTL_SECONDS", "OPENWEATHER_EMPTY_LOOKUP_TTL_SECONDS",
                "OPENWEATHER_TIMEOUT_SECONDS", "DATABASE_URL"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setattr(geo, "utc_now", lambda: NOW)
    monkeypatch.setattr(air, "utc_now", lambda: NOW)
    monkeypatch.setattr(http.time, "sleep", Mock())
    monkeypatch.setattr(requests, "get", Mock(side_effect=AssertionError("Live HTTP forbidden")))
    monkeypatch.setattr(psycopg, "connect", Mock(side_effect=AssertionError("Live DB forbidden")))


def response(payload, status=200, headers=None):
    result = requests.Response()
    result.status_code = status
    result._content = json.dumps(payload).encode()
    result._content_consumed = True
    result.headers.update(headers or {})
    return result


def history_kwargs():
    return dict(raw_dir=Path("unused"), city="New York", country_code="US", lat=40.71,
                lon=-74.01, start=NOW-timedelta(hours=24), end=NOW,
                run_id="batch-1", pipeline_run_id=10)


def test_history_preserves_payload_context_and_converts_dates(monkeypatch):
    mock = Mock(return_value=copy.deepcopy(POLLUTION))
    monkeypatch.setattr(air, "get_json", mock)
    record = air.fetch_air_pollution_history(**history_kwargs())
    assert record.payload == POLLUTION
    assert record.city == "New York" and record.pipeline_run_id == 10
    assert record.request_params["start"] == int((NOW-timedelta(hours=24)).timestamp())
    assert record.request_params["end"] == int(NOW.timestamp())
    assert record.to_dict()["retrieved_at"] == "2026-10-12T12:00:00Z"
    assert "test-only-key" not in json.dumps(record.to_dict())


@pytest.mark.parametrize("change", [
    {"lat": True}, {"lat": 91}, {"lon": float("nan")}, {"country_code": "USA"},
    {"start": datetime(2026,10,1)}, {"end": NOW+timedelta(seconds=1)},
    {"start": NOW}, {"start": NOW-timedelta(microseconds=2), "end": NOW-timedelta(microseconds=1)},
    {"start": datetime(2020,1,1,tzinfo=timezone.utc)}, {"run_id": ""}, {"pipeline_run_id": True},
])
def test_invalid_history_fails_before_network(change):
    with pytest.raises(http.InputError):
        air.fetch_air_pollution_history(**(history_kwargs() | change))
    requests.get.assert_not_called()


def test_empty_history_is_valid(monkeypatch):
    monkeypatch.setattr(air, "get_json", lambda *a: {"coord": [], "list": []})
    assert air.fetch_air_pollution_history(**history_kwargs()).payload["list"] == []


def test_repeated_lookup_hits_cache_and_force_refresh_bypasses(monkeypatch):
    get = Mock(return_value=CITY)
    monkeypatch.setattr(geo, "get_json", get)
    store = MemoryCache()
    first = geo.geocode_city(Path("unused"), " New York ", "us", "NY", cache=store)
    second = geo.geocode_city(Path("unused"), "New York", "US", "New York", cache=store)
    assert not first.from_cache and second.from_cache
    assert second.lat == 40.71 and second.lon == -74.01
    assert first.retrieved_at == second.retrieved_at
    assert get.call_count == 1
    geo.geocode_city(Path("unused"), "New York", "US", "NY", cache=store, force_refresh=True)
    assert get.call_count == 2


def test_negative_cache_and_expiry(monkeypatch):
    get = Mock(return_value=[])
    monkeypatch.setattr(geo, "get_json", get)
    store = MemoryCache()
    for _ in range(2):
        with pytest.raises(http.OpenWeatherError, match="No matching city"):
            geo.geocode_city(Path("unused"), "Missing", "US", cache=store)
    assert get.call_count == 1
    monkeypatch.setattr(geo, "utc_now", lambda: NOW+timedelta(hours=1))
    with pytest.raises(http.OpenWeatherError):
        geo.geocode_city(Path("unused"), "Missing", "US", cache=store)
    assert get.call_count == 2


def test_ambiguity_is_not_silently_resolved(monkeypatch):
    monkeypatch.setattr(geo, "get_json", lambda *a: CITY + [CITY[0] | {"lat": 41}])
    with pytest.raises(http.OpenWeatherError, match="Ambiguous"):
        geo.geocode_city(Path("unused"), "New York", "US", "NY", use_cache=False)


def test_non_us_state_is_filtered_without_us_query_syntax(monkeypatch):
    get = Mock(return_value=[{"name":"London", "country":"CA", "state":"Ontario", "lat":42.9, "lon":-81.2}])
    monkeypatch.setattr(geo, "get_json", get)
    coords = geo.geocode_city(Path("unused"), "London", "CA", "Ontario", use_cache=False)
    assert coords.lat == 42.9
    get.assert_called_once_with("/geo/1.0/direct", {"q":"London,CA", "limit":5})


def test_failed_source_response_is_not_cached(monkeypatch):
    monkeypatch.setattr(geo, "get_json", Mock(side_effect=http.OpenWeatherError("Failure")))
    store = MemoryCache()
    with pytest.raises(http.OpenWeatherError):
        geo.geocode_city(Path("unused"), "New York", "US", "NY", cache=store)
    assert not store.rows


@pytest.mark.parametrize("status", [400, 401, 403, 404, 302])
def test_permanent_http_errors_do_not_retry(monkeypatch, status):
    get = Mock(return_value=response({"message":"test-only-key"}, status))
    monkeypatch.setattr(requests, "get", get)
    with pytest.raises(http.OpenWeatherError) as caught:
        http.get_json("/geo/1.0/direct", {"q":"London,GB"})
    assert "test-only-key" not in str(caught.value)
    assert get.call_count == 1


@pytest.mark.parametrize("status", [429, 500, 502, 503, 504])
def test_transient_http_errors_retry(monkeypatch, status):
    get = Mock(side_effect=[response({}, status, {"Retry-After":"2"}), response(CITY)])
    monkeypatch.setattr(requests, "get", get)
    assert http.get_json("/geo/1.0/direct", {"q":"New York,NY,US"}) == CITY
    http.time.sleep.assert_called_once_with(2)
    assert get.call_count == 2


def test_long_retry_after_is_not_shortened(monkeypatch):
    get = Mock(return_value=response({}, 429, {"Retry-After":"90"}))
    monkeypatch.setattr(requests, "get", get)
    with pytest.raises(http.OpenWeatherError):
        http.get_json("/geo/1.0/direct", {})
    assert get.call_count == 1
    http.time.sleep.assert_not_called()


def test_timeout_retries_and_suppresses_credentials(monkeypatch):
    get = Mock(side_effect=requests.Timeout("URL contains test-only-key"))
    monkeypatch.setattr(requests, "get", get)
    with pytest.raises(http.OpenWeatherError) as caught:
        http.get_json("/geo/1.0/direct", {})
    assert get.call_count == 3
    assert "test-only-key" not in "".join(traceback.format_exception(caught.value))


def test_missing_key_fails_locally(monkeypatch):
    monkeypatch.delenv("OPENWEATHER_API_KEY")
    with pytest.raises(http.ConfigurationError):
        http.get_json("/geo/1.0/direct", {})
    requests.get.assert_not_called()


def test_invalid_json_and_oversized_body(monkeypatch):
    raw = response({})
    raw._content = b"bad json"
    monkeypatch.setattr(requests, "get", Mock(return_value=raw))
    with pytest.raises(http.OpenWeatherError, match="invalid JSON"):
        http.get_json("/geo/1.0/direct", {})
    monkeypatch.setattr(http, "MAX_BODY_BYTES", 2)
    monkeypatch.setattr(requests, "get", Mock(return_value=response(CITY)))
    with pytest.raises(http.OpenWeatherError, match="exceeds"):
        http.get_json("/geo/1.0/direct", {})


@pytest.mark.parametrize("age,ttl,empty,payload,expires,hit", [
    (1,60,5,CITY,60,True), (60,60,5,CITY,120,False),
    (20,10,5,CITY,120,False), (-1,60,5,CITY,120,False),
    (4,60,5,[],120,True), (5,60,5,[],120,False),
    (2,60,5,CITY,1,False), (1,60,5,{},120,False),
])
def test_postgres_row_freshness(monkeypatch,age,ttl,empty,payload,expires,hit):
    db = MagicMock()
    db.__enter__.return_value = db
    db.execute.return_value.fetchone.return_value = (payload,NOW,NOW+timedelta(seconds=expires))
    monkeypatch.setattr(psycopg, "connect", Mock(return_value=db))
    cache = cache_module.PostgresLookupCache("postgresql://fixture")
    result = cache.get("hash", NOW+timedelta(seconds=age), ttl, empty)
    assert (result is not None) == hit


def test_postgres_missing_row_and_read_failure(monkeypatch, caplog):
    db = MagicMock()
    db.__enter__.return_value = db
    db.execute.return_value.fetchone.return_value = None
    connect = Mock(return_value=db)
    monkeypatch.setattr(psycopg, "connect", connect)
    store = cache_module.PostgresLookupCache("postgresql://secret-dsn")
    assert store.get("hash", NOW, 60, 5) is None
    connect.side_effect = psycopg.OperationalError("secret-dsn")
    assert store.get("hash", NOW, 60, 5) is None
    store.put("hash", CITY, NOW, 60)
    assert "secret-dsn" not in caplog.text


def test_postgres_write_uses_bound_json_parameters(monkeypatch):
    db = MagicMock()
    db.__enter__.return_value = db
    monkeypatch.setattr(psycopg, "connect", Mock(return_value=db))
    store = cache_module.PostgresLookupCache("postgresql://fixture")
    store.put("hash", CITY, NOW, 60)
    sql, params = db.execute.call_args_list[0].args
    assert "ON CONFLICT" in sql and "New York" not in sql
    assert params[0] == "hash" and params[1].obj == CITY
    assert params[3] == NOW+timedelta(seconds=60)


def test_existing_team_extraction_stage_accepts_real_adapters(monkeypatch):
    # Compile only the reviewed stage: the repository's other modules are missing.
    source = Path(__file__).parents[1] / "src/pipeline/orchestration/__init__.py"
    tree = ast.parse(source.read_text())
    stage = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "run_extract_stage")
    store = MemoryCache()
    monkeypatch.setattr(geo, "PostgresLookupCache", lambda: store)
    get = Mock(side_effect=lambda url, **kw: response(CITY if "/geo/" in url else POLLUTION))
    monkeypatch.setattr(requests, "get", get)
    namespace = dict(Path=Path, datetime=datetime, RawAirPollutionRecord=air.RawAirPollutionRecord,
                     settings=SimpleNamespace(cities_source="database"),
                     read_cities=lambda _: [SimpleNamespace(city="New York",country_code="US",state="NY")],
                     geocode_city=geo.geocode_city, fetch_air_pollution_history=air.fetch_air_pollution_history)
    exec(compile(ast.Module(body=[stage], type_ignores=[]), "team_stage", "exec"), namespace)
    for _ in range(2):
        records, count = namespace["run_extract_stage"](Path("unused"), NOW-timedelta(hours=24), NOW, "run-1", 10)
        assert count == 1 and records[0].pipeline_run_id == 10
        assert records[0].payload == POLLUTION
    # One geocoding request, then two fresh history requests.
    assert get.call_count == 3
