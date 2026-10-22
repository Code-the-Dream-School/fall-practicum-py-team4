import requests

# Open-Meteo turns a city name or zipcode into coordinates. No API key needed.
GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"


def geocodes(cities: list) -> dict:
    # takes a list of cities/zipcodes and returns the latitude and longitude for each
    # example: geocodes(["new york"]) -> {"new york": {"lat": 40.71, "lon": -74.01}}

    if not cities:
        raise ValueError("Missing city value. Please give at least one city or zipcode.")

    results = {}

    for city in cities:
        city = city.strip().lower()

        # ask Open-Meteo for the best match for this city
        response = requests.get(GEOCODING_URL, params={"name": city, "count": 1}, timeout=15)
        data = response.json()

        if "results" not in data:
            raise ValueError(f"Could not find '{city}'. Please check the spelling.")

        best_match = data["results"][0]
        results[city] = {"lat": best_match["latitude"], "lon": best_match["longitude"]}

    return results
