import json
import logging
from unittest.mock import MagicMock

import pytest

import src.pipeline.llm_enrich.enrich as enrich

@pytest.fixture
def supabase():
    return MagicMock()


@pytest.fixture
def configured_env(monkeypatch):
    monkeypatch.setenv('OPENROUTER_MODEL', 'test-gemma')
    monkeypatch.setenv('OPENROUTER_API_KEY', 'test-key')


def mock_pages(supabase, pages):
    query = MagicMock()
    for method in ('select', 'or_', 'order', 'limit', 'gt', 'is_'):
        getattr(query, method).return_value = query
    query.execute.side_effect = [MagicMock(data=page) for page in pages]
    supabase.table.return_value = query
    return query


def sample_rows(n, start=1):
    return [{'id': i, 'aqi': 1, 'co': 100} for i in range(start, start + n)]


def fake_responses(batch):
    return [{'id': row['id'], 'llm_response': 'Air quality is good.'} for row in batch]


def fake_enrichment(batch):
    return fake_responses(batch), 'test-gemma'


# Summary validation

def test_valid_summary():
    assert enrich.valid_summary('Air quality is good.')
    assert enrich.valid_summary('PM2.5 is elevated. Air quality is poor.')


@pytest.mark.parametrize('summary', [None, '', '   ', 42, 'No ending punctuation',
                                     'One. Two. Three. Four.', 'A' * 501 + '.'])
def test_invalid_summary(summary):
    assert not enrich.valid_summary(summary)


# Response parsing

def test_parse_response_dict():
    data = {'results': []}
    assert enrich.parse_response(data) == data


def test_parse_response_json_string():
    assert enrich.parse_response('{"results": []}') == {'results': []}


def test_parse_response_code_fence():
    assert enrich.parse_response('```json\n{"results": []}\n```') == {'results': []}


def test_parse_response_invalid_json():
    with pytest.raises(json.JSONDecodeError):
        enrich.parse_response('Invalid JSON')


def test_parse_response_not_object():
    with pytest.raises(ValueError, match='Expected JSON object'):
        enrich.parse_response('["not an object"]')


# LLM batch validation

def test_enrich_batch_matches_positions(monkeypatch):
    batch = [{'id': 101, 'aqi': 1, 'co': 100}, {'id': 102, 'aqi': 4, 'pm2_5': 40}]

    def fake_generate(prompt):
        records = json.loads(prompt.split('Measurements:\n')[1])['records']
        assert [row['position'] for row in records] == [0, 1]
        assert records[0]['aqi'] == 1
        assert records[1]['aqi'] == 4
        return json.dumps({'results': [
            {'position': 1, 'llm_response': 'Air quality is poor.'},
            {'position': 0, 'llm_response': 'Air quality is good.'},
        ]}), 'test-gemma'

    monkeypatch.setattr(enrich, 'generate_summary', fake_generate)
    assert enrich.enrich_batch(batch) == ([
        {'id': 101, 'llm_response': 'Air quality is good.'},
        {'id': 102, 'llm_response': 'Air quality is poor.'},
    ], 'test-gemma')


def test_enrich_batch_invalid_summary(monkeypatch):
    monkeypatch.setattr(enrich, 'generate_summary', lambda prompt: (json.dumps({
        'results': [{'position': 0, 'llm_response': 'Invalid summary'}]
    }), 'test-gemma'))
    with pytest.raises(enrich.EnrichmentBatchError, match='Invalid summary'):
        enrich.enrich_batch(sample_rows(1))


def test_enrich_batch_does_not_retry(monkeypatch):
    calls = []

    def fake_generate(prompt):
        calls.append(prompt)
        return 'Invalid JSON', 'test-gemma'

    monkeypatch.setattr(enrich, 'generate_summary', fake_generate)
    with pytest.raises(enrich.EnrichmentBatchError):
        enrich.enrich_batch(sample_rows(1))
    assert len(calls) == 1


def test_enrich_batch_rejects_unknown_position(monkeypatch):
    monkeypatch.setattr(enrich, 'generate_summary', lambda prompt: (json.dumps({
        'results': [{'position': 999, 'llm_response': 'Air quality is good.'}]
    }), 'test-gemma'))
    with pytest.raises(enrich.EnrichmentBatchError, match='Unexpected position'):
        enrich.enrich_batch(sample_rows(1))


def test_enrich_batch_rejects_duplicate_positions(monkeypatch):
    monkeypatch.setattr(enrich, 'generate_summary', lambda prompt: (json.dumps({
        'results': [
            {'position': 0, 'llm_response': 'Air quality is good.'},
            {'position': 0, 'llm_response': 'Air quality is poor.'},
        ]
    }), 'test-gemma'))
    with pytest.raises(enrich.EnrichmentBatchError, match='Duplicate position'):
        enrich.enrich_batch(sample_rows(2))


def test_enrich_batch_missing_results(monkeypatch):
    monkeypatch.setattr(enrich, 'generate_summary', lambda prompt: ('{}', 'test-gemma'))
    with pytest.raises(enrich.EnrichmentBatchError, match='Missing results array'):
        enrich.enrich_batch(sample_rows(1))


def test_enrich_batch_wrong_result_count(monkeypatch):
    monkeypatch.setattr(enrich, 'generate_summary', lambda prompt: ('{"results": []}', 'test-gemma'))
    with pytest.raises(enrich.EnrichmentBatchError, match='Expected 1 results'):
        enrich.enrich_batch(sample_rows(1))


@pytest.mark.parametrize('n', [0, 25])
def test_enrich_batch_rejects_invalid_size(n):
    with pytest.raises(ValueError, match='Invalid batch size'):
        enrich.enrich_batch(sample_rows(n))


def test_enrich_batch_propagates_api_error(monkeypatch):
    class TestRateLimitError(Exception):
        pass

    def fake_generate(prompt):
        raise TestRateLimitError('Rate limit exceeded')

    monkeypatch.setattr(enrich, 'generate_summary', fake_generate)
    with pytest.raises(TestRateLimitError, match='Rate limit exceeded'):
        enrich.enrich_batch(sample_rows(1))


# Supabase RPC updates

def test_update_batch(supabase):
    responses = fake_responses(sample_rows(2))
    enrich.update_batch(supabase, responses)
    supabase.rpc.assert_called_once_with('save_enrichment_batch', {'p_responses': responses})
    supabase.rpc.return_value.execute.assert_called_once()


def test_update_batch_24_records(supabase):
    enrich.update_batch(supabase, fake_responses(sample_rows(24)))
    assert len(supabase.rpc.call_args.args[1]['p_responses']) == 24


def test_update_batch_rejects_25_records(supabase):
    with pytest.raises(ValueError, match='Maximum 24'):
        enrich.update_batch(supabase, fake_responses(sample_rows(25)))
    supabase.rpc.assert_not_called()


def test_update_batch_duplicate_ids(supabase):
    with pytest.raises(ValueError, match='Duplicate'):
        enrich.update_batch(supabase, [
            {'id': 101, 'llm_response': 'Good.'},
            {'id': 101, 'llm_response': 'Poor.'},
        ])
    supabase.rpc.assert_not_called()


def test_update_batch_invalid_response(supabase):
    with pytest.raises(ValueError, match='Invalid summary'):
        enrich.update_batch(supabase, [{'id': 101, 'llm_response': None}])
    supabase.rpc.assert_not_called()


def test_update_batch_empty(supabase):
    with pytest.raises(ValueError, match='Empty batch'):
        enrich.update_batch(supabase, [])
    supabase.rpc.assert_not_called()


def test_update_batch_database_error(supabase):
    supabase.rpc.return_value.execute.side_effect = Exception('Database unavailable')
    with pytest.raises(enrich.EnrichmentDatabaseError, match='Failed to save enrichment batch'):
        enrich.update_batch(supabase, fake_responses(sample_rows(1)))


# Fetch records

def test_fetch_records(supabase):
    rows = sample_rows(1, 101)
    query = mock_pages(supabase, [rows])
    assert enrich.fetch_records(supabase, None) == rows
    supabase.table.assert_called_once_with('gold_air_data')
    query.or_.assert_called_once_with('llm_response.is.null,llm_response.eq.')
    query.order.assert_called_once_with('id')
    query.limit.assert_called_once_with(enrich.QUERY_SIZE)
    query.gt.assert_not_called()


def test_fetch_records_pagination(supabase):
    query = mock_pages(supabase, [[]])
    enrich.fetch_records(supabase, 1000)
    query.gt.assert_called_once_with('id', 1000)


def test_fetch_records_database_error(supabase):
    query = mock_pages(supabase, [])
    query.execute.side_effect = Exception('Connection failed')
    with pytest.raises(enrich.EnrichmentDatabaseError, match='Failed to fetch enrichment records'):
        enrich.fetch_records(supabase, None)


def test_fetch_records_missing_payload(supabase):
    mock_pages(supabase, [None])
    with pytest.raises(enrich.EnrichmentDatabaseError, match='Supabase returned no data payload'):
        enrich.fetch_records(supabase, None)


# End-to-end orchestration with mocked external dependencies

def test_run_enrichment(monkeypatch, configured_env, supabase):
    mock_pages(supabase, [sample_rows(2, 101), []])
    monkeypatch.setattr(enrich, 'enrich_batch', fake_enrichment)
    saved = []
    monkeypatch.setattr(enrich, 'update_batch', lambda client, responses: saved.append(responses))
    assert enrich.run_enrichment(supabase) == {
        'success': 2, 'llm_model': 'test-gemma', 'prompt_version': 'v2'
    }
    assert len(saved) == 1
    assert len(saved[0]) == 2


def test_run_enrichment_no_records(configured_env, supabase):
    mock_pages(supabase, [[]])
    assert enrich.run_enrichment(supabase) == {
        'success': 0, 'llm_model': None, 'prompt_version': 'v2'
    }
    supabase.rpc.assert_not_called()


def test_run_enrichment_pagination(monkeypatch, configured_env, supabase):
    query = mock_pages(supabase, [sample_rows(1000), sample_rows(5, 1001), []])
    monkeypatch.setattr(enrich, 'enrich_batch', fake_enrichment)
    batches = []
    monkeypatch.setattr(enrich, 'update_batch', lambda client, responses: batches.append(responses))
    result = enrich.run_enrichment(supabase)
    assert result['success'] == 1005
    assert sum(map(len, batches)) == 1005
    assert all(len(batch) <= 24 for batch in batches)
    assert len(batches) == 43  # 42 batches for page one, 1 for page two
    query.gt.assert_any_call('id', 1000)


def test_run_enrichment_partial_progress(monkeypatch, configured_env, supabase, caplog):
    mock_pages(supabase, [sample_rows(48)])

    class TestRateLimitError(Exception):
        pass

    calls = []

    def fake_enrich(batch):
        calls.append(batch)
        if len(calls) == 2:
            raise TestRateLimitError('Rate limit exceeded')
        return fake_enrichment(batch)

    monkeypatch.setattr(enrich, 'enrich_batch', fake_enrich)
    with caplog.at_level(logging.ERROR):
        with pytest.raises(TestRateLimitError, match='Rate limit exceeded') as exc_info:
            enrich.run_enrichment(supabase)
    assert exc_info.value.partial_result == {
        'success': 24, 'llm_model': 'test-gemma', 'prompt_version': 'v2'
    }
    assert len(calls) == 2
    assert supabase.rpc.call_count == 1
    assert '24 successfully saved records' in caplog.text


def test_run_enrichment_missing_model(monkeypatch, supabase):
    monkeypatch.delenv('OPENROUTER_MODEL', raising=False)
    monkeypatch.setenv('OPENROUTER_API_KEY', 'test-key')
    with pytest.raises(enrich.EnrichmentConfigurationError, match='OPENROUTER_MODEL'):
        enrich.run_enrichment(supabase)
    supabase.table.assert_not_called()


def test_run_enrichment_missing_api_key(monkeypatch, supabase):
    monkeypatch.setenv('OPENROUTER_MODEL', 'test-gemma')
    monkeypatch.delenv('OPENROUTER_API_KEY', raising=False)
    with pytest.raises(enrich.EnrichmentConfigurationError, match='OPENROUTER_API_KEY'):
        enrich.run_enrichment(supabase)
    supabase.table.assert_not_called()


# New progress / timing tests

def test_run_enrichment_progress_output(monkeypatch, configured_env, supabase, capsys):
    mock_pages(supabase, [sample_rows(25), []])
    monkeypatch.setattr(enrich, 'enrich_batch', fake_enrichment)
    monkeypatch.setattr(enrich, 'update_batch', lambda client, responses: None)
    ticks = iter([10.0, 12.5, 20.0, 20.4, 30.0, 31.25, 40.0, 40.75])
    monkeypatch.setattr(enrich.time, 'monotonic', lambda: next(ticks))

    assert enrich.run_enrichment(supabase)['success'] == 25
    output = capsys.readouterr().out
    assert 'Batch 1/2: calling OpenRouter (24 rows)...' in output
    assert 'Batch 1/2: OpenRouter responded in 2.5s. Saving to Supabase...' in output
    assert 'Batch 1/2: saved in 0.4s (total saved: 24).' in output
    assert 'Batch 2/2: calling OpenRouter (1 rows)...' in output
    assert 'Batch 2/2: OpenRouter responded in 1.2s. Saving to Supabase...' in output
    assert 'Batch 2/2: saved in 0.8s (total saved: 25).' in output


def test_run_enrichment_progress_resets_per_page(monkeypatch, configured_env, supabase, capsys):
    mock_pages(supabase, [sample_rows(24), sample_rows(1, 25), []])
    monkeypatch.setattr(enrich, 'enrich_batch', fake_enrichment)
    monkeypatch.setattr(enrich, 'update_batch', lambda client, responses: None)
    assert enrich.run_enrichment(supabase)['success'] == 25
    output = capsys.readouterr().out
    assert output.count('Batch 1/1: calling OpenRouter') == 2
    assert '(total saved: 24)' in output
    assert '(total saved: 25)' in output


def test_run_enrichment_save_failure_does_not_count_failed_batch(
    monkeypatch, configured_env, supabase, caplog, capsys
):
    mock_pages(supabase, [sample_rows(48)])
    monkeypatch.setattr(enrich, 'enrich_batch', fake_enrichment)
    calls = []

    def fake_save(client, responses):
        calls.append(responses)
        if len(calls) == 2:
            raise enrich.EnrichmentDatabaseError('Save failed')

    monkeypatch.setattr(enrich, 'update_batch', fake_save)
    with caplog.at_level(logging.ERROR):
        with pytest.raises(enrich.EnrichmentDatabaseError, match='Save failed') as exc_info:
            enrich.run_enrichment(supabase)
    assert exc_info.value.partial_result == {
        'success': 24, 'llm_model': 'test-gemma', 'prompt_version': 'v2'
    }
    assert len(calls) == 2
    assert '24 successfully saved records' in caplog.text
    output = capsys.readouterr().out
    assert '(total saved: 24)' in output
    assert '(total saved: 48)' not in output


def test_run_enrichment_no_save_if_llm_fails(monkeypatch, configured_env, supabase):
    mock_pages(supabase, [sample_rows(1)])

    def fail(batch):
        raise enrich.EnrichmentBatchError('Invalid response')

    monkeypatch.setattr(enrich, 'enrich_batch', fail)
    with pytest.raises(enrich.EnrichmentBatchError, match='Invalid response'):
        enrich.run_enrichment(supabase)
    supabase.rpc.assert_not_called()


# Batch limits and model tracking

def test_run_enrichment_max_batches(monkeypatch, configured_env, supabase):
    query = mock_pages(supabase, [sample_rows(100)])
    monkeypatch.setattr(enrich, 'enrich_batch', fake_enrichment)
    assert enrich.run_enrichment(supabase, max_batches=2) == {
        'success': 48, 'llm_model': 'test-gemma', 'prompt_version': 'v2'
    }
    assert supabase.rpc.call_count == 2
    assert query.execute.call_count == 1


@pytest.mark.parametrize('max_batches', [0, -1, 1.5, '2', True, False])
def test_run_enrichment_invalid_max_batches(configured_env, supabase, max_batches):
    with pytest.raises(ValueError, match='max_batches must be a positive integer or None') as exc_info:
        enrich.run_enrichment(supabase, max_batches=max_batches)
    assert exc_info.value.partial_result == {
        'success': 0, 'llm_model': None, 'prompt_version': 'v2'
    }
    supabase.table.assert_not_called()


def test_run_enrichment_multiple_models(monkeypatch, configured_env, supabase):
    mock_pages(supabase, [sample_rows(72), []])
    models = iter(['gemma-b', 'gemma-a', 'gemma-b'])

    def fake_enrich(batch):
        return fake_responses(batch), next(models)

    monkeypatch.setattr(enrich, 'enrich_batch', fake_enrich)
    assert enrich.run_enrichment(supabase) == {
        'success': 72, 'llm_model': 'gemma-a, gemma-b', 'prompt_version': 'v2'
    }


def test_run_enrichment_max_batches_across_pages(monkeypatch, configured_env, supabase):
    query = mock_pages(supabase, [sample_rows(24), sample_rows(48, 25)])
    monkeypatch.setattr(enrich, 'enrich_batch', fake_enrichment)
    assert enrich.run_enrichment(supabase, max_batches=2)['success'] == 48
    assert supabase.rpc.call_count == 2
    assert query.execute.call_count == 2
    query.gt.assert_called_once_with('id', 24)