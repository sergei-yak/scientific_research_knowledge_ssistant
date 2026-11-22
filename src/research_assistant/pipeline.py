"""Shared ingestion and answer entry points; retrieval modes use the same evidence contracts."""

from __future__ import annotations

import json
import subprocess
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from research_assistant.retrieval.selection import SelectorSession

from research_assistant.contracts import (
    Chunk, EvidenceItem, PaperManifestEntry, QueryRequest, RetrievalResult,
    RunArtifact, SourceExcerpt, fingerprint,
)
from research_assistant.embeddings import Encoder, TextEncoder
from research_assistant.generation import answer_question
from research_assistant.graph.repository import GraphRepository
from research_assistant.ingestion.pdf import CHUNKER_VERSION, PARSER_VERSION, make_chunks, parse_pages
from research_assistant.llm import create_client
from research_assistant.retrieval.evidence import assemble_evidence, context_hash
from research_assistant.settings import Settings
from research_assistant.smoke import check_resources


class QueryExecutionError(RuntimeError):
    """A failed generation retains its source-backed retrieval and any available raw provider result."""

    def __init__(self, message: str, artifact: RunArtifact) -> None:
        super().__init__(message)
        self.artifact = artifact


def write_immutable(path: Path, text: str) -> None:
    """Preserve earlier artifacts with identical text; new files use UTF-8/LF."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.read_text(encoding="utf-8") != text:
            raise ValueError(f"Artifact already exists with different content: {path}")
        return
    with path.open("x", encoding="utf-8", newline="\n") as handle:
        handle.write(text)


def code_identity() -> dict:
    """Record code content as well as Git state, including uncommitted implementation checks."""
    files = sorted(Path('src/research_assistant').rglob('*.py'))
    revision = subprocess.run(['git','rev-parse','HEAD'],capture_output=True,text=True,timeout=10)
    dirty = subprocess.run(['git','status','--porcelain'],capture_output=True,text=True,timeout=10)
    return {'code_revision':revision.stdout.strip() or 'unversioned', 'code_dirty':bool(dirty.stdout.strip()),
            'source_tree_sha256':fingerprint({str(p):fingerprint(p.read_text(encoding='utf-8')) for p in files})}


def ingest_paper(manifest_path: Path, settings: Settings) -> dict:
    """Verify/parse/chunk/embed one declared PDF and idempotently index its snapshot."""
    manifest = PaperManifestEntry.model_validate_json(manifest_path.read_text(encoding="utf-8"))
    encoder = Encoder()
    pages = parse_pages(manifest)
    chunks = make_chunks(manifest, pages, encoder)
    return index_prepared_paper(manifest, pages, chunks, encoder, settings)


def paper_identity(manifest: PaperManifestEntry, encoder) -> dict:
    """Keep the exact historical single-paper snapshot identity shared across entry points."""
    return {"paper_id": manifest.paper_id, "source_sha256": manifest.source_sha256,
            "pages": manifest.selected_pages, "parser": PARSER_VERSION,
            "chunker": CHUNKER_VERSION, "encoder_revision": encoder.revision,
            "mpnet_tokenizer_revision": encoder.mpnet_revision}


def index_prepared_paper(manifest: PaperManifestEntry, pages: list[dict], chunks: list[Chunk],
                         encoder, settings: Settings, *, directory: Path | None = None) -> dict:
    """Persist/embed/index preflighted source data using the same cache and graph contracts."""
    if not chunks:
        raise ValueError("No chunks produced")
    if ([p['page'] for p in pages] != manifest.selected_pages
            or any(c.paper_id != manifest.paper_id or c.source_sha256 != manifest.source_sha256
                   or c.page not in manifest.selected_pages for c in chunks)):
        raise ValueError('Prepared source membership differs from its manifest')
    identity = paper_identity(manifest, encoder)
    corpus_id = fingerprint(identity)
    directory = directory if directory is not None else Path("data/processed") / corpus_id
    snapshot = {**identity, "corpus_id": corpus_id, "paper": manifest.model_dump(),
                "chunk_count": len(chunks), "normalized_pages": len(pages),
                "chunks_sha256": fingerprint([c.model_dump() for c in chunks])}
    write_immutable(directory / "pages.jsonl", "".join(json.dumps(p, ensure_ascii=False) + "\n" for p in pages))
    write_immutable(directory / "chunks.jsonl", "".join(c.model_dump_json() + "\n" for c in chunks))
    write_immutable(directory / "snapshot.json", json.dumps(snapshot, ensure_ascii=False, sort_keys=True, indent=2) + "\n")
    vector_path = directory / "vectors-384.json"
    if vector_path.exists():
        vectors = json.loads(vector_path.read_text(encoding="utf-8"))
    else:
        vectors = encoder.encode([chunk.text for chunk in chunks])
        write_immutable(vector_path, json.dumps(vectors) + "\n")
    repository = GraphRepository(settings)
    try:
        result = repository.ingest(snapshot, manifest, chunks, vectors)
    finally:
        repository.close()
    return {**result, "snapshot_path": str(directory / "snapshot.json"),
            "chunk_path": str(directory / "chunks.jsonl"),
            "coverage": manifest.selected_pages,
            "quality": {"replacement_characters": sum(p["replacement_characters"] for p in pages),
                        "figures_tables_equations_verified": False},
            "token_limits": {"max_mini": max(c.mini_tokens for c in chunks),
                             "max_mpnet": max(c.mpnet_tokens for c in chunks)}}


def retrieve_vector(request: QueryRequest, repository: GraphRepository,
                    encoder: TextEncoder, minimum_similarity: float = 0.30,
                    *, selector: SelectorSession | None = None) -> RetrievalResult:
    """Retrieve only the declared snapshot, audit rejected candidates and pack context."""
    if request.mode != "vector":
        raise ValueError("M1 implements vector retrieval only")
    if not 0 <= minimum_similarity <= 1:
        raise ValueError("Similarity threshold must be finite and between zero and one")
    start = time.perf_counter()
    query = encoder.encode([request.question])[0]
    encoded_at = time.perf_counter()
    pairs = repository.vector_candidates(request.corpus_id, query)
    fetched_at = time.perf_counter()
    evidence, audit = [], []
    for rank, (chunk, score) in enumerate(pairs, 1):
        audit.append({"id": chunk.chunk_id, "similarity": score, "rank": rank,
                      "eligible": score >= minimum_similarity})
        if score < minimum_similarity:
            continue
        evidence.append(EvidenceItem(
            id=chunk.chunk_id, similarity=score, rank=rank,
            excerpts=[SourceExcerpt(
                chunk_id=chunk.chunk_id, paper_id=chunk.paper_id, source_sha256=chunk.source_sha256,
                source_url=chunk.source_url, page=chunk.page, section=chunk.section,
                chunk_page_start=chunk.page_start, start=0, end=len(chunk.text), text=chunk.text,
            )],
        ))
    ranks={item.id:item.rank for item in evidence}
    if selector is not None:evidence=selector.order(evidence,ranks,'vector')
    chosen, context, aliases, tokens, decisions = assemble_evidence(evidence)
    decision_map = {d["id"]: d for d in decisions}
    for row in audit:
        row.update(decision_map.get(row["id"], {"selected": False, "reason": "similarity_threshold"}))
    return RetrievalResult(
        requested_mode=request.mode, effective_mode="vector", evidence=chosen,
        context=context, context_sha256=context_hash(context), estimated_tokens=tokens,
        aliases=aliases, candidates=audit, retrieval_ms=(time.perf_counter() - start) * 1000,
        audit={'query_encoding_ms': (encoded_at-start)*1000, 'candidate_fetch_ms': (fetched_at-encoded_at)*1000,
               'ann_pool': 24, 'candidate_limit': 12, 'minimum_similarity': minimum_similarity,
               'eligible_candidates': [item.model_dump() for item in evidence],
               **({'selection':selector.audit(evidence,ranks,'vector',decisions)} if selector is not None else {})},
    )


def ask_question(request: QueryRequest, settings: Settings, context_tokens: int = 4096,
                 output_tokens: int = 512, minimum_similarity: float = 0.30,
                 review_directory: Path = Path('data/reviews/pilot')) -> RunArtifact:
    """Compatibility entry point for a grounded answer using the shared run service."""
    return run_query(request, settings, context_tokens, output_tokens, minimum_similarity, review_directory)


def run_query(request: QueryRequest, settings: Settings, context_tokens: int = 4096,
              output_tokens: int = 512, minimum_similarity: float = 0.30,
              review_directory: Path = Path('data/reviews/pilot'), *, generate: bool = True,
              workflow: str = 'ask', encoder: Encoder | None = None) -> RunArtifact:
    """Execute one query; retrieval-only runs never construct a provider or call a model."""
    if request.profile_id=='retrieval-v2' and generate:
        raise ValueError('retrieval-v2 is retrieval-only until its later generation/evaluation gates')
    from research_assistant.retrieval.service import retrieve_request
    identity = code_identity()
    if encoder is None:
        snapshot,retrieval = retrieve_request(request,settings,review_directory,minimum_similarity)
    else:
        snapshot,retrieval = retrieve_request(request,settings,review_directory,minimum_similarity,encoder=encoder)
    return _finish_query(request, settings, snapshot, retrieval, identity, context_tokens, output_tokens,
                        minimum_similarity, generate=generate, workflow=workflow)


def _finish_query(request: QueryRequest, settings: Settings, snapshot: dict, retrieval: RetrievalResult,
                 identity: dict, context_tokens: int, output_tokens: int, minimum_similarity: float,
                 *, generate: bool, workflow: str, evaluation_permit=None) -> RunArtifact:
    """Shared grounded generation/error handling after an entry point establishes retrieval authority."""
    if generate and (request.profile_id == 'retrieval-v2' or evaluation_permit is not None):
        from research_assistant.evaluation.matched_permits import validate_slot
        validate_slot(evaluation_permit, request, settings, context_tokens, output_tokens,
                      minimum_similarity, consume=True)
    before = check_resources()
    run = RunArtifact(
        run_id=uuid.uuid4().hex, created_at=datetime.now(timezone.utc).isoformat(),
        request=request, corpus_manifest=snapshot, code_revision=identity['code_revision'],
        code_dirty=identity['code_dirty'],
        configuration={"minimum_similarity": minimum_similarity, "evidence_budget": 1800,
                       "encoder": "all-MiniLM-L6-v2", "encoder_revision": snapshot['encoder_revision'],
                       "source_tree_sha256": identity['source_tree_sha256'],
                       "retrieval_rules":retrieval.audit,
                       "resources_before_generation": before},
        retrieval=retrieval, generation=None, result=None,
        generation_requested=generate, workflow=workflow,
    )
    client = None
    if request.profile_id=='retrieval-v2':
        run.configuration.update(profile=retrieval.audit['profile'],experiment_scope=retrieval.audit['experiment_scope'])
    try:
        if generate:
            client = create_client(settings, context_tokens, output_tokens) if retrieval.evidence else None
            run.result, run.generation = answer_question(request.question, retrieval, client)
    except Exception as exc:
        run.generation = getattr(client, 'last_result', None)
        run.configuration['generation_error'] = {'type': type(exc).__name__, 'message': settings.redact(str(exc))}
        raise QueryExecutionError(settings.redact(str(exc)), run) from exc
    finally:
        run.configuration['resources_after_generation'] = check_resources()
    return run
