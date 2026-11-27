# AWS Lambda ingestion

`pipeline.orchestration.lambda_handler.lambda_handler` is the Lambda entry point for a single city and date. It calls the existing geocoding/cache, raw-load, gold-city, air-extraction, air-transform, rolling-average, and gold-air loaders; it does not depend on Prefect or read the cities file. A city not already in `gold_cities` is geocoded and inserted before air-pollution processing. EventBridge can invoke it with one work item per city/date, allowing AWS retries and concurrency controls to operate on small units.

The handler returns a JSON-serializable success object with counts for each extraction, raw load, transform, rolling-average, and gold load stage. It calculates seven-day averages for AQI and PM2.5 using historical gold readings, then persists the current batch to `gold_air_data`. On failure it logs the failed stage and partial counts, then re-raises the exception so Lambda and EventBridge report a failed invocation. If `date` is omitted, the handler processes yesterday in UTC. LLM enrichment is intentionally not called here; it can be triggered by a separate Lambda.

## Event shape

Configure the EventBridge target with an input such as:

```json
{
  "city": "New York",
  "date": "2025-01-01"
}
```

The same object may be placed under the EventBridge event's `detail` property. A scheduled rule can omit `date` to process the previous UTC day. Configure one target event per city; for cities already loaded, coordinates and ID are retrieved from the Supabase geocoding cache. For a new city, the handler fetches and saves those details first.

## Configure AWS

1. Create SecureString parameters in Systems Manager Parameter Store for the OpenWeather API key, Supabase URL, and Supabase service key. Use names appropriate to the environment, for example `/city-air/dev/openweather-api-key`, `/city-air/dev/supabase-url`, and `/city-air/dev/supabase-key`.
2. Set these Lambda environment variables to those parameter names:
   - `OPENWEATHER_API_KEY_SSM_PARAMETER`
   - `SUPABASE_URL_SSM_PARAMETER`
   - `SUPABASE_KEY_SSM_PARAMETER`
3. Give the Lambda execution role `ssm:GetParameter` on only those parameter ARNs and `kms:Decrypt` for the customer-managed key if the SecureStrings use one. The role also needs the standard CloudWatch Logs permissions.
4. Ensure the function can reach OpenWeather and Supabase. If it runs in a private VPC, configure appropriate outbound network access (for example, NAT).
5. Upload the deployment ZIP, set the handler to `pipeline.orchestration.lambda_handler.lambda_handler`, choose a Python runtime matching the package build (Python 3.12), and set an adequate timeout/memory for the OpenWeather request and Supabase write.
6. Create an EventBridge schedule rule, choose this Lambda as the target, and provide the event input above. Configure the target's retry policy and a dead-letter queue to retain events that exhaust retries. Use one invocation per city/date; avoid passing a large backfill into one Lambda invocation.

Secrets are fetched at invocation time from SSM and are not logged. The handler sets them in the process environment because the existing extraction and database code reads its credentials from environment variables. Do not add a `.env` file to the Lambda package.

## Build and upload the package

The package includes the `pipeline` and `contracts` source trees and only the Lambda-specific Python dependencies. Native dependencies must be built for the same operating system, Python version, and CPU architecture as the Lambda. For the standard `x86_64` Python 3.12 runtime, run from the repository root:

```sh
docker run --rm --platform linux/amd64 \
  -v "$PWD":/var/task -w /var/task/services/pipeline \
  public.ecr.aws/lambda/python:3.12 \
  python build_lambda_package.py
```

For an `arm64` Lambda, use `--platform linux/arm64` instead. The generated ZIP is `services/pipeline/build/city_air_tracker_lambda.zip`; upload it through the Lambda console, AWS CLI, or your deployment pipeline. Re-run the command after changing application code or `requirements-lambda.txt`.

## Local checks

Install the project's test dependencies and run the handler tests from the repository root:

```sh
python -m pip install -r requirements.txt -r services/pipeline/requirements-lambda.txt
python -m pytest services/pipeline/tests/orchestration/test_lambda_handler.py -q
```

These tests call the handler with a sample event while mocking SSM, Supabase, and the external API/stages, so they do not require AWS credentials or modify a database. To exercise a live invocation, configure valid AWS credentials and the three SSM-name environment variables, then call `lambda_handler` with the event object shown above; this performs real API and database operations.
