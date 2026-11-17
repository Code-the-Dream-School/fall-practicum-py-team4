import os
import logging
from datetime import timedelta
from prefect.states import State
from supabase import create_client, Client
from dotenv import load_dotenv

LOG = logging.getLogger(__name__)

# Keep a global reference to the client
_supabase_client: Client = None

def get_supabase_client() -> Client:
    """
    Lazily initializes and returns the Supabase client.
    Returns None if credentials are missing (e.g., in CI/test environments).
    """
    global _supabase_client
    if _supabase_client is None:
        load_dotenv()
        url = os.getenv("SUPABASE_URL")
        key = os.getenv("SUPABASE_KEY")
        
        if not url or not key:
            LOG.warning("SUPABASE_URL or SUPABASE_KEY not found. Skipping Supabase logging.")
            return None
            
        _supabase_client = create_client(url, key)
    return _supabase_client


def _log_run_result(run_obj, state: State, is_success: bool = True):
    """
    Unified internal handler to log either flow or task runs to Supabase.
    """
    client = get_supabase_client()
    if client is None:
        return  # Skip logging if no client is available (e.g., during CI tests)

    result_val = state.result(raise_on_failure=False) if not is_success else state.result()
    records_count = result_val if isinstance(result_val, int) else 0

    error_msg = ""
    if not is_success:
        error_msg = state.message
        if not error_msg:
            error_msg = str(result_val) if result_val else "Unknown failure"

    run_time_seconds = (
        run_obj.total_run_time.total_seconds() 
        if run_obj.total_run_time 
        else 0.0
    )

    try:
        client.table("pipeline_runs").upsert({
            "id": str(run_obj.id),
            "process": run_obj.name,
            "status": "SUCCESS" if is_success else "FAILED",
            "runs_time": run_time_seconds,
            "created_at": run_obj.start_time.isoformat(),
            "records_added": records_count if is_success else 0,
            "message": error_msg
        }, on_conflict="id").execute()
    except Exception as e:
        LOG.error("Failed to log run result to Supabase: %s", e)

# ==========================================
# FLOW TRACKING FUNCTIONS
# ==========================================

def log_flow_success(flow, flow_run, state: State):
    """
    Prefect completion hook that logs a successful flow run to Supabase.
    Extracts the processed record count from the state result and upserts 
    metadata (duration, status, timestamp) into the pipeline_runs table.
    """
    _log_run_result(flow_run, state, is_success=True)


def log_flow_failure(flow, flow_run, state: State):
    """
    Prefect failure hook that logs a failed flow run to Supabase.
    Records a FAILED status, run duration, and sets records_added to 0 
    in the pipeline_runs table.
    """
    _log_run_result(flow_run, state, is_success=False)

# ==========================================
# TASK TRACKING FUNCTIONS
# ==========================================


def log_task_success(task, task_run, state: State):
    """
    Prefect completion hook that logs a successful task run to Supabase.
    Extracts the processed record count from the state result and upserts 
    metadata (duration, status, timestamp) into the pipeline_runs table.
    """
    _log_run_result(task_run, state, is_success=True)


def log_task_failure(task, task_run, state: State):
    """
    Prefect failure hook that logs a failed task run to Supabase.
    Records a FAILED status, run duration, and sets records_added to 0 
    in the pipeline_runs table.
    """
    _log_run_result(task_run, state, is_success=False)