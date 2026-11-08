"""Small immutable in-chat review batches with exact revision bindings."""

import json
import math
from datetime import datetime, timezone
from pathlib import Path

from research_assistant.contracts import fingerprint, text_sha
from research_assistant.pipeline import write_immutable
from research_assistant.review.contracts import HumanDecision
from research_assistant.review.store import import_decisions, load_chunks, state, validate_revision


def export_batch(directory: Path, claim_ids: list[str], batch_directory: Path, prefix: str = "R") -> dict:
    """Show complete claims, mappings, conditions and quotes before soliciting human decisions."""
    current = state(directory)
    chunks = load_chunks(directory)
    items = []
    for number, claim_id in enumerate(claim_ids, 1):
        revision = current["current"][claim_id]
        items.append({"label": f"{prefix}{number}", "revision_sha256": revision.sha256,
                      **revision.model_dump(mode="json"),
                      "current_validation_errors": validate_revision(revision, chunks, current["entities"])})
    batch = {"review_head_at_presentation": current["head"], "items": items,
             "status": "awaiting_human_decisions", "reviewer": None, "actual_review_seconds": None}
    write_immutable(batch_directory / "batch.json", json.dumps(batch, ensure_ascii=False, indent=2) + "\n")
    lines = ["# Human review batch", "", "Approve, reject, or request changes for each exact displayed revision. Record reviewer name and actual batch time; unmeasured time stays unknown.", "",
             "These are claims reported by their source papers, not independently verified scientific facts. Unknown conditions stay unknown. Named entities remain scoped to the paper/proposal unless an explicitly reviewed revision links them.", ""]
    for item in items:
        draft, paper = item["draft"], item["paper"]
        lines += [f"## {item['label']} — revision {item['revision']}", "", draft["statement"], "",
                  f"Reporting paper: {paper['title']} ({paper['paper_id']})", "",
                  f"Source: {paper['source_url']}", "",
                  f"Method: {draft['method'] or 'unknown'}; aliases: {draft['method_aliases']}", "",
                  f"Dataset: {draft['dataset'] or 'unknown'}; aliases: {draft['dataset_aliases']}", "",
                  "Conditions: " + json.dumps(draft["conditions"], ensure_ascii=False), "",
                  "Exact normalized source quotations:", ""]
        for quote in draft["quotes"]:
            lines += ["> " + quote.replace("\n", "\n> "), ""]
        for entity in item["entities"]:
            lines += [f"Explicit {entity['kind']} binding: {entity['name']}; aliases {entity['aliases']}; identity `{entity['id']}`. These exact bindings are part of the revision being reviewed.", ""]
        for span in item["support"]:
            chunk = chunks[span["chunk_id"]]
            lines += [f"[PDF page {chunk.page}]({chunk.source_url}#page={chunk.page}); chunk `{chunk.chunk_id}` "
                      f"normalized offsets [{span['start']}, {span['end']}); quotation SHA-256 `{span['quote_sha256']}`.", ""]
        lines += ["Validation issues: " + ("; ".join(item["current_validation_errors"]) or "none; semantic review still required"), "",
                  f"Claim: `{item['claim_id']}`; source SHA-256: `{paper['source_sha256']}`", "",
                  f"Revision binding: `{item['revision_sha256']}`", "", f"Change reason: {item['change_reason']}", ""]
    write_immutable(batch_directory / "REVIEW.md", "\n".join(lines))
    return {"batch_directory": str(batch_directory), "claims": len(items), "review_head": current["head"]}


def export_source_locations(directory: Path, batch_path: Path) -> Path:
    """Add source-location companions without rewriting already displayed immutable packets."""
    chunks = load_chunks(directory)
    batch = json.loads(batch_path.read_text(encoding="utf-8"))
    lines = ["# Source locations for this exact review batch", "",
             "These references identify the existing frozen support; they do not change any claim or approval binding.", ""]
    for item in batch["items"]:
        lines += [f"## {item['label']} — revision {item['revision']}", "",
                  f"Revision binding: `{item['revision_sha256']}`", ""]
        for span in item["support"]:
            chunk = chunks[span["chunk_id"]]
            lines += [f"[PDF page {chunk.page}]({chunk.source_url}#page={chunk.page}); "
                      f"chunk `{chunk.chunk_id}` [{span['start']}, {span['end']}); quote hash `{span['quote_sha256']}`.", ""]
    path = batch_path.parent / "SOURCES.md"
    write_immutable(path, "\n".join(lines))
    return path


def record_chat_decisions(directory: Path, batch_path: Path, receipt_name: str,
                          reviewer: str, verbatim_response: str, choices: dict[str, dict[str, str]],
                          batch_seconds: float | None, verbatim_time_response: str) -> dict:
    """Capture supplied human input for displayed labels only; never infer choices or duration."""
    if not reviewer.strip() or not verbatim_response.strip() or not choices:
        raise ValueError("Explicit human identity, response and decisions are required")
    if batch_seconds is not None and (not math.isfinite(batch_seconds) or batch_seconds < 0):
        raise ValueError("Review duration must be finite and nonnegative")
    if Path(receipt_name).name != receipt_name or not receipt_name.endswith(".json"):
        raise ValueError("Receipt must be a local JSON basename")
    batch = json.loads(batch_path.read_text(encoding="utf-8"))
    shown = {item["label"]: item for item in batch["items"]}
    if not set(choices) <= set(shown):
        raise ValueError("Decision refers to a label outside the displayed batch")
    current = state(directory)
    for label in choices:
        item = shown[label]
        if current["current"][item["claim_id"]].sha256 != item["revision_sha256"]:
            raise ValueError("Displayed revision is no longer current")
    content = {"batch_id": batch_path.parent.name, "presented_batch_sha256": fingerprint(batch),
               "origin": "human_chat", "reviewer": reviewer, "verbatim_decision_response": verbatim_response,
               "choices": choices, "actual_batch_review_seconds_approx": batch_seconds,
               "verbatim_time_response": verbatim_time_response,
               "time_note": "Batch duration only; per-claim duration not measured"}
    path = directory / "human-inputs" / receipt_name
    if path.exists():
        receipt = json.loads(path.read_text(encoding="utf-8"))
        if {key: receipt[key] for key in content} != content:
            raise ValueError("Existing immutable human receipt differs; preserve it and use a new receipt")
    else:
        receipt = {**content, "received_at": datetime.now(timezone.utc).isoformat()}
    text = json.dumps(receipt, ensure_ascii=False, indent=2) + "\n"
    write_immutable(path, text)
    decisions = []
    for label, choice in choices.items():
        revision = current["current"][shown[label]["claim_id"]]
        decisions.append(HumanDecision(claim_id=revision.claim_id, claim_revision=revision.revision,
            revision_sha256=revision.sha256, source_sha256=revision.paper.source_sha256,
            entity_revision=revision.entity_revision, decision=choice["decision"], reason=choice["reason"],
            reviewer=reviewer, reviewed_at=receipt["received_at"], review_seconds=None,
            review_time_note=f"Batch duration {batch_seconds} seconds (approximate), per-claim unknown; see {receipt_name}.",
            origin="human_chat", provenance_sha256=text_sha(text)))
    return import_decisions(directory, decisions, load_chunks(directory))
