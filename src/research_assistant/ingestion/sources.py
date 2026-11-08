"""Verified immutable source caches shared by review and evaluation."""

import json
from pathlib import Path

from research_assistant.contracts import Chunk, fingerprint
from research_assistant.graph.repository import corpus_names


def load_corpus_chunks(corpus_id: str) -> dict[str, Chunk]:
    """Read only one explicit corpus's hash-verified member files; never discover evaluation files."""
    corpus_names(corpus_id)
    members = json.loads((Path("data/processed") / corpus_id / "members.json").read_text(encoding="utf-8"))
    chunks = {}
    for member in members:
        rows = [Chunk.model_validate_json(line) for line in Path(member["chunk_path"]).read_text(encoding="utf-8").splitlines()]
        snapshot = json.loads(Path(member["snapshot_path"]).read_text(encoding="utf-8"))
        if fingerprint([row.model_dump() for row in rows]) != snapshot["chunks_sha256"]:
            raise ValueError("Current source cache changed")
        for row in rows:
            if row.chunk_id in chunks and chunks[row.chunk_id] != row:
                raise ValueError("Conflicting source chunk identity")
            chunks[row.chunk_id] = row
    return chunks
