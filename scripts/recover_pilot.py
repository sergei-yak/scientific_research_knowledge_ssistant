"""Exercise a snapshot in fresh Compose volumes; keep the stopped target for inspection."""

import argparse
import hashlib
import json
import os
import socket
import subprocess
import time
import uuid
from pathlib import Path

from research_assistant.contracts import QueryRequest, RetrievalResult
from research_assistant.embeddings import Encoder
from research_assistant.evaluation.development import load_dataset, review_status
from research_assistant.evaluation.scoring import score_evidence
from research_assistant.graph.recovery import capture, restore_snapshot, verify_snapshot
from research_assistant.graph.repository import GraphRepository
from research_assistant.ingestion.sources import load_corpus_chunks
from research_assistant.pipeline import run_query, write_immutable
from research_assistant.product import PILOT_CORPUS, WORKFLOWS, prepare_output
from research_assistant.retrieval.service import retrieve_request
from research_assistant.retrieval.evidence import estimate_tokens
from research_assistant.settings import Settings, configure_caches


def main() -> int:
    """Create a unique target, restore, verify copied assets/retrieval/scoring, stop without deletion."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--snapshot-dir', type=Path, required=True)
    parser.add_argument('--output-dir', type=Path, required=True)
    parser.add_argument('--bolt-port', type=int, default=8765)
    parser.add_argument('--http-port', type=int, default=8475)
    args = parser.parse_args()
    root = Path.cwd().resolve()
    snapshot_dir, output = args.snapshot_dir.resolve(), args.output_dir.resolve()
    if output.exists():
        parser.error('Use a fresh output directory')
    manifest, graph = verify_snapshot(snapshot_dir)
    settings = Settings.from_env()
    if capture(settings) != graph:
        parser.error('Source graph changed since snapshot; create a new export')
    for port in (args.bolt_port, args.http_port):
        with socket.socket() as probe:
            probe.bind(('127.0.0.1', port))
    configure_caches()
    # The encoder is a separately installed prerequisite, not read from the old source caches.
    encoder = Encoder()
    estimate_tokens('Warm the pinned estimator before switching to restored files.')
    project = 'dbu-m3-recovery-' + uuid.uuid4().hex[:12]
    env = {**os.environ, 'NEO4J_BOLT_PORT': str(args.bolt_port), 'NEO4J_HTTP_PORT': str(args.http_port)}
    command = ['docker', 'compose', '-p', project, '-f', str(root / 'compose.yaml')]
    for volume in (project + '_neo4j_data', project + '_neo4j_logs'):
        if subprocess.run(['docker', 'volume', 'inspect', volume], capture_output=True).returncode == 0:
            parser.error('Disposable volume already exists; refusing reuse')
    output.mkdir(parents=True)
    target = settings.model_copy(update={'neo4j_uri': f'bolt://127.0.0.1:{args.bolt_port}'})
    record = {'task_id': 'M3.3', 'project': project, 'source_uri': settings.neo4j_uri,
              'target_uri': target.neo4j_uri, 'source_database': settings.neo4j_database,
              'ports': {'bolt': args.bolt_port, 'http': args.http_port},
              'snapshot_manifest_sha256': hashlib.sha256((snapshot_dir / 'manifest.json').read_bytes()).hexdigest(),
              'commands': {'up': command + ['up', '-d', 'neo4j'], 'stop': command + ['stop', 'neo4j']},
              'paid_calls': 0, 'llm_calls': 0, 'held_out_accesses': 0, 'complete': False}
    write_immutable(output / 'target.json', json.dumps(record, indent=2) + '\n')
    try:
        up = subprocess.run(command + ['up', '-d', 'neo4j'], env=env, capture_output=True, text=True, timeout=120)
        write_immutable(output / 'startup.log', up.stdout + up.stderr)
        up.check_returncode()
        for _ in range(90):
            repo = GraphRepository(target)
            try:
                repo.driver.verify_connectivity()
                break
            except Exception:
                time.sleep(2)
            finally:
                repo.close()
        else:
            raise RuntimeError('Disposable Neo4j target did not become ready')
        print('Fresh target ready; restoring verified snapshot.', flush=True)
        record['restore'] = restore_snapshot(snapshot_dir, target, project)
        try:
            restore_snapshot(snapshot_dir, target, project)
        except ValueError as exc:
            if 'must be empty' not in str(exc):
                raise
            record['nonempty_target_restore_refused'] = True
        else:
            raise ValueError('Existing target unexpectedly accepted a second restore')
        print('Semantic graph/schema restored exactly; checking copied source/review assets.', flush=True)
        os.chdir(snapshot_dir / 'files')
        chunks = load_corpus_chunks(PILOT_CORPUS)
        requests = [json.loads(line) for line in Path('data/evaluation/development/pilot-v1/questions.jsonl').read_text(encoding='utf-8').splitlines()]
        fresh = {}
        for request in requests:
            for mode in ('vector', 'hybrid', 'hybrid_facts', 'graph'):
                _, retrieved = retrieve_request(QueryRequest(corpus_id=PILOT_CORPUS, mode=mode, question=request['question']),
                                                 target, encoder=encoder)
                fresh[(request['question_id'], mode)] = retrieved
                write_immutable(output / 'fresh-retrieval' / request['question_id'] / (mode + '.json'), retrieved.model_dump_json(indent=2) + '\n')
        # Gold is development-only and is loaded only for scoring, never passed to retrieval/generation.
        dataset_dir = Path('data/evaluation/development/pilot-v1')
        _, entries, _ = load_dataset(dataset_dir)
        record['gold_validation'] = review_status(dataset_dir)
        if not record['gold_validation']['ready']:
            raise ValueError('Restored development approvals are not ready')
        replay, new_scores = [], []
        recorded_scores = json.loads(Path('runs/m3/pilot-verified/summary.json').read_text(encoding='utf-8'))['scores']
        for entry in entries:
            question = entry.gold
            for mode in ('vector', 'hybrid', 'hybrid_facts', 'graph'):
                saved = json.loads((Path('runs/m3/pilot-verified') / question.question_id / (mode + '.json')).read_text(encoding='utf-8'))
                original = RetrievalResult.model_validate(saved['retrieval'])
                rescored = score_evidence(question, original, chunks)
                if rescored != recorded_scores[question.question_id][mode]:
                    raise ValueError('Saved-context scoring differs from the recorded original result')
                replay.append({'mode': mode, **rescored})
                new_scores.append({'mode': mode, **score_evidence(question, fresh[(question.question_id, mode)], chunks)})
        record['saved_context_scoring_replays'] = len(replay)
        record['saved_scores_exactly_reproduced'] = True
        record['fresh_retrievals_scored'] = len(new_scores)
        write_immutable(output / 'scoring-replay.json', json.dumps({'saved': replay, 'fresh': new_scores}, indent=2) + '\n')
        products = []
        for workflow in ('discovery', 'comparison', 'limitations'):
            run = run_query(QueryRequest(corpus_id=PILOT_CORPUS, mode='graph', question=WORKFLOWS[workflow]),
                            target, generate=False, workflow=workflow, encoder=encoder)
            view, csv_text = prepare_output(run, target)
            if view.status != 'evidence available':
                raise ValueError('Restored product scenario has insufficient selected evidence')
            write_immutable(output / 'products' / workflow / 'run.json', run.model_dump_json(indent=2) + '\n')
            write_immutable(output / 'products' / workflow / 'evidence.csv', csv_text)
            products.append(view.model_dump())
        record['product_workflows'] = products
        os.chdir(root)
        print('32 retrievals, 32 saved scoring replays and product workflows passed; exercising isolated guards.', flush=True)
        test_env = {**os.environ, 'NEO4J_URI': target.neo4j_uri, 'RUN_RETRIEVAL_SMOKE': '1', 'RUN_REVIEW_SMOKE': '1',
                    'M3_FIXTURE_REPORT': str(output / 'native-retrieval-fixture.json')}
        tests = ['uv', 'run', '--locked', '--offline', 'pytest', '-m', 'integration',
                 'tests/integration/test_graph_retrieval_repository.py', 'tests/integration/test_review_repository.py', '-q']
        check = subprocess.run(tests, env=test_env, capture_output=True, text=True, timeout=180)
        write_immutable(output / 'native-guards.log', check.stdout + check.stderr)
        record['commands']['native_guards'] = tests
        record['native_guards_exit_code'] = check.returncode
        check.check_returncode()
        if capture(target) != graph or capture(settings) != graph:
            raise ValueError('Source/restored project changed after acceptance/fixtures')
        verify_snapshot(snapshot_dir)
        record['complete'] = True
        record['source_preserved'] = True
        record['restored_assets_unchanged'] = True
    except Exception as exc:
        record['error'] = settings.redact(str(exc))
        raise
    finally:
        os.chdir(root)
        stopped = subprocess.run(command + ['stop', 'neo4j'], env=env, capture_output=True, text=True, timeout=90)
        record['target_stopped'] = stopped.returncode == 0
        write_immutable(output / 'stop.log', stopped.stdout + stopped.stderr)
        write_immutable(output / 'report.json', json.dumps(record, indent=2) + '\n')
    print(json.dumps({'complete': record['complete'], 'target_stopped': record['target_stopped'], 'report': str(output / 'report.json')}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
