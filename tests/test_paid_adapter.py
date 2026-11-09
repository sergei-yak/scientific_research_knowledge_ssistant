"""Paid boundaries use a fake transport and temporary journals; no network or real funds."""

from datetime import date
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from research_assistant.contracts import DraftAnswer
from research_assistant.extraction.contracts import ExtractionResponse
from research_assistant.llm import paid
from research_assistant.settings import Settings


def client(monkeypatch, tmp_path, **changes):
    monkeypatch.setattr(paid, 'BUDGET_DIRECTORY', tmp_path)
    monkeypatch.setattr(paid, 'RATE_REVIEW_DATE', date.today().isoformat())
    calls = []
    response = SimpleNamespace(model='gpt-6.1-terra', id='response-fixture', status='completed', output=[],
        output_text='{"answer":"No result established.","citations":[],"insufficient_evidence":true}',
        usage=SimpleNamespace(input_tokens=100, output_tokens=30), model_dump=lambda **kwargs: {'raw': 'retained'})
    def create(**kwargs):
        calls.append(kwargs)
        return response
    def sdk(**kwargs):
        assert kwargs['max_retries'] == 0 and kwargs['base_url'] == 'https://api.openai.com/v1'
        return SimpleNamespace(responses=SimpleNamespace(create=create))
    monkeypatch.setattr(paid, 'OpenAI', sdk)
    values = dict(openai_api_key='fake-key', generation_provider='openai', generation_model='gpt-6.1-terra',
        api_budget_approved=True, api_budget_usd=1, api_max_request_usd=.1, api_max_requests=2)
    values.update(changes)
    return paid.OpenAIClient(Settings(**values), output_tokens=128), response, calls


def test_structured_response_uses_strict_schema_and_durable_reservation(monkeypatch, tmp_path):
    model, response, calls = client(monkeypatch, tmp_path)
    value, result = model.generate_structured(DraftAnswer, [{'role': 'user', 'content': 'Question'}])
    assert value.insufficient_evidence and result.settings['provider_response'] == {'raw': 'retained'}
    assert calls[0]['text']['format']['strict'] and calls[0]['store'] is False
    assert calls[0]['reasoning'] == {'effort': 'none'} and calls[0]['tools'] == []
    assert [event['kind'] for event in paid.read_ledger(tmp_path)] == ['reserve', 'response']


def test_open_mapping_uses_explicit_json_mode_and_validates_full_schema(monkeypatch, tmp_path):
    model, response, calls = client(monkeypatch, tmp_path)
    response.output_text = '{"candidates":[],"no_claim_reason":"No reported claim."}'
    value, _ = model.generate_structured(ExtractionResponse, [{'role': 'user', 'content': 'Extract.'}])
    assert not value.candidates and calls[0]['text']['format'] == {'type': 'json_object'}
    assert 'schema' in calls[0]['input'][0]['content']


@pytest.mark.parametrize('changes', [{'api_budget_approved': False}, {'openai_api_key': ''},
    {'api_max_requests': 0}, {'max_retries': 1}, {'max_concurrency': 2}, {'generation_model': 'another-model'},
    {'api_budget_scope': 'm3_3_readiness'}])
def test_invalid_authorization_or_limits_prevent_network(monkeypatch, tmp_path, changes):
    with pytest.raises(ValueError):
        client(monkeypatch, tmp_path, **changes)
    assert not (tmp_path / 'openai.jsonl').exists()


def test_request_and_money_caps_persist_across_clients(monkeypatch, tmp_path):
    model, _, calls = client(monkeypatch, tmp_path, api_max_requests=1)
    model.generate_text([{'role': 'user', 'content': 'READY'}])
    another, _, second_calls = client(monkeypatch, tmp_path, api_max_requests=1)
    with pytest.raises(ValueError, match='count exhausted'):
        another.generate_text([{'role': 'user', 'content': 'READY'}])
    assert len(calls) == 1 and not second_calls
    model, _, calls = client(monkeypatch, tmp_path, api_max_requests=4, api_budget_usd=.03, api_max_request_usd=.03)
    with pytest.raises(ValueError, match='remaining approved budget'):
        model.generate_text([{'role': 'user', 'content': 'READY'}])
    assert not calls


def test_unknown_transport_failure_retains_reserved_funds(monkeypatch, tmp_path):
    model, _, calls = client(monkeypatch, tmp_path, api_max_requests=1)
    def failure(**kwargs): raise TimeoutError('Unknown billable outcome')
    model.client.responses.create = failure
    with pytest.raises(TimeoutError):
        model.generate_text([{'role': 'user', 'content': 'READY'}])
    assert [event['kind'] for event in paid.read_ledger(tmp_path)] == ['reserve', 'unknown']
    with pytest.raises(ValueError, match='count exhausted'):
        model.generate_text([{'role': 'user', 'content': 'READY'}])


def test_individual_request_ceiling_blocks_before_any_charge(monkeypatch, tmp_path):
    model, _, calls = client(monkeypatch, tmp_path, api_max_request_usd=.001)
    with pytest.raises(ValueError, match='per-request ceiling'):
        model.generate_text([{'role': 'user', 'content': 'READY'}])
    assert not calls and paid.read_ledger(tmp_path) == []


def test_readiness_approval_cannot_enable_normal_generation_and_leaves_original_settings_unchanged(tmp_path):
    from research_assistant.integrations import readiness_settings
    import json
    original = Settings(openai_api_key='fake')
    approval = tmp_path / 'approval.json'
    approval.write_text(json.dumps({'scope':'m3_3_readiness','source':'synthetic user fixture','verbatim':'approved fixture',
        'api_budget_usd':.1,'api_max_request_usd':.05,'api_max_requests':2,'max_output_tokens':128,
        'max_concurrency':1,'max_retries':0}), encoding='utf-8')
    selected = readiness_settings(original, approval)
    assert selected.api_budget_scope == 'm3_3_readiness' and selected.api_budget_approved
    assert not original.api_budget_approved and original.generation_provider == 'ollama'
    selected = selected.model_copy(update={'generation_provider':'openai','generation_model':'gpt-6.1-terra'})
    with pytest.raises(ValueError, match='outside the explicitly approved budget scope'):
        paid.OpenAIClient(selected, output_tokens=128)


@pytest.mark.parametrize('problem', ['incomplete', 'missing_usage', 'bad_json', 'wrong_model', 'refusal'])
def test_invalid_provider_responses_preserve_raw_output_and_reservations(monkeypatch, tmp_path, problem):
    model, response, calls = client(monkeypatch, tmp_path)
    if problem == 'incomplete': response.status = 'incomplete'
    if problem == 'missing_usage': response.usage = None
    if problem == 'bad_json': response.output_text = 'invalid JSON'
    if problem == 'wrong_model': response.model = 'substitute'
    if problem == 'refusal': response.output = [SimpleNamespace(type='message', content=[SimpleNamespace(type='refusal')])]
    with pytest.raises((ValueError, ValidationError)):
        model.generate_structured(DraftAnswer, [{'role': 'user', 'content': 'Question'}])
    assert model.last_result is not None and len(paid.read_ledger(tmp_path)) == 2 and len(calls) == 1


def test_busy_or_corrupt_ledger_and_context_overflow_never_call_transport(monkeypatch, tmp_path):
    model, _, calls = client(monkeypatch, tmp_path)
    with pytest.raises(ValueError, match='safety margin'):
        model.generate_text([{'role': 'user', 'content': 'long prompt ' * 10000}])
    lock = tmp_path / '.openai.lock'
    lock.write_text('another active request', encoding='utf-8')
    with pytest.raises(FileExistsError):
        model.generate_text([{'role': 'user', 'content': 'READY'}])
    lock.unlink()
    (tmp_path / 'openai.jsonl').write_text('corrupt', encoding='utf-8')
    with pytest.raises(ValueError):
        model.generate_text([{'role': 'user', 'content': 'READY'}])
    assert not calls
