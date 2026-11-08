"""Five-paper pilot snapshots reuse verified single-paper ingestion without rewriting M1."""

from __future__ import annotations

import json
import re
from pathlib import Path

from pydantic import Field, model_validator

from research_assistant.contracts import Contract, PaperManifestEntry, fingerprint
from research_assistant.graph.repository import GraphRepository
from research_assistant.pipeline import ingest_paper, write_immutable
from research_assistant.settings import Settings


class PilotManifest(Contract):
    """A bounded, versioned corpus; selection rules are recorded before inference."""

    version: int = 1
    selection_record: str
    papers: list[PaperManifestEntry] = Field(min_length=5, max_length=5)

    @model_validator(mode="after")
    def unique_papers(self) -> PilotManifest:
        """Duplicate versions/identities cannot stand in for five papers."""
        if len({p.paper_id for p in self.papers}) != len(self.papers):
            raise ValueError("Duplicate pilot paper IDs")
        arxiv_ids = [re.sub(r"v\d+$", "", p.arxiv_id or p.paper_id) for p in self.papers]
        if len(set(arxiv_ids)) != len(arxiv_ids):
            raise ValueError("Duplicate versions of the same pilot paper")
        return self


def ingest_pilot(manifest_path: Path, metadata_path: Path, settings: Settings) -> dict:
    """Reuse single-paper snapshots, then build a separate immutable combined snapshot."""
    manifest = PilotManifest.model_validate_json(manifest_path.read_text(encoding="utf-8"))
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    expected = {p.paper_id: p.source_sha256 for p in manifest.papers}
    if {p["paper_id"]: p["source_sha256"] for p in metadata["papers"]} != expected:
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
    identity = {"format": "pilot-corpus-v1", "manifest_sha256": fingerprint(manifest.model_dump()),
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
