# Gold data dictionary

Every column in the two gold tables: what it means, its type and unit, where
it comes from, and whether it can be empty.

Gold rows are built by
`services/pipeline/src/pipeline/transform/transform_to_gold.py`. The Pydantic
models are `GoldCities` and `GoldAirDict` in
`services/pipeline/contracts/data_contracts.py`. Column types were checked
read-only against the Supabase API schema (project `fall-practicum-py-team4`)
on 2026-11-07.

| Table | One row per | Built by |
| --- | --- | --- |
| `gold_cities` | city | `transform_city_data(city_record)` |
| `gold_air_data` | city per hour | `transform_air_data(supabase_client, air_record)` |

`gold_air_data.city_id` points to `gold_cities.id`, so **a city must be in
`gold_cities` before its air data can be transformed.** If the lookup finds no
match, `transform_air_data` logs a warning and returns `[]`.

## `gold_cities`

Source: the raw city record from Open-Meteo geocoding. Only the first result,
`payload.results[0]`, is used. If `results` is missing or empty,
`transform_city_data` raises `ValueError`.

Cleaning rules:
- Strings are lowercased.
- Floats are rounded to 4 decimal places.
- A field missing from the payload is stored as `null`.

| Column | Meaning | Type | Unit / format | Comes from | Nullable |
| --- | --- | --- | --- | --- | --- |
| `id` | Row id | `int8` | assigned by the database | — | No (primary key) |
| `city` | City name | `text` | lowercase, e.g. `new york` | `results[0].name` | Yes |
| `state` | State or region | `text` | lowercase, e.g. `new york` | `results[0].admin1` | Yes |
| `country` | Country name | `text` | lowercase full name, e.g. `united states` (not an ISO code) | `results[0].country` | Yes |
| `lat` | Latitude, north positive | `float8` | decimal degrees, 4 places | `results[0].latitude` | Yes |
| `lon` | Longitude, east positive | `float8` | decimal degrees, 4 places | `results[0].longitude` | Yes |
| `population` | Population | `int8` | people | `results[0].population` | Yes |
| `elevation` | Height above sea level | `float8` | metres, 4 places | `results[0].elevation` | Yes |

`retrieve_city_id(supabase_client, city)` looks rows up by exact `city`
match, so callers pass the name in lowercase.

## `gold_air_data`

Source: the raw air record from the OpenWeather Air Pollution history API.
`parse_air_data` turns each item in `data.list` into one row. An item with no
`dt` (timestamp) is skipped and logged. Any other missing value is stored as
`null`.

| Column | Meaning | Type | Unit / format | Comes from | Nullable |
| --- | --- | --- | --- | --- | --- |
| `id` | Row id | `int8` | assigned by the database | — | No (primary key) |
| `city_id` | City the reading belongs to | `int8` | foreign key to `gold_cities.id` | `retrieve_city_id(...)` using the raw record's `city`, lowercased | Yes |
| `date_time` | Hour the reading represents | `timestamptz` | UTC, rounded down to the hour | `data.list[].dt` (Unix seconds) via `convert_unix_to_datetime` | Yes |
| `aqi` | OpenWeather air quality index | `int4` | 1–5, 5 is worst | `data.list[].main.aqi` | Yes |
| `co` | Carbon monoxide | `float8` | µg/m³ | `data.list[].components.co` | Yes |
| `pm2_5` | Fine particulate matter (≤ 2.5 µm) | `float8` | µg/m³ | `data.list[].components.pm2_5` | Yes |
| `no2` | Nitrogen dioxide | `float8` | µg/m³ | `data.list[].components.no2` | Yes |
| `retrieve_date` | Day the raw data was fetched | `date` | `YYYY-MM-DD` (UTC) | raw record `retrieve_date` | Yes |
| `sentiment_label` | Word label for the AQI | `text` | see [below](#sentiment_label) | **Placeholder:** `""` for now | Yes |
| `aqi_rolling_7d` | Mean AQI over the previous 7 days | `float8` | 1.0–5.0, or 0 during warm-up | **Placeholder:** `0.0` for now | Yes |
| `pm2_5_rolling_7d` | Mean PM2.5 over the previous 7 days | `float8` | µg/m³, or 0 during warm-up | **Placeholder:** `0.0` for now | Yes |
| `llm_response` | Plain-English summary of the reading | `text` | free text | **Placeholder:** `""` for now | Yes |

OpenWeather also returns `no`, `o3`, `so2`, `pm10` and `nh3`. Gold doesn't keep
them. All pollutant values are µg/m³ as delivered, CO included
([OpenWeather Air Pollution API](https://openweathermap.org/api/air-pollution)).

### `sentiment_label`

Planned mapping, from `aqi_to_sentiment` in `data_contracts.py`:

| `aqi` | `sentiment_label` |
| --- | --- |
| 1 | Good |
| 2 | Fair |
| 3 | Moderate |
| 4 | Poor |
| 5 | Very Poor |

### Rolling averages

These will be filled by `add_rolling_average(readings, field)` in
`pipeline/transform/rolling_average.py`, called once with `"aqi"` and once
with `"pm2_5"`:

- **Window:** 7 days of time, `(date_time - 7 days, date_time]`, per city.
  Hourly data averages about 168 readings.
- **Warm-up:** the value is `0` until the city has 7 full days of history
  before the reading (team decision), so a partial average is never shown.
- **Gaps:** missing hours are skipped, and the mean uses the readings present.
- **Duplicates:** two readings with the same `date_time` raise `ValueError`.

## Known gaps

- `transform_to_gold.py` currently doesn't fill `sentiment_label`,
  `aqi_rolling_7d`, `pm2_5_rolling_7d` or `llm_response`. They hold the
  placeholders listed above.
- Neither table has a unique key (for example on `gold_air_data`
  `(city_id, date_time)`), so loading the same day twice inserts duplicates.
