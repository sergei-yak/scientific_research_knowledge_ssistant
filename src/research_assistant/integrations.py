"""Bounded live adapter probes, separate from the no-cost M0 configuration checks."""

import json
from datetime import datetime, timezone
from importlib.metadata import version
from pathlib import Path

from research_assistant.embeddings import Encoder
from research_assistant.graph.repository import GraphRepository
from research_assistant.llm import create_client
from research_assistant.product import PILOT_CORPUS
from research_assistant.settings import Settings
from research_assistant.smoke import ProbeAnswer, check_resources


def readiness_settings(settings: Settings, approval_path: Path) -> Settings:
    """Apply an explicitly supplied recorded approval only to readiness probes, without editing .env."""
    approval = json.loads(approval_path.read_text(encoding='utf-8'))
    if approval.get('scope') != 'm3_3_readiness' or not approval.get('source') or not approval.get('verbatim'):
        raise ValueError('Expected a recorded user approval for M3.3 readiness')
    fields = ('api_budget_usd', 'api_max_request_usd', 'api_max_requests', 'max_output_tokens', 'max_concurrency', 'max_retries')
    return Settings.model_validate({**settings.model_dump(), **{field: approval[field] for field in fields},
                                    'api_budget_approved': True, 'api_budget_scope': 'm3_3_readiness'})


def provider_checks(settings: Settings, providers: list[str]) -> dict:
    """Explicitly probe requested providers with two calls each; unavailable paid checks stay pending."""
    if not providers or len(set(providers)) != len(providers) or not set(providers) <= {'ollama', 'openai'}:
        raise ValueError('Choose each supported provider at most once')
    encoder = Encoder()
    repo = GraphRepository(settings)
    try:
        snapshot = repo.snapshot(PILOT_CORPUS)
        matches = repo.vector_candidates(PILOT_CORPUS, encoder.encode(['retrieval methods'])[0])
    finally:
        repo.close()
    results = []
    for provider in providers:
        if provider == 'openai' and settings.paid_probe_blockers():
            results.append({'provider': provider, 'status': 'pending', 'requests_made': 0,
                            'blockers': settings.paid_probe_blockers()})
            continue
        model = settings.openai_model if provider == 'openai' else (
            settings.generation_model if settings.generation_provider == 'ollama' else settings.extraction_model)
        selected = settings.model_copy(update={'generation_provider': provider, 'generation_model': model})
        row = {'provider': provider, 'model': model, 'status': 'failed', 'operations_attempted': 0,
               'explicit_probe_selection': True, 'outputs': [], 'resources_before': check_resources()}
        client = None
        try:
            client = create_client(selected, context_tokens=4096, output_tokens=128, operation='m3_3_readiness')
            client.prompt_version = 'm3-adapter-readiness-v1'
            row['operations_attempted'] += 1
            text = client.generate_text([{'role': 'user', 'content': 'Reply with the single word READY.'}])
            row['outputs'].append(text.model_dump(mode='json'))
            if text.text.strip().upper() != 'READY':
                raise ValueError('Text adapter probe did not return READY')
            encoder.encode(['simultaneous CPU encoder inference with loaded local model'])
            row['operations_attempted'] += 1
            value, structured = client.generate_structured(ProbeAnswer,
                [{'role': 'user', 'content': 'Return JSON with status="ok" and value=2.'}])
            row['outputs'].append(structured.model_dump(mode='json'))
            if value.status != 'ok' or value.value != 2:
                raise ValueError('Structured adapter probe returned incorrect values')
            row['status'] = 'passed'
        except Exception as exc:
            row.update(error_type=type(exc).__name__, error=settings.redact(str(exc)),
                       failed_provider_result=client.last_result.model_dump(mode='json') if client and client.last_result else None)
        row['resources_after'] = check_resources()
        results.append(row)
    return {'task_id': 'M3.3', 'created_at': datetime.now(timezone.utc).isoformat(),
            'sdk_versions': {name: version(name) for name in ('openai', 'ollama')},
            'checks': results, 'resident_encoder_revision': encoder.revision,
            'database_snapshot_ready': snapshot['corpus_id'], 'database_vector_search_results': len(matches),
            'selected_generation_provider_unchanged': settings.generation_provider,
            'complete': all(row['status'] == 'passed' for row in results) and set(providers) == {'ollama', 'openai'}}
