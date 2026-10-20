import json
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, Mock

import psycopg
import pytest
import requests

import data_contracts as dc
from pipeline import contracts
from pipeline import orchestration as orch
from pipeline.extract import geocoding as geo
from pipeline.transform.gold_rows import GOLD_TABLE_COLUMNS, to_gold_rows
from pipeline.retention import RETENTION_DAYS, ROLLING_WARMUP_DAYS, extraction_window, retention_cutoff

NOW = datetime(2026, 10, 19, 20, tzinfo=timezone.utc)
CITY = [{"name": "Charlotte", "country": "US", "state": "North Carolina", "lat": 35.23, "lon": -80.84}]
COMPONENTS = {"co": 200.0, "no": 0.1, "no2": 5.0, "o3": 60.0, "so2": 1.0, "pm2_5": 7.5, "pm10": 10.0, "nh3": 0.5}


def hourly_payload(start, end):
    first = int(start.timestamp()) // 3600 * 3600 + 3600
    return {"coord": {"lon": -80.84, "lat": 35.23}, "list": [
        {"dt": dt, "main": {"aqi": 1 + (dt // 3600) % 5}, "components": dict(COMPONENTS)}
        for dt in range(first, int(end.timestamp()) + 1, 3600)
    ]}


def stand_in_transform(raw_records):
    # Minimal stand-in for the T4AIR-16 transform: RawAirTrackerData -> GoldSchema.
    return [{
        "retrieve_date": record["retrieve_date"],
        "coordinates": record["coord"],
        "city": record["city"],
        "country": record["country"],
        "readings": [{
            "date_time": datetime.fromtimestamp(row["dt"], tz=timezone.utc),
            "aqi": row["main"]["aqi"],
            "components": row["components"],
        } for row in record["list"]],
    } for record in raw_records]


class MemoryRunStore:
    def __init__(self):
        self.rows = []

    def save(self, row):
        self.rows.append(row)
        return 101


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    monkeypatch.setenv("OPENWEATHER_API_KEY", "test-only-key")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setattr(geo, "utc_now", lambda: NOW)
    monkeypatch.setattr(contracts, "utc_now", lambda: NOW)
    monkeypatch.setattr(psycopg, "connect", Mock(side_effect=AssertionError("Live DB forbidden")))


@pytest.fixture
def http(monkeypatch):
    def get(url, params, **_):
        body = CITY if "/geo/" in url else hourly_payload(
            datetime.fromtimestamp(params["start"], tz=timezone.utc),
            datetime.fromtimestamp(params["end"], tz=timezone.utc))
        result = requests.Response()
        result.status_code = 200
        result._content = json.dumps(body).encode()
        result._content_consumed = True
        return result
    mock = Mock(side_effect=get)
    monkeypatch.setattr(requests, "get", mock)
    return mock


def run(config, **kwargs):
    kwargs.setdefault("transform", stand_in_transform)
    kwargs.setdefault("load_raw", Mock())
    kwargs.setdefault("load_gold", Mock())
    return orch.run_pipeline_job(config, now=NOW, **kwargs)


def test_retention_windows():
    start, end = extraction_window(NOW)
    assert end == NOW and NOW - start == timedelta(days=RETENTION_DAYS + ROLLING_WARMUP_DAYS)
    assert NOW - retention_cutoff(NOW) == timedelta(days=60)
    with pytest.raises(ValueError):
        extraction_window(datetime(2026, 10, 19))


def test_contract_input_hourly_run_logs_pipeline_runs_shape(http):
    store = MemoryRunStore()
    raw_loaded, gold_loaded = Mock(), []
    result = run({"cities": ["Charlotte, NC, US"], "daily": False},
                 load_raw=raw_loaded, load_gold=gold_loaded.extend, run_store=store)
    assert set(result.to_dict()) == {"id", "status", "records_added", "runs_time", "created_at"}
    assert store.rows == [{k: v for k, v in result.to_dict().items() if k != "id"}]
    assert result.id == 101 and result.status == "succeeded" and result.created_at == "2026-10-19T20:00:00Z"
    # 60 days of hourly readings kept; the 7 warm-up days are dropped after rolling.
    assert result.records_added == 60 * 24 == len(gold_loaded[0]["readings"])
    readings = gold_loaded[0]["readings"]
    assert gold_loaded[0]["city"] == "charlotte, nc, us" and gold_loaded[0]["country"] == "us"
    assert readings[0]["date_time"] > retention_cutoff(NOW)
    assert all(r["aqi_rolling_7d"] is not None for r in readings)
    assert readings[0]["risk_score"] == 50.0
    dc.GoldSchema.model_validate(gold_loaded[0])
    # load_raw(raw_records: list) is called once with contract-shaped raw records.
    (raw_records,), _ = raw_loaded.call_args
    assert raw_loaded.call_count == 1 and len(raw_records) == 1
    raw = dc.RawAirTrackerData.model_validate(raw_records[0])
    assert len(raw.list) == (RETENTION_DAYS + ROLLING_WARMUP_DAYS) * 24
    assert http.call_count == 2


def test_contract_default_daily_keeps_one_reading_per_day_at_time_of_day(http):
    gold = []
    result = run({"cities": ["charlotte, us"], "time_of_day": "15:00"}, load_gold=gold.extend)
    readings = gold[0]["readings"]
    assert result.records_added == 60 == len(readings)
    assert {r["date_time"].hour for r in readings} == {15}
    assert all(r["aqi_rolling_7d"] is not None for r in readings)


def test_contract_date_range_is_used_and_gold_still_keeps_60_days(http):
    gold = []
    run({"cities": ["charlotte, us"], "date_range": "06/01/2026 - 10/18/2026", "daily": True},
        load_gold=gold.extend)
    params = http.call_args_list[-1].kwargs["params"]
    assert params["start"] == int(datetime(2026, 6, 1, tzinfo=timezone.utc).timestamp())
    assert params["end"] == int(datetime(2026, 10, 19, tzinfo=timezone.utc).timestamp())
    assert all(r["date_time"] > retention_cutoff(NOW) for r in gold[0]["readings"])


@pytest.mark.parametrize("config", [{}, {"cities": []}, {"cities": [""]}, {"cities": "london"}])
def test_missing_city_stops_the_pipeline_and_is_recorded(http, config):
    store = MemoryRunStore()
    with pytest.raises(ValueError, match="Missing city"):
        run(config, run_store=store)
    assert store.rows[0]["status"] == "failed" and store.rows[0]["records_added"] == 0
    http.assert_not_called()


def test_failed_load_is_recorded_and_reraised(http):
    store = MemoryRunStore()
    with pytest.raises(RuntimeError, match="db down"):
        run({"cities": ["charlotte, us"]}, load_gold=Mock(side_effect=RuntimeError("db down")), run_store=store)
    assert store.rows[0]["status"] == "failed" and store.rows[0]["records_added"] == 0


def test_default_run_store_logs_the_row(http, caplog):
    caplog.set_level("INFO", logger=orch.__name__)
    result = run({"cities": ["charlotte, us"]})
    assert caplog.records[-1].pipeline_run == result.to_dict()


def test_orchestration_has_no_azure_or_missing_imports():
    source = open(orch.__file__).read().lower()
    assert "azure" not in source and "read_cities" not in source


def test_supabase_run_store_inserts_row_and_returns_db_id(http):
    client = MagicMock()
    client.table.return_value.insert.return_value.execute.return_value.data = [{"id": 7}]
    result = run({"cities": ["charlotte, us"]}, run_store=orch.SupabaseRunStore(client))
    client.table.assert_called_once_with("pipeline_runs")
    (row,), _ = client.table.return_value.insert.call_args
    # Exactly the pipeline_runs columns; id comes from the database.
    assert set(row) == {"status", "records_added", "runs_time", "created_at"}
    assert result.id == 7 and result.status == "succeeded"


def test_gold_rows_use_gold_table_columns(http):
    gold = []
    run({"cities": ["charlotte, us"]}, load_gold=gold.extend)
    rows = to_gold_rows(gold[0])
    # Columns seen in Supabase gold_table on 2026-10-20, minus the database id.
    assert set(rows[0]) == {"longitude", "latitude", "city", "country", "co", "pm2_5", "no2",
                            "date", "retrieve_date", "aqi", "sentiment_label", "running_average"}
    assert set(GOLD_TABLE_COLUMNS.values()) == set(rows[0])
    assert len(rows) == 60 and rows[0]["sentiment_label"] in {"Good", "Fair", "Moderate", "Poor", "Very Poor"}
    assert rows[0]["retrieve_date"] == "2026-10-19T00:00:00+00:00"
    assert rows[0]["date"].endswith("+00:00") and rows[0]["running_average"] is not None
