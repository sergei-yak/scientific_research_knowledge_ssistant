"""Corpus isolation and anonymous scoring use synthetic development data only."""

import csv
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from research_assistant.contracts import LLMResult
from research_assistant.evaluation import blinding
from research_assistant.generation import validate_answer
from research_assistant.contracts import DraftAnswer
from research_assistant.ingestion.corpus import ExpansionManifest, PilotManifest
from test_product import fixture_run


def samples():
    """Synthetic equal-condition answers include a graph request's explicit baseline fallback."""
    run, _, chunks = fixture_run()
    run.corpus_manifest['corpus_id'] = run.request.corpus_id
    run.configuration['encoder_revision'] = run.corpus_manifest['encoder_revision']
    items = []
    for mode in blinding.CONDITIONS:
        copied = run.model_copy(deep=True)
        copied.run_id = 'private-' + mode
        copied.request.mode = copied.retrieval.requested_mode = mode
        copied.generation_requested = True
        copied.generation = LLMResult(text='synthetic response', provider='fixture', model='fixture', digest='fixture',
            elapsed_ms=0, usage={}, settings={}, messages=[])
        copied.result = validate_answer(DraftAnswer(answer='Reported benchmark.', citations=['E1'], insufficient_evidence=False), copied.retrieval)
        items.append(blinding.ScoringInput(question_id='DEV-SYNTHETIC', condition=mode, run=copied))
    return items, chunks


def bundle(tmp_path, monkeypatch):
    """Use an isolated development-root layout; never touch private evaluator directories."""
    monkeypatch.chdir(tmp_path)
    directory = Path('data/evaluation/development/synthetic/blind')
    items, chunks = samples()
    report = blinding.build_development_bundle(items, chunks, directory)
    return directory, report


def score_form(directory):
    """Explicitly synthetic test scores, never production human approval records."""
    source = directory / 'public/scores.csv'
    with source.open(newline='') as f:
        rows = list(csv.DictReader(f))
    for row in rows:
        row.update(correctness='1', citation_support='1', reviewer='SYNTHETIC TEST ONLY',
                   scored_at='2026-11-08T12:00:00Z', notes='synthetic test score')
    target = directory / 'synthetic-completed.csv'
    with target.open('w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=blinding.SCORE_FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    return target


def test_public_export_whitelist_and_reveal_after_sealed_scores(tmp_path, monkeypatch):
    directory, report = bundle(tmp_path, monkeypatch)
    packet = json.loads((directory / 'public/answers.json').read_text())
    assert report['answers'] == 4 and report['human_scores_supplied'] == 0
    assert len({p['answer_id'] for p in packet}) == 4
    assert all(set(p) == {'answer_id', 'question_id', 'question', 'answer', 'abstained', 'citations'} for p in packet)
    text = json.dumps(packet)
    assert all(secret not in text for secret in ['private-graph', 'fallback_reason', 'effective_mode', 'graph_paths', 'item_id'])
    with pytest.raises(FileNotFoundError):
        blinding.reveal_development_scores(directory)
    blinding.seal_development_scores(directory, score_form(directory))
    result = blinding.reveal_development_scores(directory)
    assert all(x == {'wins': 0, 'ties': 1, 'losses': 0} for x in result['paired_correctness'].values())
    assert next(x for x in result['rows'] if x['requested_condition'] == 'graph')['effective_mode'] == 'hybrid_facts'


def test_blank_duplicate_partial_and_changed_mapping_rejected(tmp_path, monkeypatch):
    directory, _ = bundle(tmp_path, monkeypatch)
    with pytest.raises(ValueError):
        blinding.seal_development_scores(directory, directory / 'public/scores.csv')
    completed = score_form(directory)
    with completed.open(newline='') as f:
        rows = list(csv.DictReader(f))
    rows[-1]['answer_id'] = rows[0]['answer_id']
    with completed.open('w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=blinding.SCORE_FIELDS); w.writeheader(); w.writerows(rows)
    with pytest.raises(ValueError, match='exactly once'):
        blinding.seal_development_scores(directory, completed)
    blinding.seal_development_scores(directory, score_form(directory))
    reveal_path = directory / 'private/reveal.json'
    data = json.loads(reveal_path.read_text()); data['mapping'][0]['requested_condition'] = 'graph'
    reveal_path.write_text(json.dumps(data))
    with pytest.raises(ValueError, match='different packet'):
        blinding.reveal_development_scores(directory)


def test_incomplete_matrix_bad_sources_and_external_output_rejected(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    items, chunks = samples()
    output = Path('data/evaluation/development/synthetic/blind')
    with pytest.raises(ValueError, match='exactly once'):
        blinding.build_development_bundle(items[:-1], chunks, output)
    items[0].run.retrieval.context += 'hidden text'
    with pytest.raises(ValueError):
        blinding.build_development_bundle(items, chunks, output)
    with pytest.raises(ValueError, match='versioned directory'):
        blinding.build_development_bundle(items, chunks, tmp_path / 'external-never-open')
    assert not (tmp_path / 'external-never-open').exists()


def test_changed_generator_limits_or_missing_response_fail_comparison(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    items, chunks = samples()
    items[0].run.generation.settings['num_predict'] = 128
    with pytest.raises(ValueError, match='mixes corpus/code/encoder/generator'):
        blinding.build_development_bundle(items, chunks, Path('data/evaluation/development/test/mixed'))
    items, chunks = samples()
    items[0].run.generation = None
    with pytest.raises(ValueError, match='saved generation response'):
        blinding.build_development_bundle(items, chunks, Path('data/evaluation/development/test/incomplete'))


def test_manifest_profiles_preserve_pilot_and_reject_duplicate_versions():
    original = json.loads(Path('manifests/pilot-five-papers.json').read_text(encoding='utf-8'))
    assert PilotManifest.model_validate(original).model_dump() == original
    with pytest.raises(ValidationError):
        ExpansionManifest.model_validate({**original, 'selection_sha256': 'a' * 64})
    additions = []
    for i in range(15):
        additions.append({**original['papers'][0], 'paper_id': f'test:{i}', 'arxiv_id': f'2499.{i:05d}v1'})
    expanded = {**original, 'papers': original['papers'] + additions, 'selection_sha256': 'a' * 64}
    assert len(ExpansionManifest.model_validate(expanded).papers) == 20
    expanded['papers'][-1]['arxiv_id'] = additions[0]['arxiv_id'].replace('v1', 'v2')
    with pytest.raises(ValidationError, match='Duplicate versions'):
        ExpansionManifest.model_validate(expanded)


def test_scope_extension_preserves_human_history_and_refuses_changed_sources(tmp_path, monkeypatch):
    from research_assistant.review import scope
    from research_assistant.review.store import import_decisions, state
    from test_review_workflow import fixture, human
    source, target = tmp_path / 'original', tmp_path / 'expanded'
    revision, chunks = fixture(source)
    import_decisions(source, [human(revision)], chunks)
    original_head = state(source)['head']
    (source / 'projections').mkdir()
    (source / 'projections/original.json').write_text('original derived cache')
    monkeypatch.setattr(scope, 'load_corpus_chunks', lambda _: chunks)
    monkeypatch.setattr(scope, 'load_chunks', lambda _: chunks)
    result = scope.extend_scope(source, target, 'b' * 64)
    assert result['new_human_decisions'] == 0 and result['eligible_carried_claims'] == 1
    assert state(source)['head'] == state(target)['head'] == original_head
    assert not (target / 'projections').exists()
    assert (target / 'inherited' / ('a' * 64) / 'projections/original.json').read_text() == 'original derived cache'
    assert json.loads((source / 'config.json').read_text())['corpus_id'] == 'a' * 64
    with pytest.raises(ValueError, match='new directory'):
        scope.extend_scope(source, target, 'b' * 64)
    monkeypatch.setattr(scope, 'load_corpus_chunks', lambda _: {})
    with pytest.raises(ValueError, match='preserve every original'):
        scope.extend_scope(source, tmp_path / 'invalid', 'c' * 64)
    assert not (tmp_path / 'invalid').exists()


def test_evaluator_receipt_is_only_attested_and_rejects_wrong_counts_or_scope():
    from research_assistant.evaluation.readiness import CATEGORIES, EvaluatorAttestation, check_attestation
    value = dict(evaluator='SYNTHETIC TEST', validated_at='2026-11-08T12:00:00Z',
        corpus_id='a' * 64, review_head='b' * 64, development_dataset_sha256='c' * 64,
        heldout_questions_sha256='d' * 64, heldout_annotations_sha256='e' * 64,
        development_counts={c: 2 for c in CATEGORIES}, heldout_counts={c: 4 for c in CATEGORIES},
        independent_source_support_validated=True, corpus_scoped_unanswerability_validated=True,
        private_inputs_external_to_development=True, private_content_exposed_to_development=False, exposure_notes='')
    receipt = EvaluatorAttestation.model_validate(value)
    result = check_attestation(receipt, 'a' * 64, 'b' * 64, 'c' * 64)
    assert result['status'] == 'attested' and result['total_questions'] == 24
    assert not result['final_evaluation_authorized'] and not result['independently_verified_private_content']
    with pytest.raises(ValueError, match='different corpus'):
        check_attestation(receipt, 'f' * 64, 'b' * 64, 'c' * 64)
    with pytest.raises(ValidationError):
        EvaluatorAttestation.model_validate({**value, 'heldout_counts': {c: 3 for c in CATEGORIES}})
    with pytest.raises(ValidationError, match='Placeholder hashes'):
        EvaluatorAttestation.model_validate({**value, 'heldout_annotations_sha256': '0' * 64})
