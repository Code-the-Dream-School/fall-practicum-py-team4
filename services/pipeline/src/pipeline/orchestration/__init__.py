"""Run extract -> load raw -> transform -> load gold and record one pipeline_runs row.

Input is the data_contracts input configuration. Stages use the contract
signatures: geocodes(cities) -> dict, extract(...) -> list,
load_raw(raw_records) -> None, transform(raw_records) -> list. Transform
(T4AIR-16) and the loaders (T4AIR-15 raw, gold storage) are passed in until
they are merged. The final log matches the pipeline_runs table.
"""

from __future__ import annotations

import itertools
import logging
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any, Protocol

from pipeline import contracts
from pipeline.retention import drop_expired

log = logging.getLogger(__name__)

RawRecord = dict[str, Any]  # RawAirTrackerData shape, with city and country
GoldRecord = dict[str, Any]  # GoldSchema shape


@dataclass(frozen=True)
class PipelineRunLog:
    id: int | None  # assigned by pipeline_runs when the row is saved
    status: str  # "succeeded" or "failed"
    records_added: int
    runs_time: float  # seconds
    created_at: str  # UTC ISO-8601, e.g. 2026-10-19T20:00:00Z

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class RunStore(Protocol):
    def save(self, row: dict[str, Any]) -> int:
        """Insert one pipeline_runs row (without id) and return its new id."""


class LoggingRunStore:
    """Local stand-in: logs the row and numbers runs from 1."""

    def __init__(self) -> None:
        self._ids = itertools.count(1)

    def save(self, row: dict[str, Any]) -> int:
        return next(self._ids)


class SupabaseRunStore:
    """Writes to the Supabase pipeline_runs table (id, status, records_added, runs_time, created_at)."""

    def __init__(self, supabase_client) -> None:
        self._client = supabase_client

    def save(self, row: dict[str, Any]) -> int:
        response = self._client.table("pipeline_runs").insert(row).execute()
        return response.data[0]["id"]


def _iso_utc(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def run_extract_stage(
    settings: contracts.PipelineInput, *, geocodes=contracts.geocodes, extract=contracts.extract,
) -> list[RawRecord]:
    raw_records = []
    for city, point in geocodes(settings.cities).items():
        for record in extract(
            point["lat"], point["lon"], "/history", settings.start, settings.end,
            settings.daily, settings.time_of_day,
        ):
            # The pollution API does not return these; gold needs them.
            raw_records.append({**record, "city": city, "country": point.get("country")})
    return raw_records


def finalize_gold(record: GoldRecord, now: datetime) -> GoldRecord:
    """Apply the 60-day cut and the contract's lowercase rule to one gold record."""
    result = {**record, "readings": drop_expired(record["readings"], now)}
    for field in ("city", "country"):
        if isinstance(record.get(field), str):
            result[field] = record[field].lower()
    return result


def run_transform_stage(
    raw_records: list[RawRecord], transform: Callable[[list], list], now: datetime,
) -> list[GoldRecord]:
    return [finalize_gold(record, now) for record in transform(raw_records)]


def run_pipeline_job(
    config: dict,
    *,
    transform: Callable[[list], list],
    load_raw: Callable[[list], None],
    load_gold: Callable[[list], None],
    run_store: RunStore | None = None,
    now: datetime | None = None,
    geocodes=contracts.geocodes,
    extract=contracts.extract,
) -> PipelineRunLog:
    store = run_store if run_store is not None else LoggingRunStore()
    created = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    started = time.perf_counter()
    records_added = 0
    status = "failed"
    try:
        settings = contracts.parse_input(config, created)
        raw_records = run_extract_stage(settings, geocodes=geocodes, extract=extract)
        load_raw(raw_records)
        gold_records = run_transform_stage(raw_records, transform, created)
        load_gold(gold_records)
        records_added = sum(len(record["readings"]) for record in gold_records)
        status = "succeeded"
    except Exception:
        log.exception("Pipeline failed")
        raise
    finally:
        row = {
            "status": status,
            "records_added": records_added,
            "runs_time": round(time.perf_counter() - started, 2),
            "created_at": _iso_utc(created),
        }
        run = PipelineRunLog(id=store.save(row), **row)
        log.info("pipeline_runs row", extra={"pipeline_run": run.to_dict()})
    return run
