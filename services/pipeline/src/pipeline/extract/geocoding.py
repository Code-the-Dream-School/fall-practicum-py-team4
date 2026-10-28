import requests
import logging
from datetime import datetime, timezone
from pydantic import BaseModel, field_validator
from typing import Optional
# from data_contracts import RawCityRecord

logger = logging.getLogger(__name__)

# Open-Meteo turns a city name or zipcode into coordinates. No API key needed.
GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"


def geocodes(city: str) -> dict:
    # takes a single city/zipcode and return the latitude and longitude for it

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

    data = response.json()

    if "results" not in data or not data['results']:
        logger.warning("No geocoding results found for city: %s", city)
        raise ValueError(f"Could not find '{city}'. Please check the spelling.")

    city_name = data['results'][0]['name']
    retrieve_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    logger.info("Successfully retrieved and matched city: %s", city_name)

    results = {
        "city": city_name,
        "payload": data,
        "retrieve_date": retrieve_date,
    }

    # we need to move contracts.py to the root folder, so we can use pydantic to validate the data
    # # this should be a RawCityRecord
    # record = RawCityRecord(
    #     city = city_name,
    #     payload = data,
    #     retrieve_date = datetime.now(timezone.utc).strftime("%Y-%m-%d"),
    # )
    #
    #return RawCityRecord

    return results