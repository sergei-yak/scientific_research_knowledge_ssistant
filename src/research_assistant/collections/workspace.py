"""Checked collection QA, source files and exports shared by the CLI and Streamlit."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
from typing import BinaryIO

from research_assistant.collections.contracts import InputReference, UserCollection, supported_url
from research_assistant.collections.scope import guard_user_write
from research_assistant.collections.store import CollectionRegistry
from research_assistant.contracts import QueryRequest, RunArtifact, fingerprint
from research_assistant.graph.search import SearchRepository
from research_assistant.ingestion.sources import load_corpus_chunks, source_identity
from research_assistant.ingestion.user_import import ImportInput, run_import
from research_assistant.pipeline import QueryExecutionError, run_query, write_immutable
from research_assistant.product import ProductView, prepare_output
from research_assistant.settings import Settings

USER_MODES = {'vector': 'Vector', 'hybrid': 'Hybrid'}
ALL_USER_MODES = {**USER_MODES, 'hybrid_facts': 'Hybrid + Approved Facts', 'graph': 'Graph'}


@dataclass(frozen=True)
class SourcePDF:
    """Hash-checked local bytes with the original user reference and authoritative page coverage."""

    paper_id: str
    reference: str
    filename: str
    web_url: str | None
    data: bytes
    indexed_pages: tuple[int, ...]


@dataclass(frozen=True)
class ReadyCollection:
    """A current committed revision whose local sources and actual indexes have been checked."""

    collection: UserCollection
    snapshot: dict
    sources: dict[str, SourcePDF]
    marker: dict


def verify_collection(registry: CollectionRegistry, collection_id: str, settings: Settings,
                      expected_head: str | None = None) -> ReadyCollection:
    """Fail closed on changed ownership, sources, member paths, publication or live indexes."""
    collection = registry.get(collection_id)
    if expected_head is not None and collection.sha256 != expected_head:
        raise ValueError('Collection changed; select its current revision and submit again')
    if not collection.documents or collection.binding is None:
        raise ValueError('Import documents before asking a question')
    registry.committed_import(collection)
    guard_user_write(settings)
    directory = registry.workspace / 'data/processed' / collection.corpus_id
    if directory.resolve() != directory:
        raise ValueError('Collection snapshot path was redirected')
    for name in ('snapshot.json', 'members.json'):
        if (directory / name).resolve() != directory / name:
            raise ValueError('Collection snapshot/member file was redirected')
    raw = (directory / 'snapshot.json').read_bytes()
    if hashlib.sha256(raw).hexdigest() != collection.binding.snapshot_sha256:
        raise ValueError('Collection index snapshot changed')
    snapshot = json.loads(raw)
    if (snapshot.get('corpus_id') != collection.corpus_id
            or snapshot.get('collection_id') != collection.collection_id
            or snapshot.get('collection_revision') != collection.revision
            or snapshot.get('scope_sha256') != registry.scope.sha256
            or snapshot.get('input_sources') != [d.model_dump(mode='json') for d in collection.documents]):
        raise ValueError('Index snapshot belongs to another collection/revision')
    members = json.loads((directory / 'members.json').read_bytes())
    if len(members) != len(collection.documents):
        raise ValueError('Collection member count changed')
    sources = {}
    for document, member in zip(collection.documents, members):
        parent = Path(member['snapshot_path']).parent
        if not re.fullmatch(r'[a-f0-9]{64}', parent.name):
            raise ValueError('Invalid member snapshot identity')
        expected = registry._path('documents', document.source_sha256, 'processed', parent.name)
        if (member['paper_id'] != document.paper_id or parent != expected
                or Path(member['snapshot_path']) != expected / 'snapshot.json'
                or Path(member['chunk_path']) != expected / 'chunks.jsonl'):
            raise ValueError('Collection member cache is foreign or redirected')
        registry._path('documents', document.source_sha256, 'processed', parent.name, 'snapshot.json')
        registry._path('documents', document.source_sha256, 'processed', parent.name, 'chunks.jsonl')
        data = registry._path('sources', document.source_sha256 + '.pdf').read_bytes()
        if len(data) != document.byte_count or hashlib.sha256(data).hexdigest() != document.source_sha256:
            raise ValueError('Source PDF changed; downloads and answers are disabled')
        filename = document.source.value if document.source.kind == 'upload' else 'paper-' + document.source_sha256[:12] + '.pdf'
        sources[document.paper_id] = SourcePDF(document.paper_id, document.source.value, filename,
            supported_url(document.source.value) if document.source.kind == 'url' else None,
            data, document.indexed_pages)
    chunks = load_corpus_chunks(collection.corpus_id)
    if len(chunks) != collection.binding.chunk_count or source_identity(chunks) != collection.binding.chunks_sha256:
        raise ValueError('Collection source chunks changed')
    for chunk in chunks.values():
        source = sources.get(chunk.paper_id)
        if (source is None or chunk.page not in source.indexed_pages
                or chunk.source_url != 'userpdf://' + chunk.source_sha256
                or chunk.source_sha256 != next(d.source_sha256 for d in collection.documents if d.paper_id == chunk.paper_id)):
            raise ValueError('Chunk is outside selected collection source coverage')
    repo = SearchRepository(settings)
    try:
        if repo.snapshot(collection.corpus_id) != snapshot:
            raise ValueError('Database snapshot differs from the selected collection')
        with repo.reading(collection.corpus_id, None, settings.graph_query_timeout_seconds):
            repo.check_indexes(collection.corpus_id, False)
    finally:
        repo.close()
    if registry.get(collection_id) != collection:
        raise ValueError('Collection changed during readiness checks')
    marker = {'collection_id': collection.collection_id, 'revision': collection.revision,
        'collection_sha256': collection.sha256, 'scope_sha256': registry.scope.sha256,
        'snapshot_sha256': collection.binding.snapshot_sha256,
        'chunks_sha256': collection.binding.chunks_sha256, 'target_uri': registry.scope.target_uri}
    return ReadyCollection(collection, snapshot, sources, marker)


def checked_output(registry: CollectionRegistry, collection_id: str, run: RunArtifact,
                   settings: Settings, expected_head: str | None = None) -> tuple[ProductView, str, ReadyCollection]:
    """Recheck before every display/export; never retrieve, encode or regenerate a saved answer."""
    if (run.request.mode not in ALL_USER_MODES or run.request.profile_id != 'baseline'
            or run.request.selector_id != 'reference' or run.request.scope_file is not None
            or run.workflow != 'ask'):
        raise ValueError('User collections support the standard reference profile only')
    ready = verify_collection(registry, collection_id, settings, expected_head)
    if run.request.mode not in USER_MODES:
        from research_assistant.collections.reviews import require_fact_ready
        require_fact_ready(registry, ready, settings)
    if (run.request.corpus_id != ready.collection.corpus_id or run.corpus_manifest != ready.snapshot
            or run.configuration.get('user_collection') != ready.marker
            or (run.request.mode in USER_MODES and any(item.kind != 'chunk' or item.graph_paths for item in run.retrieval.evidence))):
        raise ValueError('Saved answer/evidence belongs to a different or changed collection')
    references = {key: {'reference': source.reference, 'filename': source.filename}
                  for key, source in ready.sources.items()}
    view, csv_text = prepare_output(run, settings, review_directory=registry.review_directory(ready.collection),
                                   source_references=references)
    return view, csv_text, ready


def query_collection(registry: CollectionRegistry, collection_id: str, expected_head: str,
                     question: str, mode: str, settings: Settings, *, generate: bool = False,
                     encoder=None) -> RunArtifact:
    """One explicit query through shared retrieval/generation, retaining completed and failed artifacts."""
    if mode not in ALL_USER_MODES:
        raise ValueError('Unsupported collection retrieval mode')
    with registry.query_lock():
        ready = verify_collection(registry, collection_id, settings, expected_head)
        if mode not in USER_MODES:
            from research_assistant.collections.reviews import require_fact_ready
            require_fact_ready(registry, ready, settings)
        request = QueryRequest(question=question.strip(), corpus_id=ready.collection.corpus_id, mode=mode)
        def bind(run: RunArtifact) -> RunArtifact:
            return run.model_copy(update={'configuration': {**run.configuration, 'user_collection': ready.marker}})
        try:
            run = bind(run_query(request, settings, generate=generate, workflow='ask', encoder=encoder,
                                 review_directory=registry.review_directory(ready.collection)))
        except QueryExecutionError as exc:
            artifact = bind(exc.artifact)
            write_immutable(Path('runs/user-collections/queries') / artifact.run_id / 'failed-run.json',
                            artifact.model_dump_json(indent=2) + '\n')
            raise QueryExecutionError(str(exc), artifact) from exc
        write_immutable(Path('runs/user-collections/queries') / run.run_id / 'run.json', run.model_dump_json(indent=2) + '\n')
        checked_output(registry, collection_id, run, settings, expected_head)
        return run


def import_collection(registry: CollectionRegistry, collection_id: str, expected_head: str,
                      uploads: list[tuple[str, BinaryIO]], urls: list[str], settings: Settings,
                      *, encoder_factory=None, on_progress=None) -> dict:
    """Convert explicitly supplied UI/CLI inputs at one shared import boundary."""
    entries = []
    for name, stream in uploads:
        if stream.seekable():
            stream.seek(0)
        entries.append(ImportInput(InputReference(kind='upload', value=name), stream))
    entries.extend(ImportInput(InputReference(kind='url', value=url.strip())) for url in urls if url.strip())
    job = registry.queue(collection_id, expected_head, tuple(e.reference for e in entries))
    options = {'on_progress': on_progress}
    if encoder_factory is not None:
        options['encoder_factory'] = encoder_factory
    return run_import(registry, job.job_id, entries, settings, **options)
