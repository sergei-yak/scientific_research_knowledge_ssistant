"""Development-only offline diagnostics over immutable saved retrieval evidence."""

from __future__ import annotations

from research_assistant.contracts import Chunk, EvaluationQuestion, EvidenceItem, RetrievalResult
from research_assistant.evaluation.scoring import score_candidates
from research_assistant.retrieval.catalog import ReviewCatalog, checked_fact, chunk_evidence


def validate_candidates(items: list[EvidenceItem], chunks: dict[str, Chunk], catalog: ReviewCatalog) -> None:
    """Require canonical complete candidates and current approvals before gold scoring."""
    for item in items:
        if item.kind == 'approved_fact':
            checked_fact(item, catalog)
        else:
            if item.id not in chunks or item.excerpts != chunk_evidence(chunks[item.id]).excerpts:
                raise ValueError('Saved raw candidate is not its complete canonical source')


def incremental_graph_support(question: EvaluationQuestion, graph: RetrievalResult,
                              ablation: RetrievalResult, baseline_ids: set[str],
                              chunks: dict[str, Chunk]) -> dict:
    """Witness new final facts with actual novel excerpts, allowing redundant support.

    Gold never changes evidence. A fact must be covered in Graph, absent from the
    paired ablation, and lost when all novel items are removed. Record novel
    excerpts overlapping its exact registered source spans. This accommodates
    joint AND support and redundant OR witnesses; it is a source contribution
    witness, not a claim that each item is individually causally necessary.
    """
    from research_assistant.evaluation.scoring import score_evidence
    graph_facts = set(score_evidence(question, graph, chunks)['covered_facts'])
    base_facts = set(score_evidence(question, ablation, chunks)['covered_facts'])
    novel = [item for item in graph.evidence if item.id not in baseline_ids]
    without = [item for item in graph.evidence if item.id in baseline_ids]
    without_facts = set(score_candidates(question, without, chunks)['covered_facts'])
    gains = graph_facts - base_facts
    necessary_novel_facts = gains - without_facts
    witnesses = []
    for item in novel:
        for fact in question.facts:
            if fact.fact_id not in necessary_novel_facts:
                continue
            overlaps = []
            for support in fact.support_sets:
                for span in support:
                    source = chunks[span.chunk_id]
                    for ex in item.excerpts:
                        other = chunks[ex.chunk_id]
                        if ((source.paper_id, source.source_sha256, source.page, source.parser_version, source.chunker_version)
                                == (other.paper_id, other.source_sha256, other.page, other.parser_version, other.chunker_version)):
                            start = max(source.page_start + span.start, other.page_start + ex.start)
                            end = min(source.page_start + span.end, other.page_start + ex.end)
                            if start < end:
                                overlaps.append({'gold_chunk': span.chunk_id, 'source_chunk': ex.chunk_id,
                                                 'page_start': start, 'page_end': end})
            if overlaps:
                witnesses.append({'candidate_id': item.id, 'fact_id': fact.fact_id, 'source_overlaps': overlaps})
    return {'novel_selected_ids': sorted(item.id for item in novel),
            'gained_final_facts': sorted(gains),
            'gains_requiring_novel_source': sorted(necessary_novel_facts),
            'novel_source_witnesses': witnesses,
            'has_incremental_support': bool(witnesses)}
