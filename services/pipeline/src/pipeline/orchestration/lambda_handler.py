import json
import logging
import math
import os
from collections.abc import Mapping
from datetime import datetime, timedelta, timezone
from typing import Any

import boto3
from supabase import create_client

from pipeline.extract.extract import extract
from pipeline.extract.geocoding import geocodes
from pipeline.extract.geocoding_cache import get_city_from_cache
from pipeline.load.load_gold import load_gold_air_data, load_gold_cities
from pipeline.load.load_raw import load_raw_air_pollution, load_raw_cities
from pipeline.transform.rolling_average import (
    add_rolling_average,
    fetch_historical_readings,
    get_timestamp,
)
from pipeline.transform.transform_to_gold import transform_air_data, transform_city_data

logger = logging.getLogger(__name__)


def _read_ssm_parameter(ssm_client: Any, environment_variable: str) -> str:
    parameter_name = os.getenv(environment_variable)
    if not parameter_name:
        raise ValueError(f"Missing required environment variable {environment_variable}.")

    response = ssm_client.get_parameter(Name=parameter_name, WithDecryption=True)
    value = response.get("Parameter", {}).get("Value")
    if not value:
        raise ValueError(f"SSM parameter configured by {environment_variable} is empty.")
    return value


def _parse_coordinate(value: Any, name: str, minimum: float, maximum: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"Event '{name}' must be a finite number between {minimum} and {maximum}.")
    try:
        coordinate = float(value)
    except OverflowError as error:
        raise ValueError(
            f"Event '{name}' must be a finite number between {minimum} and {maximum}."
        ) from error
    if not math.isfinite(coordinate) or not minimum <= coordinate <= maximum:
        raise ValueError(f"Event '{name}' must be a finite number between {minimum} and {maximum}.")
    return coordinate


def _parse_event(event: dict[str, Any]) -> tuple[str, str]:
    if not isinstance(event, dict):
        raise ValueError("Lambda event must be a JSON object.")

    details = event.get("detail", event)
    if not isinstance(details, dict):
        raise ValueError("Event detail must be a JSON object.")

    city = details.get("city")
    target_date = details.get("date")

    if not isinstance(city, str) or not city.strip():
        raise ValueError("Event must include a non-empty 'city'.")

    if target_date is None:
        target_date = (datetime.now(timezone.utc).date() - timedelta(days=1)).isoformat()
    if not isinstance(target_date, str):
        raise ValueError("Event 'date' must use YYYY-MM-DD format.")
    try:
        parsed_date = datetime.strptime(target_date, "%Y-%m-%d").date()
    except ValueError as error:
        raise ValueError("Event 'date' must use YYYY-MM-DD format.") from error
    if parsed_date.isoformat() != target_date:
        raise ValueError("Event 'date' must use YYYY-MM-DD format.")

    return city.strip(), target_date


def lambda_handler(event: dict[str, Any], _context: Any) -> dict[str, Any]:
    """Ingest one city's daily air-pollution batch through the gold layer."""
    city, target_date = _parse_event(event)
    counts = {
        "extract_geocoding": 0,
        "load_raw_cities": 0,
        "transform_cities": 0,
        "load_gold_cities": 0,
        "extract_air_pollution": 0,
        "load_raw_air_pollution": 0,
        "transform_air_records": 0,
        "transform_rolling_records": 0,
        "load_gold_air_records": 0,
    }
    stage = "configuration"

    try:
        ssm_client = boto3.client("ssm")
        os.environ["OPENWEATHER_API_KEY"] = _read_ssm_parameter(
            ssm_client, "OPENWEATHER_API_KEY_SSM_PARAMETER"
        )
        supabase_url = _read_ssm_parameter(ssm_client, "SUPABASE_URL_SSM_PARAMETER")
        supabase_key = _read_ssm_parameter(ssm_client, "SUPABASE_KEY_SSM_PARAMETER")
        supabase_client = create_client(supabase_url, supabase_key)

        stage = "check_geocoding_cache"
        city_data = get_city_from_cache(city, supabase_client)
        if not city_data:
            stage = "extract_geocoding"
            city_data = geocodes(city)
            counts["extract_geocoding"] = 1

            stage = "load_raw_cities"
            counts["load_raw_cities"] = load_raw_cities(supabase_client, city_data)

            stage = "transform_city"
            gold_city = transform_city_data(city_data)
            counts["transform_cities"] = 1

            stage = "load_gold_cities"
            counts["load_gold_cities"] = load_gold_cities(supabase_client, gold_city)
            city = gold_city["city"]

            stage = "check_geocoding_cache"
            city_data = get_city_from_cache(city, supabase_client)
            if not city_data:
                raise RuntimeError(f"Geocoding cache still empty for '{city}' after gold load.")

        city = city_data["city"]
        city_id = city_data["city_id"]
        latitude = _parse_coordinate(city_data.get("latitude"), "latitude", -90, 90)
        longitude = _parse_coordinate(city_data.get("longitude"), "longitude", -180, 180)
        if isinstance(city_id, bool) or not isinstance(city_id, int) or city_id < 1:
            raise ValueError(f"Geocoding cache returned an invalid city_id for '{city}'.")

        stage = "extract_air_pollution"
        raw_data = extract(city, latitude, longitude, target_date)
        counts["extract_air_pollution"] = 1

        stage = "load_raw_air_pollution"
        counts["load_raw_air_pollution"] = load_raw_air_pollution(supabase_client, raw_data)

        stage = "transform_air_pollution"
        current_batch: list[Mapping[str, Any]] = [
            reading for reading in transform_air_data(raw_data, city_id)
        ]
        counts["transform_air_records"] = len(current_batch)

        rolling_data: list[dict[str, Any]] = []
        if current_batch:
            stage = "fetch_historical_air_data"
            full_dataset: list[Mapping[str, Any]] = [
                reading
                for reading in fetch_historical_readings(
                    supabase_client=supabase_client,
                    city_id=city_id,
                    current_readings=current_batch,
                    city_name=city,
                    table_name="gold_air_data",
                )
            ]

            stage = "calculate_rolling_averages"
            enriched_dataset: list[Mapping[str, Any]] = full_dataset
            for field in ("aqi", "pm2_5"):
                enriched_dataset = [
                    reading
                    for reading in add_rolling_average(enriched_dataset, field=field)
                ]
            batch_start = min(
                get_timestamp(reading, index)
                for index, reading in enumerate(current_batch)
            )
            rolling_data = [
                dict(reading)
                for reading in enriched_dataset
                if reading["date_time"] >= batch_start
            ]
            counts["transform_rolling_records"] = len(rolling_data)

        if rolling_data:
            stage = "load_gold_air_pollution"
            counts["load_gold_air_records"] = load_gold_air_data(
                supabase_client, rolling_data
            )

        result = {
            "status": "SUCCESS",
            "city": city,
            "date": target_date,
            "counts": counts,
        }
        logger.info(json.dumps(result, sort_keys=True))
        return result
    except Exception as error:
        failure = {
            "status": "FAILED",
            "city": city,
            "date": target_date,
            "failed_stage": stage,
            "counts": counts,
            "error_type": type(error).__name__,
            "error_message": str(error),
        }
        logger.exception("%s", json.dumps(failure, sort_keys=True))
        raise
