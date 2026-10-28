import os, requests, logging
from dotenv import load_dotenv
from datetime import datetime, timezone
# consider the use of dateutil.parser to parse virtually any date format? 

logger = logging.getLogger(__name__)

# OpenWeather Air Pollution API. Needs OPENWEATHER_API_KEY in your environment or .env file.
AIR_POLLUTION_URL = "https://api.openweathermap.org/data/2.5/air_pollution"


def get_unix(time: str, date: str) -> int:
    """
    Takes a time ('12:00') and a date string ('YYYY-MM-DD')
    and returns the unix time (UTC).
    """
    try:
        moment = datetime.strptime(date + " " + time, "%Y-%m-%d %H:%M")
        moment = moment.replace(tzinfo=timezone.utc)
        return int(moment.timestamp())
    except ValueError as e:
        logger.error("Invalid format or date/time values for Date '%s' and Time '%s'", date, time)
        raise ValueError(f"Invalid format or date/time values for Date '{date}' and Time '{time}': {e}")


def extract(city_name: str, latitude: float, longitude: float, date: str) -> dict:
    # we are only using the /history endpoint so far
    # extracts 24 hours of data for the given date

    load_dotenv()
    api_key = os.getenv("OPENWEATHER_API_KEY")
    if not api_key:
        logger.error("Missing OPENWEATHER_API_KEY in environment or .env file.")
        raise ValueError("Missing OPENWEATHER_API_KEY. Add it to your environment or .env file.")

    # build the request
    url = AIR_POLLUTION_URL + "/history"

    # Calculate the 24-hour window for the given date
    one_day = 24 * 60 * 60
    start_unix = get_unix("00:00", date)
    end_unix = start_unix + one_day

    params = {
        "lat": latitude,
        "lon": longitude,
        "appid": api_key,
        "start": start_unix,
        "end": end_unix,
    }

    logger.info(
        "Fetching air pollution history for city '%s' (lat: %s, lon: %s) on date %s",
        city_name,
        latitude,
        longitude,
        date,
    )

    # call OpenWeather
    try:
        response = requests.get(url, params=params, timeout=30)
    except requests.RequestException:
        # don't show the original error: it contains the URL, which includes the API key
        logger.error("Network or connection error occurred while contacting OpenWeather.")
        raise RuntimeError("Could not reach OpenWeather. Check your internet connection.") from None
    if response.status_code != 200:
        logger.error("OpenWeather returned error status code: HTTP %s", response.status_code)
        raise RuntimeError(f"OpenWeather returned an error: HTTP {response.status_code}")
    
    payload = response.json()
    logger.info("Successfully retrieved air pollution history for %s", city_name)

    # package the result like RawOpenWeather in data_contracts.py
    # we need to move contracts.py to the root folder, so we can use pydantic to validate the data
    record = {
        "city": city_name,
        "target_date": date,
        "data": payload,
        "start": start_unix,
        "end": end_unix,
        "retrieve_date": datetime.now(timezone.utc).strftime("%Y-%m-%d")   
    }

    return record