import datetime

from pydantic import BaseModel, field_validator
from typing import Optional

# --- Raw Schema ---

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

class GoldListItem(BaseModel):
    date_time: datetime.datetime
    aqi: int
    components: Components

class GoldSchema(BaseModel):
    retrieve_date: datetime.date
    coordinates: Coordinates
    city: str
    readings: list[ListItem]

# Golden Data Example
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

def extract(latitude: float, longitude: float, endpoint='/', start_date=None, end_date=None ) -> list: 
    # Takes latitude and longitude coordinates
    # Extracts data from openweathermap and uses the raw schema to validate values 
    # Requires start and end dates if endpoint is set to 'history'
    # Returns a list of instances of raw data
    if endpoint == "/history" and (start_date == None or end_date == None):
        print("When using the '/history' endpoint, start and end dates must be specified")
        return[]
    
    return []

def load_raw(raw_records: list) -> None:
    # Takes a list of raw data instances and loads the raw data into the database
    # Returns nothing
    pass

def transform(raw_records: list) -> list:
    # Takes a list of raw data instances. Cleans and transforms the data and 
    # returns it in a form following the gold schema
    return []
