
import logging
import os
from pathlib import Path
from .openrouter_client import generate_summary

PROMPT = (Path(__file__).resolve().parents[2] / 'prompts' / 'air_quality_summary.txt').read_text(encoding='utf-8')
PROMPT_VERSION = 'v1'
FIELDS = ('aqi', 'sentiment_label', 'co', 'pm2_5', 'aqi_rolling_7d', 'pm2_5_rolling_7d')


def valid_summary(summary):
    if not isinstance(summary, str) or not 1 <= len(summary.strip()) <= 500:
        return False
    return 1 <= sum(summary.count(mark) for mark in '.!?') <= 3


def run_enrichment(supabase, run_id):
    rows = supabase.table('gold_air_data').select('*').is_('llm_summary', 'null').execute().data
    results = {'success': 0, 'skipped': 0, 'failed': 0}

    # Store model information in the existing pipeline run
    supabase.table('pipeline_runs').update({
        'llm_model': os.environ['OPENROUTER_MODEL'],
        'prompt_version': PROMPT_VERSION
    }).eq('id', run_id).execute()

    for row in rows:
        if row.get('aqi') not in (1, 2, 3, 4, 5) or all(row.get(key) is None for key in ('co', 'pm2_5')):
            results['skipped'] += 1
            continue

        measurements = '\n'.join(
            f'{key}: {row[key]}'
            for key in FIELDS
            if row.get(key) is not None
        )
        prompt = f'{PROMPT}\n\nMeasurements:\n{measurements}'

        try:
            for attempt in range(2):
                try:
                    summary = generate_summary(prompt)
                    if valid_summary(summary):
                        break
                    raise ValueError('Invalid summary format')
                except Exception:
                    if attempt == 1:
                        raise

            supabase.table('gold_air_data').update({
                'llm_summary': summary.strip(),
                'pipeline_run_id': run_id
            }).eq('id', row['id']).execute()

            results['success'] += 1

        except Exception as exc:
            results['failed'] += 1
            logging.exception(
                'Enrichment failed for gold record %s: %s',
                row.get('id'), exc
            )

    return results
