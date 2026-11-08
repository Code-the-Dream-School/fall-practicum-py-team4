import pytest
from unittest.mock import MagicMock, patch
from prefect.states import State

from pipeline.utils.track_runs import get_supabase_client, log_flow_success, log_flow_failure
import pipeline.utils.track_runs as logger_module


@pytest.fixture(autouse=True)
def reset_supabase_singleton():
    """Resets the global client before and after each test."""
    logger_module._supabase_client = None
    yield
    logger_module._supabase_client = None


@pytest.mark.unit
@patch("pipeline.utils.track_runs.load_dotenv")
def test_get_supabase_client_missing_env(mock_load_dotenv, monkeypatch):
    """Test that missing environment variables return None gracefully instead of crashing."""
    # Force singleton to None right before this test
    logger_module._supabase_client = None
    
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_KEY", raising=False)
    
    client = get_supabase_client()
    assert client is None


@pytest.mark.unit
@patch("pipeline.utils.track_runs.create_client")
def test_get_supabase_client_success(mock_create_client, monkeypatch):
    """Test that the client initializes correctly when credentials are provided."""
    logger_module._supabase_client = None
    
    monkeypatch.setenv("SUPABASE_URL", "https://mock-url.supabase.co")
    monkeypatch.setenv("SUPABASE_KEY", "mock-key")
    
    mock_instance = MagicMock()
    mock_create_client.return_value = mock_instance

    client = get_supabase_client()
    
    assert client == mock_instance
    mock_create_client.assert_called_once_with("https://mock-url.supabase.co", "mock-key")


@pytest.mark.unit
@patch("pipeline.utils.track_runs.get_supabase_client")
def test_log_flow_success_executes_upsert(mock_get_client):
    """Test that a successful flow run correctly triggers a Supabase upsert with record count."""
    mock_client = MagicMock()
    mock_get_client.return_value = mock_client
    
    mock_flow = MagicMock()
    
    # Ensure flow_run.name is a string (matching what the logger extracts)
    mock_flow_run = MagicMock()
    mock_flow_run.id = "12345-abcde"
    mock_flow_run.name = "city_air_tracker_pipeline"  
    mock_flow_run.total_run_time = 12.5
    mock_flow_run.start_time.isoformat.return_value = "2026-11-02T10:00:00+00:00"
    
    mock_state = MagicMock(spec=State)
    mock_state.result.return_value = 42  # 42 records processed

    log_flow_success(mock_flow, mock_flow_run, mock_state)

    mock_client.table.assert_called_once_with("pipeline_runs")
    mock_client.table().upsert.assert_called_once_with({
        "id": "12345-abcde",
        "process": "city_air_tracker_pipeline",
        "status": "SUCCESS",
        "runs_time": 12.5,
        "created_at": "2026-11-02T10:00:00+00:00",
        "records_added": 42,
        "message": ""
    }, on_conflict="id")
    mock_client.table().upsert().execute.assert_called_once()


@pytest.mark.unit
@patch("pipeline.utils.track_runs.get_supabase_client")
def test_log_flow_failure_executes_upsert(mock_get_client):
    """Test that a failed flow run triggers a Supabase upsert with 0 records added."""
    mock_client = MagicMock()
    mock_get_client.return_value = mock_client
    
    mock_flow = MagicMock()
    
    mock_flow_run = MagicMock()
    mock_flow_run.id = "12345-abcde"
    mock_flow_run.name = "city_air_tracker_pipeline"  
    mock_flow_run.total_run_time = 5.0
    mock_flow_run.start_time.isoformat.return_value = "2026-11-02T10:00:00+00:00"
    
    mock_state = MagicMock(spec=State)
    mock_state.message = "Pipeline extraction failed due to API timeout"

    log_flow_failure(mock_flow, mock_flow_run, mock_state)

    mock_client.table().upsert.assert_called_once_with({
        "id": "12345-abcde",
        "process": "city_air_tracker_pipeline",
        "status": "FAILED",
        "runs_time": 5.0,
        "created_at": "2026-11-02T10:00:00+00:00",
        "records_added": 0,
        "message": "Pipeline extraction failed due to API timeout"
    }, on_conflict="id")
    mock_client.table().upsert().execute.assert_called_once()