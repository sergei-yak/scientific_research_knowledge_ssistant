"""Export inspectable review packets without manufacturing approval rows."""

import csv
import io
import json
from pathlib import Path

from research_assistant.contracts import Chunk
from research_assistant.pipeline import write_immutable


def export_bundle(directory: Path, bundle: dict, chunks: list[Chunk]) -> None:
    """JSON is canonical; Markdown is readable and CSV has empty decision fields only."""
    write_immutable(directory / "bundle.json", json.dumps(bundle, ensure_ascii=False, indent=2) + "\n")
    paper, stats = bundle["paper"], bundle["stats"]
    lines = [f"# Human review: {paper['title']}", "", "**All claims are pending. Mechanical validation does not approve claims.**", "",
             f"Paper: `{paper['paper_id']}` | PDF SHA-256: `{paper['source_sha256']}`", "",
             f"Source: {paper['source_url']}", "", f"Initial review allowance: {stats['initial_review_minutes']} minutes; unused time never grants approval.", "",
             "Section labels are parser heuristics, not verified section boundaries. HippoRAG 2's labels remain 'Front matter'; consult the PDF page and inspection record.", "",
             f"Generated: {stats['generated']}; unique review candidates: {stats['unique_candidates']}; mechanically validated: {stats['validated']}; approved: 0; pending: {stats['pending']}.", "",
             "Check reporting-paper ownership, exact source support, proposed method/dataset mappings and aliases, missing conditions, and whether the statement overstates the evidence.", "",
             "Record reviewer identity, actual review time and a decision/reason for each reviewed claim in decisions.csv. Blank decisions remain pending. M2.2 will validate/import decisions; editing this file does not update the graph.", "",
             bundle["coverage_note"], ""]
    by_id = {c.chunk_id: c for c in chunks}
    passages = {p["id"]: p for p in bundle["passages"]}
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=["claim_id", "claim_revision", "source_sha256", "entity_revision", "reviewer", "reviewed_at", "review_seconds", "decision", "reason", "entity_mapping_notes"])
    writer.writeheader()
    for number, candidate in enumerate(bundle["candidates"], 1):
        draft = candidate["draft"]
        passage = passages[candidate["passage_id"]]
        lines += [f"## {number}. {draft['kind']} — {candidate['validation_status']}", "",
                  f"Claim ID: `{candidate['claim_id']}`; revision 1", "", draft["statement"], "",
                  f"Proposed method: {draft['method'] or 'unknown'}; aliases: {', '.join(draft['method_aliases']) or 'none'}", "",
                  f"Proposed dataset: {draft['dataset'] or 'unknown'}; aliases: {', '.join(draft['dataset_aliases']) or 'none'}", "",
                  f"Entity proposal revision: `{candidate['entity_revision']}`. Approve only this displayed mapping; use needs_review with notes if it must change.", "",
                  "Conditions: " + json.dumps(draft["conditions"], ensure_ascii=False), "",
                  f"Source page {passage['page']}, section {passage['section']}; normalized page interval [{passage['start']}, {passage['end']}).", ""]
        for quote in draft["quotes"]:
            lines += ["> " + quote.replace("\n", "\n> "), ""]
        if candidate["claim"]:
            for span in candidate["claim"]["support"]:
                source = by_id[span["chunk_id"]]
                lines += [f"Support `{span['chunk_id']}` [{span['start']}, {span['end']}); quote SHA-256 `{span['quote_sha256']}`; [PDF page {source.page}]({source.source_url}#page={source.page}).", ""]
        lines += ["Validation errors: " + ("; ".join(candidate["validation_errors"]) or "none; semantic support still unreviewed"), "",
                  "Decision: **pending human review**", ""]
        writer.writerow({"claim_id": candidate["claim_id"], "claim_revision": 1, "source_sha256": paper["source_sha256"],
                         "entity_revision": candidate["entity_revision"]})
    lines += ["## Extraction coverage", "", f"Selected pages: {stats['selected_pages']}", "",
              f"Unselected pages within retrieval coverage: {stats['unselected_covered_pages']}", "",
              f"Requests with failed/unknown outcome: {stats['failed_requests']}. Raw responses and failure records are in bundle.json and the persistent extraction ledger.", ""]
    write_immutable(directory / "REVIEW.md", "\n".join(lines))
    write_immutable(directory / "decisions.csv", stream.getvalue())
