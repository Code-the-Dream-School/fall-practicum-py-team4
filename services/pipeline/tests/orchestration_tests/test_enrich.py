import json
from unittest.mock import MagicMock

import pytest

import src.pipeline.orchestration.llm_enrich.enrich as enrich


# -------------------------------
# Summary validation
# -------------------------------

def test_valid_summary():
    assert enrich.valid_summary(
        "Air quality is good."
    )

    assert enrich.valid_summary(
        "PM2.5 is elevated. Air quality is poor."
    )


@pytest.mark.parametrize("summary", [
    None,
    "",
    "   ",
    42,
    "No ending punctuation",
    "One. Two. Three. Four.",
    "A" * 501 + ".",
])
def test_invalid_summary(summary):
    assert not enrich.valid_summary(summary)


# -------------------------------
# Record validation
# -------------------------------

@pytest.mark.parametrize("aqi", [1, 2, 3, 4, 5])
def test_valid_aqi(aqi):
    row = {"aqi": aqi, "co": 100, "pm2_5": None}

    assert enrich.valid_record(row)


@pytest.mark.parametrize("aqi", [None, 0, 6, -1])
def test_invalid_aqi(aqi):
    row = {"aqi": aqi, "co": 100, "pm2_5": 10}

    assert not enrich.valid_record(row)


def test_record_requires_pollutant():
    row = {
        "aqi": 2,
        "co": None,
        "pm2_5": None
    }

    assert not enrich.valid_record(row)


def test_record_accepts_pm25_only():
    row = {
        "aqi": 3,
        "co": None,
        "pm2_5": 12.5
    }

    assert enrich.valid_record(row)


# -------------------------------
# LLM batch processing
# -------------------------------

def test_enrich_batch_matches_ids(monkeypatch):
    batch = [
        {"id": 101, "aqi": 1, "co": 100},
        {"id": 102, "aqi": 4, "pm2_5": 40}
    ]

    def fake_generate(prompt):
        data = json.loads(prompt.split("Measurements:\n")[1])

        assert [row["id"] for row in data["records"]] == [101, 102]

        # Deliberately reverse output order.
        return json.dumps({
            "results": [
                {"id": 102, "llm_response": "Air quality is poor."},
                {"id": 101, "llm_response": "Air quality is good."}
            ]
        })

    monkeypatch.setattr(enrich, "generate_summary", fake_generate)

    result = enrich.enrich_batch(batch)

    assert result == {
        101: "Air quality is good.",
        102: "Air quality is poor."
    }


def test_enrich_batch_invalid_summary(monkeypatch):
    monkeypatch.setattr(
        enrich,
        "generate_summary",
        lambda prompt: json.dumps({
            "results": [
                {"id": 101, "llm_response": "Invalid summary"}
            ]
        })
    )

    result = enrich.enrich_batch([
        {"id": 101, "aqi": 2, "co": 100}
    ])

    assert result == {101: None}


def test_enrich_batch_retries(monkeypatch):
    calls = []

    def fake_generate(prompt):
        calls.append(prompt)

        if len(calls) == 1:
            return "Invalid JSON"

        return json.dumps({
            "results": [
                {"id": 101, "llm_response": "Air quality is good."}
            ]
        })

    monkeypatch.setattr(enrich, "generate_summary", fake_generate)

    result = enrich.enrich_batch([
        {"id": 101, "aqi": 1, "co": 100}
    ])

    assert len(calls) == 2
    assert result == {101: "Air quality is good."}


def test_enrich_batch_rejects_unknown_id(monkeypatch):
    monkeypatch.setattr(
        enrich,
        "generate_summary",
        lambda prompt: json.dumps({
            "results": [
                {"id": 999, "llm_response": "Air quality is good."}
            ]
        })
    )

    result = enrich.enrich_batch([
        {"id": 101, "aqi": 1, "co": 100}
    ])

    assert result == {}


def test_enrich_batch_rejects_duplicate_ids(monkeypatch):
    monkeypatch.setattr(
        enrich,
        "generate_summary",
        lambda prompt: json.dumps({
            "results": [
                {"id": 101, "llm_response": "Air quality is good."},
                {"id": 101, "llm_response": "Air quality is poor."}
            ]
        })
    )

    result = enrich.enrich_batch([
        {"id": 101, "aqi": 1, "co": 100}
    ])

    assert result == {}


# -------------------------------
# Supabase batch updates
# -------------------------------

@pytest.fixture
def supabase():
    return MagicMock()


def test_update_batch(supabase):
    responses = [
        {"id": 101, "llm_response": "Air quality is good."},
        {"id": 102, "llm_response": "Air quality is poor."}
    ]

    enrich.update_batch(supabase, responses)

    supabase.table.assert_called_once_with("gold_air_data")

    supabase.table.return_value.upsert.assert_called_once_with(
        responses,
        on_conflict="id"
    )

    supabase.table.return_value.upsert.return_value.execute.assert_called_once()


def test_update_batch_24_records(supabase):
    responses = [
        {"id": i, "llm_response": "Air quality is good."}
        for i in range(24)
    ]

    enrich.update_batch(supabase, responses)

    assert len(
        supabase.table.return_value.upsert.call_args.args[0]
    ) == 24


def test_update_batch_rejects_25_records(supabase):
    responses = [
        {"id": i, "llm_response": "Air quality is good."}
        for i in range(25)
    ]

    with pytest.raises(ValueError, match="Maximum 24"):
        enrich.update_batch(supabase, responses)

    supabase.table.assert_not_called()


def test_update_batch_duplicate_ids(supabase):
    responses = [
        {"id": 101, "llm_response": "Good."},
        {"id": 101, "llm_response": "Poor."}
    ]

    with pytest.raises(ValueError, match="Duplicate"):
        enrich.update_batch(supabase, responses)

    supabase.table.assert_not_called()


def test_update_batch_null_response(supabase):
    responses = [
        {"id": 101, "llm_response": None}
    ]

    enrich.update_batch(supabase, responses)

    assert (
        supabase.table.return_value.upsert.call_args.args[0][0]
        ["llm_response"]
        is None
    )


def test_update_batch_empty(supabase):
    enrich.update_batch(supabase, [])

    supabase.table.assert_not_called()


# -------------------------------
# Full enrichment pipeline
# -------------------------------

def test_run_enrichment(monkeypatch):
    monkeypatch.setenv("MODEL_NAME", "test-gemma")

    supabase = MagicMock()

    rows = [
        {"id": 101, "aqi": 1, "co": 100, "pm2_5": None},
        {"id": 102, "aqi": 3, "co": None, "pm2_5": 15},
        {"id": 103, "aqi": 6, "co": 100, "pm2_5": 20}
    ]

    query = MagicMock()
    query.select.return_value = query
    query.is_.return_value = query
    query.order.return_value = query
    query.limit.return_value = query
    query.gt.return_value = query
    query.execute.side_effect = [
        MagicMock(data=rows),
        MagicMock(data=[])
    ]

    supabase.table.return_value = query

    monkeypatch.setattr(
        enrich,
        "enrich_batch",
        lambda batch: {
            101: "Air quality is good.",
            102: "Air quality is moderate."
        }
    )

    update_calls = []

    monkeypatch.setattr(
        enrich,
        "update_batch",
        lambda client, responses: update_calls.append(responses)
    )

    results, metadata = enrich.run_enrichment(supabase)

    assert results == {"success": 2}

    assert metadata == {
        "llm_model": "test-gemma",
        "prompt_version": "v1"
    }

    assert len(update_calls) == 1

    assert update_calls[0] == [
        {"id": 101, "llm_response": "Air quality is good."},
        {"id": 102, "llm_response": "Air quality is moderate."},
        {"id": 103, "llm_response": None}
    ]


def test_run_enrichment_pagination(monkeypatch):
    monkeypatch.setenv("MODEL_NAME", "test-gemma")

    supabase = MagicMock()
    query = MagicMock()

    query.select.return_value = query
    query.is_.return_value = query
    query.order.return_value = query
    query.limit.return_value = query
    query.gt.return_value = query

    # 1,005 records across two pages.
    first_page = [
        {"id": i, "aqi": 1, "co": 100}
        for i in range(1, 1001)
    ]

    second_page = [
        {"id": i, "aqi": 1, "co": 100}
        for i in range(1001, 1006)
    ]

    query.execute.side_effect = [
        MagicMock(data=first_page),
        MagicMock(data=second_page),
        MagicMock(data=[])
    ]

    supabase.table.return_value = query

    monkeypatch.setattr(
        enrich,
        "enrich_batch",
        lambda batch: {
            row["id"]: "Air quality is good."
            for row in batch
        }
    )

    batches = []

    monkeypatch.setattr(
        enrich,
        "update_batch",
        lambda client, responses: batches.append(responses)
    )

    results, _ = enrich.run_enrichment(supabase)

    assert results["success"] == 1005
    assert sum(len(batch) for batch in batches) == 1005
    assert all(len(batch) <= 24 for batch in batches)

    query.limit.assert_any_call(1000)
    query.gt.assert_any_call("id", 1000)