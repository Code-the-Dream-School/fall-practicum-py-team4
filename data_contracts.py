import datetime

from pydantic import BaseModel, field_validator
from typing import Optional

# --- Raw Schemas ---

# open-mateo

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

class RawOpenMateo(BaseModel):
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

class RawAirTrackerData(BaseModel):
    coord: Coordinates
    list: list[ListItem]
    request_params: Optional[Parameters] = None
    retrieve_date: str

# Raw Data Example

# open-mateo
raw_mateo = {
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

# open-mateo

class Locations(BaseModel):
    name: str
    lat: float
    lon: float
    elevation: float
    country: str
    region: str
    population: int

class GoldenMateo(BaseModel):
    locations: list[Locations]

# OpenWeather

class GoldListItem(BaseModel):
    date_time: datetime.datetime
    aqi: int
    components: Components

class GoldSchema(BaseModel):
    retrieve_date: datetime.date
    coordinates: Coordinates
    city: str
    readings: list[GoldListItem]

# Golden Data Example

golden_mateo = [
    {
        "name": "Paris",
        "lat": 48.85341,
        "lon": 2.3488,
        "elevation": 42.0,
        "country": "France",
        "region": "Europe",
        "population": 2138551
    }
]

golden_data = {
    "retrieve_date": "2026-10-11",
    "coordinates": {
        "lon": -73.98,
        "lat": 40.74
    },
    "city": "New York",
    "readings": [
        {
            "aqi": 2,
            "components": {
                "co": 130.95, 
                "no": 0.02, 
                "no2": 0.96, 
                "o3": 93.26, 
                "so2": 0.28, 
                "pm2_5": 3.25, 
                "pm10": 4.28, 
                "nh3": 0.01
            }, 
            "date_time": "2026-10-11 15:36:04.900413"
        }
    ]
}

# --- Function Signatures ---

def geocodes(cities: list) -> dict:
    # takes a list of cities/zipcodes and returns the latitude and longitude for each as a dictionary
    return{}

def get_unix(time: str, start_date: str) -> int:
    # takes a time and start date to determine the unix time code
    # try/except block to determine time and start_date are correct types
    unix_code = 0
    return unix_code

def extract(latitude: float, longitude: float, endpoint='/', start_date=None, end_date=None, daily=True, time_of_day='1200') -> list: 
    # latitude and longitude coordinates from the geocodes function
    # endpoint directs the call to the present, forcast, or history data for the given point
    # start_date and end_date are optional and are used to set the dates when requesting the 'history' endpoint
    # daily is optional and automatically set to True. this retrieves one pull per day at the time set by time_of_day, else hourly
    # time_of_day sets the hour of day to retrieve for each day when daily is set to True, else '1200'
    # extracts data from openweathermap and uses the raw schema to validate values 
    # requires start and end dates if endpoint is set to 'history'
    # check for value and key errors with try/except blocks. write message to user to correct errors
    # when using 'history' endpoint, start_date, end_date, and daily are required. time_of_day required when daily is True
    # returns a list of instances of raw data


    if endpoint == "/history" and (start_date == None or end_date == None):
        print("When using the '/history' endpoint, start and end dates must be specified")
        return[]
    
    return []

def load_raw(raw_records: list) -> None:
    # takes a list of raw data instances and loads the raw data into the database
    # uses the defined raw schema to read and write
    # try/except blocks to check for upload issues, displays warnings and updates progress

    # Returns nothing
    pass

def transform(raw_records: list) -> list:
    # takes a list of raw data instances. Cleans and transforms the data
    # try/except blocks to catch type and key errors while transforming
    # returns it in a form following the gold schema
    return []

# --- Input Configuration ---

cities: list[str]                       # accepts city names and zipcodes
date_range: Optional[str] = ""
daily: Optional[bool] = True            # openweather pulls hourly, so this will set a daily pull to avoid timeouts
time_of_day: Optional[str] = "12:00"

# Input Example

input = {
    "cities": ["new york", "london", "seoul", "jakarta"],
    "date_range": "01/01/2020 - 01/01/2026",
    "daily": True,
    "time_of_day": "15:00"
}

# all strings are converted to lowercase.
# numbers are recorded as floats except when given integers by data source.
# dates are converted to datetime objects, and ranges are split into two categories, start and end.
# date ranges should specify one daily value, and capture the same time of day for entire range
# missing or invalid values are replaced with NaN, and the row is removed from the dataframe.
# missing city value will stop the pipeline from running and request user input.
# date_range only needed when searching for historical information.
