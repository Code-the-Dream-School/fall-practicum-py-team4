# OpenWeather extraction and lookup caching

The extract modules implement T4AIR-5 and T4AIR-8 and are called by
`pipeline.orchestration.run_extract_stage`.

- `geocode_city(raw_dir, city, country_code, state=None)` returns `Coordinates`
  with `lat`, `lon`, `retrieved_at`, `from_cache`, `country` and `state`.
  Any country works; U.S. state names or codes are also accepted. Whether
  gold stays U.S.-only and gains a `state` field is still a team decision.
- `fetch_air_pollution_history(raw_dir, city, country_code, lat, lon, start, end,
  run_id, pipeline_run_id)` returns a `RawAirPollutionRecord`.
- `raw_dir` is retained for compatibility and may be `None`. These functions
  do not write raw files or persist air-pollution responses.
- History window: orchestration requests the last 60 days plus 7 warm-up days
  for the rolling average (`pipeline.retention.extraction_window`). See the
  [gold data dictionary](gold_data_dictionary.md#retention-60-days).

## Setup

Use Python 3.10 or later. The repository's requirements already include
`requests`, `psycopg[binary]`, and `pytest`.

Set these environment variables in the shell that runs the pipeline. Replace
the placeholders locally; do not commit actual credentials.

```shell
export OPENWEATHER_API_KEY="your-api-key"
export DATABASE_URL="postgresql://username:password@localhost:5432/database_name"
```

`DATABASE_URL` is the cache connection setting introduced by these modules. It
can point to local PostgreSQL or the team's managed PostgreSQL database. Use
the connection options required by that database, such as `sslmode=require`.
The modules read process environment variables; they do not load `.env` files.

Before enabling the cache, apply the additive SQL migration once from the
repository root, using an account allowed to create its table and index:

```shell
psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f services/pipeline/sql/001_geocoding_cache.sql
```

The runtime account needs SELECT, INSERT, UPDATE, and DELETE privileges on
`public.openweather_geocoding_cache`. A missing connection setting or an
unavailable cache produces a warning and falls back to the API.

Optional environment settings:

| Setting | Default | Meaning |
| --- | --- | --- |
| `OPENWEATHER_TIMEOUT_SECONDS` | `15` | HTTP read timeout; connection timeout is 5 seconds. |
| `OPENWEATHER_LOOKUP_TTL_SECONDS` | `2592000` | Successful geocoding responses expire after 30 days. |
| `OPENWEATHER_EMPTY_LOOKUP_TTL_SECONDS` | `3600` | Empty geocoding responses expire after one hour. |

Setting either cache TTL to zero disables reuse and storage for that response
type. `geocode_city(..., force_refresh=True)` bypasses the cached read and
refreshes the entry. `geocode_city(..., use_cache=False)` bypasses cache reads
and writes for the call.

## Cache behavior

Only geocoding lookup responses are cached. Historical air-pollution data is
requested for each extraction. The cache key contains a version, endpoint,
normalized query parameters, and the state filter; it does not contain the API
key. City whitespace and country case are normalized, and equivalent US state
names and postal codes share a key. City-name case is preserved.

The cache stores the original list of geocoding candidates as JSONB together
with its retrieval and expiry times. Expired entries are ignored on reads and
removed during writes. API failures and malformed responses are not cached.
Concurrent writes use an upsert that prevents an older response from replacing
a newer one. Concurrent cache misses may still make duplicate API requests.

Country and optional state filters are checked after retrieval. US state names
or codes are supported; for other countries, supply the full state name used
by the provider. No matching location raises `OpenWeatherError`. Multiple
distinct matching coordinates also raise an error instead of selecting an
arbitrary city. A valid empty API response is cached to avoid repeated misses.

## Raw record contract

`RawAirPollutionRecord` preserves the complete source response in `payload`.
Its metadata contains the city, country, requested coordinates, UTC time
window, run identifiers, retrieval time, endpoint, source, schema version, and
request parameters without the API key. Three views are available for the
open "raw data storage" decision:

| Call | Shape | Use |
| --- | --- | --- |
| `record.payload` | Original OpenWeather response | Store only the source data |
| `record.to_raw_contract()` | `RawAirTrackerData` in `data_contracts.py` (`coord`, `list`, `request_params`, `retrieve_date`) | Matches the team contract |
| `record.to_dict()` | Full envelope with run metadata; timestamps as UTC ISO-8601 strings | Keep lineage with each raw row |

Source payload fields remain
unchanged, including any fields not currently used by the transform.

Historical requests require timezone-aware datetimes, a start on or after
2020-11-27, and an end no later than the current time. Start must precede end
after conversion to Unix seconds. An empty historical `list` is a valid result.
Invalid inputs raise `InputError`; missing or invalid environment settings
raise `ConfigurationError`; source errors raise `OpenWeatherError`.

The shared HTTP boundary uses HTTPS, disables redirects, limits response size
to 10 MiB, and makes at most three attempts for connection failures or HTTP
429/500/502/503/504. Retry-After values are honored for waits up to 30 seconds;
a longer requested wait raises an error so the caller can retry later.
Exception messages omit authenticated URLs and response bodies.

## Validation and remaining integration

Run from the repository root with dependencies installed:

```shell
python -m pytest services/pipeline/tests
python -m compileall services
```

The extract tests mock HTTP and PostgreSQL connections. They cover input and
response validation, raw metadata, retries, credential exclusion, lookup cache
hits and expiry, ambiguity, and database failure handling.
`test_orchestration.py` imports the orchestration module directly and runs a
full job with the real extractors over mocked HTTP.

## Orchestration

`run_pipeline_job(config, transform=..., load_raw=..., load_gold=..., run_store=...)`
takes the data_contracts input configuration:

```python
{"cities": ["new york", "london, gb", "charlotte, nc, us", "28202"],
 "date_range": "",          # "" = last 60 days (+7 warm-up); or "MM/DD/YYYY - MM/DD/YYYY"
 "daily": True,             # one reading per day at time_of_day (UTC)
 "time_of_day": "12:00"}
```

A city can be a bare name (provider's top match), `city, country`,
`city, state, country`, or a ZIP code. A missing or empty `cities` stops the
run with `ValueError`.

It runs `geocodes` -> `extract` -> `load_raw(raw_records)` ->
`transform(raw_records)` -> enrich (category, score, rolling AQI, 60-day cut)
-> `load_gold`. Those names and signatures are the ones in `data_contracts.py`
and live in `pipeline/contracts.py`; `load_raw` and `transform` are passed in
until T4AIR-15 and T4AIR-16 are merged. Raw records are `RawAirTrackerData`
dicts plus `city` and `country`. Deployment target is AWS (Lambda +
EventBridge + RDS PostgreSQL, logs in CloudWatch), per
`docs/refined_architecture_diagram.md`; nothing here depends on Azure.

Each run produces one `pipeline_runs` row:

```json
{"id": 101, "status": "succeeded", "records_added": 1440, "runs_time": 18.52, "created_at": "2026-10-19T20:00:00Z"}
```

These are the columns of the Supabase `pipeline_runs` table (checked
2026-10-20). `run_store` needs `save(row) -> id`. `SupabaseRunStore(client)`
inserts the row into `pipeline_runs` and returns the database id; the default
`LoggingRunStore` only logs it. Gold rows for the Supabase `gold_table` come
from `pipeline.transform.gold_rows.to_gold_rows`; see the column mapping and
gaps in the [gold data dictionary](gold_data_dictionary.md#supabase-gold_table-mapping).

This does not verify a live OpenWeather call, a live PostgreSQL round trip,
or the real transform and loaders.
