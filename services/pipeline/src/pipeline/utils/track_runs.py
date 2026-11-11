import os
import logging
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

# ==========================================
# FLOW TRACKING FUNCTIONS
# ==========================================

def log_flow_success(flow, flow_run, state: State):
    """
    Prefect completion hook that logs a successful flow run to Supabase.
    Extracts the processed record count from the state result and upserts 
    metadata (duration, status, timestamp) into the pipeline_runs table.
    """
    client = get_supabase_client()
    if client is None:
        return  # Skip logging if no client is available (e.g., during CI tests)

    result_val = state.result()
    records_count = result_val if isinstance(result_val, int) else 0

    try:
        client.table("pipeline_runs").upsert({
            "id": str(flow_run.id),
            "process": flow_run.name,
            "status": "SUCCESS",
            "runs_time": flow_run.total_run_time,
            "created_at": flow_run.start_time.isoformat(),
            "records_added": records_count,
            "message": ""
        }, on_conflict="id").execute()
    except Exception as e:
        LOG.error("Failed to log flow success to Supabase: %s", e)


def log_flow_failure(flow, flow_run, state: State):
    """
    Prefect failure hook that logs a failed flow run to Supabase.
    Records a FAILED status, run duration, and sets records_added to 0 
    in the pipeline_runs table.
    """
    client = get_supabase_client()
    if client is None:
        return

    error_msg = state.message

    # Fallback to checking the exception object if message is empty
    if not error_msg:
        res = state.result(raise_on_failure=False)
        error_msg = str(res) if res else "Unknown flow failure"
    
    try:
        client.table("pipeline_runs").upsert({
            "id": str(flow_run.id),
            "process": flow_run.name,
            "status": "FAILED",
            "runs_time": flow_run.total_run_time,
            "created_at": flow_run.start_time.isoformat(),
            "records_added": 0,
            "message": error_msg
        }, on_conflict="id").execute()
    except Exception as e:
        LOG.error("Failed to log flow failure to Supabase: %s", e)

# ==========================================
# TASK TRACKING FUNCTIONS
# ==========================================


def log_task_success(task, task_run, state: State):
    """
    Prefect completion hook that logs a successful task run to Supabase.
    Extracts the processed record count from the state result and upserts 
    metadata (duration, status, timestamp) into the pipeline_runs table.
    """
    client = get_supabase_client()
    if client is None:
        return  # Skip logging if no client is available (e.g., during CI tests)

    result_val = state.result()
    records_count = result_val if isinstance(result_val, int) else 0

    try:
        client.table("pipeline_runs").upsert({
            "id": str(task_run.id),
            "process": task_run.name,
            "status": "SUCCESS",
            "runs_time": task_run.total_run_time,
            "created_at": task_run.start_time.isoformat(),
            "records_added": records_count,
            "message": ""
        }, on_conflict="id").execute()
    except Exception as e:
        LOG.error("Failed to log task success to Supabase: %s", e)


def log_task_failure(task, task_run, state: State):
    """
    Prefect failure hook that logs a failed task run to Supabase.
    Records a FAILED status, run duration, and sets records_added to 0 
    in the pipeline_runs table.
    """

    client = get_supabase_client()
    if client is None:
        return

    error_msg = state.message

    # Fallback to checking the exception object if message is empty
    if not error_msg:
        res = state.result(raise_on_failure=False)
        error_msg = str(res) if res else "Unknown task failure"
    
    try:
        client.table("pipeline_runs").upsert({
            "id": str(task_run.id),
            "process": task_run.name,
            "status": "FAILED",
            "runs_time": task_run.total_run_time,
            "created_at": task_run.start_time.isoformat(),
            "records_added": 0,
            "message": error_msg
        }, on_conflict="id").execute()
    except Exception as e:
        LOG.error("Failed to log task failure to Supabase: %s", e)