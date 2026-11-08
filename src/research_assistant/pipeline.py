"""M1 services shared by CLI and the future UI; raw evidence only."""

from __future__ import annotations

import json
import subprocess
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from research_assistant.contracts import (
    Chunk, EvidenceItem, PaperManifestEntry, QueryRequest, RetrievalResult,
    RunArtifact, SourceExcerpt, fingerprint,
)
from research_assistant.embeddings import Encoder
from research_assistant.generation import answer_question
from research_assistant.graph.repository import GraphRepository
from research_assistant.ingestion.pdf import CHUNKER_VERSION, PARSER_VERSION, make_chunks, parse_pages
from research_assistant.llm import OllamaClient
from research_assistant.retrieval.evidence import assemble_evidence, context_hash
from research_assistant.settings import Settings
from research_assistant.smoke import check_resources


def write_immutable(path: Path, text: str) -> None:
    """Preserve earlier artifacts with identical text; new files use UTF-8/LF."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.read_text(encoding="utf-8") != text:
            raise ValueError(f"Artifact already exists with different content: {path}")
        return
    with path.open("x", encoding="utf-8", newline="\n") as handle:
        handle.write(text)


def ingest_paper(manifest_path: Path, settings: Settings) -> dict:
    """Verify/parse/chunk/embed one declared PDF and idempotently index its snapshot."""
    manifest = PaperManifestEntry.model_validate_json(manifest_path.read_text(encoding="utf-8"))
    encoder = Encoder()
    pages = parse_pages(manifest)
    chunks = make_chunks(manifest, pages, encoder)
    if not chunks:
        raise ValueError("No chunks produced")
    identity = {"paper_id": manifest.paper_id, "source_sha256": manifest.source_sha256,
                "pages": manifest.selected_pages, "parser": PARSER_VERSION,
                "chunker": CHUNKER_VERSION, "encoder_revision": encoder.revision,
                "mpnet_tokenizer_revision": encoder.mpnet_revision}
    corpus_id = fingerprint(identity)
    directory = Path("data/processed") / corpus_id
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
                    encoder: Encoder, minimum_similarity: float = 0.30) -> RetrievalResult:
    """Retrieve only the declared snapshot, audit rejected candidates and pack context."""
    if request.mode != "vector":
        raise ValueError("M1 implements vector retrieval only")
    if not 0 <= minimum_similarity <= 1:
        raise ValueError("Similarity threshold must be finite and between zero and one")
    start = time.perf_counter()
    pairs = repository.vector_candidates(request.corpus_id, encoder.encode([request.question])[0])
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
    chosen, context, aliases, tokens, decisions = assemble_evidence(evidence)
    decision_map = {d["id"]: d for d in decisions}
    for row in audit:
        row.update(decision_map.get(row["id"], {"selected": False, "reason": "similarity_threshold"}))
    return RetrievalResult(
        requested_mode=request.mode, effective_mode="vector", evidence=chosen,
        context=context, context_sha256=context_hash(context), estimated_tokens=tokens,
        aliases=aliases, candidates=audit, retrieval_ms=(time.perf_counter() - start) * 1000,
    )


def ask_question(request: QueryRequest, settings: Settings, context_tokens: int = 4096,
                 output_tokens: int = 512, minimum_similarity: float = 0.30) -> RunArtifact:
    """Run the real vector baseline with inspectable prompts/evidence/source metadata."""
    code_files = sorted(Path("src/research_assistant").rglob("*.py"))
    source_tree = fingerprint({str(p): fingerprint(p.read_text(encoding="utf-8")) for p in code_files})
    encoder = Encoder()
    repository = GraphRepository(settings)
    try:
        snapshot = repository.snapshot(request.corpus_id)
        if snapshot["encoder_revision"] != encoder.revision:
            raise ValueError("Query encoder revision differs from the indexed snapshot")
        retrieval = retrieve_vector(request, repository, encoder, minimum_similarity)
    finally:
        repository.close()
    before = check_resources()
    client = OllamaClient(settings, context_tokens, output_tokens) if retrieval.evidence else None
    answer, generation = answer_question(request.question, retrieval, client)
    revision = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, timeout=10)
    dirty = subprocess.run(["git", "status", "--porcelain"], capture_output=True, text=True, timeout=10)
    return RunArtifact(
        run_id=uuid.uuid4().hex, created_at=datetime.now(timezone.utc).isoformat(),
        request=request, corpus_manifest=snapshot, code_revision=revision.stdout.strip() or "unversioned",
        code_dirty=bool(dirty.stdout.strip()),
        configuration={"minimum_similarity": minimum_similarity, "evidence_budget": 1800,
                       "encoder": "all-MiniLM-L6-v2", "encoder_revision": encoder.revision,
                       "source_tree_sha256": source_tree,
                       "resources_before_generation": before, "resources_after_generation": check_resources()},
        retrieval=retrieval, generation=generation, result=answer,
    )
