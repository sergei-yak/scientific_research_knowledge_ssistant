"""Adapter check exit codes distinguish failures from successful/pending inspection."""

import json

import pytest

from research_assistant.__main__ import main
from research_assistant import integrations


@pytest.mark.parametrize('status,exit_code', [('passed', 0), ('pending', 0), ('failed', 1)])
def test_provider_check_preserves_actual_status_and_signals_failure(monkeypatch, tmp_path, status, exit_code):
    monkeypatch.setattr(integrations, 'provider_checks', lambda *args: {
        'task_id': 'M3.3', 'checks': [{'provider': 'openai', 'status': status}], 'complete': status == 'passed'})
    output = tmp_path / 'report.json'
    assert main(['provider-check', '--providers', 'openai', '--output', str(output)]) == exit_code
    assert json.loads(output.read_text(encoding='utf-8'))['checks'][0]['status'] == status
