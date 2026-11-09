"""One renderer/budget/deduplication policy for every retrieval mode."""

from __future__ import annotations

import json
from typing import Callable

from research_assistant.contracts import Chunk, EvidenceItem, RetrievalResult, SourceExcerpt, text_sha


def validate_context(result: RetrievalResult, chunks: dict[str, Chunk]) -> dict[tuple, list[tuple[int, int, str]]]:
    """Verify the exact rendered context and immutable source spans for scoring and product output."""
    context, aliases = render_context(result.evidence)
    if context != result.context or text_sha(context) != result.context_sha256 or aliases != result.aliases:
        raise ValueError('Context/evidence integrity mismatch')
    if estimate_tokens(context) != result.estimated_tokens or result.estimated_tokens > 1800:
        raise ValueError('Context token estimate/budget mismatch')
    shown: dict[tuple, list[tuple[int, int, str]]] = {}
    for item in result.evidence:
        for excerpt in item.excerpts:
            chunk = chunks.get(excerpt.chunk_id)
            if (chunk is None or excerpt.paper_id != chunk.paper_id or excerpt.source_sha256 != chunk.source_sha256
                    or excerpt.source_url != chunk.source_url or excerpt.section != chunk.section
                    or excerpt.page != chunk.page or excerpt.chunk_page_start != chunk.page_start
                    or excerpt.end > len(chunk.text) or chunk.text[excerpt.start:excerpt.end] != excerpt.text):
                raise ValueError('Rendered excerpt is not an exact source span')
            key = (chunk.paper_id, chunk.source_sha256, chunk.page, chunk.parser_version, chunk.chunker_version)
            shown.setdefault(key, []).append((chunk.page_start + excerpt.start,
                                              chunk.page_start + excerpt.end, excerpt.text))
    return shown


def estimate_tokens(text: str) -> int:
    """Count the fixed shared estimate; model-native context is checked separately."""
    import tiktoken
    return len(tiktoken.get_encoding("o200k_base").encode(text))


def render_context(items: list[EvidenceItem]) -> tuple[str, dict[str, str]]:
    """Serialize all shown information and share exact duplicate source spans."""
    sources, units, source_ids, aliases = [], [], {}, {}
    for number, item in enumerate(items, 1):
        alias = f"E{number}"
        aliases[alias] = item.id
        refs = []
        for excerpt in item.excerpts:
            key = (excerpt.paper_id, excerpt.source_sha256, excerpt.page,
                   excerpt.chunk_page_start + excerpt.start,
                   excerpt.chunk_page_start + excerpt.end, excerpt.text)
            if key not in source_ids:
                source_id = f"S{len(source_ids) + 1}"
                source_ids[key] = source_id
                sources.append({"id": source_id, "paper": excerpt.paper_id,
                                "page": excerpt.page, "section": excerpt.section,
                                "text": excerpt.text})
            refs.append(source_ids[key])
        unit = {"id": alias, "sources": refs}
        if item.kind == "approved_fact":
            unit.update(claim=item.claim_text, conditions=item.conditions)
        if item.graph_paths:
            unit["paths"] = item.graph_paths
        units.append(unit)
    return json.dumps({"sources": sources, "evidence": units}, ensure_ascii=False,
                      separators=(",", ":")), aliases


def _uncovered(start: int, end: int, covered: list[tuple[int, int]]) -> list[tuple[int, int]]:
    pieces = [(start, end)]
    for lower, upper in sorted(covered):
        remaining = []
        for left, right in pieces:
            if upper <= left or lower >= right:
                remaining.append((left, right))
            else:
                if left < lower:
                    remaining.append((left, lower))
                if upper < right:
                    remaining.append((upper, right))
        pieces = remaining
    return pieces


def assemble_evidence(
    candidates: list[EvidenceItem], budget: int = 1800,
    counter: Callable[[str], int] = estimate_tokens,
) -> tuple[list[EvidenceItem], str, dict[str, str], int, list[dict]]:
    """Pack complete fact bundles and nonrepeated raw source spans, at most six units."""
    if not 1 <= budget <= 1800:
        raise ValueError("Evidence budget must be between 1 and 1800")
    selected, decisions, identities = [], [], set()
    covered: dict[tuple, list[tuple[int, int]]] = {}
    for candidate in candidates:
        identity = (("fact", tuple(sorted(candidate.approved_claim_ids)), candidate.claim_revision)
                    if candidate.kind == "approved_fact" else ("chunk", candidate.id))
        reason = None
        item = candidate.model_copy(deep=True)
        if identity in identities:
            reason = "duplicate_identity"
        elif len(selected) >= 6:
            reason = "unit_limit"
        elif item.kind == "chunk":
            excerpts = []
            for ex in item.excerpts:
                key = (ex.paper_id, ex.source_sha256, ex.page)
                absolute = ex.chunk_page_start
                for left, right in _uncovered(absolute + ex.start, absolute + ex.end, covered.get(key, [])):
                    local_start, local_end = left - absolute, right - absolute
                    excerpts.append(ex.model_copy(update={
                        "start": local_start, "end": local_end,
                        "text": ex.text[local_start - ex.start:local_end - ex.start],
                    }))
            if not excerpts:
                reason = "covered_source"
            elif len(excerpts) > 3:
                reason = "fragment_limit"
            else:
                item = EvidenceItem.model_validate({**item.model_dump(), "excerpts": excerpts})
        if reason is None:
            context, _ = render_context(selected + [item])
            if counter(context) > budget:
                reason = "token_budget"
        if reason is None:
            selected.append(item)
            identities.add(identity)
            for ex in item.excerpts:
                key = (ex.paper_id, ex.source_sha256, ex.page)
                covered.setdefault(key, []).append((ex.chunk_page_start + ex.start, ex.chunk_page_start + ex.end))
        decisions.append({"id": candidate.id, "selected": reason is None, "reason": reason})
    context, aliases = render_context(selected)
    return selected, context, aliases, counter(context), decisions


def context_hash(context: str) -> str:
    """Record the exact string delivered to the generator."""
    return text_sha(context)
