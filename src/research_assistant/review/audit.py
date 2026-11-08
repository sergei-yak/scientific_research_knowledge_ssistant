"""Offline replay of review identities, exact support and cumulative request limits."""

import csv
import json
from pathlib import Path

from research_assistant.contracts import Chunk, fingerprint, text_sha
from research_assistant.extraction.contracts import ExtractionResponse, ProposedClaim


def audit_packets(directory: Path) -> dict:
    """Verify saved packets without inference, networking, approvals or graph mutation."""
    from research_assistant.extraction.pilot import read_attempts, validate_candidate

    summary = json.loads((directory / "summary.json").read_text(encoding="utf-8"))
    members = json.loads((Path("data/processed") / summary["corpus_id"] / "members.json").read_text(encoding="utf-8"))
    sources = {}
    for member in members:
        chunks = [Chunk.model_validate_json(line) for line in Path(member["chunk_path"]).read_text(encoding="utf-8").splitlines()]
        snapshot = json.loads(Path(member["snapshot_path"]).read_text(encoding="utf-8"))
        if fingerprint([c.model_dump() for c in chunks]) != snapshot["chunks_sha256"]:
            raise ValueError("Source chunk cache hash mismatch")
        sources[member["paper_id"]] = chunks
    reports = []
    for row in summary["papers"]:
        root = directory / row["paper_id"].replace(":", "-")
        bundle = json.loads((root / "bundle.json").read_text(encoding="utf-8"))
        paper, stats = bundle["paper"], bundle["stats"]
        chunks = sources[paper["paper_id"]]
        passages = {p["id"]: p for p in bundle["passages"]}
        ledger = Path("data/extraction/by-source") / fingerprint([paper["paper_id"], paper["source_sha256"]])
        attempts = read_attempts(ledger)
        if (attempts != bundle["requests"] or len(attempts) != stats["requests_reserved"]
                or sum(r["generated"] for r in attempts) != stats["generated"]
                or sum(r["unknown_candidate_upper_bound"] for r in attempts) != stats["unknown_candidate_upper_bound"]):
            raise ValueError("Packet/request-journal accounting mismatch")
        original_candidates = {}
        for attempt in attempts:
            if attempt["status"] == "completed":
                for draft in ExtractionResponse.model_validate(attempt["draft"]).candidates:
                    candidate = validate_candidate(draft, paper, attempt["passage"], chunks)
                    original_candidates[candidate["claim_id"]] = candidate
        if list(original_candidates.values()) != bundle["candidates"]:
            raise ValueError("Packet/raw-model-candidate provenance mismatch")
        if (stats["requests_reserved"] > 8 or stats["selected_passages"] > 8
                or stats["generated"] + stats["unknown_candidate_upper_bound"] > 12):
            raise ValueError("Cumulative extraction cap exceeded")
        if stats["approved"] or stats["rejected"] or stats["human_review_seconds"]:
            raise ValueError("An extraction packet must not manufacture human decisions/time")
        if (len(bundle["candidates"]) != stats["unique_candidates"]
                or sum(c["validation_status"] == "validated" for c in bundle["candidates"]) != stats["validated"]):
            raise ValueError("Packet candidate counts mismatch")
        for candidate in bundle["candidates"]:
            expected = validate_candidate(ProposedClaim.model_validate(candidate["draft"]), paper,
                                          passages[candidate["passage_id"]], chunks)
            if expected != candidate:
                raise ValueError("Review candidate identity/source/validation mismatch")
            if candidate["claim"]:
                by_id = {chunk.chunk_id: chunk for chunk in chunks}
                for span in candidate["claim"]["support"]:
                    chunk = by_id[span["chunk_id"]]
                    if text_sha(chunk.text[span["start"]:span["end"]]) != span["quote_sha256"]:
                        raise ValueError("Support quotation hash mismatch")
        with (root / "decisions.csv").open(encoding="utf-8", newline="") as handle:
            decisions = list(csv.DictReader(handle))
        candidates = {c["claim_id"]: c for c in bundle["candidates"]}
        if len(decisions) != len(candidates) or {r["claim_id"] for r in decisions} != set(candidates):
            raise ValueError("Review CSV/candidate identity mismatch")
        for decision in decisions:
            candidate = candidates[decision["claim_id"]]
            if (decision["source_sha256"] != paper["source_sha256"] or decision["claim_revision"] != "1"
                    or decision["entity_revision"] != candidate["entity_revision"]):
                raise ValueError("Review CSV source/mapping revision mismatch")
        reports.append({"paper_id": paper["paper_id"], "candidates": len(candidates),
                        "validated": stats["validated"], "requests_reserved": stats["requests_reserved"],
                        "unknown_candidate_upper_bound": stats["unknown_candidate_upper_bound"],
                        "decisions_entered_not_imported": sum(bool(r["decision"]) for r in decisions), "status": "passed"})
    return {"task_id": "M2.1", "status": "passed", "corpus_id": summary["corpus_id"], "papers": reports,
            "note": "Mechanical replay only; human decisions are not imported or approved by this check."}
