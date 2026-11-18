from prefect import task
from typing import Any, Mapping
import time

from pipeline.utils.planner import AirPollutionPlanner
from pipeline.utils.track_runs import log_task_success, log_task_failure, get_supabase_client
from pipeline.extract.geocoding import geocodes
from pipeline.extract.geocoding_cache import get_city_from_cache
from pipeline.extract.extract import extract
from pipeline.load.load_raw import load_raw_cities, load_raw_air_pollution
from pipeline.transform.transform_to_gold import transform_city_data, transform_air_data
from pipeline.transform.rolling_average import get_timestamp, fetch_historical_readings, add_rolling_average
from pipeline.load.load_gold import load_gold_cities, load_gold_air_data

# from pipeline.orchestration.enrich import run_enrichment

# Execution Plan
@task(retries=0,
    name="Generate Execution Plan",
    on_completion=[log_task_success],
    on_failure=[log_task_failure]
)
def generate_execution_plan(cities: list[str], mode: str | None) -> list[dict]:
    """Inspects Supabase to build an execution plan of missing dates per city."""
    planner = AirPollutionPlanner(cities=cities, mode=mode)
    plan = planner.create_execution_plan()
    return plan

# Geocoding Cache
@task(
    retries=3,
    retry_delay_seconds=10,
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
    city_name: str
) -> tuple[int, list[dict[str, Any]]]:
    """Calculates 7-day rolling averages for multiple fields (e.g., AQI, PM2.5)
    in a single pass, filters output."""
    enriched_readings = full_dataset
    for field in fields:
        enriched_readings = add_rolling_average(enriched_readings, field=field)

    # Discard historical readings
    batch_start = min(get_timestamp(r, i) for i, r in enumerate(current_batch))
    rolling7d_output = [r for r in enriched_readings if r["date_time"] >= batch_start]
    
    return (len(rolling7d_output), rolling7d_output)

# Load Gold Cities
@task(
    retries=3,
    retry_delay_seconds=10,
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
    name="Load Gold Air Pollution Data",
    on_completion=[log_task_success],
    on_failure=[log_task_failure]
)
def load_gold_air_data_task(data) -> dict:
    """Loads gold air pollution data into Supabase raw_cities"""
    client = get_supabase_client()
    return load_gold_air_data(client, data)

# Enrich LLM
# @task(
#     retries=2,
#     retry_delay_seconds=10,
#     name="LLM Enrichment",
#     on_completion=[log_task_success],
#     on_failure=[log_task_failure]
# )
# def llm_enrichment_task() -> dict:
#     """Enrichs data using LLM"""
#     client = get_supabase_client()
#     return run_enrichment(client)