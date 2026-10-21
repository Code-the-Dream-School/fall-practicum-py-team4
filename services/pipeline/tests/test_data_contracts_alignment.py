"""The pipeline's outputs validate against the team's data_contracts.py."""

import copy
from datetime import datetime, timedelta, timezone

import data_contracts as contracts
from pipeline.extract.openweather_air_pollution import RawAirPollutionRecord

NOW = datetime(2026, 10, 19, 20, tzinfo=timezone.utc)


def test_contract_examples_still_validate():
    contracts.GoldSchema.model_validate(contracts.golden_data)
    contracts.RawAirTrackerData.model_validate(contracts.raw_data)
    contracts.GoldenMateo.model_validate(contracts.golden_mateo)


def test_extract_record_converts_to_raw_contract():
    payload = copy.deepcopy(contracts.raw_data)
    del payload["retrieve_date"]
    record = RawAirPollutionRecord(
        city="New York", country_code="US", lat=50.0, lon=50.0,
        start=NOW - timedelta(days=67), end=NOW, run_id="r", pipeline_run_id=1,
        retrieved_at=NOW, request_params={"lat": 50.0, "lon": 50.0, "start": 1, "end": 2}, payload=payload,
    )
    raw = contracts.RawAirTrackerData.model_validate(record.to_raw_contract())
    assert raw.retrieve_date == "2026-10-19" and raw.request_params.end == 2
    assert raw.city == "new york"
