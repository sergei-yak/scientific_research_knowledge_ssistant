"""Snapshot and vector-boundary failures must happen before database mutation."""

from pathlib import Path

import pytest

from research_assistant.graph.repository import GraphRepository, corpus_names
from research_assistant.pipeline import write_immutable


@pytest.mark.parametrize("vectors", [[[0.0] * 384], [[0.0] * 768], [[float("nan")] * 384]])
def test_ingest_invalid_vectors_never_opens_a_session(vectors):
    repository = object.__new__(GraphRepository)  # No driver exists; validation must come first.
    with pytest.raises(ValueError, match="vector"):
        repository.ingest({"corpus_id": "a" * 64}, None, [object()], vectors)


def test_schema_identifiers_only_accept_content_hashes():
    with pytest.raises(ValueError):
        corpus_names("anything` MATCH (n) DETACH DELETE n")
    assert corpus_names("a" * 64)[0].startswith("RACorpus_")


def test_artifact_rerun_is_idempotent_and_conflicts_preserve_prior_bytes(tmp_path):
    path = tmp_path / "artifact.json"
    write_immutable(path, '{"value":"Ω"}\n')
    original = path.read_bytes()
    write_immutable(path, '{"value":"Ω"}\n')
    assert path.read_bytes() == original
    with pytest.raises(ValueError, match="different content"):
        write_immutable(path, "different")
    assert path.read_bytes() == original
