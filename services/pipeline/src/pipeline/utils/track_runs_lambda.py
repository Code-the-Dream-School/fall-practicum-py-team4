import functools
import logging
import os
import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Callable, Optional, Union

from dotenv import load_dotenv
from supabase import Client, create_client

LOG = logging.getLogger(__name__)

RUN_TYPE_PIPELINE = "PIPELINE" # instead of FLOW
RUN_TYPE_STEP = "STEP" # instead of TASK

_supabase_client: Optional[Client] = None


def get_supabase_client() -> Optional[Client]:
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


def _extract_record_count(result_val: Any) -> int:
    """
    Safely extracts a record count based on the return signatures
    of pipeline functions (tuples with counts, integers, lists, dicts, etc.).
    """
    if result_val is None:
        return 0
    
    # If the task returns an integer directly (load tasks)
    if isinstance(result_val, int) and not isinstance(result_val, bool):
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


def _extract_failure_records(error: Optional[BaseException]) -> int:
    """Extracts partial record counts attached to an exception before it was raised."""
    if error is None:
        return 0

    partial = getattr(error, "partial_result", None)
    if partial is not None:
        return _extract_record_count(partial)

    records = getattr(error, "records_added", 0)
    return records if isinstance(records, int) and not isinstance(records, bool) else 0


def _log_run_result(
    *,
    run_id: str,
    process_name: str,
    run_type: str,
    is_success: bool,
    start_time: datetime,
    run_time_seconds: float,
    result_val: Any = None,
    error: Optional[BaseException] = None,
) -> None:
    """Logs a pipeline or step execution to Supabase."""
    client = get_supabase_client()
    if client is None:
        return

    records_count = (
        _extract_record_count(result_val)
        if is_success
        else _extract_failure_records(error)
    )

    error_msg = ""
    if not is_success:
        if error is not None:
            error_msg = f"{type(error).__name__}: {error}" if str(error) else type(error).__name__
        else:
            error_msg = str(result_val) if result_val else "Unknown failure"

    payload = {
        "id": str(run_id),
        "run_type": run_type,
        "process": process_name,
        "status": "SUCCESS" if is_success else "FAILED",
        "runs_time": round(max(0.0, run_time_seconds), 2),
        "created_at": start_time.isoformat(),
        "records_added": records_count,
        "message": error_msg,
    }

    meta_source = result_val if is_success else getattr(error, "partial_result", None)

    if isinstance(meta_source, dict):
        if "llm_model" in meta_source:
            payload["llm_model"] = meta_source["llm_model"]
        if "prompt_version" in meta_source:
            payload["prompt_version"] = meta_source["prompt_version"]
    elif process_name in ("LLM Enrichment", "City Air Tracker LLM Enrichment"):
        try:
            from pipeline.llm_enrich.enrich import PROMPT_VERSION
            payload["prompt_version"] = PROMPT_VERSION
        except ImportError as e:
            LOG.warning("Could not import PROMPT_VERSION for %s: %s", process_name, e)
        payload["llm_model"] = getattr(error, "llm_model", None) or os.getenv("OPENROUTER_MODEL")

    try:
        client.table("pipeline_runs").upsert(payload, on_conflict="id").execute()
    except Exception as e:
        LOG.error("Failed to log run result to Supabase: %s", e)


def track(
    func: Optional[Union[Callable, str]] = None,
    *,
    name: Optional[str] = None,
    run_type: str = RUN_TYPE_STEP,
) -> Callable:
    """
    Decorator to log execution metadata for any plain Python function to Supabase.
    Supports @track, @track("Step Name"), or @track(name="Step Name", run_type=...).
    """
    if isinstance(func, str):
        name = func
        func = None

    def decorator(target_func: Callable) -> Callable:
        process_name = name or target_func.__name__

        @functools.wraps(target_func)
        def wrapper(*args, **kwargs):
            run_id = str(uuid.uuid4())
            start_time = datetime.now(timezone.utc)
            start_perf = time.perf_counter()

            try:
                result = target_func(*args, **kwargs)
            except Exception as exc:
                _log_run_result(
                    run_id=run_id,
                    process_name=process_name,
                    run_type=run_type,
                    is_success=False,
                    start_time=start_time,
                    run_time_seconds=time.perf_counter() - start_perf,
                    error=exc,
                )
                raise

            _log_run_result(
                run_id=run_id,
                process_name=process_name,
                run_type=run_type,
                is_success=True,
                start_time=start_time,
                run_time_seconds=time.perf_counter() - start_perf,
                result_val=result,
            )
            return result

        return wrapper

    return decorator(func) if func is not None else decorator


class RunTracker:
    """Captures the return value of a `with track_run(...)` block for record counting."""

    def __init__(self, run_id: str):
        self.run_id = run_id
        self.result: Any = None

    def set_result(self, value: Any) -> Any:
        self.result = value
        return value


@contextmanager
def track_run(
    process_name: str,
    run_type: str = RUN_TYPE_PIPELINE,
    run_id: Optional[str] = None,
):
    """
    Context manager for tracking an overall Lambda invocation.
    Pass `run_id=context.aws_request_id` to match the row ID to CloudWatch logs.
    """
    resolved_run_id = run_id or str(uuid.uuid4())
    tracker = RunTracker(resolved_run_id)
    start_time = datetime.now(timezone.utc)
    start_perf = time.perf_counter()

    try:
        yield tracker
    except Exception as exc:
        _log_run_result(
            run_id=resolved_run_id,
            process_name=process_name,
            run_type=run_type,
            is_success=False,
            start_time=start_time,
            run_time_seconds=time.perf_counter() - start_perf,
            error=exc,
        )
        raise
    else:
        _log_run_result(
            run_id=resolved_run_id,
            process_name=process_name,
            run_type=run_type,
            is_success=True,
            start_time=start_time,
            run_time_seconds=time.perf_counter() - start_perf,
            result_val=tracker.result,
        )