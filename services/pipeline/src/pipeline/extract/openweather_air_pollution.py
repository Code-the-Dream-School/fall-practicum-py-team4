import os
from datetime import datetime, timezone

import requests
from dotenv import load_dotenv

# OpenWeather Air Pollution API. Needs OPENWEATHER_API_KEY in your environment or .env file.
AIR_POLLUTION_URL = "https://api.openweathermap.org/data/2.5/air_pollution"


def get_unix(time: str, start_date: str) -> int:
    # takes a time ("12:00") and a date ("10/01/2026") and returns the unix time (UTC)
    moment = datetime.strptime(start_date + " " + time, "%m/%d/%Y %H:%M")
    moment = moment.replace(tzinfo=timezone.utc)
    return int(moment.timestamp())


def extract(city_name: str, latitude: float, longitude: float, date=str) -> list:
    # we are only using the /history endpoint so far
    # extracts 24 hours of data for the given date

    load_dotenv()
    api_key = os.getenv("OPENWEATHER_API_KEY")
    if not api_key:
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

    # call OpenWeather
    try:
        response = requests.get(url, params=params, timeout=30)
    except requests.RequestException:
        # don't show the original error: it contains the URL, which includes the API key
        raise RuntimeError("Could not reach OpenWeather. Check your internet connection.") from None
    if response.status_code != 200:
        raise RuntimeError(f"OpenWeather returned an error: HTTP {response.status_code}")
    
    payload = response.json()

    # package the result like RawOpenWeather in data_contracts.py
    # we need to move contracts.py to the root folder, so we can use pydantic to validate the data
    record = {
        "city": city_name,
        "target_date": date,
        "data": payload,
        "start": start_unix,
        "end": end_unix,
        "retrieve_date": datetime.now(timezone.utc).strftime("%m/%d/%Y")   
    }

    return record