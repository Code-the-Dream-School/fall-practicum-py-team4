"""Tests for src.pipeline.transform.enrichment.enrich (no API or database calls)."""
from unittest.mock import MagicMock

import pytest

# Run from the services/pipeline project root with pytest installed.
from src.pipeline.orchestration.llm_enrich import enrich


@pytest.fixture
def supabase():
    db = MagicMock()
    db.table.return_value.select.return_value.is_.return_value.execute.return_value.data = []
    return db


def set_rows(db, rows):
    db.table.return_value.select.return_value.is_.return_value.execute.return_value.data = rows


def sample_row(**changes):
    row = {"id": 10, "aqi": 3, "sentiment_label": "Moderate", "co": 240,
           "pm2_5": 18.5, "aqi_rolling_7d": 2.7, "pm2_5_rolling_7d": 16.2}
    row.update(changes)
    return row


@pytest.fixture(autouse=True)
def model_env(monkeypatch):
    monkeypatch.setenv("OPENROUTER_MODEL", "google/gemma-4-26b-a4b-it:free")


def test_valid_summary():
    assert enrich.valid_summary("Air quality is moderate. PM2.5 is 18.5 μg/m³.")
    assert enrich.valid_summary("Air quality is moderate.")


@pytest.mark.parametrize("summary", [None, "", "   ", 42, "No ending punctuation", "a" * 501,
                                      "One. Two. Three. Four."])
def test_invalid_summary(summary):
    assert not enrich.valid_summary(summary)


def test_success_saves_summary_and_run_id(supabase, monkeypatch):
    set_rows(supabase, [sample_row()])
    llm = MagicMock(return_value="Air quality is moderate.")
    monkeypatch.setattr(enrich, "generate_summary", llm)

    assert enrich.run_enrichment(supabase, "run-123") == {"success": 1, "skipped": 0, "failed": 0}
    llm.assert_called_once()
    assert "aqi: 3" in llm.call_args.args[0]
    assert "pm2_5: 18.5" in llm.call_args.args[0]
    supabase.table.assert_any_call("pipeline_runs")
    supabase.table.assert_any_call("gold_air_data")
    updates = [call.args[0] for call in supabase.table.return_value.update.call_args_list]
    assert {"llm_model": "google/gemma-4-26b-a4b-it:free", "prompt_version": "v1"} in updates
    assert {"llm_summary": "Air quality is moderate.", "enrichment_run_id": "run-123"} in updates
    assert all("llm_model" not in u for u in updates if "llm_summary" in u)


@pytest.mark.parametrize("changes", [
    {"aqi": None}, {"aqi": 6}, {"co": None, "pm2_5": None},
])
def test_skips_ineligible_record(supabase, monkeypatch, changes):
    set_rows(supabase, [sample_row(**changes)])
    llm = MagicMock()
    monkeypatch.setattr(enrich, "generate_summary", llm)
    assert enrich.run_enrichment(supabase, "run-123") == {"success": 0, "skipped": 1, "failed": 0}
    llm.assert_not_called()


def test_retries_invalid_response_once(supabase, monkeypatch):
    set_rows(supabase, [sample_row()])
    llm = MagicMock(side_effect=["", "Air quality is moderate."])
    monkeypatch.setattr(enrich, "generate_summary", llm)
    assert enrich.run_enrichment(supabase, "run-123")["success"] == 1
    assert llm.call_count == 2


def test_failure_after_two_attempts(supabase, monkeypatch):
    set_rows(supabase, [sample_row()])
    llm = MagicMock(side_effect=["", "still invalid"])
    monkeypatch.setattr(enrich, "generate_summary", llm)
    assert enrich.run_enrichment(supabase, "run-123")["failed"] == 1
    assert llm.call_count == 2
    updates = [call.args[0] for call in supabase.table.return_value.update.call_args_list]
    assert not any("llm_summary" in update for update in updates)


def test_one_failure_does_not_stop_batch(supabase, monkeypatch):
    set_rows(supabase, [sample_row(id=1), sample_row(id=2)])
    llm = MagicMock(side_effect=[RuntimeError("API down"), RuntimeError("API down"),
                                 "Air quality is moderate."])
    monkeypatch.setattr(enrich, "generate_summary", llm)
    assert enrich.run_enrichment(supabase, "run-123") == {"success": 1, "skipped": 0, "failed": 1}
    assert llm.call_count == 3


def test_no_pending_records_makes_no_llm_calls(supabase, monkeypatch):
    llm = MagicMock()
    monkeypatch.setattr(enrich, "generate_summary", llm)
    assert enrich.run_enrichment(supabase, "run-123") == {"success": 0, "skipped": 0, "failed": 0}
    llm.assert_not_called()
    supabase.table.return_value.select.return_value.is_.assert_called_with("llm_summary", "null")
