import copy
import logging
import os
import pytest

from datetime import datetime, timezone
from dotenv import load_dotenv
from pipeline.transform.transform_to_gold import (
    convert_unix_to_datetime,
    parse_air_data,
    transform_air_data,
    transform_city_data,
)

log = logging.getLogger(__name__)

timestamp = 1793841909
city_id = 1

# Name that will never collide with real pipeline data
TEST_CITY = "pytest city"

SAMPLE_RAW_CITY_PAYLOAD = {
    'city': 'New York',
    'payload': {
        'generationtime_ms': 0.29575825,
        'results': [{
            'admin1': 'New York',
            'admin1_id': 5128638,
            'country': 'United States',
            'country_code': 'US',
            'country_id': 6252001,
            'elevation': 10.0,
            'feature_code': 'PPL',
            'id': 5128581,
            'latitude': 40.71427,
            'longitude': -74.00597,
            'name': 'New York',
            'population': 8804190,
            'postcodes': [],
            'timezone': 'America/New_York'
        }]
    },
    'extracted_at': '2026-11-01'
}

SAMPLE_RAW_AIR_PAYLOAD = {
    "city": "new york",
    "target_date": "2025-05-01",
    "payload": {
        "coord": {
            "lon": -74.01,
            "lat": 40.71
        },
        "list": [
            {
                "main": {
                    "aqi": 2
                },
                "components": {
                    "co": 207.09,
                    "no": 0.12,
                    "no2": 11.75,
                    "o3": 90.7,
                    "so2": 1.28,
                    "pm2_5": 8.56,
                    "pm10": 10.69,
                    "nh3": 0.82
                },
                "dt": 1746057600
            },
            {
                "main": {
                    "aqi": 2
                },
                "components": {
                    "co": 212.69,
                    "no": 0,
                    "no2": 12.28,
                    "o3": 83.31,
                    "so2": 1.17,
                    "pm2_5": 9.37,
                    "pm10": 11.82,
                    "nh3": 0.84
                },
                "dt": 1746061200
            },
            {
                "main": {
                    "aqi": 2
                },
                "components": {
                    "co": 217.08,
                    "no": 0,
                    "no2": 12.32,
                    "o3": 78.33,
                    "so2": 1.07,
                    "pm2_5": 10.01,
                    "pm10": 12.59,
                    "nh3": 0.82
                },
                "dt": 1746064800
            }
        ]
    },
    "request_params": {
        "start": 1746057600,
        "end": 1746143999
    },
    "extracted_at": "2026-10-31"
}

SAMPLE_GOLD_CITY = {
    "state": "new york",
    "lat": 40.7143,
    "lon": -74.006,
    "population": 8804190,
    "elevation": 10.0,
    "city": "new york",
    "country": "united states"
}

SAMPLE_GOLD_AIR = [
    {
        "date_time": datetime(2025, 5, 1, 0, 0, tzinfo=timezone.utc),
        "co": 207.09,
        "pm2_5": 8.56,
        "no2": 11.75,
        "aqi": 2,
        "retrieve_date": "2026-10-31",
        "sentiment_label": "Fair",
        "city_id": 1,
        "aqi_rolling_7d": 0.0,
        "pm2_5_rolling_7d": 0.0,
        "llm_response": ""
    },
    {
        "date_time": datetime(2025, 5, 1, 1, 0, tzinfo=timezone.utc),
        "co": 212.69,
        "pm2_5": 9.37,
        "no2": 12.28,
        "aqi": 2,
        "retrieve_date": "2026-10-31",
        "sentiment_label": "Fair",
        "city_id": 1,
        "aqi_rolling_7d": 0.0,
        "pm2_5_rolling_7d": 0.0,
        "llm_response": ""
    },
    {
        "date_time": datetime(2025, 5, 1, 2, 0, tzinfo=timezone.utc),
        "co": 217.08,
        "pm2_5": 10.01,
        "no2": 12.32,
        "aqi": 2,
        "retrieve_date": "2026-10-31",
        "sentiment_label": "Fair",
        "city_id": 1,
        "aqi_rolling_7d": 0.0,
        "pm2_5_rolling_7d": 0.0,
        "llm_response": ""
    }
]

# --- Tests ---

@pytest.mark.unit
def test_convert_unix_to_datetime():
    assert convert_unix_to_datetime(timestamp) == datetime(2026, 11, 5, 1, 0, tzinfo=timezone.utc)

@pytest.mark.unit
def test_transform_city_data():
    flat_city = transform_city_data(SAMPLE_RAW_CITY_PAYLOAD)
    assert flat_city == SAMPLE_GOLD_CITY

@pytest.mark.unit
def test_invalid_city_record():
    city_record = {"payload": {"results": [[]]}}
    with pytest.raises(ValueError):
        transform_city_data(city_record)

@pytest.mark.unit
def test_missing_city_variable():
    city_record = {**copy.deepcopy(SAMPLE_RAW_CITY_PAYLOAD)}
    city_record['payload']['results'][0]['name'] = ''
    city_missing = transform_city_data(city_record)
    expected_city_missing = {**copy.deepcopy(SAMPLE_GOLD_CITY), "city": ''}
    assert city_missing == expected_city_missing

@pytest.mark.unit
def test_city_validation_fail():
    city_record = {**copy.deepcopy(SAMPLE_RAW_CITY_PAYLOAD)}
    city_record['payload']['results'][0]['name'] = 6
    with pytest.raises(RuntimeError):
        transform_city_data(city_record)

@pytest.mark.unit
def test_empty_city_record():
    city_record = {}
    with pytest.raises(ValueError):
        transform_city_data(city_record)

@pytest.mark.unit
def test_parse_air_data():
    flat_air = parse_air_data(SAMPLE_RAW_AIR_PAYLOAD, 1)
    assert flat_air == SAMPLE_GOLD_AIR

@pytest.mark.unit
def test_parse_validation_fail():
    air_record = {**copy.deepcopy(SAMPLE_RAW_AIR_PAYLOAD), "city": TEST_CITY, "extracted_at": 0}
    with pytest.raises(RuntimeError):
        parse_air_data(air_record, 1)

@pytest.mark.unit
def test_transform_air_data():
    city_id = 1
    air_record = {**copy.deepcopy(SAMPLE_RAW_AIR_PAYLOAD), "city": TEST_CITY}
    gold_air = transform_air_data(air_record, city_id)
    expected_gold_air = [
        {**record, "city_id": city_id}
        for record in SAMPLE_GOLD_AIR
    ]
    assert gold_air == expected_gold_air

@pytest.mark.unit
def test_missing_air_variable():
    city_id = 1
    air_record_raw_missing = {**copy.deepcopy(SAMPLE_RAW_AIR_PAYLOAD), "city": TEST_CITY, "extracted_at": ''}
    gold_air_missing = transform_air_data(air_record_raw_missing, city_id)
    expected_gold_air_missing = [
        {**record, "city_id": city_id, "retrieve_date": ''}
        for record in SAMPLE_GOLD_AIR
    ]
    assert gold_air_missing == expected_gold_air_missing

@pytest.mark.unit
def test_incorrect_city_id():
    air_record = {**copy.deepcopy(SAMPLE_RAW_AIR_PAYLOAD), "city": TEST_CITY}
    with pytest.raises(ValueError):
            transform_air_data(air_record, 0)

@pytest.mark.unit
def test_empty_air_data():
    city_id = 1
    with pytest.raises(ValueError):
        transform_air_data({}, 0)
