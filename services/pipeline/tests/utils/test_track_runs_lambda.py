from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

import pipeline.utils.track_runs_lambda as logger_module
from pipeline.utils.track_runs_lambda import (
    RUN_TYPE_PIPELINE,
    RUN_TYPE_STEP,
    _extract_record_count,
    get_supabase_client,
    track,
    track_run,
)

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def reset_supabase_singleton():
    """Resets the global client before and after each test."""
    logger_module._supabase_client = None
    yield
    logger_module._supabase_client = None


@patch("pipeline.utils.track_runs_lambda.load_dotenv")
def test_get_supabase_client_missing_env(mock_load_dotenv, monkeypatch):
    """Test that missing environment variables return None gracefully instead of crashing."""
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_KEY", raising=False)

    client = get_supabase_client()
    assert client is None


@patch("pipeline.utils.track_runs_lambda.create_client")
def test_get_supabase_client_success(mock_create_client, monkeypatch):
    """Test that the client initializes correctly when credentials are provided."""
    monkeypatch.setenv("SUPABASE_URL", "https://mock-url.supabase.co")
    monkeypatch.setenv("SUPABASE_KEY", "mock-key")

    mock_instance = MagicMock()
    mock_create_client.return_value = mock_instance

    client = get_supabase_client()

    assert client == mock_instance
    mock_create_client.assert_called_once_with("https://mock-url.supabase.co", "mock-key")


@patch("pipeline.utils.track_runs_lambda.time.perf_counter", side_effect=[100.0, 112.5])
@patch("pipeline.utils.track_runs_lambda.datetime")
@patch("pipeline.utils.track_runs_lambda.get_supabase_client")
def test_track_run_success_executes_upsert(mock_get_client, mock_datetime, mock_perf_counter):
    """Test that a successful track_run block upserts pipeline metadata with the provided run_id."""
    mock_client = MagicMock()
    mock_get_client.return_value = mock_client
    mock_datetime.now.return_value = datetime(2026, 11, 2, 10, 0, 0, tzinfo=timezone.utc)

    with track_run("city_air_tracker_pipeline", run_id="12345-abcde") as run:
        run.set_result(42)

    mock_client.table.assert_called_once_with("pipeline_runs")
    mock_client.table().upsert.assert_called_once_with(
        {
            "id": "12345-abcde",
            "process": "city_air_tracker_pipeline",
            "run_type": RUN_TYPE_PIPELINE,
            "status": "SUCCESS",
            "runs_time": 12.5,
            "created_at": "2026-11-02T10:00:00+00:00",
            "records_added": 42,
            "message": "",
        },
        on_conflict="id",
    )
    mock_client.table().upsert().execute.assert_called_once()


@patch("pipeline.utils.track_runs_lambda.time.perf_counter", side_effect=[200.0, 205.0])
@patch("pipeline.utils.track_runs_lambda.datetime")
@patch("pipeline.utils.track_runs_lambda.get_supabase_client")
def test_track_run_failure_executes_upsert_and_reraises(
    mock_get_client, mock_datetime, mock_perf_counter
):
    """Test that a failed track_run block logs FAILED with 0 records and re-raises for Lambda."""
    mock_client = MagicMock()
    mock_get_client.return_value = mock_client
    mock_datetime.now.return_value = datetime(2026, 11, 2, 10, 0, 0, tzinfo=timezone.utc)

    with pytest.raises(TimeoutError, match="Pipeline extraction failed due to API timeout"):
        with track_run("city_air_tracker_pipeline", run_id="12345-abcde"):
            raise TimeoutError("Pipeline extraction failed due to API timeout")

    mock_client.table().upsert.assert_called_once_with(
        {
            "id": "12345-abcde",
            "process": "city_air_tracker_pipeline",
            "run_type": RUN_TYPE_PIPELINE,
            "status": "FAILED",
            "runs_time": 5.0,
            "created_at": "2026-11-02T10:00:00+00:00",
            "records_added": 0,
            "message": "TimeoutError: Pipeline extraction failed due to API timeout",
        },
        on_conflict="id",
    )
    mock_client.table().upsert().execute.assert_called_once()


@patch("pipeline.utils.track_runs_lambda.uuid.uuid4", return_value="67890-fghij")
@patch("pipeline.utils.track_runs_lambda.time.perf_counter", side_effect=[10.0, 18.3])
@patch("pipeline.utils.track_runs_lambda.datetime")
@patch("pipeline.utils.track_runs_lambda.get_supabase_client")
def test_track_decorator_success_executes_upsert(
    mock_get_client, mock_datetime, mock_perf_counter, mock_uuid
):
    """Test that a @track-decorated function returns its value and logs a step run."""
    mock_client = MagicMock()
    mock_get_client.return_value = mock_client
    mock_datetime.now.return_value = datetime(2026, 11, 2, 10, 5, 0, tzinfo=timezone.utc)

    @track
    def extract_city_air_data():
        return 15

    result = extract_city_air_data()

    assert result == 15
    mock_client.table.assert_called_once_with("pipeline_runs")
    mock_client.table().upsert.assert_called_once_with(
        {
            "id": "67890-fghij",
            "process": "extract_city_air_data",
            "run_type": RUN_TYPE_STEP,
            "status": "SUCCESS",
            "runs_time": 8.3,
            "created_at": "2026-11-02T10:05:00+00:00",
            "records_added": 15,
            "message": "",
        },
        on_conflict="id",
    )
    mock_client.table().upsert().execute.assert_called_once()


@patch("pipeline.utils.track_runs_lambda.uuid.uuid4", return_value="67890-fghij")
@patch("pipeline.utils.track_runs_lambda.time.perf_counter", side_effect=[10.0, 12.1])
@patch("pipeline.utils.track_runs_lambda.datetime")
@patch("pipeline.utils.track_runs_lambda.get_supabase_client")
def test_track_decorator_failure_executes_upsert_and_reraises(
    mock_get_client, mock_datetime, mock_perf_counter, mock_uuid
):
    """Test that a failing @track-decorated function logs FAILED and propagates the exception."""
    mock_client = MagicMock()
    mock_get_client.return_value = mock_client
    mock_datetime.now.return_value = datetime(2026, 11, 2, 10, 5, 0, tzinfo=timezone.utc)

    @track("extract_city_air_data")
    def load_step():
        raise RuntimeError("Task failed during database insertion")

    with pytest.raises(RuntimeError, match="Task failed during database insertion"):
        load_step()

    mock_client.table().upsert.assert_called_once_with(
        {
            "id": "67890-fghij",
            "process": "extract_city_air_data",
            "run_type": RUN_TYPE_STEP,
            "status": "FAILED",
            "runs_time": 2.1,
            "created_at": "2026-11-02T10:05:00+00:00",
            "records_added": 0,
            "message": "RuntimeError: Task failed during database insertion",
        },
        on_conflict="id",
    )
    mock_client.table().upsert().execute.assert_called_once()


@patch("pipeline.utils.track_runs_lambda.uuid.uuid4", return_value="llm-99999")
@patch("pipeline.utils.track_runs_lambda.time.perf_counter", side_effect=[0.0, 4.25])
@patch("pipeline.utils.track_runs_lambda.datetime")
@patch("pipeline.utils.track_runs_lambda.get_supabase_client")
def test_track_decorator_logs_llm_enrichment_metadata(
    mock_get_client, mock_datetime, mock_perf_counter, mock_uuid
):
    """Test that enrichment dicts populate llm_model, prompt_version, and success count."""
    mock_client = MagicMock()
    mock_get_client.return_value = mock_client
    mock_datetime.now.return_value = datetime(2026, 11, 2, 10, 15, 0, tzinfo=timezone.utc)

    @track("LLM Enrichment")
    def enrich():
        return {"llm_model": "google/gemma-3-27b-it:free", "prompt_version": "v2", "success": 7}

    enrich()

    mock_client.table().upsert.assert_called_once_with(
        {
            "id": "llm-99999",
            "process": "LLM Enrichment",
            "run_type": RUN_TYPE_STEP,
            "status": "SUCCESS",
            "runs_time": 4.25,
            "created_at": "2026-11-02T10:15:00+00:00",
            "records_added": 7,
            "message": "",
            "llm_model": "google/gemma-3-27b-it:free",
            "prompt_version": "v2",
        },
        on_conflict="id",
    )


@patch("pipeline.utils.track_runs_lambda.get_supabase_client", return_value=None)
def test_track_decorator_runs_normally_when_supabase_disabled(mock_get_client):
    """Test that functions still return results when Supabase credentials are absent."""

    @track
    def local_step():
        return (5, ["a", "b"])

    assert local_step() == (5, ["a", "b"])


@pytest.mark.parametrize(
    ("result_val", "expected_count"),
    [
        (None, 0),
        (12, 12),
        (True, 0),
        ((8, "df_placeholder"), 8),
        ((False, "df_placeholder"), 0),
        ([1, 2, 3], 3),
        ({"llm_model": "model-x", "success": 4}, 4),
        ({"key": "val"}, 1),
        ({}, 0),
        ("raw string", 0),
        (MagicMock(shape=(11, 6)), 11),
    ],
)
def test_extract_record_count(result_val, expected_count):
    """Verify record count extraction across all pipeline return signatures."""
    assert _extract_record_count(result_val) == expected_count

@patch("pipeline.utils.track_runs_lambda.uuid.uuid4", return_value="llm-partial-1")
@patch("pipeline.utils.track_runs_lambda.time.perf_counter", side_effect=[0.0, 14.2])
@patch("pipeline.utils.track_runs_lambda.datetime")
@patch("pipeline.utils.track_runs_lambda.get_supabase_client")
def test_track_decorator_failure_records_partial_progress(
    mock_get_client, mock_datetime, mock_perf_counter, mock_uuid
):
    """Test that a failing step logs partial_result records and LLM metadata before re-raising."""
    mock_client = MagicMock()
    mock_get_client.return_value = mock_client
    mock_datetime.now.return_value = datetime(2026, 11, 2, 10, 15, 0, tzinfo=timezone.utc)

    @track("LLM Enrichment")
    def enrich_partial_fail():
        err = RuntimeError("OpenRouter failed on batch 21")
        err.partial_result = {
            "success": 480,
            "llm_model": "google/gemma-3-27b-it:free",
            "prompt_version": "v2",
        }
        raise err

    with pytest.raises(RuntimeError, match="OpenRouter failed on batch 21"):
        enrich_partial_fail()

    mock_client.table().upsert.assert_called_once_with(
        {
            "id": "llm-partial-1",
            "run_type": RUN_TYPE_STEP,
            "process": "LLM Enrichment",
            "status": "FAILED",
            "runs_time": 14.2,
            "created_at": "2026-11-02T10:15:00+00:00",
            "records_added": 480,
            "message": "RuntimeError: OpenRouter failed on batch 21",
            "llm_model": "google/gemma-3-27b-it:free",
            "prompt_version": "v2",
        },
        on_conflict="id",
    )