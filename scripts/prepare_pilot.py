"""Reconstruct the declared pilot manifest from locally cached, versioned arXiv sources."""

import hashlib
import html
import json
from pathlib import Path

from research_assistant.contracts import PaperManifestEntry
from research_assistant.ingestion.corpus import PilotManifest
from research_assistant.pipeline import write_immutable


def main() -> None:
    """No downloads, model calls or credential access; fail if a local source is missing."""
    papers = [PaperManifestEntry.model_validate_json(Path("manifests/pilot-paper.json").read_text(encoding="utf-8"))]
    selections = [
        ("2404.16130v1", 11, "Main text through discussion/conclusion; references begin on page 12."),
        ("2405.14831v1", 10, "Main text and limitations through page 10; that page also contains acknowledgments and the start of references. Later references/appendices omitted."),
        ("2410.05779v1", 10, "Main text through conclusion; references and appendices on pages 11-16 omitted."),
        ("2502.14802v1", 8, "Main text through most of the conclusion. Page 9 mixes the conclusion tail, impact statement, acknowledgments and bibliography columns; omitted. Remaining references/appendices omitted."),
    ]
    for identity, end, note in selections:
        raw = json.loads((Path("data/metadata/arxiv-v1") / (identity + ".json")).read_text(encoding="utf-8"))
        path = Path("data/raw") / ("arxiv-" + identity + ".pdf")
        rights = raw["rights_url"].replace("http:", "https:")
        papers.append(PaperManifestEntry(
            paper_id="arxiv:" + identity, title=html.unescape(raw["title"]),
            source_url="https://arxiv.org/pdf/" + identity,
            source_sha256=hashlib.sha256(path.read_bytes()).hexdigest(), local_path=path.as_posix(),
            arxiv_id=identity, document_type="primary_study", rights_url=rights,
            rights="License displayed on pinned arXiv landing page: " + rights + " Cached for local academic analysis; not committed or redistributed.",
            selected_pages=list(range(1, end + 1)),
            selection_reason=note + " See manifests/PILOT_SELECTION.md. Tables, equations and figures are not independently verified.",
        ))
    manifest = PilotManifest(selection_record="manifests/PILOT_SELECTION.md", papers=papers)
    write_immutable(Path("manifests/pilot-five-papers.json"), manifest.model_dump_json(indent=2) + "\n")
    print("Prepared five-paper manifest from verified local sources; no live calls.")


if __name__ == "__main__":
    main()
