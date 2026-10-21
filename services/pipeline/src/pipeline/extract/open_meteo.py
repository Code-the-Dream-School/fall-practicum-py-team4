"""Open-Meteo geocoding: the raw source for GoldenMateo in data_contracts.py.

Coordinates for the pollution calls still come from geocoding.py (OpenWeather,
cached). This lookup only adds the location details gold needs: elevation,
country, region and population. No API key is required.
"""

import requests

from .openweather_http import OpenWeatherError

SEARCH_URL = "https://geocoding-api.open-meteo.com/v1/search"


def fetch_location(name: str, count: int = 1) -> dict:
    """Return the raw response (RawOpenMateo shape) for a city or postal code."""
    if not isinstance(name, str) or not name.strip():
        raise ValueError("Missing city value")
    try:
        response = requests.get(
            SEARCH_URL, params={"name": name.strip(), "count": count, "format": "json"},
            timeout=(5, 15), allow_redirects=False,
        )
    except requests.RequestException:
        raise OpenWeatherError("Open-Meteo connection failed") from None
    if response.status_code != 200:
        raise OpenWeatherError(f"Open-Meteo HTTP {response.status_code}")
    try:
        payload = response.json()
    except ValueError:
        raise OpenWeatherError("Open-Meteo returned invalid JSON") from None
    if not isinstance(payload, dict):
        raise OpenWeatherError("Expected an Open-Meteo object")
    # Open-Meteo leaves "results" out when nothing matches.
    payload.setdefault("results", [])
    return payload
