"""Product ownership, current approval, source integrity and safe evidence exports."""

import csv
import io
from contextlib import nullcontext

import pytest

from research_assistant import product
from research_assistant.contracts import Chunk, EvidenceItem, QueryRequest, RetrievalResult, RunArtifact, text_sha
from research_assistant.retrieval.catalog import ReviewCatalog, chunk_evidence
from research_assistant.retrieval.evidence import assemble_evidence, validate_context
from research_assistant.settings import Settings


def fixture_run(workflow='comparison', text='Exact reported quotation, with a comma.\nSecond line.'):
    """Two paper-owned approved evaluations sharing a base benchmark, not a score protocol."""
    chunks, facts, items = {}, {}, []
    for number in range(2):
        chunk = Chunk(chunk_id=f'c{number}', paper_id=f'paper-{number}', source_sha256=str(number) * 64,
                      source_url=f'https://example.invalid/{number}', page=number + 1, section='Evaluation',
                      page_start=0, page_end=len(text), text=text, text_sha256=text_sha(text),
                      parser_version='fixture', chunker_version='fixture', mini_tokens=10, mpnet_tokens=10)
        chunks[chunk.chunk_id] = chunk
        raw = chunk_evidence(chunk)
        item = EvidenceItem(id=f'f{number}', kind='approved_fact', excerpts=raw.excerpts,
                            approved_claim_ids=[f'claim-{number}'], claim_revision=2,
                            claim_text=f'Method {number} evaluated Benchmark.',
                            conditions={'method': f'Method {number}', 'dataset': 'Benchmark', 'split': None})
        facts[item.id] = {'id': item.id, 'kind': 'evaluation', 'paper_id': chunk.paper_id,
                          'evidence': item.model_dump(), 'entities': [{'id': f'm{number}', 'kind': 'method'}]}
        items.append(item)
    selected, context, aliases, tokens, audit = assemble_evidence(items)
    retrieval = RetrievalResult(requested_mode='graph', effective_mode='hybrid_facts', fallback_reason='no_new_eligible_graph_candidates',
        evidence=selected, context=context, context_sha256=text_sha(context), aliases=aliases,
        estimated_tokens=tokens, candidates=audit, retrieval_ms=1, audit={'review_head': 'head-1'})
    run = RunArtifact(run_id='test-run', created_at='2026-11-08T00:00:00Z',
        request=QueryRequest(question='Compare the methods.', corpus_id='a' * 64, mode='graph'),
        corpus_manifest={'encoder_revision': 'encoder'}, code_revision='fixture', code_dirty=False,
        configuration={}, retrieval=retrieval, generation=None, result=None, generation_requested=False, workflow=workflow)
    return run, ReviewCatalog('a' * 64, 'head-1', facts, {}), chunks


def test_discovery_and_comparison_preserve_two_reporting_papers_and_unknowns():
    run, catalog, _ = fixture_run('discovery')
    view = product.build_view(run, catalog)
    assert (view.paper_count, view.method_count, view.status) == (2, 2, 'evidence available')
    assert {row['paper'] for row in view.rows} == {'paper-0', 'paper-1'}
    assert all('#page=' in row['citations'] and row['split'] == 'unknown' for row in view.rows)
    run.workflow = 'comparison'
    view = product.build_view(run, catalog)
    assert any('dataset_version: missing' in n for n in view.notices)
    assert any('No controlled numerical ranking' in n for n in view.notices)


def test_incompatible_conditions_are_qualified_even_with_shared_benchmark():
    notices = product.comparison_notices([{'dataset': 'X', 'split': 'test', 'metric': 'F1'},
                                          {'dataset': 'X', 'split': 'validation', 'metric': 'EM'}])
    assert any('split: reported conditions differ' in n for n in notices)
    assert any('metric: reported conditions differ' in n for n in notices)
    assert any('protocol: missing' in n for n in notices)


def test_raw_excerpts_do_not_become_approved_discovery_or_limitation_claims():
    run, catalog, chunks = fixture_run('limitations')
    run.retrieval.evidence = [chunk_evidence(next(iter(chunks.values())))]
    assert product.build_view(run, catalog).status == 'partial evidence'
    assert product.build_view(run, catalog).rows == []
    run.workflow = 'ask'
    assert product.build_view(run, catalog).status == 'evidence available'


def test_limitations_exposes_only_approved_findings():
    run, catalog, _ = fixture_run('limitations')
    catalog.facts['f0']['kind'] = 'finding'
    view = product.build_view(run, catalog)
    assert len(view.rows) == 1 and view.rows[0]['paper'] == 'paper-0'


def test_discovery_does_not_count_two_unrelated_benchmark_papers_as_coverage():
    from research_assistant.review.contracts import EntityDefinition
    run, catalog, _ = fixture_run('discovery')
    catalog.entities['wanted'] = EntityDefinition(id='wanted', kind='dataset', name='Wanted benchmark', aliases=[])
    run.request.question = 'Which methods were evaluated on Wanted benchmark?'
    view = product.build_view(run, catalog)
    assert view.paper_count == 0 and view.status == 'partial evidence'


def test_tampered_approved_claim_is_not_displayed():
    run, catalog, _ = fixture_run()
    run.retrieval.evidence[0].claim_text = 'An invented improved result.'
    with pytest.raises(ValueError, match='differs from the current'):
        product.build_view(run, catalog)


def test_csv_exact_quotations_conditions_and_explicit_fallback():
    run, _, _ = fixture_run()
    rows = list(csv.DictReader(io.StringIO(product.evidence_csv(run))))
    assert len(rows) == 2
    assert rows[0]['quotation'] == run.retrieval.evidence[0].excerpts[0].text
    assert rows[0]['paper'] == 'paper-0' and rows[0]['page'] == '1'
    assert rows[0]['claim_revision'] == '2' and '"split": null' in rows[0]['condition']
    assert rows[0]['requested_mode'] == 'graph' and rows[0]['effective_mode'] == 'hybrid_facts'
    assert rows[0]['fallback_reason'] == 'no_new_eligible_graph_candidates'


@pytest.mark.parametrize('text', ['=SUM(A1:A2)', ' +cmd', '-1+2', '@formula', '\tformula', "'literal"])
def test_csv_formula_escaping_is_reversible(text):
    import json
    run, _, _ = fixture_run(text=text)
    row = next(csv.DictReader(io.StringIO(product.evidence_csv(run))))
    assert 'quotation' in json.loads(row['escaped_fields'])
    assert row['quotation'][1:] == text


@pytest.mark.parametrize('field,value', [('source_url', 'https://wrong.invalid'), ('text', 'x' * 49)])
def test_shared_context_validator_rejects_source_tampering(field, value):
    run, _, chunks = fixture_run()
    excerpt = run.retrieval.evidence[0].excerpts[0]
    setattr(excerpt, field, value)
    _, context, aliases, tokens, _ = assemble_evidence(run.retrieval.evidence)
    run.retrieval.context, run.retrieval.aliases = context, aliases
    run.retrieval.context_sha256, run.retrieval.estimated_tokens = text_sha(context), tokens
    with pytest.raises(ValueError, match='exact source span'):
        validate_context(run.retrieval, chunks)


def test_output_rechecks_current_projection_and_graph_before_csv(monkeypatch):
    run, catalog, chunks = fixture_run()
    calls = []
    class Repo:
        def __init__(self, settings): pass
        def snapshot(self, corpus): return run.corpus_manifest
        def reading(self, *args): return nullcontext()
        def fact_vectors(self, *args): calls.append('graph checked')
        def close(self): calls.append('closed')
    monkeypatch.setattr(product, 'load_corpus_chunks', lambda _: chunks)
    monkeypatch.setattr(product, 'load_catalog', lambda *args: catalog)
    monkeypatch.setattr(product, 'review_lock', lambda _: nullcontext())
    monkeypatch.setattr(product, 'SearchRepository', Repo)
    assert product.prepare_output(run, Settings())[0].paper_count == 2
    assert calls == ['graph checked', 'closed']
    catalog.head = 'new-head'
    with pytest.raises(ValueError, match='Review head changed'):
        product.prepare_output(run, Settings())
    catalog.head = 'head-1'
    del catalog.facts['f0']
    with pytest.raises(ValueError, match='no longer'):
        product.prepare_output(run, Settings())


def test_retrieval_only_service_does_not_construct_generator(monkeypatch):
    from research_assistant import pipeline
    from research_assistant.retrieval import service
    run, _, _ = fixture_run()
    monkeypatch.setattr(service, 'retrieve_request', lambda *args: (run.corpus_manifest, run.retrieval))
    monkeypatch.setattr(pipeline, 'code_identity', lambda: dict(code_revision='test', code_dirty=False, source_tree_sha256='hash'))
    monkeypatch.setattr(pipeline, 'check_resources', lambda: {})
    monkeypatch.setattr(pipeline, 'create_client', lambda *args: pytest.fail('No generation requested'))
    result = pipeline.run_query(run.request, Settings(), generate=False, workflow='discovery')
    assert result.result is None and result.generation is None and not result.generation_requested


def test_cli_retrieve_and_export_share_services_and_stale_export_creates_no_csv(monkeypatch, tmp_path, capsys):
    from research_assistant.__main__ import main
    from research_assistant import pipeline
    run, catalog, _ = fixture_run()
    monkeypatch.setattr(pipeline, 'run_query', lambda *args, **kwargs: run)
    run_path = tmp_path / 'run.json'
    assert main(['retrieve', '--corpus', run.request.corpus_id, '--question', 'Compare.',
                 '--mode', 'graph', '--output', str(run_path)]) == 0
    assert 'hybrid_facts' in capsys.readouterr().out
    monkeypatch.setattr(product, 'prepare_output', lambda *args: (product.build_view(run, catalog), product.evidence_csv(run)))
    csv_path = tmp_path / 'evidence.csv'
    assert main(['export-evidence', '--run', str(run_path), '--output', str(csv_path)]) == 0
    assert len(list(csv.DictReader(io.StringIO(csv_path.read_text(encoding='utf-8'))))) == 2
    def stale(*args): raise ValueError('Review head changed')
    monkeypatch.setattr(product, 'prepare_output', stale)
    blocked = tmp_path / 'blocked.csv'
    assert main(['export-evidence', '--run', str(run_path), '--output', str(blocked)]) == 1
    assert not blocked.exists()


def test_abstention_citation_normalization_preserves_raw_model_output():
    from research_assistant.contracts import DraftAnswer, LLMResult
    from research_assistant.generation import answer_question
    run, _, _ = fixture_run()
    raw = LLMResult(text='{"answer":"No measurement established.","insufficient_evidence":true,"citations":["E1"]}',
                    provider='fixture', model='fixture', digest='fixture', elapsed_ms=1, usage={}, settings={}, messages=[])
    class Client:
        def generate_structured(self, schema, messages):
            return DraftAnswer.model_validate_json(raw.text), raw
    answer, generation = answer_question('What measured gain?', run.retrieval, Client())
    assert answer.insufficient_evidence and answer.citations == []
    assert generation.text == raw.text
    assert generation.settings['answer_normalization']['discarded_citations'] == ['E1']
    assert raw.settings == {}


def test_generation_failure_retains_actual_evidence_and_raw_response(monkeypatch):
    from research_assistant import pipeline
    from research_assistant.contracts import LLMResult
    from research_assistant.retrieval import service
    run, _, _ = fixture_run()
    raw = LLMResult(text='invalid answer', provider='fixture', model='fixture', digest='fixture',
                    elapsed_ms=1, usage={}, settings={}, messages=[])
    class Client:
        last_result = raw
        def __init__(self, *args): pass
    monkeypatch.setattr(service, 'retrieve_request', lambda *args: (run.corpus_manifest, run.retrieval))
    monkeypatch.setattr(pipeline, 'code_identity', lambda: dict(code_revision='test', code_dirty=False, source_tree_sha256='hash'))
    monkeypatch.setattr(pipeline, 'check_resources', lambda: {'checked': True})
    monkeypatch.setattr(pipeline, 'create_client', Client)
    def invalid(*args): raise ValueError('Unknown evidence citation')
    monkeypatch.setattr(pipeline, 'answer_question', invalid)
    with pytest.raises(pipeline.QueryExecutionError) as captured:
        pipeline.run_query(run.request, Settings())
    failed = captured.value.artifact
    assert failed.retrieval == run.retrieval and failed.generation == raw and failed.result is None
    assert failed.configuration['generation_error']['type'] == 'ValueError'
    assert failed.configuration['resources_after_generation'] == {'checked': True}
