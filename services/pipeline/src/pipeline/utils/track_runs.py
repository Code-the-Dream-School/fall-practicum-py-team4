import os
import sys
import logging
from datetime import datetime, timezone
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


def _extract_record_count(result_val) -> int:
    """
    Safely extracts a record count based on the specific return signatures 
    of your tasks (tuples with counts, integers, lists, dicts, etc.).
    """
    if result_val is None:
        return 0
    
    # If the task returns an integer directly (load tasks)
    if isinstance(result_val, int):
        return result_val
        
    # If the task returns a tuple, the first element being the count (transform_city, transform_air, calculate_rolling_averages)
    if isinstance(result_val, tuple) and len(result_val) > 0:
        if isinstance(result_val[0], bool):
            return 0
        if isinstance(result_val[0], int):
            return result_val[0]
        
    # If the task returns a list
    if isinstance(result_val, list):
        return len(result_val)

    # If the task/flow returns an enrichment result dict
    if (
        isinstance(result_val, dict)
        and "llm_model" in result_val
        and isinstance(result_val.get("success"), int)
        and not isinstance(result_val.get("success"), bool)
    ):
        return result_val["success"]
        
    # If the task returns a single dictionary
    if isinstance(result_val, dict):
        return 1 if result_val else 0
        
    # Pandas DataFrames or objects with a .shape attribute
    if hasattr(result_val, "shape"):
        shape = result_val.shape
        return shape[0] if shape else 0
        
    # Generic fallback for other sized collections
    if hasattr(result_val, "__len__") and not isinstance(result_val, (str, bytes)):
        return len(result_val)
        
    return 0

def _extract_failure_records(error: str | None) -> int:
    """Extracts partial record counts attached to an exception before it was raised."""
    if error is None:
        return 0

    partial = getattr(error, "partial_result", None)
    if partial is not None:
        return _extract_record_count(partial)

    records = getattr(error, "records_added", 0)
    return records if isinstance(records, int) and not isinstance(records, bool) else 0


def _log_run_result(run_obj, state: State, is_success: bool = True, static_name: str = None, run_type: str = None):
    """
    Unified internal handler to log either flow or task runs to Supabase.
    """
    client = get_supabase_client()
    if client is None:
        return  # Skip logging if no client is available (e.g., during CI tests)

    try:
        result_val = state.result(raise_on_failure=False) if not is_success else state.result()
    except Exception as e:
        LOG.warning("Could not retrieve state result for run %s: %s", getattr(run_obj, "id", "unknown"), e)
        result_val = None

    failed_exc = None
    if not is_success:
        if isinstance(result_val, BaseException):
            failed_exc = result_val
        else:
            _, active_exc, _ = sys.exc_info()
            if isinstance(active_exc, BaseException):
                failed_exc = active_exc

    records_count = (
        _extract_record_count(result_val)
        if is_success
        else _extract_failure_records(failed_exc)
    )

    error_msg = ""
    if not is_success:
        error_msg = state.message
        if not error_msg:
            error_msg = str(result_val) if result_val else "Unknown failure"

    total_run_time = getattr(run_obj, "total_run_time", None)
    if total_run_time and total_run_time.total_seconds() > 0:
        run_time_seconds = round(total_run_time.total_seconds(), 2)
    elif getattr(run_obj, "start_time", None):
        end_time = getattr(state, "timestamp", None) or datetime.now(timezone.utc)
        run_time_seconds = round(max(0.0, (end_time - run_obj.start_time).total_seconds()), 2)
    else:
        run_time_seconds = 0.0

    start_time_iso = (
        run_obj.start_time.isoformat() 
        if getattr(run_obj, "start_time", None) 
        else None
    )

    process_name = static_name if static_name else getattr(run_obj, "name", "unknown")

    payload = {
        "id": str(run_obj.id),
        "run_type": run_type,
        "process": process_name,
        "status": "SUCCESS" if is_success else "FAILED",
        "runs_time": run_time_seconds,
        "created_at": start_time_iso,
        "records_added": records_count,
        "message": error_msg,
    }

    meta_source = result_val if is_success else getattr(failed_exc, "partial_result", None)

    if isinstance(meta_source, dict):
        if "llm_model" in meta_source:
            payload["llm_model"] = meta_source["llm_model"]
        if "prompt_version" in meta_source:
            payload["prompt_version"] = meta_source["prompt_version"]
    elif process_name in ("LLM Enrichment", "City Air Tracker LLM Enrichment"):
        from pipeline.llm_enrich.enrich import PROMPT_VERSION
        payload["llm_model"] = getattr(failed_exc, "llm_model", None) or os.getenv("OPENROUTER_MODEL")
        payload["prompt_version"] = PROMPT_VERSION

    try:
        client.table("pipeline_runs").upsert(payload, on_conflict="id").execute()
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
    _log_run_result(flow_run, state, is_success=True, static_name=getattr(flow, "name", None), run_type="FLOW")



def log_flow_failure(flow, flow_run, state: State):
    """
    Prefect failure hook that logs a failed flow run to Supabase.
    Records a FAILED status, run duration, and sets records_added to 0 
    in the pipeline_runs table.
    """
    _log_run_result(flow_run, state, is_success=False, static_name=getattr(flow, "name", None), run_type="FLOW")


# ==========================================
# TASK TRACKING FUNCTIONS
# ==========================================


def log_task_success(task, task_run, state: State):
    """
    Prefect completion hook that logs a successful task run to Supabase.
    Extracts the processed record count from the state result and upserts 
    metadata (duration, status, timestamp) into the pipeline_runs table.
    """
    _log_run_result(task_run, state, is_success=True, static_name=getattr(task, "name", None), run_type="TASK")


def log_task_failure(task, task_run, state: State):
    """
    Prefect failure hook that logs a failed task run to Supabase.
    Records a FAILED status, run duration, and sets records_added to 0 
    in the pipeline_runs table.
    """
    _log_run_result(task_run, state, is_success=False, static_name=getattr(task, "name", None), run_type="TASK")
