import json
import logging
import os
import re
from pathlib import Path
import time

from .openrouter_client import generate_summary

PROMPT = (
    Path(__file__).resolve().parent
    / 'air_quality_summary.txt'
).read_text(encoding='utf-8')

PROMPT_VERSION = 'v2'
BATCH_SIZE = 24
QUERY_SIZE = 1000

FIELDS = (
    'aqi',
    'sentiment_label',
    'co',
    'pm2_5',
    'aqi_rolling_7d',
    'pm2_5_rolling_7d',
)


class EnrichmentBatchError(Exception):
    """LLM batch failed validation."""


class EnrichmentDatabaseError(Exception):
    """Database operation failed."""


class EnrichmentConfigurationError(Exception):
    """Required enrichment configuration is missing."""


def valid_summary(summary):
    if not isinstance(summary, str):
        return False

    if not 1 <= len(summary.strip()) <= 500:
        return False

    text = re.sub(r'(?<=\d)\.(?=\d)', '', summary)
    sentences = re.findall(r'[.!?]+', text)

    return 1 <= len(sentences) <= 3


def parse_response(response):
    if isinstance(response, str):
        cleaned = response.strip()

        if cleaned.startswith('```'):
            cleaned = re.sub(
                r'^```(?:json)?\s*',
                '',
                cleaned,
                flags=re.IGNORECASE
            )
            cleaned = re.sub(r'\s*```$', '', cleaned)

        response = json.loads(cleaned)

    if not isinstance(response, dict):
        raise ValueError('Expected JSON object')

    return response


def enrich_batch(batch):
    if not batch or len(batch) > BATCH_SIZE:
        raise ValueError('Invalid batch size')

    records = [
        {
            'position': position,
            **{
                key: row[key]
                for key in FIELDS
                if row.get(key) is not None
            }
        }
        for position, row in enumerate(batch)
    ]

    prompt = (
        f'{PROMPT}\n\nMeasurements:\n'
        f'{json.dumps({"records": records})}'
    )

    expected_positions = set(range(len(batch)))

    try:
        response = generate_summary(prompt)
        response_data = parse_response(response)

        items = response_data.get('results')

        if not isinstance(items, list):
            raise ValueError('Missing results array')

        if len(items) != len(batch):
            raise ValueError(
                f'Expected {len(batch)} results, '
                f'received {len(items)}'
            )

        summaries = {}

        for item in items:
            if not isinstance(item, dict):
                raise ValueError('Invalid result object')

            position = item.get('position')
            summary = item.get('llm_response')

            if (
                type(position) is not int
                or position not in expected_positions
            ):
                raise ValueError(
                    f'Unexpected position: {position}'
                )

            if position in summaries:
                raise ValueError(
                    f'Duplicate position: {position}'
                )

            if not valid_summary(summary):
                raise ValueError(
                    f'Invalid summary at position {position}'
                )

            summaries[position] = summary.strip()

        if set(summaries) != expected_positions:
            raise ValueError('Missing expected positions')

        return [
            {
                'id': row['id'],
                'llm_response': summaries[position]
            }
            for position, row in enumerate(batch)
        ]

    except (ValueError, KeyError) as exc:
        logging.exception('LLM batch validation failed')
        raise EnrichmentBatchError(
            f'LLM batch validation failed: {exc}'
        ) from exc


def update_batch(supabase, responses):
    if not responses:
        raise ValueError('Empty batch')

    if len(responses) > BATCH_SIZE:
        raise ValueError('Maximum 24 records per batch')

    ids = [row['id'] for row in responses]

    if len(ids) != len(set(ids)):
        raise ValueError('Duplicate row IDs')

    if any(
        not valid_summary(row.get('llm_response'))
        for row in responses
    ):
        raise ValueError('Invalid summary in batch')

    try:
        supabase.rpc(
            'save_enrichment_batch',
            {'p_responses': responses}
        ).execute()

    except Exception as exc:
        logging.exception('Failed to save enrichment batch')
        raise EnrichmentDatabaseError(
            f'Failed to save enrichment batch: {exc}'
        ) from exc


def fetch_records(supabase, last_id):
    try:
        query = (
            supabase.table('gold_air_data')
            .select(
                'id,aqi,sentiment_label,co,pm2_5,'
                'aqi_rolling_7d,pm2_5_rolling_7d'
            )
            .or_('llm_response.is.null,llm_response.eq.')
            .order('id')
            .limit(QUERY_SIZE)
        )

        if last_id is not None:
            query = query.gt('id', last_id)

        response = query.execute()

        if response.data is None:
            raise ValueError('Supabase returned no data payload')

        return response.data

    except Exception as exc:
        logging.exception('Failed to fetch enrichment records')
        raise EnrichmentDatabaseError(
            f'Failed to fetch enrichment records: {exc}'
        ) from exc


def run_enrichment(supabase):
    llm_model = os.environ.get('OPENROUTER_MODEL')

    success = 0
    last_id = None

    try:
        if not llm_model:
            raise EnrichmentConfigurationError(
                'OPENROUTER_MODEL is not configured'
            )

        if not os.environ.get('OPENROUTER_API_KEY'):
            raise EnrichmentConfigurationError(
                'OPENROUTER_API_KEY is not configured'
            )

        while True:
            rows = fetch_records(supabase, last_id)

            if not rows:
                break

            last_id = rows[-1]['id']

            total_batches = (len(rows) + BATCH_SIZE - 1) // BATCH_SIZE

            for batch_idx, start in enumerate(
                range(0, len(rows), BATCH_SIZE),
                start=1
            ):
                batch = rows[start:start + BATCH_SIZE]

                print(
                    f"Batch {batch_idx}/{total_batches}: "
                    f"calling OpenRouter ({len(batch)} rows)..."
                )

                t0 = time.monotonic()
                responses = enrich_batch(batch)

                print(
                    f"Batch {batch_idx}/{total_batches}: "
                    f"OpenRouter responded in "
                    f"{time.monotonic() - t0:.1f}s. "
                    f"Saving to Supabase..."
                )

                t1 = time.monotonic()
                update_batch(supabase, responses)

                success += len(responses)

                print(
                    f"Batch {batch_idx}/{total_batches}: "
                    f"saved in {time.monotonic() - t1:.1f}s "
                    f"(total saved: {success})."
                )

    except Exception:
        logging.exception(
            'Enrichment failed after %s successfully saved records',
            success
        )
        raise

    return {
        'success': success,
        'llm_model': llm_model,
        'prompt_version': PROMPT_VERSION
    }