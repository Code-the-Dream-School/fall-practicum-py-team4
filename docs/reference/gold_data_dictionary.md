# Gold data dictionary (T4AIR-19)

Every gold field in `data_contracts.py`: what it means, its type and unit,
where it comes from, and whether it is required. Includes the derived fields
from T4AIR-20 (category, score) and T4AIR-21 (rolling average).

The contract is nested Pydantic data. The Supabase `gold_table` is flat (one
row per reading) and uses different names; see
[Supabase gold_table mapping](#supabase-gold_table-mapping). T4AIR-22 owns
the physical tables.
`[]` means "each element of the list". **Required** means present in every
completed gold record; **nullable** means present but may be `null`.

## OpenWeather air pollution (`GoldSchema`)

One record per city per pipeline run; `readings` holds that city's
observations for the last 60 days (see [Retention](#retention-60-days)).

| Field path | Meaning | Type | Unit / format | Comes from | Required |
| --- | --- | --- | --- | --- | --- |
| `retrieve_date` | Day the API response was fetched | `datetime.date` | `YYYY-MM-DD` (UTC) | UTC date of `RawAirPollutionRecord.retrieved_at` (raw `retrieve_date`) | Yes |
| `coordinates` | Point the readings belong to | `Coordinates` | object `{lon, lat}` | Raw `coord` | Yes |
| `coordinates.lon` | Longitude, east positive | `float` | decimal degrees, -180 to 180 | Raw `coord.lon` (from geocoding) | Yes |
| `coordinates.lat` | Latitude, north positive | `float` | decimal degrees, -90 to 90 | Raw `coord.lat` (from geocoding) | Yes |
| `city` | City the readings were requested for | `str` | lowercase, exactly as written in the input `cities` list (e.g. `new york`, `charlotte, nc, us`, `28202`) | Raw `city`, which orchestration adds from the input; the pollution API does not return it. `enrich_gold_record` lowercases it | Yes |
| `country` | Country of the city | `str` or `null` | lowercase ISO 3166 code, e.g. `us`, `gb` | `geocodes()` result, carried on the raw record; `enrich_gold_record` lowercases it | No (nullable) |
| `readings` | Observations for this city | `list[GoldListItem]` | list, sorted by `date_time`; may be empty. One per hour, or one per day at `time_of_day` when input `daily` is true (the contract default) | Each accepted row of raw `list` | Yes |
| `readings[].date_time` | Time the observation represents | `datetime.datetime` | UTC, timezone-aware, ISO-8601 | Raw `list[].dt` (Unix seconds) via `datetime.fromtimestamp(dt, tz=timezone.utc)` | Yes |
| `readings[].aqi` | OpenWeather air quality index | `int` | 1-5, 5 is worst | Raw `list[].main.aqi` | Yes |
| `readings[].components` | Pollutant concentrations | `Components` | object, eight pollutants below | Raw `list[].components` | Yes |
| `readings[].components.co` | Carbon monoxide | `float` | µg/m³ | Raw `components.co` | Yes |
| `readings[].components.no` | Nitrogen monoxide | `float` | µg/m³ | Raw `components.no` | Yes |
| `readings[].components.no2` | Nitrogen dioxide | `float` | µg/m³ | Raw `components.no2` | Yes |
| `readings[].components.o3` | Ozone | `float` | µg/m³ | Raw `components.o3` | Yes |
| `readings[].components.so2` | Sulphur dioxide | `float` | µg/m³ | Raw `components.so2` | Yes |
| `readings[].components.pm2_5` | Fine particulate matter (≤ 2.5 µm) | `float` | µg/m³ | Raw `components.pm2_5` | Yes |
| `readings[].components.pm10` | Coarse particulate matter (≤ 10 µm) | `float` | µg/m³ | Raw `components.pm10` | Yes |
| `readings[].components.nh3` | Ammonia | `float` | µg/m³ | Raw `components.nh3` | Yes |
| `readings[].aqi_category` | Label for the AQI | `Literal` `str` | `Good`, `Fair`, `Moderate`, `Poor`, `Very Poor` | **Derived** (T4AIR-20): `aqi_to_category(aqi)` | Yes |
| `readings[].risk_score` | PM2.5 as a percentage of the WHO reference | `float` | percent, ≥ 0, not capped | **Derived** (T4AIR-20): `pm2_5 / 15 * 100` | Yes |
| `readings[].aqi_rolling_7d` | Mean AQI over the 7 days ending at this reading | `float` or `null` | 1.0-5.0 | **Derived** (T4AIR-21): `add_rolling_aqi(readings)` | Yes, nullable |

All eight pollutant values are µg/m³ as delivered by OpenWeather, CO included.
Field units: [OpenWeather Air Pollution API](https://openweathermap.org/api/air-pollution).

### `aqi_category` (T4AIR-20)

| `aqi` | `aqi_category` |
| --- | --- |
| 1 | Good |
| 2 | Fair |
| 3 | Moderate |
| 4 | Poor |
| 5 | Very Poor |

Labels keep OpenWeather's capitalisation, an intentional exception to the
contract's "all strings lowercase" rule. Integral floats (`2.0`) are accepted;
anything else (0, 6, 2.5, `"2"`, `True`, `None`, NaN) raises `ValueError`.

### `risk_score` (T4AIR-20)

`risk_score = pm2_5 / 15 * 100`, where 15 µg/m³ is the WHO 2021 24-hour PM2.5
guideline ([WHO guidelines, table 3.6](https://www.ncbi.nlm.nih.gov/books/NBK574591/table/ch3.tab6/)).

| PM2.5 (µg/m³) | `risk_score` | Reads as |
| --- | --- | --- |
| 0 | 0 | none reported |
| 7.5 | 50 | half the WHO reference |
| 15 | 100 | at the WHO reference |
| 30 | 200 | twice the WHO reference |

Dashboard label: **PM2.5 vs WHO limit (%)**. It is a comparison with one number,
not a health probability or the US EPA AQI, and an hourly value cannot prove
24-hour compliance. Stored unrounded; round for display. Negative, missing or
non-numeric PM2.5 raises `ValueError` (never silently 0). The constant lives in
`PM25_REFERENCE_UG_M3`; if it changes, recompute stored scores.

The category comes from OpenWeather's AQI, which looks at every pollutant; the
score looks at PM2.5 only. A reading can be `Poor` with a low score (e.g. high
ozone).

### `aqi_rolling_7d` (T4AIR-21)

- **Window:** 7 days of time, `(date_time - 7 days, date_time]`, per city.
  It is time-based, so hourly data averages ~168 readings and daily data 7.
- **Why 7 days:** hourly AQI jumps around with traffic and weather; a week
  smooths that out and covers both weekdays and the weekend, so the dashboard
  can show whether a city's air is trending better or worse.
- **First few days:** `null` until the city has a full 7 days of history
  before the reading. We chose `null` over a partial average because a mean of
  a few hours would look as trustworthy as a full week. In normal runs this
  never shows, because each run fetches 7 extra warm-up days
  (see [Retention](#retention-60-days)); it appears for a city whose history
  is shorter, e.g. at the start of OpenWeather's archive.
- **Gaps:** missing hours are skipped; the mean uses the readings present.
- **Grouping:** one `GoldSchema` record = one city, so readings are never mixed
  across cities. Duplicate timestamps raise `ValueError` (T4AIR-16 should
  dedupe first).
- Stored unrounded.

## Supabase gold_table mapping

Checked read-only in the Supabase dashboard (project
`fall-practicum-py-team4`) on 2026-10-20. `to_gold_rows(record)` in
`pipeline/transform/gold_rows.py` turns one enriched record into these rows.

| `gold_table` column | Type | Nullable | Contract path |
| --- | --- | --- | --- |
| `id` | `int8` | no (primary key) | assigned by the database |
| `longitude` | `float8` | yes | `coordinates.lon` |
| `latitude` | `float8` | yes | `coordinates.lat` |
| `city` | `text` | yes | `city` |
| `country` | `text` | yes | `country` |
| `co` | `float8` | yes | `readings[].components.co` |
| `pm2_5` | `float8` | yes | `readings[].components.pm2_5` |
| `no2` | `float8` | yes | `readings[].components.no2` |
| `date` | `timestamptz` | yes | `readings[].date_time` |
| `retrieve_date` | `timestamptz` | yes | `retrieve_date` (sent as UTC midnight) |
| `aqi` | `int4` | yes | `readings[].aqi` |
| `sentiment_label` | `text` | **no** | `readings[].aqi_category` |
| `running_average` | `float8` | yes | `readings[].aqi_rolling_7d` |

Gaps for T4AIR-22 (nothing was changed in Supabase):

- No column for `risk_score` (T4AIR-20), so the score is computed but not
  stored. Suggested: `risk_score float8`.
- No columns for `no`, `o3`, `so2`, `pm10`, `nh3`.
- No unique key on (`city`, `date`) or (`latitude`, `longitude`, `date`), so
  re-running a day inserts duplicates. `raw_table` already has
  `raw_table_date_lat_lon_idx` for the same purpose.
- Column names differ from the contract (`sentiment_label`/`aqi_category`,
  `running_average`/`aqi_rolling_7d`, `date`/`date_time`). The mapping above
  bridges them; the team can rename either side later.

`raw_table` (`id`, `longitude`, `latitude`, `hours`, `date`, `data jsonb`)
matches T4AIR-15's `load_raw`, which stores the OpenWeather payload in `data`.
`pipeline_runs` (`id int8`, `status text not null`, `records_added int4`,
`runs_time float8`, `created_at timestamptz`) matches `PipelineRunLog`;
`SupabaseRunStore` inserts the row and reads back the database `id`.

## Retention (60 days)

Defined in `services/pipeline/src/pipeline/retention.py`:

1. **Initial load and daily updates use the same path.** With an empty
   input `date_range` (the default) every run requests `now - 67 days` to
   `now` (60 kept + 7 warm-up) with one history call per city. Re-pulling
   keeps the code simple and the load idempotent. If a `date_range` is given
   it is requested as-is (clamped to OpenWeather's archive start, 11/27/2020),
   but gold still keeps only the last 60 days.
2. **Transform** computes the rolling average over all 67 days, then
   `enrich_gold_record(record, now=...)` keeps only readings newer than
   `now - 60 days`.
3. **Removal of older rows** in the database belongs to the gold loader /
   T4AIR-22, e.g. `DELETE FROM <gold table> WHERE date_time <= now() - interval '60 days'`
   after each upsert keyed on city + `date_time`.

## Geographic lookup (`GoldenMateo`)

Separate from the pollution readings; no derived fields. Raw source:
`pipeline.extract.open_meteo.fetch_location(name)`; gold:
`pipeline.transform.locations.to_gold_locations(raw)`. Strings are lowercased.
A result missing any required field is dropped (contract invalid-row rule).

| Field path | Meaning | Type | Unit / format | Comes from | Required |
| --- | --- | --- | --- | --- | --- |
| `locations` | Selected geocoding results | `list[Locations]` | list | Accepted Open-Meteo `results[]` | Yes |
| `locations[].name` | Place name | `str` | lowercase | `results[].name` | Yes |
| `locations[].lat` | Latitude | `float` | decimal degrees, -90 to 90 | `results[].latitude` | Yes |
| `locations[].lon` | Longitude | `float` | decimal degrees, -180 to 180 | `results[].longitude` | Yes |
| `locations[].elevation` | Height above sea level | `float` | metres | `results[].elevation` | Yes |
| `locations[].country` | Country name | `str` | lowercase full name, not ISO code | `results[].country` | Yes |
| `locations[].region` | Continent | `str` | lowercase, e.g. `europe`, `america`, `asia` | Part of `results[].timezone` before the `/` (`Europe/Paris` -> `europe`), which matches the contract example | Yes |
| `locations[].population` | Population | `int` | people | `results[].population` | Yes |

Open question (meeting 10/19): if the team keeps a **U.S.-only** scope, gold
should gain a `state` field. The extractor already returns it:
`geocode_city(...)` now sets `Coordinates.state` and `Coordinates.country`.

## Run log (`pipeline_runs`)

Not a gold table, but every run writes one row in this shape
(`PipelineRunLog` in `pipeline/orchestration/__init__.py`):

| Field | Meaning | Type | Unit / format |
| --- | --- | --- | --- |
| `id` | Run id | `int8` | assigned by the database on insert |
| `status` | Outcome | `str` | `succeeded` or `failed` |
| `records_added` | Gold readings handed to the gold loader | `int` | count; 0 on failure |
| `runs_time` | Wall-clock duration | `float` | seconds, 2 decimals |
| `created_at` | Run start | `str` | UTC ISO-8601, `2026-10-19T20:00:00Z` |
