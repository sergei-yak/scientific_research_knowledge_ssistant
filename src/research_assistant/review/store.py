"""Hash-chained local review history; replay is authoritative and projections are rebuildable."""

from __future__ import annotations

import csv
import io
import json
import unicodedata
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from research_assistant.contracts import Chunk, fingerprint, text_sha
from research_assistant.extraction.contracts import ProposedClaim
from research_assistant.graph.repository import corpus_names
from research_assistant.ingestion.sources import load_corpus_chunks
from research_assistant.pipeline import write_immutable
from research_assistant.review.audit import audit_packets
from research_assistant.review.contracts import EntityDefinition, HumanDecision, ReviewRevision, mapping_identity


@contextmanager
def review_lock(directory: Path) -> Iterator[None]:
    """Exclusive owned lock; a stale lock requires investigation, never automatic takeover."""
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / ".review.lock"
    with path.open("x", encoding="utf-8") as handle:
        handle.write("Review operation in progress; preserve this lock after a crash.\n")
    try:
        yield
    finally:
        path.unlink()


def read_events(directory: Path) -> list[dict]:
    """Reject changed, missing, reordered or unrecognized journal events."""
    events, previous = [], "0" * 64
    for number, path in enumerate(sorted((directory / "events").glob("*.json")), 1):
        event = json.loads(path.read_text(encoding="utf-8"))
        digest = event.pop("sha256")
        if (event["sequence"] != number or event["previous_sha256"] != previous
                or fingerprint(event) != digest or event["kind"] not in {"revision", "decision", "decisions", "entity"}):
            raise ValueError("Review journal chain/identity mismatch")
        previous = digest
        events.append({**event, "sha256": digest})
    return events


def append_event(directory: Path, kind: str, payload: dict) -> str:
    """Append once under a caller-held lock; exact replay is idempotent."""
    events = read_events(directory)
    for event in events:
        if event["kind"] == kind and event["payload"] == payload:
            return event["sha256"]
    record = {"sequence": len(events) + 1, "previous_sha256": events[-1]["sha256"] if events else "0" * 64,
              "kind": kind, "payload": payload}
    digest = fingerprint(record)
    write_immutable(directory / "events" / f"{len(events)+1:06d}-{digest}.json",
                    json.dumps({**record, "sha256": digest}, ensure_ascii=False, indent=2) + "\n")
    return digest


def state(directory: Path) -> dict:
    """Replay current revisions, decisions and alias definitions; preserve all prior versions."""
    events = read_events(directory)
    revisions, decisions, entities = {}, {}, {}
    for event in events:
        if event["kind"] == "revision":
            revision = ReviewRevision.model_validate(event["payload"])
            key = (revision.claim_id, revision.revision)
            if key in revisions and revisions[key] != revision:
                raise ValueError("Conflicting immutable claim revision")
            revisions[key] = revision
            for entity in revision.entities:
                entities.setdefault(entity.id, entity)
        elif event["kind"] in {"decision", "decisions"}:
            rows = [event["payload"]] if event["kind"] == "decision" else event["payload"]["decisions"]
            for row in rows:
                decision = HumanDecision.model_validate(row)
                decisions[(decision.claim_id, decision.claim_revision)] = (decision, fingerprint(row))
        else:
            entity = EntityDefinition.model_validate(event["payload"])
            entities[entity.id] = entity
    current = {}
    for (claim_id, revision_number), revision in revisions.items():
        if claim_id not in current or revision_number > current[claim_id].revision:
            current[claim_id] = revision
    return {"head": events[-1]["sha256"] if events else "0" * 64,
            "revisions": revisions, "current": current, "decisions": decisions, "entities": entities}


def entities_for(paper_id: str, draft: ProposedClaim, proposal_revision: str) -> list[EntityDefinition]:
    """Start paper/proposal-scoped; explicit reviewed revisions may later share entity IDs."""
    return [EntityDefinition(id=kind + "_" + fingerprint([paper_id, proposal_revision, kind]),
                             kind=kind, name=name, aliases=getattr(draft, kind + "_aliases"))
            for kind in ("method", "dataset") if (name := getattr(draft, kind))]


def prepare_review(packet_directory: Path, directory: Path) -> dict:
    """Import audited proposals into a new/replayed review history, creating no decisions."""
    audit = audit_packets(packet_directory)
    corpus_names(audit["corpus_id"])
    config = {"corpus_id": audit["corpus_id"], "packet_directory": str(packet_directory.resolve()),
              "mapping_policy": "paper_and_proposal_scoped_until_explicitly_revised"}
    with review_lock(directory):
        config_path = directory / "config.json"
        if config_path.exists():
            existing = json.loads(config_path.read_text(encoding="utf-8"))
            if existing["corpus_id"] != audit["corpus_id"]:
                raise ValueError("Review packet belongs to a different corpus")
        else:
            write_immutable(config_path, json.dumps(config, indent=2) + "\n")
        write_immutable(directory / "imports" / (fingerprint(config) + ".json"),
                        json.dumps(config, indent=2) + "\n")
        for paper in audit["papers"]:
            bundle = json.loads((packet_directory / paper["paper_id"].replace(":", "-") / "bundle.json").read_text(encoding="utf-8"))
            for candidate in bundle["candidates"]:
                draft = ProposedClaim.model_validate(candidate["draft"])
                revision = ReviewRevision(claim_id=candidate["claim_id"], revision=1, paper=bundle["paper"],
                    draft=draft, support=candidate["claim"]["support"] if candidate["claim"] else [],
                    validation_errors=candidate["validation_errors"], entity_revision=candidate["entity_revision"],
                    entities=entities_for(paper["paper_id"], draft, candidate["entity_revision"]),
                    change_reason=f"Original audited {audit.get('task_id', 'M2.1')} candidate; no human decision")
                append_event(directory, "revision", revision.model_dump(mode="json"))
    return export_decisions(directory)


def export_decisions(directory: Path) -> dict:
    """Emit a new head-addressed CSV for current revisions, with human fields blank."""
    current = state(directory)
    fields = ["claim_id", "claim_revision", "revision_sha256", "source_sha256", "entity_revision",
              "reviewer", "reviewed_at", "review_seconds", "review_time_note", "decision", "reason"]
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=fields)
    writer.writeheader()
    for revision in current["current"].values():
        writer.writerow({"claim_id": revision.claim_id, "claim_revision": revision.revision,
                         "revision_sha256": revision.sha256, "source_sha256": revision.paper.source_sha256,
                         "entity_revision": revision.entity_revision})
    path = directory / "exports" / (current["head"] + ".csv")
    write_immutable(path, buffer.getvalue())
    return {"review_directory": str(directory), "review_head": current["head"],
            "claims": len(current["current"]), "decision_template": str(path)}


def load_chunks(directory: Path) -> dict[str, Chunk]:
    """Read only the selected corpus's verified immutable member chunks."""
    config = json.loads((directory / "config.json").read_text(encoding="utf-8"))
    return load_corpus_chunks(config["corpus_id"])


def decision_matches(revision: ReviewRevision, decision: HumanDecision) -> bool:
    """One shared binding predicate for import, projection and graph publication."""
    return (decision.claim_id == revision.claim_id and decision.claim_revision == revision.revision
            and decision.revision_sha256 == revision.sha256
            and decision.source_sha256 == revision.paper.source_sha256
            and decision.entity_revision == revision.entity_revision)


def validate_revision(revision: ReviewRevision, chunks: dict[str, Chunk], entities: dict) -> list[str]:
    """Fail closed on source/alias/support changes; never infer missing experiment conditions."""
    errors = list(revision.validation_errors)
    if revision.relation_roles is not None:
        dataset_ids={e.id for e in revision.entities if e.kind=='dataset'}
        if (revision.draft.kind!='finding' or not revision.relation_roles
                or set(revision.relation_roles)-dataset_ids
                or revision.entity_revision!=mapping_identity(revision.entities,revision.relation_roles)):
            errors.append('Relationship role requires a fresh exact-bound Finding/dataset revision')
    if not revision.support or len(revision.support) > 3:
        errors.append("One to three exact supporting spans are required")
    if revision.draft.kind == "evaluation" and (revision.paper.document_type == "survey"
            or not revision.draft.method or not revision.draft.dataset):
        errors.append("Evaluation needs its own reporting paper, method and dataset")
    intervals = {}
    for span in revision.support:
        chunk = chunks.get(span.chunk_id)
        if (chunk is None or span.paper_id != revision.paper.paper_id
                or chunk.paper_id != revision.paper.paper_id
                or span.source_sha256 != revision.paper.source_sha256
                or chunk.source_sha256 != span.source_sha256 or span.end > len(chunk.text)
                or text_sha(chunk.text[span.start:span.end]) != span.quote_sha256):
            errors.append("Supporting source identity/quotation changed")
        else:
            intervals.setdefault((chunk.paper_id, chunk.source_sha256, chunk.page), []).append(
                (chunk.page_start + span.start, chunk.page_start + span.end, chunk.text[span.start:span.end]))
    texts = []
    for pieces in intervals.values():
        merged = []
        for left, right, text in sorted(pieces):
            if merged and left <= merged[-1][1]:
                begin, end, content = merged[-1]
                overlap = min(end, right) - left
                if content[left-begin:left-begin+overlap] != text[:overlap]:
                    errors.append("Conflicting source spans")
                if right > end:
                    merged[-1] = (begin, right, content + text[max(0, end-left):])
            else:
                merged.append((left, right, text))
        texts.extend(text for _, _, text in merged)
    if any(not any(quote in text for text in texts) for quote in revision.draft.quotes):
        errors.append("A proposed quotation is not completely covered by exact support")
    for entity in revision.entities:
        if entity.id not in entities or entities[entity.id].revision != entity.revision:
            errors.append("Entity/alias revision changed")
    normalize = lambda value: unicodedata.normalize("NFKC", value).casefold().strip()
    for kind in ("method", "dataset"):
        name = getattr(revision.draft, kind)
        mappings = [e for e in revision.entities if e.kind == kind]
        if (not name and mappings) or (name and (len(mappings) != 1 or normalize(name) not in {
                normalize(value) for value in [mappings[0].name, *mappings[0].aliases]})):
            errors.append("Proposed method/dataset does not match its explicit entity binding")
    return sorted(set(errors))


def import_decisions(directory: Path, decisions: list[HumanDecision], chunks: dict[str, Chunk]) -> dict:
    """Validate the entire batch before appending any human decisions; blanks do not enter here."""
    with review_lock(directory):
        current = state(directory)
        seen, new = set(), []
        identity = lambda d: fingerprint(d.model_dump(mode="json", exclude={"provenance_sha256", "origin"}))
        previous = set()
        for event in read_events(directory):
            if event["kind"] in {"decision", "decisions"}:
                rows = [event["payload"]] if event["kind"] == "decision" else event["payload"]["decisions"]
                previous.update(identity(HumanDecision.model_validate(row)) for row in rows)
        for decision in decisions:
            if decision.claim_id in seen:
                raise ValueError("Duplicate/conflicting decisions in one batch")
            seen.add(decision.claim_id)
            revision = current["current"].get(decision.claim_id)
            if revision is None or not decision_matches(revision, decision):
                raise ValueError("Decision does not match the current displayed claim/source/mapping revision")
            if decision.decision == "approved" and validate_revision(revision, chunks, current["entities"]):
                raise ValueError("An invalid/unresolved candidate cannot be approved")
            if identity(decision) in previous:
                continue
            prior = current["decisions"].get((decision.claim_id, decision.claim_revision))
            if prior and decision.reviewed_at <= prior[0].reviewed_at:
                raise ValueError("A changed decision needs a newer human review timestamp")
            new.append(decision.model_dump(mode="json"))
        if new:
            append_event(directory, "decisions", {"decisions": new})
    return {"review_head": state(directory)["head"], "decisions_supplied": len(decisions), "new_decisions": len(new)}


def import_csv(directory: Path, path: Path) -> dict:
    """Snapshot the human-edited file and import explicit rows only; keep unknown time explicit."""
    raw = path.read_bytes()
    provenance = text_sha(raw.decode("utf-8-sig"))
    rows = list(csv.DictReader(io.StringIO(raw.decode("utf-8-sig"))))
    decisions = []
    for row in rows:
        if not row["decision"].strip():
            continue
        decisions.append(HumanDecision(**{**row, "review_seconds": float(row["review_seconds"]) if row["review_seconds"].strip() else None,
                                         "origin": "human_csv", "provenance_sha256": provenance}))
    write_immutable(directory / "human-inputs" / (provenance + ".csv"), raw.decode("utf-8-sig"))
    return import_decisions(directory, decisions, load_chunks(directory))


def propose_revision(directory: Path, revision: ReviewRevision, chunks: dict[str, Chunk]) -> dict:
    """Append a proposed correction; changing anything revokes previous-revision eligibility."""
    with review_lock(directory):
        current = state(directory)
        old = current["current"].get(revision.claim_id)
        if (old is None or revision.revision != old.revision + 1 or revision.predecessor_sha256 != old.sha256
                or revision.paper.paper_id != old.paper.paper_id):
            raise ValueError("Revision must extend the exact prior claim without moving reporting papers")
        # Changed aliases explicitly update definitions and invalidate all old references to those IDs.
        append_event(directory, "revision", revision.model_dump(mode="json"))
        for entity in revision.entities:
            append_event(directory, "entity", entity.model_dump(mode="json"))
    return {"review_head": state(directory)["head"], "status": "needs_review", "claim_id": revision.claim_id,
            "revision": revision.revision, "source_errors": validate_revision(revision, chunks, state(directory)["entities"])}
