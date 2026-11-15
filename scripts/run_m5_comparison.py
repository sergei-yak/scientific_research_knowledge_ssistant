"""Prepare/run the once-only public M5.4 retrieval matrix; no gold/provider imports."""

import argparse
import json
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

from research_assistant.contracts import QueryRequest, RunArtifact, fingerprint, text_sha
from research_assistant.embeddings import Encoder
from research_assistant.evaluation.freeze import file_sha
from research_assistant.graph.recovery import capture
from research_assistant.graph.search import SearchRepository, plan_metrics
from research_assistant.ingestion.sources import load_corpus_chunks, source_identity
from research_assistant.pipeline import code_identity, run_query, write_immutable
from research_assistant.product import prepare_output
from research_assistant.retrieval.catalog import load_catalog
from research_assistant.retrieval.profiles import retrieval_profile, validate_scope
from research_assistant.retrieval.reranker import verified_manifest, model_identity
from research_assistant.review.store import review_lock
from research_assistant.settings import Settings, configure_caches
from research_assistant.smoke import check_resources

ROOT = Path('runs/retrieval-v2/m5-4/comparison-v1')
POLICY = Path('runs/retrieval-v2/diagnostics/m5-1-20261115T203824Z-a4189b/development-comparison-manifest-v2.json')
DATA = Path('data/evaluation/development/expansion-v1')
REVIEW = Path('data/reviews/expansion-v1')
SCOPE = Path('data/scopes/retrieval-v2.json')
ARMS = [('A0', 'baseline', 'reference'), ('A1', 'retrieval-v2', 'reference'), ('A2', 'retrieval-v2', 'cross_encoder')]
MODES = ['vector', 'hybrid', 'hybrid_facts', 'graph']
EXPECTED_GRAPH = '58a501badf4c47b7e1ab7fbc606a393ba953c342ec5fc2cceafa419bb6bc10fe'


def save(path, value):
    """Exclusive JSON output; never overwrite an experiment receipt."""
    write_immutable(path, json.dumps(value, indent=2, ensure_ascii=False) + '\n')


def inputs():
    """Bind code, tests, runner/scorer, policies and unchanged public question bytes."""
    paths = [p for prefix in ('src', 'tests') for p in Path(prefix).rglob('*.py')]
    paths += [Path('scripts/run_m5_comparison.py'), Path('scripts/score_m5_comparison.py'),
              Path('pyproject.toml'), Path('uv.lock'), POLICY, SCOPE,
              Path('manifests/reranker-msmarco-minilm-l6-v1.json'), DATA/'questions.jsonl', DATA/'manifest.json']
    return {str(p): file_sha(p) for p in sorted(paths)}


def ready():
    """Attest the new physical target/current source and all search indexes without writes."""
    settings = Settings.from_env()
    scope = json.loads(SCOPE.read_text(encoding='utf-8'))
    chunks = load_corpus_chunks(scope['corpus_id'])
    with review_lock(REVIEW):
        catalog = load_catalog(REVIEW, scope['corpus_id'], chunks)
        repo = SearchRepository(settings)
        try:
            validate_scope(QueryRequest(question='Scope readiness', corpus_id=scope['corpus_id'],
                profile_id='retrieval-v2', scope_file=str(SCOPE)), settings, REVIEW, chunks, catalog, repo)
            snapshot = repo.snapshot(scope['corpus_id'])
            with repo.reading(scope['corpus_id'], catalog.head, 30):
                repo.check_indexes(scope['corpus_id'], True)
                repo.fact_vectors(catalog, chunks, snapshot['encoder_revision'], strict_roles=True)
        finally:
            repo.close()
    graph = capture(settings)
    assert fingerprint(graph) == EXPECTED_GRAPH
    assert len(catalog.facts) == 51 and catalog.head == scope['review_head']
    assert fingerprint(catalog.facts) == '8f0ad62ac6f6d190ef15b981d3bececa9d777203bac61d8b82361a3394004989'
    assert source_identity(chunks) == scope['source_chunks_sha256']
    stopped = subprocess.run(['docker', 'inspect', 'dbu-m4-recovery-edaaed2160a3-neo4j-1',
        '--format', '{{.State.Status}}'], capture_output=True, text=True, check=True).stdout.strip()
    assert stopped == 'exited'
    return settings, {'scope': scope, 'catalog_sha256': fingerprint(catalog.facts),
        'approved_facts': len(catalog.facts), 'graph_sha256': fingerprint(graph),
        'index_schema_sha256': fingerprint(graph['indexes']), 'snapshot': snapshot,
        'consumed_target_stopped': True}


def prepare():
    """Record execution and scoring semantics before the first measured retrieval."""
    if ROOT.exists():
        raise ValueError('Existing immutable comparison; do not prepare/restart it')
    assert file_sha(POLICY) == '94ffd77ec1e71a83d8825e7e81b562a818cea18209c043f28a575d8e6f7b7269'
    policy = json.loads(POLICY.read_text(encoding='utf-8'))
    metadata = json.loads((DATA/'manifest.json').read_text(encoding='utf-8'))
    questions = [json.loads(line) for line in (DATA/'questions.jsonl').read_text(encoding='utf-8').splitlines()]
    assert text_sha((DATA/'questions.jsonl').read_text(encoding='utf-8')) == metadata['questions_sha256']
    assert [q['question_id'] for q in questions] == policy['development_ids']
    assert all(q['split'] == 'development' and set(q) <= {'category', 'question', 'question_id', 'secondary_tags', 'split'} for q in questions)
    _, readiness = ready()
    model = verified_manifest()
    manifest = {'task_id': 'M5.4', 'prepared_at': datetime.now(timezone.utc).isoformat(),
        **code_identity(), 'file_sha256': inputs(), 'policy': policy, 'readiness': readiness,
        'profiles': {arm: retrieval_profile(profile, selector).model_dump() for arm, profile, selector in ARMS},
        'model': model.model_dump(), 'model_identity': model_identity(model),
        'arms': ARMS, 'modes': MODES, 'questions': questions,
        'request_limit': 96, 'concurrency': 1, 'retries': 0, 'generation': 0, 'paid': 0,
        'cache_policy': 'Fresh runner process; one resident MiniLM initialized before matrix. No inference warmup. First A2 loads reranker; thereafter resident. Each request rehashes assets; per-request feature cache starts empty. OS/Neo4j caches uncontrolled and likely warm from prior engineering. Fixed order, not a speed benchmark.',
        'resources_at_prepare': check_resources(),
        'scoring': {'when': 'Separate offline process after all artifacts are sealed; gold never enters retrieval',
            'candidate_pool': 'Canonical eligible pre-packing source excerpt union, graph uses merged retained pool; report baseline and graph pool separately. Not generator context or top-6.',
            'final': 'Shared score_evidence on actual source-validated rendered final context; unanswerable N/A',
            'novel_support': 'Final Graph fact absent from paired fact-ablation final AND absent after removing every selected ID outside full ablation candidate pool; witness novel exact registered source overlaps. Joint/OR-redundant contributions allowed, no individually-necessary-item claim.',
            'gate': policy['go_no_go'], 'tolerance': 1e-12},
        'query_plan_probes': 'After measured matrix only: for A0/A1/A2 each family, first nonempty saved call (else first call), EXPLAIN+PROFILE, at most 24 read-only executions. Report operator work separately; no inference/retrieval request retry.',
        'failure_policy': policy['execution_order']['failure_policy'], 'private_access': False}
    save(ROOT/'execution-manifest.json', manifest)
    print(json.dumps({'prepared': str(ROOT), 'manifest_sha256': file_sha(ROOT/'execution-manifest.json'), 'readiness': readiness}, default=str), flush=True)


def run():
    """Reserve once before each sequential request; retain failures and stop affected arm."""
    manifest = json.loads((ROOT/'execution-manifest.json').read_text(encoding='utf-8'))
    assert inputs() == manifest['file_sha256']
    if (ROOT/'execution-started.json').exists():
        raise ValueError('Started matrix cannot be retried/resumed by this runner')
    settings, readiness = ready()
    assert readiness == manifest['readiness']
    save(ROOT/'execution-started.json', {'manifest_sha256': file_sha(ROOT/'execution-manifest.json'),
        'started_at': datetime.now(timezone.utc).isoformat(), 'resources': check_resources()})
    t = time.perf_counter(); encoder = Encoder(); encoder_ms = (time.perf_counter()-t)*1000
    outcomes = []; failed = set()
    for question in manifest['questions']:
        for arm, profile, selector in ARMS:
            if arm in failed:
                continue
            for mode in MODES:
                identity = question['question_id'] + '-' + arm + '-' + mode
                save(ROOT/'reservations'/(identity+'.json'), {'id': identity, 'sequence': len(outcomes)+1,
                     'reserved_at': datetime.now(timezone.utc).isoformat(), 'manifest_sha256': file_sha(ROOT/'execution-manifest.json')})
                request = QueryRequest(question=question['question'], corpus_id=readiness['scope']['corpus_id'],
                    mode=mode, profile_id=profile, selector_id=selector, scope_file=str(SCOPE) if profile=='retrieval-v2' else None)
                started = time.perf_counter()
                try:
                    run_artifact = run_query(request, settings, review_directory=REVIEW, generate=False, encoder=encoder)
                    wall_ms = (time.perf_counter()-started)*1000
                    assert not run_artifact.generation_requested and run_artifact.generation is None and run_artifact.result is None
                    save(ROOT/'runs'/(identity+'.json'), run_artifact.model_dump())
                    started = time.perf_counter(); prepare_output(run_artifact, settings, review_directory=REVIEW)
                    row = {'id': identity, 'question_id': question['question_id'], 'arm': arm, 'mode': mode,
                        'status': 'passed', 'run_sha256': file_sha(ROOT/'runs'/(identity+'.json')),
                        'run_query_wall_ms': wall_ms, 'export_validation_ms': (time.perf_counter()-started)*1000,
                        'context_sha256': run_artifact.retrieval.context_sha256}
                except Exception as exc:
                    row = {'id': identity, 'status': 'failed', 'error_type': type(exc).__name__, 'error': settings.redact(str(exc)),
                        'selection_diagnostics': getattr(exc, 'selection_diagnostics', None)}
                    failed.add(arm)
                save(ROOT/'outcomes'/(identity+'.json'), row); outcomes.append(row)
                print(json.dumps({k:v for k,v in row.items() if k!='selection_diagnostics'}), flush=True)
                if arm in failed:
                    break
    _, after = ready(); assert after == readiness
    save(ROOT/'execution-complete.json', {'task_id': 'M5.4', 'outcomes': outcomes, 'attempts': len(outcomes),
        'failures': sum(r['status']=='failed' for r in outcomes), 'encoder_initialization_ms': encoder_ms,
        'resources_after': check_resources(), 'target_preserved': True, 'generation': 0, 'paid': 0,
        'private_access': False, 'completed_at': datetime.now(timezone.utc).isoformat()})


def plans():
    """Replay bounded saved route plans separately from matrix latency/inference."""
    manifest = json.loads((ROOT/'execution-manifest.json').read_text(encoding='utf-8'))
    assert inputs() == manifest['file_sha256'] and (ROOT/'execution-complete.json').exists()
    if (ROOT/'query-plan-probes.json').exists():
        raise ValueError('Plan probes already recorded')
    settings, before = ready(); results = []
    repo = SearchRepository(settings)
    try:
        for arm, profile, _ in ARMS:
            by_family = {}
            for q in manifest['questions']:
                run_artifact = RunArtifact.model_validate_json((ROOT/'runs'/(q['question_id']+'-'+arm+'-graph.json')).read_bytes())
                for call in run_artifact.retrieval.audit['graph_calls']:
                    key = call['template']
                    if key not in by_family or (not by_family[key]['rows'] and call['rows']):
                        by_family[key] = call
            for family, call in by_family.items():
                inspections = {}
                for inspection in ('EXPLAIN', 'PROFILE'):
                    with repo.reading(before['scope']['corpus_id'], before['scope']['review_head'], 30):
                        rows, plan = repo.traverse(before['scope']['corpus_id'], family, call['parameters'], inspection, profile_id=profile)
                    inspections[inspection] = {'returned_rows': len(rows), 'metrics': plan_metrics(plan)}
                    if inspection=='PROFILE':
                        assert rows == call['rows']
                results.append({'arm': arm, 'family': family, 'anchor': call['seed_id'], 'saved_rows': len(call['rows']), 'inspections': inspections})
    finally:
        repo.close()
    assert ready()[1] == before
    save(ROOT/'query-plan-probes.json', {'separate_read_only_executions': len(results)*2, 'results': results,
        'selection': manifest['query_plan_probes'], 'target_preserved': True})
    print(json.dumps({'plan_probes': len(results)*2, 'families': len(results)}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument('action', choices=['prepare', 'run', 'plans'])
    configure_caches(); globals()[parser.parse_args().action]()
