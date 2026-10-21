"""The pipeline's outputs validate against the team's data_contracts.py."""

import copy
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from pydantic import BaseModel, ValidationError

import data_contracts as contracts
from pipeline.extract.openweather_air_pollution import RawAirPollutionRecord
from pipeline.transform.enrich import enrich_gold_record

NOW = datetime(2026, 10, 19, 20, tzinfo=timezone.utc)
DICTIONARY = Path(__file__).parents[3] / "docs/reference/gold_data_dictionary.md"


def gold_record(days=10):
    return {
        "retrieve_date": NOW.date(),
        "coordinates": {"lon": -73.98, "lat": 40.74},
        "city": "new york",
        "readings": [{
            "date_time": NOW - timedelta(days=d),
            "aqi": 1 + d % 5,
            "components": copy.deepcopy(contracts.golden_data["readings"][0]["components"]),
        } for d in range(days)],
    }


def test_enriched_gold_validates_against_gold_schema():
    enriched = enrich_gold_record(gold_record())
    model = contracts.GoldSchema.model_validate(enriched)
    assert model.readings[-1].aqi_rolling_7d is not None
    assert model.readings[0].aqi_rolling_7d is None
    assert model.readings[0].risk_score == pytest.approx(3.25 / 15 * 100)


def test_unenriched_gold_is_rejected_by_updated_schema():
    with pytest.raises(ValidationError):
        contracts.GoldSchema.model_validate(gold_record())


def test_retention_drops_readings_older_than_60_days_after_rolling():
    record = gold_record(days=70)
    enriched = enrich_gold_record(record, now=NOW)
    assert len(enriched["readings"]) == 60  # day 60 sits exactly on the cutoff and is dropped
    assert all(r["aqi_rolling_7d"] is not None for r in enriched["readings"])
    assert len(record["readings"]) == 70


def test_contract_examples_still_validate():
    contracts.GoldSchema.model_validate(contracts.golden_data)
    contracts.RawAirTrackerData.model_validate(contracts.raw_data)


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


def _field_paths(model, prefix=""):
    for name, field in model.model_fields.items():
        path = f"{prefix}{name}"
        yield path
        inner = field.annotation
        args = getattr(inner, "__args__", ())
        inner = args[0] if args and isinstance(args[0], type) else inner
        if isinstance(inner, type) and issubclass(inner, BaseModel):
            suffix = "[]." if getattr(field.annotation, "__origin__", None) is list else "."
            yield from _field_paths(inner, path + suffix)


@pytest.mark.parametrize("model", [contracts.GoldSchema, contracts.GoldenMateo])
def test_data_dictionary_documents_every_gold_field(model):
    documented = set(re.findall(r"^\| `([^`]+)`", DICTIONARY.read_text(), flags=re.M))
    missing = set(_field_paths(model)) - documented
    assert not missing
