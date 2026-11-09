"""Independent span credit, shared evidence budgets and citation integrity."""

import pytest

from research_assistant.contracts import (
    Chunk, DraftAnswer, EvaluationQuestion, EvidenceItem, GoldFact, RetrievalResult,
    SourceExcerpt, SourceSpanRef, text_sha,
)
from research_assistant.evaluation.scoring import score_evidence
from research_assistant.generation import answer_question, validate_answer
from research_assistant.retrieval.evidence import assemble_evidence, estimate_tokens, render_context


def source(text="Method X uses Dataset Y.", identity="c1", base=0):
    return Chunk(chunk_id=identity, paper_id="synthetic-paper", source_sha256="a" * 64,
                 source_url="https://example.invalid/paper", page=1, section="Methods",
                 page_start=base, page_end=base + len(text), text=text, text_sha256=text_sha(text),
                 parser_version="fixture", chunker_version="fixture", mini_tokens=8, mpnet_tokens=8)


def item(chunk, start=0, end=None, fact=False):
    end = len(chunk.text) if end is None else end
    return EvidenceItem(
        id=chunk.chunk_id, kind="approved_fact" if fact else "chunk",
        approved_claim_ids=["graph-key-unrelated-to-gold"] if fact else [],
        claim_revision=1 if fact else None, claim_text="Reported evaluation" if fact else None,
        excerpts=[SourceExcerpt(chunk_id=chunk.chunk_id, paper_id=chunk.paper_id,
            source_sha256=chunk.source_sha256, source_url=chunk.source_url, page=1,
            section=chunk.section, chunk_page_start=chunk.page_start,
            start=start, end=end, text=chunk.text[start:end])],
    )


def retrieval(items):
    context, aliases = render_context(items)
    return RetrievalResult(requested_mode="vector", effective_mode="vector", evidence=items,
        context=context, context_sha256=text_sha(context), estimated_tokens=estimate_tokens(context),
        aliases=aliases, candidates=[], retrieval_ms=0)


def span(chunk, start=0, end=None):
    end = len(chunk.text) if end is None else end
    return SourceSpanRef(paper_id=chunk.paper_id, source_sha256=chunk.source_sha256,
        chunk_id=chunk.chunk_id, start=start, end=end, quote_sha256=text_sha(chunk.text[start:end]))


def question(facts, sets=None, category="direct"):
    return EvaluationQuestion(question_id="synthetic-q", question="Which dataset?",
        split="development", category=category, reference_answer="Dataset Y",
        sufficient_fact_sets=sets if sets is not None else [[facts[0].fact_id]], facts=facts)


@pytest.mark.parametrize("fact", [False, True])
def test_raw_and_approved_facts_receive_identical_span_credit(fact):
    chunk = source()
    gold = question([GoldFact(fact_id="F1", statement="Evaluation", support_sets=[[span(chunk)]])])
    assert score_evidence(gold, retrieval([item(chunk, fact=fact)]), {chunk.chunk_id: chunk})["evidence_fact_recall_at_6"] == 1


def test_joint_support_alternatives_and_best_sufficient_fact_set():
    a, b, alternative = source("First premise", "a"), source("Second premise", "b", 100), source("Equivalent complete support", "alt", 200)
    f1 = GoldFact(fact_id="F1", statement="Both premises", support_sets=[[span(a), span(b)], [span(alternative)]])
    f2 = GoldFact(fact_id="F2", statement="Other answer", support_sets=[[span(b)]])
    gold = question([f1, f2], sets=[["F1"], ["F2"]])
    chunks = {c.chunk_id: c for c in (a, b, alternative)}
    assert score_evidence(gold, retrieval([item(a)]), chunks)["evidence_fact_recall_at_6"] == 0
    assert score_evidence(gold, retrieval([item(alternative)]), chunks)["evidence_fact_recall_at_6"] == 1
    assert score_evidence(gold, retrieval([item(a), item(b)]), chunks)["evidence_fact_recall_at_6"] == 1


def test_truncated_support_or_claim_id_alone_never_grants_coverage():
    chunk = source()
    gold = question([GoldFact(fact_id="F1", statement="Complete fact", support_sets=[[span(chunk)]])])
    evidence = item(chunk, end=6, fact=True)
    evidence.claim_text = chunk.text
    evidence.approved_claim_ids = ["F1"]
    assert score_evidence(gold, retrieval([evidence]), {chunk.chunk_id: chunk})["covered_facts"] == []


def test_invalid_source_hash_and_fabricated_context_are_rejected():
    chunk = source()
    annotation = span(chunk).model_copy(update={"quote_sha256": "wrong"})
    gold = question([GoldFact(fact_id="F1", statement="Fact", support_sets=[[annotation]])])
    with pytest.raises(ValueError, match="Gold"):
        score_evidence(gold, retrieval([item(chunk)]), {chunk.chunk_id: chunk})
    valid = question([GoldFact(fact_id="F1", statement="Fact", support_sets=[[span(chunk)]])])
    result = retrieval([item(chunk)])
    result.context += " extra hidden answer"
    with pytest.raises(ValueError, match="integrity"):
        score_evidence(valid, result, {chunk.chunk_id: chunk})


def test_unanswerable_recall_is_not_zero_or_one():
    result = score_evidence(question([], sets=[], category="unanswerable"), retrieval([]), {})
    assert result["evidence_fact_recall_at_6"] is None


def test_assembler_caps_units_and_counts_graph_metadata_in_budget():
    candidates = [item(source(f"Evidence {i}", str(i), i * 100)) for i in range(9)]
    chosen, _, _, _, _ = assemble_evidence(candidates, counter=lambda text: 1)
    assert len(chosen) == 6
    candidates[0].graph_paths = [{"template": "synthetic", "entity_ids": ["x" * 2000]}]
    chosen, context, _, tokens, decisions = assemble_evidence(candidates, counter=len)
    assert tokens == len(context) <= 1800
    assert decisions[0]["reason"] == "token_budget"
    assert all(c.id != candidates[0].id for c in chosen)


def test_overlapping_chunks_keep_only_new_spans_and_offset_credit():
    first, second = source("abcdefghij", "first"), source("fghijklmno", "second", 5)
    chosen, _, _, _, _ = assemble_evidence([item(first), item(second)], counter=len)
    assert chosen[1].excerpts[0].text == "klmno"
    assert chosen[1].excerpts[0].start == 5
    gold = question([GoldFact(fact_id="F1", statement="Tail", support_sets=[[span(second, 5)]])])
    assert score_evidence(gold, retrieval(chosen), {first.chunk_id: first, second.chunk_id: second})["covered_facts"] == ["F1"]
    # The overlap is quoted in the first chunk, so the complete second source span
    # is still present across the actual context, without matching graph IDs.
    complete = question([GoldFact(fact_id="F1", statement="Complete", support_sets=[[span(second)]])])
    assert score_evidence(complete, retrieval(chosen), {first.chunk_id: first, second.chunk_id: second})["covered_facts"] == ["F1"]


def test_shared_fact_sources_render_once_without_dropping_distinct_claims():
    chunk = source()
    a, b = item(chunk, fact=True), item(chunk, fact=True)
    b.id, b.approved_claim_ids = "different-fact", ["different-claim"]
    chosen, context, _, _, _ = assemble_evidence([a, b], counter=len)
    assert len(chosen) == 2 and context.count(chunk.text) == 1


def test_unknown_or_missing_citations_are_rejected_and_abstention_is_explicit():
    result = retrieval([item(source())])
    with pytest.raises(ValueError, match="absent"):
        validate_answer(DraftAnswer(answer="Claim", citations=["E99"], insufficient_evidence=False), result)
    with pytest.raises(ValueError, match="requires citations"):
        validate_answer(DraftAnswer(answer="Claim", citations=[], insufficient_evidence=False), result)
    answer, generation = answer_question("Unknown?", retrieval([]), None)
    assert answer.insufficient_evidence and generation is None and answer.citations == []
