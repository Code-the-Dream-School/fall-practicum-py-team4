
import json
import logging
from unittest.mock import MagicMock

import pytest

import src.pipeline.orchestration.llm_enrich.enrich as enrich


# -------------------------------
# Fixtures
# -------------------------------

@pytest.fixture
def supabase():
    return MagicMock()


@pytest.fixture
def configured_env(monkeypatch):
    monkeypatch.setenv("OPENROUTER_MODEL", "test-gemma")
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")


def mock_pages(supabase, pages):
    query = MagicMock()

    query.select.return_value = query
    query.is_.return_value = query
    query.order.return_value = query
    query.limit.return_value = query
    query.gt.return_value = query

    query.execute.side_effect = [
        MagicMock(data=page)
        for page in pages
    ]

    supabase.table.return_value = query
    return query


# -------------------------------
# Summary validation
# -------------------------------

def test_valid_summary():
    assert enrich.valid_summary("Air quality is good.")

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
# JSON response parsing
# -------------------------------

def test_parse_response_dict():
    response = {"results": []}

    assert enrich.parse_response(response) == response


def test_parse_response_json_string():
    response = '{"results": []}'

    assert enrich.parse_response(response) == {
        "results": []
    }


def test_parse_response_code_fence():
    response = '```json\n{"results": []}\n```'

    assert enrich.parse_response(response) == {
        "results": []
    }


def test_parse_response_invalid_json():
    with pytest.raises(json.JSONDecodeError):
        enrich.parse_response("Invalid JSON")


def test_parse_response_not_object():
    with pytest.raises(ValueError, match="Expected JSON object"):
        enrich.parse_response('["not an object"]')


# -------------------------------
# LLM batch processing
# -------------------------------

def test_enrich_batch_matches_positions(monkeypatch):
    batch = [
        {"id": 101, "aqi": 1, "co": 100},
        {"id": 102, "aqi": 4, "pm2_5": 40}
    ]

    def fake_generate(prompt):
        data = json.loads(
            prompt.split("Measurements:\n")[1]
        )

        assert [
            row["position"]
            for row in data["records"]
        ] == [0, 1]

        assert data["records"][0]["aqi"] == 1
        assert data["records"][1]["aqi"] == 4

        # Deliberately reverse response order.
        return json.dumps({
            "results": [
                {
                    "position": 1,
                    "llm_response": "Air quality is poor."
                },
                {
                    "position": 0,
                    "llm_response": "Air quality is good."
                }
            ]
        })

    monkeypatch.setattr(
        enrich, "generate_summary", fake_generate
    )

    result = enrich.enrich_batch(batch)

    assert result == [
        {
            "id": 101,
            "llm_response": "Air quality is good."
        },
        {
            "id": 102,
            "llm_response": "Air quality is poor."
        }
    ]


def test_enrich_batch_invalid_summary(monkeypatch):
    monkeypatch.setattr(
        enrich,
        "generate_summary",
        lambda prompt: json.dumps({
            "results": [
                {
                    "position": 0,
                    "llm_response": "Invalid summary"
                }
            ]
        })
    )

    with pytest.raises(
        enrich.EnrichmentBatchError,
        match="Invalid summary"
    ):
        enrich.enrich_batch([
            {"id": 101, "aqi": 2, "co": 100}
        ])


def test_enrich_batch_does_not_retry(monkeypatch):
    calls = []

    def fake_generate(prompt):
        calls.append(prompt)
        return "Invalid JSON"

    monkeypatch.setattr(
        enrich, "generate_summary", fake_generate
    )

    with pytest.raises(enrich.EnrichmentBatchError):
        enrich.enrich_batch([
            {"id": 101, "aqi": 1, "co": 100}
        ])

    assert len(calls) == 1


def test_enrich_batch_rejects_unknown_position(monkeypatch):
    monkeypatch.setattr(
        enrich,
        "generate_summary",
        lambda prompt: json.dumps({
            "results": [
                {
                    "position": 999,
                    "llm_response": "Air quality is good."
                }
            ]
        })
    )

    with pytest.raises(
        enrich.EnrichmentBatchError,
        match="Unexpected position"
    ):
        enrich.enrich_batch([
            {"id": 101, "aqi": 1, "co": 100}
        ])


def test_enrich_batch_rejects_duplicate_positions(monkeypatch):
    monkeypatch.setattr(
        enrich,
        "generate_summary",
        lambda prompt: json.dumps({
            "results": [
                {
                    "position": 0,
                    "llm_response": "Air quality is good."
                },
                {
                    "position": 0,
                    "llm_response": "Air quality is poor."
                }
            ]
        })
    )

    with pytest.raises(
        enrich.EnrichmentBatchError,
        match="Duplicate position"
    ):
        enrich.enrich_batch([
            {"id": 101, "aqi": 1, "co": 100},
            {"id": 102, "aqi": 4, "co": 200}
        ])


def test_enrich_batch_missing_results(monkeypatch):
    monkeypatch.setattr(
        enrich,
        "generate_summary",
        lambda prompt: json.dumps({})
    )

    with pytest.raises(
        enrich.EnrichmentBatchError,
        match="Missing results array"
    ):
        enrich.enrich_batch([
            {"id": 101, "aqi": 1, "co": 100}
        ])


def test_enrich_batch_wrong_result_count(monkeypatch):
    monkeypatch.setattr(
        enrich,
        "generate_summary",
        lambda prompt: json.dumps({
            "results": []
        })
    )

    with pytest.raises(
        enrich.EnrichmentBatchError,
        match="Expected 1 results"
    ):
        enrich.enrich_batch([
            {"id": 101, "aqi": 1, "co": 100}
        ])


def test_enrich_batch_rejects_empty():
    with pytest.raises(ValueError, match="Invalid batch size"):
        enrich.enrich_batch([])


def test_enrich_batch_rejects_25_records():
    batch = [
        {"id": i, "aqi": 1, "co": 100}
        for i in range(25)
    ]

    with pytest.raises(ValueError, match="Invalid batch size"):
        enrich.enrich_batch(batch)


def test_enrich_batch_propagates_api_error(monkeypatch):
    class TestRateLimitError(Exception):
        pass

    def fake_generate(prompt):
        raise TestRateLimitError("Rate limit exceeded")

    monkeypatch.setattr(
        enrich, "generate_summary", fake_generate
    )

    with pytest.raises(
        TestRateLimitError,
        match="Rate limit exceeded"
    ):
        enrich.enrich_batch([
            {"id": 101, "aqi": 1, "co": 100}
        ])


# -------------------------------
# Supabase RPC batch updates
# -------------------------------

def test_update_batch(supabase):
    responses = [
        {"id": 101, "llm_response": "Air quality is good."},
        {"id": 102, "llm_response": "Air quality is poor."}
    ]

    enrich.update_batch(supabase, responses)

    supabase.rpc.assert_called_once_with(
        "save_enrichment_batch",
        {"p_responses": responses}
    )

    supabase.rpc.return_value.execute.assert_called_once()


def test_update_batch_24_records(supabase):
    responses = [
        {"id": i, "llm_response": "Air quality is good."}
        for i in range(24)
    ]

    enrich.update_batch(supabase, responses)

    args = supabase.rpc.call_args.args

    assert len(args[1]["p_responses"]) == 24


def test_update_batch_rejects_25_records(supabase):
    responses = [
        {"id": i, "llm_response": "Air quality is good."}
        for i in range(25)
    ]

    with pytest.raises(ValueError, match="Maximum 24"):
        enrich.update_batch(supabase, responses)

    supabase.rpc.assert_not_called()


def test_update_batch_duplicate_ids(supabase):
    responses = [
        {"id": 101, "llm_response": "Good."},
        {"id": 101, "llm_response": "Poor."}
    ]

    with pytest.raises(ValueError, match="Duplicate"):
        enrich.update_batch(supabase, responses)

    supabase.rpc.assert_not_called()


def test_update_batch_invalid_response(supabase):
    responses = [
        {"id": 101, "llm_response": None}
    ]

    with pytest.raises(ValueError, match="Invalid summary"):
        enrich.update_batch(supabase, responses)

    supabase.rpc.assert_not_called()


def test_update_batch_empty(supabase):
    with pytest.raises(ValueError, match="Empty batch"):
        enrich.update_batch(supabase, [])

    supabase.rpc.assert_not_called()


def test_update_batch_database_error(supabase):
    supabase.rpc.return_value.execute.side_effect = Exception(
        "Database unavailable"
    )

    responses = [
        {"id": 101, "llm_response": "Air quality is good."}
    ]

    with pytest.raises(
        enrich.EnrichmentDatabaseError,
        match="Failed to save enrichment batch"
    ):
        enrich.update_batch(supabase, responses)


# -------------------------------
# Fetch records
# -------------------------------

def test_fetch_records(supabase):
    rows = [
        {"id": 101, "aqi": 1, "co": 100}
    ]

    query = mock_pages(supabase, [rows])

    result = enrich.fetch_records(supabase, None)

    assert result == rows

    supabase.table.assert_called_once_with("gold_air_data")
    query.limit.assert_called_once_with(1000)


def test_fetch_records_pagination(supabase):
    query = mock_pages(supabase, [[]])

    enrich.fetch_records(supabase, 1000)

    query.gt.assert_called_once_with("id", 1000)


def test_fetch_records_database_error(supabase):
    query = mock_pages(supabase, [])
    query.execute.side_effect = Exception("Connection failed")

    with pytest.raises(
        enrich.EnrichmentDatabaseError,
        match="Failed to fetch enrichment records"
    ):
        enrich.fetch_records(supabase, None)


# -------------------------------
# Full enrichment pipeline
# -------------------------------

def test_run_enrichment(
    monkeypatch, configured_env, supabase
):
    rows = [
        {"id": 101, "aqi": 1, "co": 100},
        {"id": 102, "aqi": 3, "pm2_5": 15}
    ]

    mock_pages(supabase, [rows, []])

    monkeypatch.setattr(
        enrich,
        "enrich_batch",
        lambda batch: [
            {
                "id": row["id"],
                "llm_response": "Air quality is good."
            }
            for row in batch
        ]
    )

    saved_batches = []

    monkeypatch.setattr(
        enrich,
        "update_batch",
        lambda client, responses: saved_batches.append(responses)
    )

    result = enrich.run_enrichment(supabase)

    assert result == {
        "success": 2,
        "llm_model": "test-gemma",
        "prompt_version": "v2"
    }

    assert len(saved_batches) == 1
    assert len(saved_batches[0]) == 2


def test_run_enrichment_no_records(
    configured_env, supabase
):
    mock_pages(supabase, [[]])

    result = enrich.run_enrichment(supabase)

    assert result == {
        "success": 0,
        "llm_model": "test-gemma",
        "prompt_version": "v2"
    }

    supabase.rpc.assert_not_called()


def test_run_enrichment_pagination(
    monkeypatch, configured_env, supabase
):
    first_page = [
        {"id": i, "aqi": 1, "co": 100}
        for i in range(1, 1001)
    ]

    second_page = [
        {"id": i, "aqi": 1, "co": 100}
        for i in range(1001, 1006)
    ]

    query = mock_pages(
        supabase,
        [first_page, second_page, []]
    )

    monkeypatch.setattr(
        enrich,
        "enrich_batch",
        lambda batch: [
            {
                "id": row["id"],
                "llm_response": "Air quality is good."
            }
            for row in batch
        ]
    )

    batches = []

    monkeypatch.setattr(
        enrich,
        "update_batch",
        lambda client, responses: batches.append(responses)
    )

    result = enrich.run_enrichment(supabase)

    assert result["success"] == 1005
    assert sum(len(batch) for batch in batches) == 1005
    assert all(len(batch) <= 24 for batch in batches)

    query.limit.assert_any_call(1000)
    query.gt.assert_any_call("id", 1000)



def test_run_enrichment_partial_progress(
    monkeypatch, configured_env, supabase, caplog
):
    rows = [
        {"id": i, "aqi": 1, "co": 100}
        for i in range(1, 49)
    ]

    mock_pages(supabase, [rows])

    class TestRateLimitError(Exception):
        pass

    calls = []

    def fake_enrich_batch(batch):
        calls.append(batch)

        if len(calls) == 2:
            raise TestRateLimitError("Rate limit exceeded")

        return [
            {
                "id": row["id"],
                "llm_response": "Air quality is good."
            }
            for row in batch
        ]

    monkeypatch.setattr(
        enrich, "enrich_batch", fake_enrich_batch
    )

    with caplog.at_level(logging.ERROR):
        with pytest.raises(
            TestRateLimitError,
            match="Rate limit exceeded"
        ):
            enrich.run_enrichment(supabase)

    assert len(calls) == 2
    assert supabase.rpc.call_count == 1
    assert "24 successfully saved records" in caplog.text


def test_run_enrichment_missing_model(
    monkeypatch, supabase
):
    monkeypatch.delenv("OPENROUTER_MODEL", raising=False)
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")

    with pytest.raises(
        enrich.EnrichmentConfigurationError,
        match="OPENROUTER_MODEL"
    ):
        enrich.run_enrichment(supabase)


def test_run_enrichment_missing_api_key(
    monkeypatch, supabase
):
    monkeypatch.setenv("OPENROUTER_MODEL", "test-gemma")
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)

    with pytest.raises(
        enrich.EnrichmentConfigurationError,
        match="OPENROUTER_API_KEY"
    ):
        enrich.run_enrichment(supabase)
