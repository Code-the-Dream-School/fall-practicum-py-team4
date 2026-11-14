import logging

from datetime import datetime, timezone
from contracts.data_contracts import GoldCities, GoldAirData
from pipeline.transform.sentiment_label import aqi_to_sentiment

log = logging.getLogger(__name__)


def convert_unix_to_datetime(unix: int) -> datetime:
    """
    Converts a unix timestamp to a UTC datetime object.
    Strip minutes, seconds, and microseconds to create the clean hourly bucket
    """

    date_time = datetime.fromtimestamp(unix, timezone.utc)
    return date_time.replace(minute=0, second=0, microsecond=0)

def transform_city_data(city_record: dict) -> dict:
    """Takes a raw city record. Enriches the record and returns a dictionary"""

    if not city_record or not isinstance(city_record, dict):
        log.error("Empty or invalid city record.")
        raise ValueError("Empty or invalid city.")

    results = city_record.get("payload", {}).get("results", [])
    if not results or not isinstance(results[0], dict):
        raise ValueError("City record has no results.")
    city_data = results[0]

    city_data_dict = {
        "state": "admin1",
        "lat": "latitude",
        "lon": "longitude",
        "population": "population",
        "elevation": "elevation",
        "city": "name",
        "country": "country"
    }
    flat_enrich_city = {}

    for gold_name, raw_name in city_data_dict.items():
        value = city_data.get(raw_name)
        if isinstance(value, float):
            value = round(value, 4)
        elif isinstance(value, str):
            value = value.lower()
        flat_enrich_city[gold_name] = value

    # Validate against data contracts
    try:
        validated_record = GoldCities(**flat_enrich_city)
    except Exception as e:
        log.error("Data validation failed for city %s: %s", flat_enrich_city['city'], e)
        raise RuntimeError(f"OpenWeather response failed Pydantic validation: {e}") from e

    return validated_record.model_dump()

def parse_air_data(air_record: dict, city_id: int) -> list[dict]:
    """
    Flattens each hourly reading in the air record into a row for gold_air_data.
    Skips readings with no timestamp; other missing values are stored as None.
    """

    retrieve_date = air_record.get("extracted_at")
    readings = air_record.get("payload", {}).get("list", [])

    flat_air_records = []
    for reading in readings:
        if "dt" not in reading:
            log.warning("Skipping reading with no timestamp: %s", reading)
            continue
        components = reading.get("components", {})
        aqi = reading.get("main", {}).get("aqi")
        flat_air_records.append({
            "date_time": convert_unix_to_datetime(reading["dt"]),
            "co": components.get("co"),
            "pm2_5": components.get("pm2_5"),
            "no2": components.get("no2"),
            "aqi": aqi,
            "retrieve_date": retrieve_date,
            "sentiment_label": aqi_to_sentiment(aqi),
            "city_id": city_id,
            "aqi_rolling_7d": 0.0,          # replaced after transform
            "pm2_5_rolling_7d": 0.0,        # replaced after transform
            "llm_response": ""              # replaced after transform
        })
        
    try:
        validated_air_records = GoldAirData.model_validate({'gold_air_data': flat_air_records})
    except Exception as e:
        log.error("Data validation failed for city %s: %s", city_id, e)
        raise RuntimeError(f"OpenWeather response failed Pydantic validation: {e}") from e
    return validated_air_records.model_dump()['gold_air_data']


def transform_air_data(air_record: dict, city_id: int) -> list[dict]:
    """
    Takes raw air record and city_id. Returns a list of 
    flat dictionaries by calling the parse function.
    Raises ValueError if missing or invalid variable is passed.
    """

    if not air_record or not isinstance(air_record, dict):
        log.error("Invalid air_record: %s", air_record)
        raise ValueError("Invalid or empty data payload provided.")
    elif not city_id or city_id < 1 or not isinstance(city_id, int):
        log.error("Invalid city_id: %s", city_id)
        raise ValueError("Missing or invalid city ID.")
    else:
        return parse_air_data(air_record, city_id)
