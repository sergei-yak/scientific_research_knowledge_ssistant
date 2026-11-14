"""Verify the expanded frozen export in a fresh target, then prove server-enforced read-only access."""

import argparse
import json
import os
from pathlib import Path
import socket
import subprocess
import time
import uuid

from research_assistant.contracts import QueryRequest, RetrievalResult, fingerprint
from research_assistant.embeddings import Encoder, MPNetEncoder
from research_assistant.evaluation.development import load_dataset, review_status
from research_assistant.evaluation.freeze import file_sha, public_asset
from research_assistant.evaluation.scoring import score_evidence
from research_assistant.graph.recovery import capture, require_read_only, restore_snapshot, verify_snapshot
from research_assistant.graph.repository import GraphRepository
from research_assistant.pipeline import run_query, write_immutable
from research_assistant.product import WORKFLOWS, prepare_output
from research_assistant.retrieval.embedding_experiment import retrieve_embedding
from research_assistant.retrieval.evidence import estimate_tokens
from research_assistant.settings import Settings, configure_caches


def wait_ready(settings: Settings) -> None:
    """Bound readiness waiting for the fresh target only."""
    for _ in range(90):
        repo = GraphRepository(settings)
        try:
            repo.driver.verify_connectivity()
            return
        except Exception:
            time.sleep(2)
        finally:
            repo.close()
    raise RuntimeError('Disposable target did not become ready')


def main() -> int:
    """No provider calls, held-out inputs, working-data resets or volume deletions."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--snapshot-dir', type=Path, required=True)
    parser.add_argument('--output-dir', type=Path, required=True)
    parser.add_argument('--bolt-port', type=int, default=9765)
    parser.add_argument('--http-port', type=int, default=9475)
    args = parser.parse_args()
    root = Path.cwd().resolve()
    snapshot_dir, output = public_asset(args.snapshot_dir), public_asset(args.output_dir)
    if output.exists():
        parser.error('Use a fresh recovery output directory')
    manifest, graph = verify_snapshot(snapshot_dir)
    settings = Settings.from_env()
    source_sha = fingerprint(capture(settings))
    if source_sha != manifest['source_graph_sha256'] or not manifest.get('freeze_projection'):
        parser.error('Source graph changed or the export lacks its explicit frozen projection')
    for port in (args.bolt_port, args.http_port):
        with socket.socket() as probe:
            probe.bind(('127.0.0.1', port))
    configure_caches()
    mini, mpnet = Encoder(), MPNetEncoder()
    estimate_tokens('Warm the pinned estimator before using copied development assets.')
    project = 'dbu-m4-recovery-' + uuid.uuid4().hex[:12]
    env = {**os.environ, 'NEO4J_READ_ONLY': 'false', 'NEO4J_BOLT_PORT': str(args.bolt_port), 'NEO4J_HTTP_PORT': str(args.http_port)}
    command = ['docker', 'compose', '-p', project, '-f', str(root / 'compose.yaml')]
    for volume in (project + '_neo4j_data', project + '_neo4j_logs'):
        if subprocess.run(['docker', 'volume', 'inspect', volume], capture_output=True).returncode == 0:
            parser.error('Disposable target volume already exists; refusing reuse')
    output.mkdir(parents=True)
    target = settings.model_copy(update={'neo4j_uri': f'bolt://127.0.0.1:{args.bolt_port}'})
    record = {'task_id': 'M4.2.3', 'project': project, 'source_uri': settings.neo4j_uri, 'target_uri': target.neo4j_uri,
        'ports': {'bolt': args.bolt_port, 'http': args.http_port}, 'graph_sha256': manifest['graph_sha256'],
        'snapshot_manifest_sha256': file_sha(snapshot_dir / 'manifest.json'), 'complete': False,
        'target_read_only_proved': False, 'provider_calls': 0, 'private_evaluation_inputs_read': 0}
    write_immutable(output / 'target.json', json.dumps(record, indent=2) + '\n')
    try:
        up = subprocess.run(command + ['up', '-d', '--pull', 'never', 'neo4j'], env=env, capture_output=True, text=True, timeout=120)
        write_immutable(output / 'up.log', up.stdout + up.stderr)
        up.check_returncode()
        wait_ready(target)
        record['restore'] = restore_snapshot(snapshot_dir, target, project)
        record['image_id'] = record['restore']['image_id']
        try:
            restore_snapshot(snapshot_dir, target, project)
        except ValueError as exc:
            if 'must be empty' not in str(exc):
                raise
            record['second_restore_refused'] = True
        else:
            raise ValueError('Nonempty restore target was not rejected')
        fixture_env = {**os.environ, 'NEO4J_URI': target.neo4j_uri, 'RUN_RETRIEVAL_SMOKE': '1',
                       'RUN_REVIEW_SMOKE': '1', 'RUN_EMBEDDING_SMOKE': '1'}
        tests = subprocess.run(['uv', 'run', '--locked', '--offline', 'pytest', '-m', 'integration',
            'tests/integration/test_graph_retrieval_repository.py', 'tests/integration/test_review_repository.py',
            'tests/integration/test_embedding_repository.py', '-q', '--junitxml=' + str(output / 'native-guards.xml')],
            env=fixture_env, capture_output=True, text=True, timeout=180)
        write_immutable(output / 'native-guards.log', tests.stdout + tests.stderr)
        tests.check_returncode()
        record['native_guard_cases'] = 3
        if capture(target) != graph:
            raise ValueError('Native fixtures changed restored data/schema')
        env.update(NEO4J_READ_ONLY='true', NEO4J_IMAGE=record['image_id'])
        readonly = subprocess.run(command + ['up', '-d', '--pull', 'never', 'neo4j'], env=env, capture_output=True, text=True, timeout=120)
        write_immutable(output / 'read-only-start.log', readonly.stdout + readonly.stderr)
        readonly.check_returncode()
        wait_ready(target)
        record['read_only_probe'] = require_read_only(target)
        record['target_read_only_proved'] = True
        os.chdir(snapshot_dir / 'files')
        dataset = Path('data/evaluation/development/expansion-v1')
        source, entries, chunks = load_dataset(dataset)
        if source['corpus_id'] != manifest['review_corpus_id'] or not review_status(dataset)['ready']:
            raise ValueError('Restored expanded development/review scope is unready')
        saved = json.loads(Path('runs/m4-2/development-encoders/summary.json').read_text(encoding='utf-8'))['results']
        replays, fresh, context_changes = [], [], 0
        by_id = {entry.gold.question_id: entry.gold for entry in entries}
        for row in saved:
            name = 'mpnet' if row['encoder'] == 'mpnet' else row['mode']
            old = json.loads((Path('runs/m4-2/development-encoders') / row['question_id'] / (name + '.json')).read_text(encoding='utf-8'))
            previous = RetrievalResult.model_validate(old['retrieval'])
            replay = score_evidence(by_id[row['question_id']], previous, chunks)
            if replay != row['score']:
                raise ValueError('Saved development scoring did not reproduce exactly')
            replays.append(replay)
            question = by_id[row['question_id']]
            if row['encoder'] == 'mpnet':
                artifact = retrieve_embedding(source['corpus_id'], question.question, 'mpnet', target, encoder=mpnet)
                retrieved = RetrievalResult.model_validate(artifact['retrieval'])
            else:
                run = run_query(QueryRequest(corpus_id=source['corpus_id'], question=question.question, mode=row['mode']),
                    target, review_directory=Path('data/reviews/expansion-v1'), generate=False, encoder=mini)
                artifact, retrieved = run.model_dump(mode='json'), run.retrieval
            write_immutable(output / 'fresh' / row['question_id'] / (name + '.json'), json.dumps(artifact, indent=2) + '\n')
            fresh.append({'encoder': row['encoder'], 'mode': row['mode'], **score_evidence(question, retrieved, chunks)})
            context_changes += retrieved.context_sha256 != previous.context_sha256
        write_immutable(output / 'scoring.json', json.dumps({'saved_replays': replays, 'fresh': fresh}, indent=2) + '\n')
        record.update(saved_context_scoring_replays=len(replays), fresh_development_retrievals=len(fresh),
                      fresh_context_changes=context_changes, copied_chunks=len(chunks))
        products = []
        for workflow in ('discovery', 'comparison', 'limitations'):
            run = run_query(QueryRequest(corpus_id=source['corpus_id'], mode='graph', question=WORKFLOWS[workflow]),
                target, review_directory=Path('data/reviews/expansion-v1'), generate=False, workflow=workflow, encoder=mini)
            view, csv_text = prepare_output(run, target, Path('data/reviews/expansion-v1'))
            if view.status != 'evidence available':
                raise ValueError('Restored product workflow has no selected evidence')
            write_immutable(output / 'products' / (workflow + '.csv'), csv_text)
            products.append({'workflow': workflow, 'papers': view.paper_count, 'units': len(run.retrieval.evidence)})
        record['products'] = products
        os.chdir(root)
        if capture(target) != graph or fingerprint(capture(settings)) != source_sha:
            raise ValueError('Working/restored graph changed during verification')
        verify_snapshot(snapshot_dir)
        record.update(complete=True, source_preserved=True, copied_assets_verified=True)
    except Exception as exc:
        record['error'] = settings.redact(str(exc))
        raise
    finally:
        os.chdir(root)
        stopped = subprocess.run(command + ['stop', 'neo4j'], env=env, capture_output=True, text=True, timeout=120)
        record['target_stopped'] = stopped.returncode == 0
        write_immutable(output / 'stop.log', stopped.stdout + stopped.stderr)
        write_immutable(output / 'report.json', json.dumps(record, indent=2) + '\n')
    print(json.dumps({'complete': record['complete'], 'target_stopped': record['target_stopped'],
                      'read_only': record['target_read_only_proved'], 'report': str(output / 'report.json')}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
