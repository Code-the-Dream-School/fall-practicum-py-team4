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


def extract(latitude: float, longitude: float, endpoint='/', start_date=None, end_date=None, daily=True, time_of_day='1200') -> list:
    # endpoint: "/" = current, "/forecast" = forecast, "/history" = past data
    # history needs start_date and end_date like "10/01/2026" (end_date is included)
    # daily=True keeps one reading per day (at time_of_day, UTC); daily=False keeps every hour

    if endpoint not in ["/", "/forecast", "/history"]:
        raise ValueError("endpoint must be '/', '/forecast' or '/history'")

    if endpoint == "/history" and (start_date is None or end_date is None):
        print("When using the '/history' endpoint, start and end dates must be specified")
        return []

    load_dotenv()
    api_key = os.getenv("OPENWEATHER_API_KEY")
    if not api_key:
        raise ValueError("Missing OPENWEATHER_API_KEY. Add it to your environment or .env file.")

    # build the request
    url = AIR_POLLUTION_URL
    params = {"lat": latitude, "lon": longitude, "appid": api_key}

    if endpoint == "/forecast":
        url = AIR_POLLUTION_URL + "/forecast"

    if endpoint == "/history":
        url = AIR_POLLUTION_URL + "/history"
        one_day = 24 * 60 * 60
        params["start"] = get_unix("00:00", start_date)
        params["end"] = get_unix("00:00", end_date) + one_day

    # call OpenWeather
    try:
        response = requests.get(url, params=params, timeout=30)
    except requests.RequestException:
        # don't show the original error: it contains the URL, which includes the API key
        raise RuntimeError("Could not reach OpenWeather. Check your internet connection.") from None
    if response.status_code != 200:
        raise RuntimeError(f"OpenWeather returned an error: HTTP {response.status_code}")
    data = response.json()

    # keep only one reading per day if daily is True
    readings = data["list"]
    if daily and endpoint != "/":
        wanted_hour = int(time_of_day.replace(":", "")[:2])  # "12:00" or "1200" -> 12
        daily_readings = []
        for reading in readings:
            reading_time = datetime.fromtimestamp(reading["dt"], tz=timezone.utc)
            if reading_time.hour == wanted_hour:
                daily_readings.append(reading)
        readings = daily_readings

    # package the result like RawAirTrackerData in data_contracts.py
    record = {
        "coord": data["coord"],
        "list": readings,
        "retrieve_date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
    }
    if endpoint == "/history":
        record["request_params"] = {"start": params["start"], "end": params["end"]}

    return [record]
