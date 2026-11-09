from prefect import task
import time

from pipeline.utils.planner import AirPollutionPlanner
from pipeline.utils.track_runs import log_task_success, log_task_failure, get_supabase_client
from pipeline.extract.geocoding import geocodes
from pipeline.extract.geocoding_cache import get_city_from_cache
from pipeline.extract.extract import extract
from pipeline.load.load_raw import load_raw_cities, load_raw_air_pollution
from pipeline.transform.transform_to_gold import transform_city_data, transform_air_data

# Execution Plan
@task(retries=2,
    name="Generate Execution Plan",
    on_completion=[log_task_success],
    on_failure=[log_task_failure]
)
def generate_execution_plan(cities: list[str]) -> list[dict]:
    """Inspects Supabase to build an execution plan of missing dates per city."""
    planner = AirPollutionPlanner(cities=cities)
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
    time.sleep(2)
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
    data = extract(city_name=city, latitude=lat, longitude=lon, date=date)
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
def load_raw_cities_task(data) -> dict:
    """Loads Raw City data into Supabase raw_cities"""
    client = get_supabase_client()
    load_raw_cities(supabase_client=client, data=data)
    time.sleep(2)
    return 1

# Load Raw Air Pollution
@task(
    retries=3,
    retry_delay_seconds=10,
    name="Load Raw Air Pollution",
    on_completion=[log_task_success],
    on_failure=[log_task_failure]
)
def load_raw_air_pollution_task(data) -> dict:
    """Loads Raw Air Pollution Data into Supabase raw_air_pollution"""
    client = get_supabase_client()
    load_raw_air_pollution(supabase_client=client, data=data)
    time.sleep(2)
    return 1

# Transform GoldCities
@task(
    retries=3,
    retry_delay_seconds=10,
    name="Transform into GoldCities",
    on_completion=[log_task_success],
    on_failure=[log_task_failure]
)
def transform_city(data) -> dict:
    """Loads Raw Air Pollution Data into Supabase raw_air_pollution"""
    client = get_supabase_client()
    load_raw_air_pollution(supabase_client=client, data=data)
    time.sleep(2)
    return 1

# Transform GoldAirData
@task(
    retries=3,
    retry_delay_seconds=10,
    name="Transform into GoldAirData",
    on_completion=[log_task_success],
    on_failure=[log_task_failure]
)
def transform_air(data) -> dict:
    """Loads Raw Air Pollution Data into Supabase raw_air_pollution"""
    client = get_supabase_client()
    load_raw_air_pollution(supabase_client=client, data=data)
    time.sleep(2)
    return 1