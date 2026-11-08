"""Propose bounded corrections from exact existing sources, without new extraction or approval."""

import json
from pathlib import Path

from research_assistant.contracts import fingerprint, text_sha
from research_assistant.extraction.contracts import ProposedClaim
from research_assistant.extraction.pilot import map_quote
from research_assistant.review.contracts import EntityDefinition
from research_assistant.review.store import load_chunks, propose_revision, state, validate_revision


def revise_from_quotes(directory: Path, claim_id: str, draft: ProposedClaim,
                       quotations: list[tuple[int, str]], entities: list[EntityDefinition], reason: str) -> dict:
    """Check exact page quotations and current bindings before registering an unapproved revision."""
    current = state(directory)
    old = current["current"][claim_id]
    chunks = load_chunks(directory)
    config = json.loads((directory / "config.json").read_text(encoding="utf-8"))
    members = json.loads((Path("data/processed") / config["corpus_id"] / "members.json").read_text(encoding="utf-8"))
    member = next(m for m in members if m["paper_id"] == old.paper.paper_id)
    pages = {p["page"]: p for line in Path(member["snapshot_path"]).with_name("pages.jsonl").read_text(encoding="utf-8").splitlines()
             if (p := json.loads(line))}
    support = []
    for page_number, quote in quotations:
        support.extend(map_quote(quote, {"paper_id": old.paper.paper_id, "page": page_number,
            "start": 0, "text": pages[page_number]["text"]}, list(chunks.values())))
    # One excerpt may cover several exact quotations in the same chunk. Any included gaps are
    # real source text and will be rendered/counted, never hidden or replaced with ellipses.
    groups = {}
    for span in support:
        if span.chunk_id not in groups:
            groups[span.chunk_id] = span
        else:
            previous = groups[span.chunk_id]
            start, end = min(previous.start, span.start), max(previous.end, span.end)
            groups[span.chunk_id] = span.model_copy(update={"start": start, "end": end,
                "quote_sha256": text_sha(chunks[span.chunk_id].text[start:end])})
    draft = draft.model_copy(deep=True, update={"quotes": [q for _, q in quotations]})
    # Revalidate even if callers used model_copy to edit a Pydantic object.
    draft = ProposedClaim.model_validate(draft.model_dump())
    proposed = old.model_copy(deep=True, update={"revision": old.revision + 1,
        "predecessor_sha256": old.sha256, "draft": draft, "support": list(groups.values()),
        "validation_errors": [], "entities": entities,
        "entity_revision": fingerprint([e.model_dump() for e in entities]), "change_reason": reason})
    expected_entities = {**current["entities"], **{entity.id: entity for entity in entities}}
    errors = validate_revision(proposed, chunks, expected_entities)
    if errors:
        raise ValueError("Proposed correction is still unresolved: " + "; ".join(errors))
    return propose_revision(directory, proposed, chunks)
