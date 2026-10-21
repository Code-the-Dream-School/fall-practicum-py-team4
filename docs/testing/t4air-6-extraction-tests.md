# T4AIR-6: Extraction test notes

I updated the tests to use extract() from pipeline.contracts instead of
fetch_air_pollution_history().

The tests check successful extraction, the returned data structure,
invalid inputs, empty and malformed responses, request failures, and
missing or invalid API configuration.

All API responses are mocked, so these tests don't make real requests
or need a real API key.

## How I checked it

I ran this from the repository root using Python 3.12.10:

python -m pytest services/pipeline/tests -v

All 94 tests passed, including the 20 tests in my extraction test file.

GitHub showed no checks for this PR. The workflow only runs for PRs
targeting main, and mine is set to merge into
feature/T4AIR-5-T4AIR-8-extract-client-lookup-cache.