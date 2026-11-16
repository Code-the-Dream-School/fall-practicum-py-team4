
import json
import logging
import os
from pathlib import Path
import re

from .openrouter_client import generate_summary

PROMPT = (
    Path(__file__).resolve().parent
    / 'air_quality_summary.txt'
).read_text(encoding='utf-8')

PROMPT_VERSION = 'v1'
BATCH_SIZE = 24
QUERY_SIZE = 1000

FIELDS = (
    'aqi',
    'sentiment_label',
    'co',
    'pm2_5',
    'aqi_rolling_7d',
    'pm2_5_rolling_7d'
)


def valid_summary(summary):
    if not isinstance(summary, str) or not 1 <= len(summary.strip()) <= 500:
        return False

    text = re.sub(r'(?<=\d)\.(?=\d)', '', summary)
    sentences = re.findall(r'[.!?]+', text)

    return 1 <= len(sentences) <= 3


def valid_record(row):
    return (
        row.get('aqi') in (1, 2, 3, 4, 5)
        and any(row.get(key) is not None for key in ('co', 'pm2_5'))
    )


def enrich_batch(batch):
    records = [
        {
            'id': row['id'],
            **{
                key: row[key]
                for key in FIELDS
                if row.get(key) is not None
            }
        }
        for row in batch
    ]

    prompt = (
        f'{PROMPT}\n\n'
        f'Measurements:\n{json.dumps({"records": records})}'
    )

    expected_ids = {row['id'] for row in batch}

    for attempt in range(2):
        try:
            response = generate_summary(prompt)

            if isinstance(response, str):
                response = json.loads(response)

            if not isinstance(response, dict):
                raise ValueError('Expected a JSON object')

            items = response.get('results')

            if not isinstance(items, list):
                raise ValueError('Missing results array')

            summaries = {}

            for item in items:
                if not isinstance(item, dict):
                    raise ValueError('Invalid result object')

                row_id = item.get('id')
                summary = item.get('llm_response')

                if row_id not in expected_ids:
                    raise ValueError(f'Unexpected ID: {row_id}')

                if row_id in summaries:
                    raise ValueError(f'Duplicate ID: {row_id}')

                if valid_summary(summary):
                    summaries[row_id] = summary.strip()
                else:
                    summaries[row_id] = None

            return summaries

        except Exception as exc:
            logging.warning(
                'Batch attempt %s failed: %s',
                attempt + 1,
                exc
            )

    return {}


def update_batch(supabase, responses):
    if not responses:
        return

    if len(responses) > BATCH_SIZE:
        raise ValueError('Maximum 24 records per batch')

    ids = [row['id'] for row in responses]

    if len(ids) != len(set(ids)):
        raise ValueError('Duplicate row IDs in batch')

    supabase.table('gold_air_data').upsert(
        responses,
        on_conflict='id'
    ).execute()


def run_enrichment(supabase):
    results = {'success': 0}

    metadata = {
        'llm_model': os.environ['MODEL_NAME'],
        'prompt_version': PROMPT_VERSION
    }

    last_id = None

    while True:
        query = (
            supabase.table('gold_air_data')
            .select('id,aqi,sentiment_label,co,pm2_5,'
                    'aqi_rolling_7d,pm2_5_rolling_7d')
            .is_('llm_response', 'null')
            .order('id')
            .limit(QUERY_SIZE)
        )

        if last_id is not None:
            query = query.gt('id', last_id)

        rows = query.execute().data or []

        if not rows:
            break

        last_id = rows[-1]['id']

        for start in range(0, len(rows), BATCH_SIZE):
            batch = rows[start:start + BATCH_SIZE]

            valid_rows = [
                row for row in batch
                if valid_record(row)
            ]

            summaries = enrich_batch(valid_rows) if valid_rows else {}

            responses = [
                {
                    'id': row['id'],
                    'llm_response': summaries.get(row['id'])
                }
                for row in batch
            ]

            try:
                update_batch(supabase, responses)

                results['success'] += sum(
                    response['llm_response'] is not None
                    for response in responses
                )

            except Exception as exc:
                logging.exception(
                    'Database batch update failed: %s',
                    exc
                )

    return results, metadata
