"""Development-only annotations, source checks and explicit human gold validation.

This module does not implement the frozen evaluation runner. It rejects external
dataset directories and held-out rows before annotation/scoring operations.
"""

from __future__ import annotations

import json
import math
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from pydantic import Field, model_validator

from research_assistant.contracts import (
    Chunk, Contract, EvaluationQuestion, EvidenceItem, RetrievalResult, SourceExcerpt,
    SourceSpanRef, fingerprint, text_sha,
)
from research_assistant.evaluation.scoring import score_evidence
from research_assistant.ingestion.sources import load_corpus_chunks
from research_assistant.pipeline import write_immutable
from research_assistant.retrieval.evidence import assemble_evidence


class ReasoningLink(Contract):
    """A human-readable question-design relation, never executable Cypher or a gold graph ID."""

    source: str = Field(min_length=1)
    relation: str = Field(min_length=1)
    target: str = Field(min_length=1)


class GoldChoice(Contract):
    """A human decision on an evaluation annotation, separate from graph claim approval."""

    decision: Literal["approved", "rejected", "needs_review"]
    reason: str = Field(min_length=1)


class GoldReceipt(Contract):
    """Exact annotation bindings and verbatim provenance for one supplied human response."""

    origin: Literal["human_chat"]
    reviewer: str = Field(min_length=1)
    dataset_sha256: str
    presented_batch_sha256: str
    entry_hashes: dict[str, str]
    verbatim_response: str = Field(min_length=1)
    choices: dict[str, GoldChoice]
    actual_batch_review_seconds_approx: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    per_question_seconds: None = None
    verbatim_time_response: str
    received_at: datetime

    @model_validator(mode="after")
    def explicit_decision(self) -> GoldReceipt:
        """Require timezone, identity and reasons; unknown durations stay unknown."""
        if (self.received_at.tzinfo is None or not self.reviewer.strip()
                or not self.verbatim_response.strip() or not self.choices
                or set(self.choices) != set(self.entry_hashes)
                or any(not value.reason.strip() for value in self.choices.values())):
            raise ValueError("Explicit bound human identity, choices, reasons and timezone are required")
        return self


class DevelopmentAnnotation(Contract):
    """An independently reviewed question and its exact source-based scoring annotation."""

    revision: int = Field(default=1, ge=1)
    gold: EvaluationQuestion
    secondary_tags: list[str] = Field(default_factory=list)
    category_rationale: str = Field(min_length=1)
    reasoning_chain: list[ReasoningLink] = Field(default_factory=list)
    unanswerable_rationale: str | None = None
    context_spans: list[SourceSpanRef] = Field(default_factory=list)

    @model_validator(mode="after")
    def development_only(self) -> DevelopmentAnnotation:
        """Enforce category precedence and explicit limitations without granting human validation."""
        if self.gold.split != "development":
            raise ValueError("This workflow accepts development annotations only")
        chain = self.reasoning_chain
        if any(a.target != b.source for a, b in zip(chain, chain[1:])):
            raise ValueError("Reasoning links must form a connected chain")
        if self.gold.category == "multi_hop" and len(chain) < 2:
            raise ValueError("Multi-hop needs at least two explicit linked relations")
        if self.gold.category != "multi_hop" and len(chain) >= 2:
            raise ValueError("Multi-hop takes category precedence")
        if self.gold.category == "unanswerable" and not self.unanswerable_rationale:
            raise ValueError("Corpus-unanswerability needs an explicit rationale and source-coverage caveat")
        papers = {s.paper_id for fact in self.gold.facts for alternative in fact.support_sets for s in alternative}
        if self.gold.category == "direct" and len(papers) != 1:
            raise ValueError("A direct question must use one reporting paper")
        if self.gold.category == "cross_paper" and len(papers) < 2:
            raise ValueError("Cross-paper needs at least two reporting papers")
        return self


def development_directory(directory: Path) -> Path:
    """Reject private/external directories before reading, listing or writing their contents."""
    target = directory.resolve()
    allowed = Path("data/evaluation/development").resolve()
    if not allowed.is_relative_to(Path.cwd().resolve()) or target == allowed or not target.is_relative_to(allowed):
        raise ValueError("Choose a versioned directory inside data/evaluation/development")
    return target


def source_identity(chunks: dict[str, Chunk]) -> str:
    """Bind gold to immutable source content, independently of graph or approval IDs."""
    return fingerprint([chunks[key].model_dump() for key in sorted(chunks)])


def source_excerpt(span: SourceSpanRef, chunks: dict[str, Chunk]) -> SourceExcerpt:
    """Resolve a source reference for display; the shared scorer validates its hash and ownership."""
    chunk = chunks[span.chunk_id]
    return SourceExcerpt(chunk_id=chunk.chunk_id, paper_id=span.paper_id,
        source_sha256=span.source_sha256, source_url=chunk.source_url, page=chunk.page,
        section=chunk.section, chunk_page_start=chunk.page_start,
        start=span.start, end=span.end, text=chunk.text[span.start:span.end])


def assembled_result(items: list[EvidenceItem]) -> RetrievalResult:
    """Exercise the common packer; this oracle feasibility witness is not a retrieval experiment."""
    evidence, context, aliases, tokens, decisions = assemble_evidence(items)
    return RetrievalResult(requested_mode="annotation_witness", effective_mode="annotation_witness",
        evidence=evidence, context=context, context_sha256=text_sha(context), estimated_tokens=tokens,
        aliases=aliases, candidates=decisions, retrieval_ms=0)


def validate_annotations(entries: list[DevelopmentAnnotation], chunks: dict[str, Chunk]) -> list[dict]:
    """Validate eight stratified drafts and source-only feasible contexts without approving them."""
    if len(entries) != 8 or len({e.gold.question_id for e in entries}) != 8:
        raise ValueError("Expected eight unique development questions")
    if Counter(e.gold.category for e in entries) != dict.fromkeys(
            ("direct", "cross_paper", "multi_hop", "unanswerable"), 2):
        raise ValueError("Expected two development questions in each primary category")
    reports = []
    for entry in entries:
        question = entry.gold
        # The existing scorer checks ALL gold alternatives even for an empty context.
        score_evidence(question, assembled_result([]), chunks)
        for span in entry.context_spans:
            excerpt = source_excerpt(span, chunks)
            chunk = chunks[span.chunk_id]
            if (excerpt.paper_id != chunk.paper_id or excerpt.source_sha256 != chunk.source_sha256
                    or text_sha(excerpt.text) != span.quote_sha256):
                raise ValueError("Context-only annotation source identity/hash is invalid")
        witnesses = []
        for sufficient in question.sufficient_fact_sets:
            spans = [span for fact in question.facts if fact.fact_id in sufficient for span in fact.support_sets[0]]
            # One raw unit per source chunk, using complete chunks; no gold assertion is supplied as evidence.
            ids = list(dict.fromkeys(span.chunk_id for span in spans))
            items = []
            for chunk_id in ids:
                chunk = chunks[chunk_id]
                full = SourceSpanRef(paper_id=chunk.paper_id, source_sha256=chunk.source_sha256,
                    chunk_id=chunk_id, start=0, end=len(chunk.text), quote_sha256=chunk.text_sha256)
                items.append(EvidenceItem(id=chunk_id, excerpts=[source_excerpt(full, chunks)],
                                          retrieval_origin="annotation_witness"))
            result = assembled_result(items)
            score = score_evidence(question, result, chunks)
            witnesses.append({"units": len(result.evidence), "estimated_tokens": result.estimated_tokens,
                              "recall": score["evidence_fact_recall_at_6"], "context_sha256": result.context_sha256})
        if question.category != "unanswerable" and not any(w["recall"] == 1 for w in witnesses):
            raise ValueError("No first-alternative source witness fits the shared context limits")
        reports.append({"question_id": question.question_id, "category": question.category,
                        "entry_sha256": fingerprint(entry.model_dump(mode="json")),
                        "witnesses": witnesses, "semantic_validation": "pending_human"})
    return reports


def create_dataset(directory: Path, corpus_id: str, entries: list[DevelopmentAnnotation],
                   chunks: dict[str, Chunk], absence_audit: dict) -> dict:
    """Write an immutable development version; edited annotations require a new version directory."""
    directory = development_directory(directory)
    reports = validate_annotations(entries, chunks)
    unanswerable = {e.gold.question_id for e in entries if e.gold.category == "unanswerable"}
    if set(absence_audit.get("questions", {})) != unanswerable:
        raise ValueError("Both unanswerable drafts need corpus-wide absence-triage records")
    gold_text = "".join(json.dumps(e.model_dump(mode="json"), ensure_ascii=False, sort_keys=True) + "\n" for e in entries)
    # Only these stripped requests may later be sent to retrieval/generation.
    questions_text = "".join(json.dumps({"question_id": e.gold.question_id, "question": e.gold.question,
        "split": "development", "category": e.gold.category, "secondary_tags": e.secondary_tags},
        ensure_ascii=False, sort_keys=True) + "\n" for e in entries)
    audit_text = json.dumps(absence_audit, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    manifest = {"format": "development-gold-v1", "split": "development", "corpus_id": corpus_id,
        "source_chunks_sha256": source_identity(chunks), "annotations_sha256": text_sha(gold_text),
        "questions_sha256": text_sha(questions_text), "absence_audit_sha256": text_sha(audit_text),
        "question_count": 8, "category_counts": dict(Counter(e.gold.category for e in entries)),
        "selection": "Pilot topics and source coverage only; no held-out inputs or observed retrieval gains.",
        "review_status": "Drafts; mechanical checks do not grant human validation"}
    for name, content in [("annotations.jsonl", gold_text), ("questions.jsonl", questions_text),
                          ("absence-audit.json", audit_text), ("manifest.json", json.dumps(manifest, indent=2) + "\n")]:
        write_immutable(directory / name, content)
    return {"dataset_directory": str(directory), "dataset_sha256": fingerprint(manifest), "checks": reports}


def load_dataset(directory: Path) -> tuple[dict, list[DevelopmentAnnotation], dict[str, Chunk]]:
    """Read only named development artifacts and verify source/annotation hashes before use."""
    directory = development_directory(directory)
    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    if manifest.get("split") != "development" or manifest.get("format") != "development-gold-v1":
        raise ValueError("Not a supported development dataset")
    for name, key in [("annotations.jsonl", "annotations_sha256"), ("questions.jsonl", "questions_sha256"),
                      ("absence-audit.json", "absence_audit_sha256")]:
        if text_sha((directory / name).read_text(encoding="utf-8")) != manifest[key]:
            raise ValueError("Development artifact hash changed; create a new version and review it")
    entries = [DevelopmentAnnotation.model_validate_json(line) for line in
               (directory / "annotations.jsonl").read_text(encoding="utf-8").splitlines()]
    chunks = load_corpus_chunks(manifest["corpus_id"])
    if source_identity(chunks) != manifest["source_chunks_sha256"]:
        raise ValueError("Development source snapshot changed")
    validate_annotations(entries, chunks)
    return manifest, entries, chunks


def read_receipt(path: Path) -> dict:
    """Detect edited receipts before replay, then validate the human-record contract."""
    raw = json.loads(path.read_text(encoding="utf-8"))
    digest = raw.pop("receipt_sha256")
    if fingerprint(raw) != digest:
        raise ValueError("Gold receipt hash changed")
    GoldReceipt.model_validate(raw)
    return raw


def review_status(directory: Path) -> dict:
    """Replay exact-bound human receipts; absent/rejected/stale rows never count as validated gold."""
    directory = development_directory(directory)
    manifest, entries, _ = load_dataset(directory)
    binding = fingerprint(manifest)
    hashes = {e.gold.question_id: fingerprint(e.model_dump(mode="json")) for e in entries}
    current = {}
    for path in sorted((directory / "human-inputs").glob("*.json")):
        receipt = read_receipt(path)
        if receipt["dataset_sha256"] != binding:
            raise ValueError("Gold receipt does not match the current dataset")
        for question_id, choice in receipt["choices"].items():
            if receipt["entry_hashes"][question_id] != hashes.get(question_id):
                raise ValueError("Gold receipt does not match the exact displayed annotation")
            prior = current.get(question_id)
            at = datetime.fromisoformat(receipt["received_at"])
            if prior and at == prior[0] and choice != prior[1]:
                raise ValueError("Conflicting gold decisions have identical timestamps")
            if prior is None or at > prior[0]:
                current[question_id] = (at, choice)
    statuses = {key: current[key][1]["decision"] if key in current else "pending" for key in hashes}
    return {"dataset_sha256": binding, "questions": statuses,
            "human_validated": sum(value == "approved" for value in statuses.values()),
            "ready": all(value == "approved" for value in statuses.values())}


def export_review_batch(directory: Path, question_ids: list[str], batch_name: str) -> Path:
    """Display full questions, answers, sufficient facts, exact quotes and bindings before decisions."""
    directory = development_directory(directory)
    manifest, entries, chunks = load_dataset(directory)
    by_id = {e.gold.question_id: e for e in entries}
    if not question_ids or len(set(question_ids)) != len(question_ids) or not set(question_ids) <= set(by_id):
        raise ValueError("Review batch must contain unique known question IDs")
    if Path(batch_name).name != batch_name or batch_name in {".", ".."}:
        raise ValueError("Use a local batch basename")
    batch = {"dataset_sha256": fingerprint(manifest), "items": [
        {"entry_sha256": fingerprint(by_id[key].model_dump(mode="json")), **by_id[key].model_dump(mode="json")}
        for key in question_ids]}
    target = directory / "review-batches" / batch_name
    lines = ["# Development gold validation", "", "Approve, reject or request changes for each complete annotation, not just its answer. This does not approve graph claims or certify scientific truth.", "",
        "All sources are the pinned pilot's indexed pages. HippoRAG 2's stored Front matter section label is inaccurate; use PDF pages. Absence triage is not a proof of unanswerability. Review its corpus scope and nearby evidence.", ""]
    for item in batch["items"]:
        q = item["gold"]
        lines += [f"## {q['question_id']} — {q['category']}, revision {item['revision']}", "", q["question"], "",
                  "Reference answer: " + q["reference_answer"], "", "Category rationale: " + item["category_rationale"], "",
                  "Required sufficient fact sets: " + json.dumps(q["sufficient_fact_sets"]), "",
                  "Reasoning chain: " + json.dumps(item["reasoning_chain"], ensure_ascii=False), ""]
        for fact in q["facts"]:
            lines += [f"### {fact['fact_id']}", "", fact["statement"], ""]
            for number, support in enumerate(fact["support_sets"], 1):
                lines += [f"Alternative support {number}: ALL the following spans are required (AND). Alternatives are OR.", ""]
                for raw in support:
                    span = SourceSpanRef.model_validate(raw)
                    ex = source_excerpt(span, chunks)
                    lines += [f"[{ex.paper_id}, PDF p.{ex.page}]({ex.source_url}#page={ex.page}), chunk `{ex.chunk_id}` [{ex.start}, {ex.end}), quotation SHA-256 `{span.quote_sha256}`:", "", "> " + ex.text.replace("\n", "\n> "), ""]
        if q["category"] == "unanswerable":
            lines += ["Corpus-unanswerability rationale: " + item["unanswerable_rationale"], "", "See `../../absence-audit.json` for complete lexical-triage results; absence of keywords is not semantic validation.", ""]
            for raw in item["context_spans"]:
                ex = source_excerpt(SourceSpanRef.model_validate(raw), chunks)
                lines += [f"Context only, NOT a gold fact: [{ex.paper_id}, p.{ex.page}]({ex.source_url}#page={ex.page})", "", "> " + ex.text, ""]
        lines += [f"Exact annotation binding: `{item['entry_sha256']}`", ""]
    write_immutable(target / "batch.json", json.dumps(batch, ensure_ascii=False, indent=2) + "\n")
    write_immutable(target / "REVIEW.md", "\n".join(lines))
    return target / "batch.json"


def record_gold_decisions(directory: Path, batch_name: str, receipt_name: str, reviewer: str,
                          verbatim_response: str, choices: dict[str, dict[str, str]],
                          batch_seconds: float | None = None, verbatim_time_response: str = "not measured") -> dict:
    """Record only supplied human responses to exact displayed development annotations."""
    directory = development_directory(directory)
    if any(Path(name).name != name or name in {".", ".."} for name in (batch_name, receipt_name)):
        raise ValueError("Use local batch/receipt basenames")
    if not receipt_name.endswith(".json") or not reviewer.strip() or not verbatim_response.strip() or not choices:
        raise ValueError("Explicit human identity/response/decisions and a JSON receipt are required")
    if batch_seconds is not None and (not math.isfinite(batch_seconds) or batch_seconds < 0):
        raise ValueError("Actual batch duration must be finite and nonnegative")
    manifest, entries, _ = load_dataset(directory)
    batch = json.loads((directory / "review-batches" / batch_name / "batch.json").read_text(encoding="utf-8"))
    hashes = {e.gold.question_id: fingerprint(e.model_dump(mode="json")) for e in entries}
    shown = {item["gold"]["question_id"]: item["entry_sha256"] for item in batch["items"]}
    if batch["dataset_sha256"] != fingerprint(manifest) or not set(choices) <= set(shown):
        raise ValueError("Decisions must match the displayed development batch")
    for key, choice in choices.items():
        if shown[key] != hashes[key] or set(choice) != {"decision", "reason"} or choice["decision"] not in {
                "approved", "rejected", "needs_review"} or not choice["reason"].strip():
            raise ValueError("Stale annotation or invalid explicit decision/reason")
    content = {"origin": "human_chat", "reviewer": reviewer, "dataset_sha256": fingerprint(manifest),
        "presented_batch_sha256": fingerprint(batch), "entry_hashes": {key: hashes[key] for key in choices},
        "verbatim_response": verbatim_response, "choices": choices,
        "actual_batch_review_seconds_approx": batch_seconds, "per_question_seconds": None,
        "verbatim_time_response": verbatim_time_response}
    path = directory / "human-inputs" / receipt_name
    if path.exists():
        receipt = read_receipt(path)
        if any(receipt[key] != value for key, value in content.items()):
            raise ValueError("Preserve the existing receipt and choose a new name")
    else:
        receipt = {**content, "received_at": datetime.now(timezone.utc).isoformat()}
    GoldReceipt.model_validate(receipt)
    write_immutable(path, json.dumps({**receipt, "receipt_sha256": fingerprint(receipt)}, ensure_ascii=False, indent=2) + "\n")
    return review_status(directory)


def check_dataset(directory: Path) -> dict:
    """Report exact offline checks and pending human decisions; never load or run held-out data."""
    manifest, entries, chunks = load_dataset(directory)
    status = review_status(directory)
    checks = validate_annotations(entries, chunks)
    for row in checks:
        row["semantic_validation"] = status["questions"][row["question_id"]]
    return {"task_id": "M2.3", "corpus_id": manifest["corpus_id"],
            "checks": checks, "review": status,
            "new_llm_calls": 0, "graph_mutations": 0,
            "note": "Source witnesses demonstrate feasible annotations, not retrieval performance."}
