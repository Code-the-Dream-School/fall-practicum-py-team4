from prefect import task
from prefect.client.schemas.objects import State, TaskRun
from typing import Any
import time, httpx, requests
from postgrest.exceptions import APIError
from pipeline.llm_enrich.openrouter_client import OpenRouterRateLimited

from pipeline.utils.planner import AirPollutionPlanner
from pipeline.utils.track_runs import log_task_success, log_task_failure, get_supabase_client
from pipeline.extract.geocoding import geocodes
from pipeline.extract.geocoding_cache import get_city_from_cache
from pipeline.extract.extract import extract
from pipeline.load.load_raw import load_raw_cities, load_raw_air_pollution
from pipeline.transform.transform_to_gold import transform_city_data, transform_air_data
from pipeline.transform.rolling_average import get_timestamp, fetch_historical_readings, add_rolling_average
from pipeline.load.load_gold import load_gold_cities, load_gold_air_data
from pipeline.llm_enrich.enrich import run_enrichment


# Retry helper function
def is_transient_error(_task, _task_run: TaskRun, state: State) -> bool:
    """Retry only on transient network errors, timeouts, 5xx responses, or rate limits."""
    exc = state.result(raise_on_failure=False)

    transient_types = (
        TimeoutError,
        ConnectionError,
        requests.exceptions.Timeout,
        requests.exceptions.ConnectionError,
        httpx.TimeoutException,
        httpx.ConnectError,
        OpenRouterRateLimited,
    )

    seen = set()
    while isinstance(exc, BaseException) and id(exc) not in seen:
        seen.add(id(exc))

        # 1. Network, timeout, and rate-limit errors
        if isinstance(exc, transient_types):
            return True

        # 2. HTTP 5xx / 429 errors (requests)
        if isinstance(exc, requests.exceptions.HTTPError):
            if exc.response is not None and (
                exc.response.status_code >= 500 or exc.response.status_code == 429
            ):
                return True

        # 3. HTTP 5xx / 429 errors (httpx)
        if isinstance(exc, httpx.HTTPStatusError):
            if exc.response.status_code >= 500 or exc.response.status_code == 429:
                return True

        # 4. HTTP 5xx / 429 errors (Supabase / PostgREST)
        if isinstance(exc, APIError):
            code = str(getattr(exc, "code", "") or "")
            if code.isdigit() and (500 <= int(code) < 600 or int(code) == 429):
                return True

        exc = exc.__cause__ or exc.__context__

    return False


@task(retries=3,
    retry_delay_seconds=10,
    retry_condition_fn=is_transient_error,
    name="Generate Execution Plan",
    on_completion=[log_task_success],
    on_failure=[log_task_failure]
)
def generate_execution_plan(cities: list[str], mode: str | None, max_dates_per_city: int | None = None) -> list[dict]:
    """Inspects Supabase to build an execution plan of missing dates per city."""
    planner = AirPollutionPlanner(cities=cities, mode=mode)
    plan = planner.create_execution_plan(max_dates_per_city=max_dates_per_city)
    return plan

# Geocoding Cache
@task(
    name="Check Cache for Geocoding Data",
    on_completion=[log_task_success],
    on_failure=[log_task_failure]
)
def check_geocoding_cache(city: str) -> dict:
    """Checks for existing geocoding data on the database"""
    client = get_supabase_client()
    data = get_city_from_cache(city, supabase_client=client)
    return data

# Geocoding
@task(
    retries=3,
    retry_delay_seconds=10,
    retry_condition_fn=is_transient_error,
    name="Extract Geocoding Data",
    on_completion=[log_task_success],
    on_failure=[log_task_failure]
)
def fetch_geocoding(city: str) -> dict:
    """Extracts Geocoding data from OpenMeteo"""
    data = geocodes(city)
    time.sleep(2)
    return data

# Get Air Pollution data
@task(
    retries=3,
    retry_delay_seconds=10,
    retry_condition_fn=is_transient_error,
    name="Extract Air Pollution Data",
    on_completion=[log_task_success],
    on_failure=[log_task_failure]
)
def fetch_air_pollution(city: str, lat: float, lon: float, date: str) -> dict:
    """Extracts Air Pollution Data from OpenWeather"""
    data = extract(city, lat, lon, date)
    time.sleep(2)
    return data

# Load Raw Cities
@task(
    retries=3,
    retry_delay_seconds=10,
    retry_condition_fn=is_transient_error,
    name="Load Raw Cities",
    on_completion=[log_task_success],
    on_failure=[log_task_failure]
)
def load_raw_cities_task(data) -> int:
    """Loads Raw City data into Supabase raw_cities"""
    client = get_supabase_client()
    inserted_count = load_raw_cities(client, data)
    return inserted_count

# Load Raw Air Pollution
@task(
    retries=3,
    retry_delay_seconds=10,
    retry_condition_fn=is_transient_error,
    name="Load Raw Air Pollution",
    on_completion=[log_task_success],
    on_failure=[log_task_failure]
)
def load_raw_air_pollution_task(data) -> int:
    """Loads Raw Air Pollution Data into Supabase raw_air_pollution"""
    client = get_supabase_client()
    inserted_count = load_raw_air_pollution(client, data)
    return inserted_count

# Transform GoldCities
@task(name="Transform into GoldCities", on_completion=[log_task_success], on_failure=[log_task_failure])
def transform_city(data) -> tuple[dict, int]:
    """Transforms raw city data, returns the gold_cities entry."""
    gold_city = transform_city_data(data)
    record_count = 1
    return record_count, gold_city

# Transform GoldAirData
@task(name="Transform into GoldAirData", on_completion=[log_task_success], on_failure=[log_task_failure])
def transform_air(data, city_id) -> tuple:
    """Transforms raw air pollution data, returns the records with metadata."""
    transformed_data = transform_air_data(data, city_id)
    return (len(transformed_data), transformed_data)

# Fetch historical
@task(
    retries=3,
    retry_delay_seconds=10,
    retry_condition_fn=is_transient_error,
    name="Fetch Historical Readings",
    on_completion=[log_task_success],
    on_failure=[log_task_failure]
)
def fetch_historical(city_id: int, current_batch: list[dict[str, Any]], city_name: str) -> list[dict[str, Any]]:
    """Fetches historical readings from the database."""
    client = get_supabase_client()
    return fetch_historical_readings(
        supabase_client=client,
        city_id=city_id,
        current_readings=current_batch,
        city_name=city_name,
        table_name="gold_air_data"
    )
            
# Add Rolling Averages
@task(retries=0, name="Calculate Rolling Averages", on_completion=[log_task_success], on_failure=[log_task_failure])
def calculate_rolling_averages(
    full_dataset: list[dict[str, Any]], 
    fields: list[str], 
    current_batch: list[dict[str, Any]],
    city_name: str,
    min_readings: int = 144
) -> tuple[int, list[dict[str, Any]]]:
    """Calculates 7-day rolling averages for multiple fields (e.g., AQI, PM2.5)
    in a single pass, filters output."""
    enriched_readings = full_dataset
    if not current_batch:
        return (0, [])
    for field in fields:
        enriched_readings = add_rolling_average(
            enriched_readings,
            field=field,
            min_readings=min_readings,
        )

    # Discard historical readings
    batch_start = min(get_timestamp(r, i) for i, r in enumerate(current_batch))
    current_ts_set = {get_timestamp(r, i) for i, r in enumerate(current_batch)}

    rolling7d_output = []
    for r in enriched_readings:
        prev = r.pop("_prev_rolling", None)
        if r["date_time"] < batch_start:
            continue

        is_current = r["date_time"] in current_ts_set
        rolling_changed = any(
            prev is None or prev.get(f"{field}_rolling_7d") != r[f"{field}_rolling_7d"]
            for field in fields
        )

        if is_current or rolling_changed:
            rolling7d_output.append({**r, "llm_response": None})

    return (len(rolling7d_output), rolling7d_output)

# Load Gold Cities
@task(
    retries=3,
    retry_delay_seconds=10,
    retry_condition_fn=is_transient_error,
    name="Load Gold Cities",
    on_completion=[log_task_success],
    on_failure=[log_task_failure]
)
def load_gold_cities_task(data) -> int:
    """Loads Raw City data into Supabase raw_cities"""
    client = get_supabase_client()
    load_gold_cities(client, data)
    return 1

# Load Gold Air Pollution Data
@task(
    retries=3,
    retry_delay_seconds=10,
    retry_condition_fn=is_transient_error,
    name="Load Gold Air Pollution Data",
    on_completion=[log_task_success],
    on_failure=[log_task_failure]
)
def load_gold_air_data_task(data) -> dict:
    """Loads gold air pollution data into Supabase raw_cities"""
    client = get_supabase_client()
    return load_gold_air_data(client, data)

# Enrich LLM
@task(
    retries=2,
    retry_delay_seconds=[15, 60],
    retry_condition_fn=is_transient_error,
    name="LLM Enrichment",
    on_completion=[log_task_success],
    on_failure=[log_task_failure]
)
def llm_enrichment_task() -> dict:
    """Enrichs data using LLM"""
    client = get_supabase_client()
    return run_enrichment(client)