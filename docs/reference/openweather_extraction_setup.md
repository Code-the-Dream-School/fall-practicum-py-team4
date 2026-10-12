# OpenWeather extraction and lookup caching

The extract modules implement T4AIR-5 and T4AIR-8 using the function signatures
already called by `pipeline.orchestration.run_extract_stage`.

- `geocode_city(raw_dir, city, country_code, state=None)` returns `Coordinates`
  with `lat`, `lon`, `retrieved_at`, and `from_cache` attributes.
- `fetch_air_pollution_history(raw_dir, city, country_code, lat, lon, start, end,
  run_id, pipeline_run_id)` returns a `RawAirPollutionRecord`.
- `raw_dir` is retained for compatibility. These functions do not write raw
  files or persist air-pollution responses in PostgreSQL.

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
request parameters without the API key. `to_dict()` produces a dictionary with
UTC ISO-8601 strings for the metadata timestamps. Source payload fields remain
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
hits and expiry, ambiguity, and database failure handling. One test executes
the repository's actual `run_extract_stage` function with the new extractors
and a stubbed city reader. It loads that function alone because other runner
imports are not yet implemented on `main`.

This does not verify a live OpenWeather call, a live PostgreSQL round trip, or
the complete pipeline. The configuration, city reader, run tracking, storage,
and transform modules imported by orchestration remain separate integration
work. In particular, the proposed raw record shape must be connected to the
team's transform and PostgreSQL raw persistence before full pipeline use.
