"""Deterministic source-span scoring with alternative AND/OR support sets."""

from __future__ import annotations

from research_assistant.contracts import Chunk, EvaluationQuestion, EvidenceItem, RetrievalResult, text_sha
from research_assistant.retrieval.evidence import source_intervals, validate_context


def score_evidence(question: EvaluationQuestion, result: RetrievalResult, chunks: dict[str, Chunk]) -> dict:
    """Credit only valid source spans actually present in the assembled context."""
    shown = validate_context(result, chunks)
    covered, recall = _coverage(question, shown, chunks)
    return {"question_id": question.question_id, "covered_facts": covered,
            "evidence_fact_recall_at_6": recall, "units": len(result.evidence),
            "context_sha256": result.context_sha256}


def score_candidates(question: EvaluationQuestion, items: list[EvidenceItem], chunks: dict[str, Chunk]) -> dict:
    """Measure unbounded candidate-source coverage offline, never a generator Recall@6.

    Callers validate saved candidate identities/current approvals first. No ranking,
    selection, packer invocation or RetrievalResult budget relaxation occurs here.
    """
    if len({item.id for item in items}) != len(items):
        raise ValueError('Duplicate candidate identity')
    covered, recall = _coverage(question, source_intervals(items, chunks), chunks)
    return {'question_id': question.question_id, 'covered_facts': covered,
            'candidate_support_recall': recall, 'candidate_count': len(items)}


def _coverage(question: EvaluationQuestion, shown: dict, chunks: dict[str, Chunk]) -> tuple[list[str], float | None]:
    """One exact source-interval AND/OR rule for final contexts and candidate unions."""
    covered = set()
    for fact in question.facts:
        alternatives = []
        for support_set in fact.support_sets:
            span_coverage = []
            for span in support_set:
                chunk = chunks[span.chunk_id]
                if (span.paper_id != chunk.paper_id or span.source_sha256 != chunk.source_sha256
                        or span.end > len(chunk.text)
                        or text_sha(chunk.text[span.start:span.end]) != span.quote_sha256):
                    raise ValueError("Gold source identity/hash is invalid")
                key = (chunk.paper_id, chunk.source_sha256, chunk.page, chunk.parser_version, chunk.chunker_version)
                target_start, target_end = chunk.page_start + span.start, chunk.page_start + span.end
                cursor = target_start
                for start, end, text in sorted(shown.get(key, [])):
                    left, right = max(start, target_start), min(end, target_end)
                    if left < right and text[left - start:right - start] != chunk.text[left - chunk.page_start:right - chunk.page_start]:
                        raise ValueError("Conflicting normalized source spans")
                    if start <= cursor:
                        cursor = max(cursor, end)
                span_coverage.append(cursor >= target_end)
            alternatives.append(all(span_coverage))
        if any(alternatives):
            covered.add(fact.fact_id)
    recall = None if question.category == "unanswerable" else max(
        len(covered.intersection(facts)) / len(set(facts)) for facts in question.sufficient_fact_sets
    )
    return sorted(covered), recall
