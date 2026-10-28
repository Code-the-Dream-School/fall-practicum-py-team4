import datetime

from pydantic import BaseModel
from typing import Optional

# --- Raw Schemas ---

# open-meteo

class Results(BaseModel):
    id: int
    name: str
    latitude: float
    longitude: float
    elevation: float
    feature_code: str
    country_code: str
    admin1_id: int
    admin2_id: Optional[int] = None
    admin3_id: Optional[int] = None
    admin4_id: Optional[int] = None
    timezone: str
    population: int
    postcodes: list[str]
    country_id: int
    country: str
    admin1: str
    admin2: Optional[str] = None
    admin3: Optional[str] = None
    admin4: Optional[str] = None

class RawOpenMeteo(BaseModel):
    results: list[Results]
    generationtime_ms: float

# OpenWeather

class Components(BaseModel):
    co: float
    no: float
    no2: float
    o3: float
    so2: float
    pm2_5: float
    pm10: float
    nh3: float

class ListItem(BaseModel):
    dt: int
    main: dict[str,float]
    components: Components

class Parameters(BaseModel):
    start: int                      # unix time, UTC time zone
    end: int                        # unix time, UTC time zone

class Coordinates(BaseModel):
    lon: float
    lat: float

class RawOpenWeather(BaseModel):
    coord: Coordinates
    list: list[ListItem]
    retrieve_date: str

# City

class RawCityRecord(BaseModel):
    city: str
    payload: RawOpenMeteo
    retrieve_date: str

# Air Pollution Record

class RawAirPollutionRecord(BaseModel):
    city: str
    target_date: str
    data: RawOpenWeather
    retrieve_date: str
    request_params: Optional[Parameters] = None

# Raw Data Example

# open-meteo
raw_meteo = {
    "results": [
        {
            "id": 2988507,
            "name": "Paris",
            "latitude": 48.85341,
            "longitude": 2.3488,
            "elevation": 42.0,
            "feature_code": "PPLC",
            "country_code": "FR",
            "admin1_id": 3012874,
            "admin2_id": 2968815,
            "admin3_id": 2988506,
            "admin4_id": 6455259,
            "timezone": "Europe/Paris",
            "population": 2138551,
            "postcodes": [
                "75001",
                "75020",
                "75002",
                "75003",
                "75004",
                "75005",
                "75006",
                "75007",
                "75008",
                "75009",
                "75010",
                "75011",
                "75012",
                "75013",
                "75014",
                "75015",
                "75016",
                "75017",
                "75018",
                "75019"
            ],
            "country_id": 3017382,
            "country": "France",
            "admin1": "Île-de-France Region",
            "admin2": "Paris Department",
            "admin3": "Paris",
            "admin4": "Paris"
        }
    ],
    "generationtime_ms": 0.64599514
}

# OpenWeather
raw_data = {
    "retrieve_date": "2026-10-11",
    "coord": {
        "lon": 50.0,
        "lat": 50.0
    },
    "list": [
        {
            "dt": 1605916800,
            "main": {
                "aqi": 1.0
            },
            "components": {
                "co": 211.954,
                "no": 0.0,
                "no2": 0.217,
                "o3": 72.956,
                "so2": 0.514,
                "pm2_5": 2.563,
                "pm10": 5.757,
                "nh3": 0.216
            }
        }
    ]
}

# --- Golden Schema ---

# open-meteo

class GoldCities(BaseModel):
    city_name: str
    state: str
    country_code: str
    lat: float
    lon: float
    population: int
    elevation: float

# OpenWeather

class GoldAirData(BaseModel):
    longitude: float
    latitude: float
    city: str
    country: str
    date_time: str
    co: float
    no2: float
    pm2_5: float
    aqi: int
    retrieve_date: str
    sentiment_label: str
    running_average: float
    city_id: int

# Golden Data Example

gold_cities = {
    "city_name": "Paris",
    "state": "Île-de-France Region",
    "country_code": "FR",
    "lat": 48.85341,
    "lon": 2.3488,
    "population": 2138551,
    "elevation": 42.0
}

gold_air_data = {
    "longitude": -73.98,
    "latitude": 40.74,
    "city": "New York",
    "country": "United States",
    "date_time": "2026-10-11 15:36:04.900413",
    "co": 130.95, 
    "no2": 0.96, 
    "pm2_5": 3.25,
    "aqi": 2,
    "hour": "13:00",
    "retrieve_date": "2026-10-11",
    "sentiment_label": 'fair',
    "running_average": 2.67,
    "city_id": 3
}

# --- Function Signatures ---

def geocodes(city: str) -> dict:
    # takes a city and returns the a payload including latitude, longitude, population, and elevation as a dictionary
    return{}

def get_unix(time: str, start_date: str) -> int:
    # takes a time and start date to determine the unix time code
    # try/except block to determine time and start_date are correct types
    unix_code = 0
    return unix_code

def extract(city_name: str, latitude: float, longitude: float, date: str) -> dict:

    # city_name: for human reference (instead of reading lat and lon)
    # we are only using the /history endpoint right now, so no endpoint argument.
    # instead of start_date and end_date, use a single date (YYYY-MM_DD), as the function automatically fetches the 24 chunks that span each day.
    # return a dict instead of a list (this will actually later be a RawAirPollutionRecord)
    return {}

def load_raw(raw_records: list) -> None:
    # takes a list of raw data instances and loads the raw data into the database
    # uses the defined raw schema to read and write
    # try/except blocks to check for upload issues, displays warnings and updates progress

    # Returns nothing
    pass

def transform(raw_records: list) -> list:
    # takes a list of raw data instances. Cleans and transforms the data
    # try/except blocks to catch type and key errors while transforming
    # returns it in a form following the gold_air_data schema
    return []

# --- Input Configuration ---

city: str                               # accepts city names and zipcodes
date_range: Optional[str] = ""          # format YYYY-MM-DD for past 60 days, delimiter " - "

# Input Example

input = {
    "city": 'bogota, colombia',
    "date_range": "2026-08-26 - 2026-10-25"
}

# all strings are converted to lowercase.
# numbers are recorded as floats, max 4 decimal places, except when given integers by data source.
# dates are converted to datetime objects, and ranges are split into two categories, start and end.
# missing or invalid values are replaced with NaN, and the row is removed from the dataframe during transform
# missing city value will stop the pipeline from running and request user input. (if we have user input)
# date_range only needed when searching for historical information.
