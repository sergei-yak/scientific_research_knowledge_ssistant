"""Once-only, numerically bounded public/local import proof on the declared M8 target."""

import hashlib
import json
import os
from pathlib import Path
import subprocess
import time

import pytest

from research_assistant.collections.contracts import InputReference
from research_assistant.collections.scope import guard_user_write, load_user_scope
from research_assistant.collections.store import CollectionRegistry
from research_assistant.embeddings import Encoder
from research_assistant.graph.recovery import capture
from research_assistant.graph.repository import GraphRepository
from research_assistant.graph.search import SearchRepository
from research_assistant.ingestion.sources import load_corpus_chunks
from research_assistant.ingestion.user_download import download_pdf
from research_assistant.ingestion.user_import import ImportInput, run_import
from research_assistant.contracts import fingerprint
from research_assistant.settings import Settings

pytestmark = [pytest.mark.integration, pytest.mark.skipif(os.getenv('RUN_USER_IMPORT_SMOKE') != '1',
    reason='Requires a fresh numerical M8.2 engineering plan and the exact M8 target')]


def test_bound_real_pdf_and_link_import_once():
    """Retain all outcomes; a failed link permits independent upload work, never a URL retry."""
    out = Path('runs/m8/m8-2')
    plan_path = out / 'engineering-plan-v1.json'
    plan = json.loads(plan_path.read_bytes())
    scope, settings = load_user_scope(), Settings.from_env()
    assert scope.scope_id == plan['scope_id'] and scope.target_uri == settings.neo4j_uri == plan['target_uri']
    assert plan['automatic_retries'] == plan['paid_spend'] == plan['generator_requests'] == 0
    marker = out / 'engineering-started.json'
    with marker.open('x', encoding='utf-8') as handle:
        handle.write(json.dumps({'plan_sha256': hashlib.sha256(plan_path.read_bytes()).hexdigest(),
                                'once_only': True}) + '\n')
    ledger = out / 'engineering-events.jsonl'
    counters = {'jobs': 0, 'download_chains': 0, 'http_attempts': 0, 'encode_calls': 0, 'encoded_texts': 0, 'index_reads': 0}
    def reserve(kind, amount=1):
        bounds = {'jobs': plan['max_import_jobs'], 'download_chains': plan['max_download_chains'],
                  'http_attempts': plan['max_http_attempts'], 'encode_calls': plan['max_document_encode_calls'],
                  'encoded_texts': plan['max_encoded_texts'], 'index_reads': plan['max_derived_index_reads']}
        if counters[kind] + amount > bounds[kind]:
            raise ValueError('Engineering bound exceeded: ' + kind)
        counters[kind] += amount
        with ledger.open('a', encoding='utf-8') as handle:
            handle.write(json.dumps({'kind': kind, 'reserved': amount, 'total': counters[kind],
                                    'monotonic_time': time.monotonic()}) + '\n')
            handle.flush()
            os.fsync(handle.fileno())
    assets = json.loads((out / 'provisioned-model-assets.json').read_bytes())['assets']
    for path, record in assets.items():
        assert hashlib.sha256(Path(path).read_bytes()).hexdigest() == record['sha256']
    upload_path = Path(plan['upload_path'])
    assert hashlib.sha256(upload_path.read_bytes()).hexdigest() == plan['upload_sha256']
    prior_views = json.loads(Path('runs/m8/m8-1/protected-targets-before.json').read_bytes())
    before = {name: fingerprint(capture(Settings.from_env(Path(row['root']) / '.env')))
              for name, row in prior_views.items()}
    (out / 'protected-before.json').write_text(json.dumps(before, indent=2) + '\n')
    command = ['docker', 'compose', '--env-file', str(Path('.env').resolve()), '-p', scope.target_project,
               '-f', str(Path('compose.yaml').resolve())]
    process_env = {k: v for k, v in os.environ.items() if not k.startswith(('NEO4J_', 'COMPOSE_'))}
    startup = subprocess.run(command + ['up', '-d', '--pull', 'never', 'neo4j'], env=process_env,
                             capture_output=True, text=True, timeout=60)
    (out / 'target-startup.log').write_text(startup.stdout + startup.stderr)
    startup.check_returncode()
    for attempt in range(30):
        try:
            guard_user_write(settings)
            break
        except Exception:
            if attempt == 29: raise
            time.sleep(1)
    class CountedEncoder(Encoder):
        def __init__(self):
            import torch
            torch.set_num_threads(4)
            super().__init__()
        def encode(self, texts):
            reserve('encode_calls')
            reserve('encoded_texts', len(texts))
            return super().encode(texts)
    def counted_download(url, path, reserve):
        assert url == plan['allowed_url']
        reserve_chain = globals_reserve
        reserve_chain('download_chains')
        def attempt(record):
            reserve_chain('http_attempts')
            reserve(record)
        return download_pdf(url, path, reserve=attempt)
    globals_reserve = reserve
    registry = CollectionRegistry()
    row = registry.create('M8.2 public import engineering')
    initial = row
    outcomes = []
    def execute(entries):
        reserve('jobs')
        current = registry.get(row.collection_id)
        job = registry.queue(current.collection_id, current.sha256, tuple(e.reference for e in entries))
        result = run_import(registry, job.job_id, entries, settings,
                            encoder_factory=CountedEncoder, downloader=counted_download)
        outcomes.append(result)
        (out / ('engineering-job-' + str(len(outcomes)) + '.json')).write_text(json.dumps(result, indent=2) + '\n')
        return result
    link_passed = False
    try:
        with upload_path.open('rb') as stream:
            mixed = execute([ImportInput(InputReference(kind='upload', value=upload_path.name), stream),
                             ImportInput(InputReference(kind='url', value=plan['allowed_url']))])
        if mixed['status'] == 'ready':
            link_passed = True
        else:
            assert registry.get(row.collection_id) == initial, 'Failed batch must not publish a new revision'
            with upload_path.open('rb') as stream:
                local = execute([ImportInput(InputReference(kind='upload', value=upload_path.name), stream)])
            assert local['status'] == 'ready', local
        indexed = registry.get(row.collection_id)
        registry.committed_import(indexed)
        with upload_path.open('rb') as stream:
            duplicate = execute([ImportInput(InputReference(kind='upload', value='renamed-upload.pdf'), stream)])
        assert duplicate['status'] == 'duplicate' and registry.get(row.collection_id) == indexed
        sources = load_corpus_chunks(indexed.corpus_id)
        reserve('index_reads')
        repository = GraphRepository(settings)
        try:
            snapshot = repository.snapshot(indexed.corpus_id)
            assert snapshot['chunk_count'] == len(sources) == indexed.binding.chunk_count
            members = json.loads((Path('data/processed') / indexed.corpus_id / 'members.json').read_bytes())
            vector_path = Path(members[0]['snapshot_path']).with_name('vectors-384.json')
            vector = json.loads(vector_path.read_bytes())[0]
            reserve('index_reads')
            matches = repository.vector_candidates(indexed.corpus_id, vector)
            assert matches and all(chunk.chunk_id in sources for chunk, _ in matches)
        finally:
            repository.close()
        reserve('index_reads')
        search = SearchRepository(settings)
        try:
            with search.reading(indexed.corpus_id, None, 30):
                search.check_indexes(indexed.corpus_id, False)
        finally:
            search.close()
        assert len(indexed.documents) == (2 if link_passed else 1)
        assert registry.describe(indexed)['available_modes'] == []  # M8.3 performs product readiness checks
        report = {'status': 'passed' if link_passed else 'partial', 'link_passed': link_passed,
            'upload_passed': True, 'duplicate_unchanged': True, 'source_cache_exact': True,
            'native_vector_membership_passed': True, 'native_indexes_online': True,
            'collection_id': indexed.collection_id, 'corpus_id': indexed.corpus_id,
            'documents': len(indexed.documents), 'chunks': len(sources),
            'counters': counters, 'generator_requests': 0, 'paid_spend': 0,
            'pending': [] if link_passed else ['Live supported arXiv import did not pass; no URL retry performed']}
        (out / 'native-import-proof.json').write_text(json.dumps(report, indent=2) + '\n')
    finally:
        after = {name: fingerprint(capture(Settings.from_env(Path(row['root']) / '.env')))
                 for name, row in prior_views.items()}
        assert after == before
        (out / 'protected-after.json').write_text(json.dumps(after, indent=2) + '\n')
        stopped = subprocess.run(command + ['stop', 'neo4j'], env=process_env,
                                 capture_output=True, text=True, timeout=60)
        (out / 'target-stop.log').write_text(stopped.stdout + stopped.stderr)
        stopped.check_returncode()
