import requests
import logging
from datetime import datetime, timezone
from pydantic import BaseModel, field_validator
from typing import Optional
from contracts.data_contracts import RawOpenMeteo, RawCityRecord

logger = logging.getLogger(__name__)

# Open-Meteo turns a city name or zipcode into coordinates. No API key needed.
GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"


def geocodes(city: str) -> dict:
    # takes a single city/zipcode and return the latitude and longitude for it

    city = city.strip().lower()

    if not city:
        logger.error("Attempted to call geocodes with an empty city value.")
        raise ValueError("Missing city value. Please give at least one city or zipcode.")

    logger.info("Fetching geocoding data for city: %s", city)

    # ask Open-Meteo for the best match for this city
    try:
        response = requests.get(GEOCODING_URL, params={"name": city, "count": 1}, timeout=15)
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        logger.error("HTTP request failed for city '%s': %s", city, e)
        raise

    # Validate with Pydantic first
    try:
        data = RawOpenMeteo(**response.json())
    except Exception as e:
        logger.error("API response validation failed for city '%s': %s", city, e)
        raise RuntimeError(f"Open-Meteo response failed Pydantic validation: {e}") from e
    logger.info("Successfully validated OpenMeteo response for city: %s", city)

    if not data.results:
        logger.warning("No geocoding results found for city: %s", city)
        raise ValueError(f"Could not find '{city}'. Please check the spelling.")

    city_name = data.results[0].name.lower()
    retrieve_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    logger.info("Successfully retrieved and matched city: %s", city_name)


    try:
        record = RawCityRecord(
            city = city_name,
            payload = data,
            extracted_at = retrieve_date,
        )
    except Exception as e:
        logger.error("Data validation failed for %s: %s", city_name, e)
        raise RuntimeError(f"City response failed Pydantic validation: {e}") from e

    logger.info("Successfully validated city record for %s", city_name)

    return record.model_dump()