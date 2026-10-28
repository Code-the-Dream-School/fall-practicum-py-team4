# T4AIR-6: Extraction test notes

I updated my air pollution tests and added geocoding tests to match the
latest extract functions. They check the returned data, invalid inputs,
empty results, and errors. All API calls are mocked, so no real key is needed.

I ran:
python -m pytest services/pipeline/tests -v

All 20 tests passed: 11 air pollution tests, 8 geocoding tests, and the
existing placeholder test.