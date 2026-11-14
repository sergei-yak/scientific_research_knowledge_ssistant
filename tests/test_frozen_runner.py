"""Synthetic external inputs exercise authorization, privacy, once-only accounting and blinding."""

import csv
from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from research_assistant.contracts import DraftAnswer, EvaluationQuestion, GoldFact, LLMResult, SourceSpanRef, fingerprint, text_sha
from research_assistant.generation import validate_answer
from research_assistant.evaluation import freeze as guards, runner
from research_assistant.evaluation.blinding import SCORE_FIELDS
from research_assistant.evaluation.freeze import FinalRunAuthorization, FreezeManifest, RunPlan, file_sha
from research_assistant.settings import Settings
from test_product import fixture_run


def authorization(path, freeze_path, **overrides):
    """SYNTHETIC provenance only; this helper never accesses real evaluation/approval stores."""
    record = FinalRunAuthorization(authorization_id='1' * 32, freeze_file_sha256=file_sha(freeze_path),
        reviewer='SYNTHETIC TEST ONLY', received_at=datetime.now(timezone.utc),
        verbatim_response='SYNTHETIC fixture authorization', approved=True).model_dump(mode='json')
    record.update(overrides)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({**record, 'receipt_sha256': fingerprint(record)}), encoding='utf-8')


def test_missing_or_oversized_approval_precedes_private_resolution(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    path = Path('runs/m4-2/freeze.json')
    path.parent.mkdir(parents=True)
    path.write_text('{}')
    monkeypatch.setattr(runner, 'load_freeze', lambda *a, **k: pytest.fail('Freeze/private context reached before authorization'))
    with pytest.raises(FileNotFoundError):
        runner.execute(path, Path('runs/m4-2/missing.json'), Settings())
    approval = Path('runs/m4-2/approval.json')
    authorization(approval, path, output_tokens=1024)
    with pytest.raises(ValueError):
        runner.execute(path, approval, Settings())


def test_receipt_hash_scope_and_freeze_binding_are_enforced(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    path = Path('runs/m4-2/freeze.json')
    path.parent.mkdir(parents=True)
    path.write_text('{}')
    approval = path.with_name('approval.json')
    authorization(approval, path, freeze_file_sha256='a' * 64)
    with pytest.raises(ValueError, match='different freeze'):
        guards.authorize(approval, path)
    authorization(approval, path)
    raw = json.loads(approval.read_text())
    raw['approved'] = False
    approval.write_text(json.dumps(raw))
    with pytest.raises(ValueError, match='hash changed'):
        guards.authorize(approval, path)


@pytest.mark.parametrize('name', ['../escape.json', '.env', 'data/evaluation/heldout/gold.json'])
def test_public_asset_allowlist_rejects_private_or_secret_paths(tmp_path, monkeypatch, name):
    monkeypatch.chdir(tmp_path)
    with pytest.raises(ValueError):
        guards.public_asset(name)


def test_gold_fields_are_forbidden_in_the_stripped_provider_input():
    with pytest.raises(ValueError):
        runner.QuestionPrompt(question_id='SYNTHETIC', question='Synthetic?', split='held_out',
                              category='direct', reference_answer='SYNTHETIC SECRET')


def test_console_errors_never_echo_private_validation_content(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(runner, 'execute', lambda *a, **k: (_ for _ in ()).throw(ValueError('SYNTHETIC PRIVATE GOLD TEXT')))
    assert runner.main(['run', '--freeze', 'runs/m4-2/freeze.json', '--authorization', 'runs/m4-2/auth.json']) == 1
    output = capsys.readouterr().out
    assert 'SYNTHETIC PRIVATE' not in output and 'declined_or_failed' in output


def synthetic_execution(tmp_path, monkeypatch):
    """Construct a fake workspace and separate synthetic evaluator root; no real private paths."""
    workspace, private = tmp_path / 'workspace', tmp_path / 'synthetic-evaluator'
    workspace.mkdir()
    private.mkdir()
    monkeypatch.chdir(workspace)
    freeze_path = Path('runs/m4-2/freeze.json')
    freeze_path.parent.mkdir(parents=True)
    snapshot = Path('runs/m4-2/snapshot')
    dev_path = snapshot / 'files/data/evaluation/development/expansion-v1/questions.jsonl'
    dev_path.parent.mkdir(parents=True)
    groups = {}
    for split, count in (('development', 2), ('held_out', 4)):
        rows = []
        for category in ('direct', 'cross_paper', 'multi_hop', 'unanswerable'):
            for number in range(count):
                rows.append({'question_id': f'SYNTHETIC-{split}-{category}-{number}',
                    'question': f'Synthetic {split} {category} example {number}?', 'split': split, 'category': category})
        groups[split] = rows
    dev_path.write_text(''.join(json.dumps(row) + '\n' for row in groups['development']), encoding='utf-8')
    (private / 'questions.jsonl').write_text(''.join(json.dumps(row) + '\n' for row in groups['held_out']), encoding='utf-8')
    (private / 'annotations.jsonl').write_text('SYNTHETIC GOLD: parsed only by the post-generation fixture hook', encoding='utf-8')
    base, _, chunks = fixture_run()
    source = next(iter(chunks.values()))
    span = SourceSpanRef(paper_id=source.paper_id, source_sha256=source.source_sha256,
        chunk_id=source.chunk_id, start=0, end=len(source.text), quote_sha256=text_sha(source.text))
    gold = {}
    for row in groups['development'] + groups['held_out']:
        absent = row['category'] == 'unanswerable'
        gold[row['question_id']] = EvaluationQuestion(**row, reference_answer='SYNTHETIC SECRET REFERENCE',
            facts=[] if absent else [GoldFact(fact_id='synthetic-fact', statement='Synthetic supported fact', support_sets=[[span]])],
            sufficient_fact_sets=[] if absent else [['synthetic-fact']])
    freeze = FreezeManifest(created_at=datetime.now(timezone.utc), corpus_id=base.request.corpus_id,
        review_head='b' * 64, development_dataset_sha256='c' * 64,
        readiness_path='runs/m4-1/readiness.json', readiness_file_sha256='d' * 64,
        heldout_questions_sha256=file_sha(private / 'questions.jsonl'), heldout_annotations_sha256=file_sha(private / 'annotations.jsonl'),
        private_root=str(private), snapshot_directory=snapshot.as_posix(), snapshot_manifest_sha256='e' * 64,
        graph_sha256=fingerprint({'synthetic': 'graph'}), recovery_report='runs/m4-2/recovery.json', recovery_report_sha256='f' * 64,
        target_uri='bolt://127.0.0.1:9765', target_project='dbu-m4-recovery-synthetic', docker_image_id='sha256:' + '1' * 64,
        code_revision='synthetic', source_tree_sha256='a' * 64, files={},
        encoder_revisions={'all-MiniLM-L6-v2': 'mini', 'all-mpnet-base-v2': 'mpnet'},
        runtime_versions=guards.runtime_versions(),
        generator_model='synthetic', generator_digest='0' * 64, ollama_base_url='http://127.0.0.1:11434',
        request_timeout_seconds=180, graph_query_timeout_seconds=30)
    freeze_path.write_text(freeze.model_dump_json(), encoding='utf-8')
    approval_path = freeze_path.with_name('approval.json')
    authorization(approval_path, freeze_path)
    monkeypatch.setattr(runner, 'load_freeze', lambda *a, **k: freeze)
    monkeypatch.setattr(runner, '_target', lambda *a, **k: Settings())
    tokenizer = SimpleNamespace(encode=lambda *a, **k: [1, 2])
    monkeypatch.setattr(runner, 'Encoder', lambda: SimpleNamespace(revision='mini', mini_tokenizer=tokenizer))
    monkeypatch.setattr(runner, 'MPNetEncoder', lambda: SimpleNamespace(revision='mpnet', model=SimpleNamespace(tokenizer=tokenizer)))
    monkeypatch.setattr(runner, 'code_identity', lambda: {'source_tree_sha256': freeze.source_tree_sha256})
    monkeypatch.setattr(runner, 'estimate_tokens', lambda text: 1)
    monkeypatch.setattr(runner, 'load_corpus_chunks', lambda corpus: chunks)
    monkeypatch.setattr(runner, 'capture', lambda settings: {'synthetic': 'graph'})
    calls = []
    def query(request, settings, *args, **kwargs):
        assert 'SECRET' not in request.question
        calls.append(request)
        copied = base.model_copy(deep=True)
        copied.request = request
        copied.run_id = f'synthetic-run-{len(calls)}'
        copied.corpus_manifest['corpus_id'] = request.corpus_id
        copied.configuration['encoder_revision'] = copied.corpus_manifest['encoder_revision']
        copied.retrieval.requested_mode = copied.retrieval.effective_mode = request.mode
        copied.generation_requested = True
        copied.generation = LLMResult(text='SYNTHETIC response', provider='ollama', model='synthetic', digest='0' * 64,
            elapsed_ms=1, usage={'output_tokens': 1}, settings={}, messages=[])
        copied.result = validate_answer(DraftAnswer(answer='SYNTHETIC supported report.', citations=['E1'],
                                                   insufficient_evidence=False), copied.retrieval)
        return copied
    monkeypatch.setattr(runner, 'run_query', query)
    def load_gold(*args):
        assert len(calls) == 96, 'Gold parsed before the generation matrix completed'
        return gold
    monkeypatch.setattr(runner, '_gold', load_gold)
    monkeypatch.setattr(runner, 'retrieve_embedding', lambda *a, **k: {'retrieval': base.retrieval.model_dump(mode='json')})
    return freeze_path, approval_path, private, calls


def test_once_only_private_execution_and_complete_blind_scoring(tmp_path, monkeypatch):
    freeze, approval, private, calls = synthetic_execution(tmp_path, monkeypatch)
    try:
        result = runner.execute(freeze, approval, Settings())
    except runner.RunnerFailure as exc:
        # This fixture is explicitly synthetic and lives only in pytest's owned temporary directory.
        pytest.fail(Path(exc.private_report).read_text(encoding='utf-8'))
    assert result['answer_runs'] == 96 and result['encoder_reads'] == 48 and len(calls) == 96
    assert result['condition_results_revealed'] is False
    assert all(Counter(request.mode for request in calls[i:i+4]) == Counter(RunPlan().conditions) for i in range(0, 96, 4))
    with pytest.raises(ValueError, match='already started'):
        runner.execute(freeze, approval, Settings())
    replacement = approval.with_name('new-approval.json')
    authorization(replacement, freeze, authorization_id='2' * 32)
    with pytest.raises(ValueError, match='already started'):
        runner.execute(freeze, replacement, Settings())
    assert len(calls) == 96
    packet = Path(result['scoring_packet_directory'])
    with pytest.raises(runner.RunnerFailure):
        runner.grade(freeze, approval)  # No sealed human form yet.
    with pytest.raises(runner.RunnerFailure):
        runner.grade(freeze, approval, scores_path=packet / 'scores.csv')
    with (packet / 'scores.csv').open(newline='') as handle:
        rows = list(csv.DictReader(handle))
    for row in rows:
        row.update(correctness='1', citation_support='1', correct_abstention='', reviewer='SYNTHETIC TEST ONLY',
                   scored_at='2026-11-14T12:00:00Z', notes='Synthetic fixture; not real human scoring')
    completed = packet / 'synthetic-completed.csv'
    with completed.open('w', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=SCORE_FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    assert runner.grade(freeze, approval, scores_path=completed)['answers'] == 96
    revealed = runner.grade(freeze, approval)
    assert revealed['splits']['held_out']['questions'] == 16
    assert revealed['splits']['development']['questions'] == 8
    assert all(row['queries'] == 24 for row in revealed['vector_encoders'].values())
    assert 'SYNTHETIC SECRET' not in json.dumps(revealed)
    assert all('question_id' not in row for row in revealed['conditions'].values())


def test_frozen_executable_hash_changes_fail_before_any_private_input_read(tmp_path, monkeypatch):
    freeze_path, _, _, _ = synthetic_execution(tmp_path, monkeypatch)
    freeze = FreezeManifest.model_validate_json(freeze_path.read_bytes())
    tracked = Path('src/research_assistant/synthetic.py')
    tracked.parent.mkdir(parents=True)
    tracked.write_text('# synthetic frozen code\n')
    readiness, proof = Path(freeze.readiness_path), Path(freeze.recovery_report)
    readiness.parent.mkdir(parents=True, exist_ok=True)
    readiness.write_text('{}')
    proof.write_text('{}')
    snapshot = Path(freeze.snapshot_directory)
    (snapshot / 'manifest.json').write_text('{}')
    freeze.files = {tracked.as_posix(): file_sha(tracked)}
    freeze.readiness_file_sha256, freeze.recovery_report_sha256 = file_sha(readiness), file_sha(proof)
    freeze.snapshot_manifest_sha256 = file_sha(snapshot / 'manifest.json')
    freeze_path.write_text(freeze.model_dump_json())
    monkeypatch.setattr(guards, 'code_identity', lambda: {'source_tree_sha256': freeze.source_tree_sha256})
    monkeypatch.setattr(guards, 'verify_snapshot', lambda path: ({'graph_sha256': freeze.graph_sha256}, {}))
    assert guards.load_freeze(freeze_path).graph_sha256 == freeze.graph_sha256
    tracked.write_text('# changed after freeze\n')
    with pytest.raises(ValueError, match='asset changed'):
        guards.load_freeze(freeze_path)


@pytest.mark.parametrize('field,value', [('target_uri', 'bolt://remote.example:9765'),
    ('ollama_base_url', 'https://remote.example'), ('target_uri', 'neo4j://127.0.0.1:9765'),
    ('docker_image_id', 'neo4j:latest')])
def test_frozen_services_cannot_expand_to_remote_or_mutable_targets(tmp_path, monkeypatch, field, value):
    path, _, _, _ = synthetic_execution(tmp_path, monkeypatch)
    raw = json.loads(path.read_text())
    raw[field] = value
    with pytest.raises(ValueError):
        FreezeManifest.model_validate(raw)
