"""One current-approval eligibility rule and deterministic approved-fact content for all modes."""

from __future__ import annotations

import json
import unicodedata
from pathlib import Path

from research_assistant.contracts import Chunk, EvidenceItem, SourceExcerpt, fingerprint
from research_assistant.review.contracts import HumanDecision, ReviewRevision
from research_assistant.review.store import decision_matches, read_events, state, validate_revision

FACT_FORMAT = "fact-text-v1"


def eligible(revision: ReviewRevision, decision: HumanDecision | None, chunks: dict[str, Chunk], entities: dict) -> bool:
    """Never use an approval after any bound field/source/alias revision changes."""
    return bool(decision and decision.decision == "approved" and decision_matches(revision, decision)
                and not validate_revision(revision, chunks, entities))


def fact_content(revision: ReviewRevision, decision_id: str, chunks: dict[str, Chunk], corpus_id: str) -> dict:
    """Render the same complete fact/excerpt bundle for ablation and graph retrieval."""
    excerpts = []
    for span in revision.support:
        chunk = chunks[span.chunk_id]
        excerpts.append(SourceExcerpt(chunk_id=chunk.chunk_id, paper_id=chunk.paper_id,
            source_sha256=chunk.source_sha256, source_url=chunk.source_url, page=chunk.page,
            section=chunk.section, chunk_page_start=chunk.page_start,
            start=span.start, end=span.end, text=chunk.text[span.start:span.end]))
    fact_id = "fact_" + fingerprint([FACT_FORMAT, corpus_id, revision.claim_id, revision.revision, revision.sha256, decision_id])
    conditions = {**revision.draft.conditions, "method": revision.draft.method, "dataset": revision.draft.dataset}
    evidence = EvidenceItem(id=fact_id, kind="approved_fact", excerpts=excerpts,
        approved_claim_ids=[revision.claim_id], claim_revision=revision.revision,
        claim_text=revision.draft.statement, conditions=conditions,
        retrieval_origin="approved_fact")
    embedding = json.dumps({"paper": revision.paper.paper_id, "method": revision.draft.method,
        "dataset": revision.draft.dataset, "assertion": revision.draft.statement,
        "conditions": dict(sorted(revision.draft.conditions.items()))}, ensure_ascii=False, separators=(",", ":"))
    rendered = json.dumps({"claim_id": revision.claim_id, "claim_revision": revision.revision,
        "paper": revision.paper.paper_id, "method": revision.draft.method, "dataset": revision.draft.dataset,
        "assertion": revision.draft.statement, "conditions": dict(sorted(revision.draft.conditions.items())),
        "source_chunk_ids": evidence.source_chunk_ids, "quotations": [e.text for e in excerpts]},
        ensure_ascii=False, separators=(",", ":"))
    return {"id": fact_id, "representation_version": FACT_FORMAT, "claim_id": revision.claim_id, "claim_revision": revision.revision,
            "revision_sha256": revision.sha256, "decision_id": decision_id,
            "entity_revision": revision.entity_revision, "source_sha256": revision.paper.source_sha256,
            "paper_id": revision.paper.paper_id, "kind": revision.draft.kind,
            "entities": [e.model_dump() for e in revision.entities],
            "rendered_text": rendered, "embedding_text": embedding,
            "evidence": evidence.model_dump(), "claim_text": revision.draft.statement}


def projection(directory: Path, chunks: dict[str, Chunk]) -> dict:
    """Rebuild derived eligibility from immutable history; conflicting findings retain separate IDs."""
    current = state(directory)
    config = json.loads((directory / "config.json").read_text(encoding="utf-8"))
    facts, statuses = [], []
    for revision in current["current"].values():
        entry = current["decisions"].get((revision.claim_id, revision.revision))
        decision, decision_id = entry if entry else (None, None)
        errors = validate_revision(revision, chunks, current["entities"])
        active = eligible(revision, decision, chunks, current["entities"])
        status = ("approved" if active else decision.decision if decision and decision.decision != "approved"
                  else "needs_review" if errors or decision or revision.revision > 1 else "validated")
        statuses.append({"claim_id": revision.claim_id, "revision": revision.revision,
                         "revision_sha256": revision.sha256, "status": status, "errors": errors,
                         "paper_id": revision.paper.paper_id})
        if active:
            facts.append(fact_content(revision, decision_id, chunks, config["corpus_id"]))
    return {"review_head": current["head"], "representation_version": FACT_FORMAT,
            "ancestor_heads": ["0" * 64] + [e["sha256"] for e in read_events(directory)],
            "facts": facts, "statuses": statuses}


def alias_targets(alias: str, definitions: dict) -> list[str]:
    """Return all exact normalized candidates; ambiguity is visible and never auto-merged."""
    normalize = lambda value: unicodedata.normalize("NFKC", value).casefold().strip()
    wanted = normalize(alias)
    return sorted(entity.id for entity in definitions.values()
                  if wanted in {normalize(value) for value in [entity.name, *entity.aliases]})
