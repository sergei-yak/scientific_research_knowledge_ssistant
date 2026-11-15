"""Shared source, retrieval, provider and evaluation contracts."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


def fingerprint(value: Any) -> str:
    """Hash canonical JSON rather than process-dependent Python hashes."""
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def text_sha(text: str) -> str:
    """Hash exact normalized UTF-8 source text."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class Contract(BaseModel):
    """Reject misspelled fields at persisted/public boundaries."""

    model_config = ConfigDict(extra="forbid")


class PaperManifestEntry(Contract):
    """An immutable PDF version and explicitly declared retrieval coverage."""

    paper_id: str
    title: str
    source_url: str
    source_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    local_path: str
    arxiv_id: str | None = None
    document_type: Literal["survey", "primary_study", "other"] = "other"
    rights: str
    rights_url: str
    selected_pages: list[int] = Field(min_length=1)
    selection_reason: str


class Chunk(Contract):
    """One tokenizer-safe slice of an immutable normalized page."""

    chunk_id: str
    paper_id: str
    source_sha256: str
    source_url: str
    page: int = Field(ge=1)
    section: str
    page_start: int = Field(ge=0)
    page_end: int = Field(gt=0)
    text: str = Field(min_length=1)
    text_sha256: str
    parser_version: str
    chunker_version: str
    mini_tokens: int = Field(gt=0, le=200)
    mpnet_tokens: int = Field(gt=0, le=384)

    @model_validator(mode="after")
    def exact_source(self) -> Chunk:
        """Reject inconsistent offsets and content identities."""
        if self.page_end - self.page_start != len(self.text) or text_sha(self.text) != self.text_sha256:
            raise ValueError("Chunk offsets/hash disagree with normalized text")
        return self


class SourceExcerpt(Contract):
    """A shown span; start/end index the immutable chunk, not rendered JSON."""

    chunk_id: str
    paper_id: str
    source_sha256: str
    source_url: str
    page: int = Field(ge=1)
    section: str
    chunk_page_start: int = Field(ge=0)
    start: int = Field(ge=0)
    end: int = Field(gt=0)
    text: str = Field(min_length=1)

    @model_validator(mode="after")
    def span_length(self) -> SourceExcerpt:
        """Require an exact half-open span, including when budget/dedup clips it."""
        if self.end - self.start != len(self.text):
            raise ValueError("Excerpt length disagrees with offsets")
        return self


class SourceSpanRef(Contract):
    """Independent human annotation, with no dependency on a graph fact ID."""

    paper_id: str
    source_sha256: str
    chunk_id: str
    start: int = Field(ge=0)
    end: int = Field(gt=0)
    quote_sha256: str

    @model_validator(mode="after")
    def positive_span(self) -> SourceSpanRef:
        """Reject empty/reversed annotation intervals."""
        if self.end <= self.start:
            raise ValueError("Gold span is empty/reversed")
        return self


class ClaimRevision(Contract):
    """A candidate claim; construction never grants review approval."""

    claim_id: str
    revision: int = Field(ge=1)
    kind: Literal["evaluation", "finding"]
    reporting_paper_id: str
    text: str
    conditions: dict[str, str | None] = Field(default_factory=dict)
    support: list[SourceSpanRef] = Field(min_length=1)
    status: Literal["candidate", "validated", "approved", "rejected", "needs_review"] = "candidate"


class ReviewDecision(Contract):
    """Shared explicit human decision; shape validation alone never authorizes approval."""

    claim_id: str
    claim_revision: int = Field(ge=1)
    revision_sha256: str
    source_sha256: str
    entity_revision: str
    reviewer: str = Field(min_length=1)
    reviewed_at: datetime
    review_seconds: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    review_time_note: str = Field(min_length=1)
    reason: str = Field(min_length=1)
    decision: Literal["approved", "rejected", "needs_review"]
    origin: Literal["human_csv", "human_chat"]
    provenance_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")

    @model_validator(mode="after")
    def explicit_human_record(self) -> ReviewDecision:
        """Require identity/time provenance and keep unmeasured durations explicit."""
        if not self.reviewer.strip() or not self.reason.strip():
            raise ValueError("Human reviewer and decision reason are required")
        if self.reviewed_at.tzinfo is None:
            raise ValueError("Review timestamp must include its timezone")
        return self


class EvidenceItem(Contract):
    """A raw chunk or a complete approved-fact bundle supplied for generation."""

    id: str
    kind: Literal["chunk", "approved_fact"] = "chunk"
    paper_ids: list[str] = Field(default_factory=list)
    source_chunk_ids: list[str] = Field(default_factory=list)
    excerpts: list[SourceExcerpt] = Field(min_length=1, max_length=3)
    approved_claim_ids: list[str] = Field(default_factory=list)
    claim_revision: int | None = None
    claim_text: str | None = None
    conditions: dict[str, str | None] = Field(default_factory=dict)
    graph_paths: list[dict[str, Any]] = Field(default_factory=list)
    retrieval_origin: str = "vector"
    similarity: float | None = Field(default=None, ge=-1, le=1)
    rank: int | None = Field(default=None, ge=1)

    @model_validator(mode="after")
    def fact_shape(self) -> EvidenceItem:
        """Require attribution/revision for facts without authorizing their approval."""
        papers = sorted({ex.paper_id for ex in self.excerpts})
        chunks = sorted({ex.chunk_id for ex in self.excerpts})
        if (self.paper_ids and self.paper_ids != papers) or (self.source_chunk_ids and self.source_chunk_ids != chunks):
            raise ValueError("Evidence source IDs disagree with its excerpts")
        self.paper_ids, self.source_chunk_ids = papers, chunks
        if self.kind == "chunk" and len(chunks) != 1:
            raise ValueError("One raw evidence unit must refer to one chunk")
        if self.kind == "approved_fact" and len(papers) != 1:
            raise ValueError("An approved scientific fact belongs to one reporting paper")
        if self.kind == "approved_fact" and (not self.approved_claim_ids or self.claim_revision is None or not self.claim_text):
            raise ValueError("Fact evidence needs approved claim IDs, revision and text")
        return self


class QueryRequest(Contract):
    """A snapshot-scoped question with an explicitly selected retrieval condition."""

    question: str = Field(min_length=1, max_length=2000)
    corpus_id: str
    mode: Literal["vector", "hybrid", "hybrid_facts", "graph"] = "vector"
    profile_id: Literal['baseline', 'retrieval-v2'] = 'baseline'
    selector_id: Literal['reference'] = 'reference'
    scope_file: str | None = None


class RetrievalProfile(Contract):
    """Explicit versioned policy identity; M5.2 implements the reference selector only."""

    profile_id: Literal['baseline', 'retrieval-v2']
    selector_id: Literal['reference'] = 'reference'
    feature_policy_version: str = 'canonical-evidence-v1'
    model_identity: dict | None = None
    policy_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')


class ExperimentScope(Contract):
    """An exact local development copy, distinct from source corpus identity."""

    profile_id: Literal['retrieval-v2']
    scope_id: str = Field(pattern=r'^m5dev-[a-f0-9]{12}$')
    corpus_id: str = Field(pattern=r'^[a-f0-9]{64}$')
    source_chunks_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    review_head: str = Field(pattern=r'^[a-f0-9]{64}$')
    review_directory: str
    target_id: str = Field(pattern=r'^dbu-m4-recovery-m5dev-[a-f0-9]{12}$')
    snapshot_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    target_uri: str
    container_id: str = Field(pattern=r'^[a-f0-9]{64}$')
    image_id: str = Field(pattern=r'^sha256:[a-f0-9]{64}$')
    volumes: list[str] = Field(min_length=2, max_length=2)
    baseline_root: str
    baseline_graph_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')


class CandidateTrace(Contract):
    """Actual selection-stage outcomes without evaluation gold; stage is explicit in its owner."""

    candidate_id: str
    origins: list[str]
    baseline_member: bool
    approval_source_checks: dict[str, bool]
    route: list[dict] = Field(default_factory=list)
    score: float | None = Field(default=None, allow_inf_nan=False)
    rank_before: int | None = Field(default=None, ge=1)
    rank_after: int | None = Field(default=None, ge=1)
    selected: bool
    exclusion_reason: str | None = None
    units: int = Field(ge=0, le=6)
    estimated_tokens: int = Field(ge=0)


class RetrievalResult(Contract):
    """Actual assembled context plus provenance; never hidden graph/gold context."""

    requested_mode: str
    effective_mode: str
    fallback_reason: str | None = None
    evidence: list[EvidenceItem] = Field(max_length=6)
    context: str
    context_sha256: str
    estimated_tokens: int = Field(ge=0, le=1800)
    aliases: dict[str, str]
    candidates: list[dict[str, Any]]
    retrieval_ms: float = Field(ge=0)
    audit: dict[str, Any] = Field(default_factory=dict)


class LLMResult(Contract):
    """Provider output and the exact request/settings used to produce it."""

    text: str
    provider: str
    model: str
    digest: str
    elapsed_ms: float
    usage: dict[str, int | None]
    settings: dict[str, Any]
    messages: list[dict[str, str]]


class DraftAnswer(Contract):
    """The local generator must either cite shown evidence or abstain."""

    answer: str = Field(min_length=1)
    citations: list[str]
    insufficient_evidence: bool


class AnswerResult(Contract):
    """A validated answer with resolved source links and explicit abstention."""

    answer: str
    insufficient_evidence: bool
    citations: list[dict[str, Any]]


class RunArtifact(Contract):
    """Replayable query inputs, evidence, provider output and optional accepted answer."""

    run_id: str
    created_at: str
    request: QueryRequest
    corpus_manifest: dict[str, Any]
    code_revision: str
    code_dirty: bool
    configuration: dict[str, Any]
    retrieval: RetrievalResult
    generation: LLMResult | None
    result: AnswerResult | None
    generation_requested: bool = True
    workflow: Literal["ask", "discovery", "comparison", "limitations"] = "ask"


class GoldFact(Contract):
    """OR between support sets; AND between spans in each support set."""

    fact_id: str
    statement: str
    support_sets: list[list[SourceSpanRef]] = Field(min_length=1)

    @model_validator(mode="after")
    def nonempty_sets(self) -> GoldFact:
        """An empty support set must not grant automatic coverage."""
        if any(not spans for spans in self.support_sets):
            raise ValueError("Support sets must be nonempty")
        return self


class EvaluationQuestion(Contract):
    """Gold data lives only in evaluation, never ingestion/retrieval."""

    question_id: str
    question: str
    split: Literal["development", "held_out"]
    category: Literal["direct", "cross_paper", "multi_hop", "unanswerable"]
    reference_answer: str
    sufficient_fact_sets: list[list[str]]
    facts: list[GoldFact]

    @model_validator(mode="after")
    def consistent_gold(self) -> EvaluationQuestion:
        """Reject vacuous gold recall and dangling or duplicate gold fact IDs."""
        ids = {fact.fact_id for fact in self.facts}
        if len(ids) != len(self.facts):
            raise ValueError("Duplicate gold fact IDs")
        if self.category == "unanswerable":
            if self.facts or self.sufficient_fact_sets:
                raise ValueError("Unanswerable questions have no sufficient evidence")
        elif not self.sufficient_fact_sets or any(not s or not set(s) <= ids for s in self.sufficient_fact_sets):
            raise ValueError("Invalid sufficient fact sets")
        return self


class HumanScore(Contract):
    """Blinded scoring shape; actual human scoring is a later milestone."""

    answer_id: str
    correctness: Literal[0, 0.5, 1]
    citation_support: Literal[0, 0.5, 1]
    correct_abstention: bool | None
    reviewer: str = Field(min_length=1)
    scored_at: str
    notes: str
