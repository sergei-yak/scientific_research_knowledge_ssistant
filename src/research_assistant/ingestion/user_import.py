"""Foreground PDF/link imports with durable jobs and source-bound immutable publication."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import logging
from pathlib import Path
import subprocess
import sys
import time
from typing import BinaryIO

from research_assistant.collections.contracts import (
    CorpusBinding, DocumentVersion, InputReference, LIMITS, TERMINAL_STATES, UserCollection,
)
from research_assistant.collections.scope import guard_user_write
from research_assistant.collections.store import CollectionRegistry
from research_assistant.contracts import PaperManifestEntry, fingerprint
from research_assistant.embeddings import Encoder
from research_assistant.graph.repository import GraphRepository
from research_assistant.graph.search import SearchRepository
from research_assistant.ingestion.pdf import make_chunks
from research_assistant.ingestion.sources import load_corpus_chunks, source_identity
from research_assistant.ingestion.user_download import ImportFailure, download_pdf
from research_assistant.ingestion.user_pdf import IMPORT_POLICY, PARSER_TIMEOUT_SECONDS
from research_assistant.pipeline import code_identity, index_prepared_paper, paper_identity, write_immutable
from research_assistant.settings import Settings


@dataclass
class ImportInput:
    """Upload streams are data, not server paths; URLs carry no implicit cookies/credentials."""

    reference: InputReference
    stream: BinaryIO | None = None


@dataclass
class PreparedPaper:
    """Shared parser output and actual document coverage, before any index publication."""

    document: DocumentVersion
    manifest: PaperManifestEntry
    pages: list[dict]


def inspect_isolated(path: Path, output: Path) -> dict:
    """Bound the parser subprocess; retain its exact success/failure artifact without retry."""
    try:
        result = subprocess.run([sys.executable, '-m', 'research_assistant.ingestion.user_pdf', str(path), str(output)],
            capture_output=True, text=True, timeout=PARSER_TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired as exc:
        raise ImportFailure('pdf_parse_timeout', 'PDF inspection exceeded its 60-second limit') from exc
    if not output.exists():
        raise ImportFailure('pdf_parse_failed', 'PDF parser stopped without a complete result')
    record = json.loads(output.read_bytes())
    if result.returncode != 0 or record.get('status') != 'passed':
        raise ImportFailure('pdf_parse_failed', record.get('message', 'PDF could not be parsed'))
    return record


def copy_upload(stream: BinaryIO, destination: Path) -> dict:
    """Bound actual streamed bytes; never trust client filename, MIME type or size declarations."""
    total, digest = 0, hashlib.sha256()
    with destination.open('xb') as handle:
        while True:
            block = stream.read(min(65536, LIMITS.max_pdf_bytes - total + 1))
            if not block:
                break
            if not isinstance(block, bytes):
                raise ImportFailure('invalid_upload', 'PDF upload must be a binary stream')
            total += len(block)
            if total > LIMITS.max_pdf_bytes:
                raise ImportFailure('file_too_large', 'PDF upload exceeds the 25 MiB limit')
            handle.write(block)
            digest.update(block)
    return {'byte_count': total, 'source_sha256': digest.hexdigest()}


def retain_source(registry: CollectionRegistry, staged: Path, digest: str, size: int) -> Path:
    """Deduplicate actual PDF bytes across this workspace without changing existing content."""
    if not 0 < size <= LIMITS.max_pdf_bytes:
        raise ImportFailure('invalid_pdf', 'PDF is empty or exceeds the file limit')
    with staged.open('rb') as handle:
        if handle.read(5) != b'%PDF-':
            raise ImportFailure('invalid_pdf', 'Input has no PDF signature')
    target = registry._path('sources', digest + '.pdf')
    if target.exists():
        if target.stat().st_size != size or hashlib.sha256(target.read_bytes()).hexdigest() != digest:
            raise ImportFailure('source_conflict', 'Existing content-addressed PDF differs; refusing overwrite')
    else:
        target.parent.mkdir(parents=True, exist_ok=True)
        with staged.open('rb') as source, target.open('xb') as output:
            while block := source.read(65536):
                output.write(block)
        if hashlib.sha256(target.read_bytes()).hexdigest() != digest:
            raise ImportFailure('source_conflict', 'Copied PDF differs from its staged content hash')
    return target


class SharedCollectionIndexer:
    """Adapt user collections to shared ingestion, graph indexes and immutable source loading."""

    def __init__(self, registry: CollectionRegistry, settings: Settings):
        self.registry, self.settings = registry, settings

    def __call__(self, candidate: UserCollection, prepared: list[PreparedPaper], encoder) -> CorpusBinding:
        """Check total chunks before any embedding/index write; publish only verified indexes."""
        groups, total = [], 0
        for paper in prepared:
            chunks = make_chunks(paper.manifest, paper.pages, encoder, max_chunks=LIMITS.max_chunks - total)
            total += len(chunks)
            groups.append((paper, chunks))
        if not total:
            raise ImportFailure('no_chunks', 'No searchable text chunks were produced')
        reports, chunk_ids = [], []
        for paper, chunks in groups:
            ident = fingerprint(paper_identity(paper.manifest, encoder))
            directory = self.registry._path('documents', paper.document.source_sha256, 'processed', ident)
            report = index_prepared_paper(paper.manifest, paper.pages, chunks, encoder,
                self.settings, directory=directory)
            reports.append({'paper_id': paper.document.paper_id, **report})
            chunk_ids.extend(c.chunk_id for c in chunks)
        all_chunks = {c.chunk_id: c for _, chunks in groups for c in chunks}
        if len(all_chunks) != total:
            raise ImportFailure('duplicate_chunks', 'Source members unexpectedly share chunk identities')
        snapshot = {'format': 'user-collection-index-v1', 'corpus_id': candidate.corpus_id,
            'collection_id': candidate.collection_id, 'collection_revision': candidate.revision,
            'scope_sha256': candidate.scope_sha256,
            'papers': [p.manifest.model_dump(mode='json') for p in prepared],
            'encoder_revision': encoder.revision, 'chunk_count': total,
            'chunk_ids_sha256': fingerprint(sorted(chunk_ids)), 'source_chunks_sha256': source_identity(all_chunks),
            'metadata': {'papers': [p.manifest.model_dump(mode='json') for p in prepared],
                         'citation_edges': [], 'citation_metadata_status': 'not_requested_unknown'},
            'input_sources': [p.document.model_dump(mode='json') for p in prepared]}
        # Derived aggregate cache stays at the shared loader's location, inside this isolated checkout.
        directory = self.registry.workspace / 'data/processed' / candidate.corpus_id
        if directory.resolve() != directory:
            raise ImportFailure('unsafe_cache_path', 'Aggregate cache path was redirected')
        write_immutable(directory / 'snapshot.json', json.dumps(snapshot, ensure_ascii=False, sort_keys=True, indent=2) + '\n')
        write_immutable(directory / 'members.json', json.dumps(reports, indent=2) + '\n')
        repository = GraphRepository(self.settings)
        try:
            repository.combine(snapshot, chunk_ids)
            if repository.snapshot(candidate.corpus_id) != snapshot:
                raise ImportFailure('index_mismatch', 'Stored corpus snapshot differs from indexed source data')
        finally:
            repository.close()
        search = SearchRepository(self.settings)
        try:
            indexes = search.prepare_indexes(candidate.corpus_id)
            if any(row['state'] != 'ONLINE' for row in indexes['indexes']):
                raise ImportFailure('index_not_ready', 'Search indexes are not ONLINE')
        finally:
            search.close()
        loaded = load_corpus_chunks(candidate.corpus_id)
        if loaded != all_chunks:
            raise ImportFailure('source_mismatch', 'Indexed source cache does not replay exactly')
        return CorpusBinding(corpus_id=candidate.corpus_id,
            snapshot_sha256=hashlib.sha256((directory / 'snapshot.json').read_bytes()).hexdigest(),
            chunks_sha256=source_identity(loaded), chunk_count=total, encoder_revision=encoder.revision)


def run_import(registry: CollectionRegistry, job_id: str, inputs: list[ImportInput], settings: Settings,
               *, encoder_factory=Encoder, downloader=download_pdf, inspector=inspect_isolated,
               indexer=None, write_guard=guard_user_write, on_progress=None) -> dict:
    """Execute a queued job once; persist every terminal outcome, never automatically resume/retry."""
    job = registry.get_job(job_id)
    if job.state != 'queued' or tuple(item.reference for item in inputs) != job.inputs:
        raise ValueError('Import job already started or supplied inputs differ; automatic resume is forbidden')
    directory = registry._path('jobs', job_id)
    with registry.worker(job_id) as token:
        items, request_count, started = [], 0, time.monotonic()
        def notify(current) -> None:
            if on_progress is not None:
                try:
                    on_progress(current)
                except Exception:
                    logging.getLogger(__name__).warning('Import progress view unavailable; durable processing continues')
        def reserve(request: dict) -> None:
            nonlocal request_count
            if request_count >= len(job.inputs) * (LIMITS.max_redirects + 1):
                raise ImportFailure('request_limit', 'Import request cap reached')
            request_count += 1
            registry._write(registry._path('jobs', job_id, 'requests', f'{request_count:06d}.json'),
                {**request, 'reserved_at': datetime.now(timezone.utc).isoformat(), 'automatic_retries': 0})
        try:
            job = registry.advance(job_id, job.sha256, token, 'resolving')
            notify(job)
            write_guard(settings)
            current = registry.get(job.collection_id)
            if current.sha256 != job.collection_sha256:
                raise ImportFailure('stale_collection', 'Collection changed since this import was queued')
            registry._write(directory / 'configuration.json', {'policy': IMPORT_POLICY,
                'policy_sha256': fingerprint(IMPORT_POLICY), 'code': code_identity(),
                'scope_sha256': registry.scope.sha256, 'request_cap': len(job.inputs) * 4,
                'generator_requests': 0, 'paid_spend': 0})
            known = {d.source_sha256 for d in current.documents}
            new_sources = []
            total_bytes = sum(d.byte_count for d in current.documents)
            for number, entry in enumerate(inputs, 1):
                staged = registry._path('jobs', job_id, 'staging', f'{number:03d}.pdf')
                staged.parent.mkdir(parents=True, exist_ok=True)
                if entry.reference.kind == 'url':
                    if entry.stream is not None:
                        raise ImportFailure('invalid_input', 'A URL input cannot also provide upload bytes')
                    resolved = downloader(entry.reference.value, staged, reserve=reserve)
                else:
                    if entry.stream is None:
                        raise ImportFailure('invalid_input', 'Upload bytes were not supplied')
                    resolved = copy_upload(entry.stream, staged)
                digest, size = resolved['source_sha256'], resolved['byte_count']
                item = {'input_index': number, 'input': entry.reference.model_dump(), **resolved,
                        'duplicate': digest in known}
                items.append(item)
                if digest in known:
                    continue
                known.add(digest)
                total_bytes += size
                if len(known) > LIMITS.max_documents or total_bytes > LIMITS.max_collection_bytes:
                    raise ImportFailure('collection_limit', 'Unique collection membership exceeds document/byte limits')
                source = retain_source(registry, staged, digest, size)
                new_sources.append((entry.reference, item, source))
            if not new_sources and current.binding is not None:
                registry.committed_import(current)
                job = registry.advance(job_id, job.sha256, token, 'duplicate',
                    'Every supplied PDF already belongs to this indexed collection; no revision/index changed')
            else:
                job = registry.advance(job_id, job.sha256, token, 'parsing')
                notify(job)
                documents = list(current.documents)
                for reference, item, path in new_sources:
                    inspection_path = registry._path('jobs', job_id, 'inspection', f"{item['input_index']:03d}.json")
                    inspection_path.parent.mkdir(parents=True, exist_ok=True)
                    inspected = inspector(path, inspection_path)
                    manifest = PaperManifestEntry.model_validate(inspected['manifest'])
                    if (manifest.source_sha256 != item['source_sha256'] or Path(manifest.local_path) != path
                            or inspected['byte_count'] != item['byte_count']):
                        raise ImportFailure('inspection_mismatch', 'Inspected PDF differs from its staged source')
                    document = DocumentVersion(paper_id=manifest.paper_id, source_sha256=manifest.source_sha256,
                        source=reference, byte_count=item['byte_count'], pdf_pages=inspected['pdf_pages'],
                        indexed_pages=tuple(inspected['indexed_pages']))
                    documents.append(document)
                    item.update(pdf_pages=document.pdf_pages, indexed_pages=list(document.indexed_pages),
                                omitted_pages=inspected['omitted_pages'])
                    write_immutable(registry._path('documents', document.source_sha256, 'inspection.json'),
                        json.dumps(inspected, ensure_ascii=False, sort_keys=True, indent=2) + '\n')
                candidate = UserCollection(collection_id=current.collection_id, scope_sha256=current.scope_sha256,
                    revision=current.revision + 1, previous_sha256=current.sha256, name=current.name,
                    created_at=datetime.now(timezone.utc), documents=tuple(documents))
                prepared = []
                for document in documents:
                    inspected = json.loads(registry._path('documents', document.source_sha256, 'inspection.json').read_bytes())
                    prepared.append(PreparedPaper(document, PaperManifestEntry.model_validate(inspected['manifest']), inspected['pages']))
                job = registry.advance(job_id, job.sha256, token, 'indexing')
                notify(job)
                encoder = encoder_factory()
                binding = (indexer or SharedCollectionIndexer(registry, settings))(candidate, prepared, encoder)
                candidate = UserCollection.model_validate({**candidate.model_dump(), 'binding': binding})
                job = registry.publish_import(job_id, job.sha256, token, candidate)
            notify(job)
            outcome = {'status': job.state, 'job_id': job_id, 'job_sha256': job.sha256,
                'collection_id': job.collection_id, 'output_corpus_id': job.output_corpus_id, 'items': items,
                'request_attempts': request_count, 'new_documents': len(new_sources),
                'elapsed_ms': (time.monotonic() - started) * 1000, 'generator_requests': 0, 'paid_spend': 0}
        except BaseException as exc:
            latest = registry.get_job(job_id)
            reason = settings.redact(str(exc))[:1000] or type(exc).__name__
            if latest.state not in TERMINAL_STATES:
                latest = registry.advance(job_id, latest.sha256, token,
                    'interrupted' if isinstance(exc, (KeyboardInterrupt, SystemExit)) else 'failed', reason)
            outcome = {'status': 'failed' if latest.state == 'ready' else latest.state,
                'job_id': job_id, 'job_sha256': latest.sha256, 'collection_id': job.collection_id,
                'error_code': getattr(exc, 'code', 'import_failed'), 'reason': reason,
                'items': items, 'request_attempts': request_count, 'generator_requests': 0, 'paid_spend': 0}
            registry._write(directory / 'outcome.json', outcome)
            if isinstance(exc, (KeyboardInterrupt, SystemExit)):
                raise
            return outcome
        registry._write(directory / 'outcome.json', outcome)
        return outcome
