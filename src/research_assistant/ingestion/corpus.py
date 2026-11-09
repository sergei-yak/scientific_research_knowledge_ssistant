"""Bounded corpus snapshots reuse single-paper ingestion without rewriting prior corpora."""

from __future__ import annotations

import json
import re
from pathlib import Path

from pydantic import Field, model_validator

from research_assistant.contracts import Contract, PaperManifestEntry, fingerprint, text_sha
from research_assistant.graph.repository import GraphRepository
from research_assistant.pipeline import ingest_paper, write_immutable
from research_assistant.settings import Settings


class CorpusBase(Contract):
    """A bounded, versioned corpus; selection rules are recorded before inference."""

    version: int = 1
    selection_record: str
    papers: list[PaperManifestEntry]

    @model_validator(mode="after")
    def unique_papers(self) -> CorpusBase:
        """Duplicate versions/identities cannot inflate a bounded corpus."""
        if len({p.paper_id for p in self.papers}) != len(self.papers):
            raise ValueError("Duplicate paper IDs")
        arxiv_ids = [re.sub(r"v\d+$", "", p.arxiv_id or p.paper_id) for p in self.papers]
        if len(set(arxiv_ids)) != len(arxiv_ids):
            raise ValueError("Duplicate versions of the same paper")
        return self


class PilotManifest(CorpusBase):
    """Keep the historical five-paper shape and identity unchanged."""

    papers: list[PaperManifestEntry] = Field(min_length=5, max_length=5)


class ExpansionManifest(CorpusBase):
    """The specification's final-sized corpus binds the actual preselection protocol."""

    papers: list[PaperManifestEntry] = Field(min_length=20, max_length=30)
    selection_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")


def ingest_pilot(manifest_path: Path, metadata_path: Path, settings: Settings) -> dict:
    """Retain the original pilot entry point and corpus identity format."""
    manifest = PilotManifest.model_validate_json(manifest_path.read_text(encoding="utf-8"))
    return _ingest(manifest, metadata_path, settings, "pilot-corpus-v1")


def ingest_expansion(manifest_path: Path, metadata_path: Path, settings: Settings) -> dict:
    """Verify selection provenance before creating a separate expanded snapshot."""
    manifest = ExpansionManifest.model_validate_json(manifest_path.read_text(encoding="utf-8"))
    if text_sha(Path(manifest.selection_record).read_text(encoding="utf-8")) != manifest.selection_sha256:
        raise ValueError("Selection protocol hash mismatch")
    return _ingest(manifest, metadata_path, settings, "expansion-corpus-v1")


def _ingest(manifest: CorpusBase, metadata_path: Path, settings: Settings, format_name: str) -> dict:
    """Share source verification and combination across bounded manifest profiles."""
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    expected = {p.paper_id: p.source_sha256 for p in manifest.papers}
    if (len(metadata["papers"]) != len(expected)
            or {p["paper_id"]: p["source_sha256"] for p in metadata["papers"]} != expected):
        raise ValueError("Metadata/source manifest mismatch")
    reports, snapshots, chunk_ids = [], [], []
    for paper in manifest.papers:
        path = Path("data/manifests") / (fingerprint(paper.model_dump()) + ".json")
        write_immutable(path, paper.model_dump_json(indent=2) + "\n")
        report = ingest_paper(path, settings)
        snapshot = json.loads(Path(report["snapshot_path"]).read_text(encoding="utf-8"))
        reports.append({"paper_id": paper.paper_id, **report})
        snapshots.append(snapshot)
        chunk_ids.extend(json.loads(line)["chunk_id"] for line in Path(report["chunk_path"]).read_text(encoding="utf-8").splitlines())
    identity = {"format": format_name, "manifest_sha256": fingerprint(manifest.model_dump()),
                "metadata_sha256": fingerprint(metadata), "members": [s["corpus_id"] for s in snapshots]}
    corpus_id = fingerprint(identity)
    snapshot = {**identity, "corpus_id": corpus_id, "papers": [p.model_dump() for p in manifest.papers],
                "encoder_revision": snapshots[0]["encoder_revision"], "chunk_count": len(chunk_ids),
                "chunk_ids_sha256": fingerprint(sorted(chunk_ids)), "metadata": metadata}
    if len({s["encoder_revision"] for s in snapshots}) != 1 or len(set(chunk_ids)) != len(chunk_ids):
        raise ValueError("Pilot has duplicate chunks or mixed encoders")
    directory = Path("data/processed") / corpus_id
    write_immutable(directory / "snapshot.json", json.dumps(snapshot, ensure_ascii=False, sort_keys=True, indent=2) + "\n")
    write_immutable(directory / "members.json", json.dumps(reports, indent=2) + "\n")
    repository = GraphRepository(settings)
    try:
        result = repository.combine(snapshot, chunk_ids)
    finally:
        repository.close()
    return {**result, "snapshot_path": str(directory / "snapshot.json"),
            "members_path": str(directory / "members.json"), "papers": reports,
            "citation_edges": len(metadata["citation_edges"])}
