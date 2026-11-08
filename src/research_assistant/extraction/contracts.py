"""Extraction-only drafts and frozen passage plans share the source contracts."""

from typing import Literal

from pydantic import Field, model_validator

from research_assistant.contracts import Contract


class PassageSelector(Contract):
    """A development-selected paragraph anchor, never a held-out query."""

    page: int = Field(ge=1)
    anchor: str = Field(min_length=5)
    max_blocks: int = Field(default=3, ge=1, le=8)
    purpose: str


class ExtractionPlan(Contract):
    """Caps can be narrowed; increasing the specification's caps needs a recorded change."""

    version: str = Field(default="bounded-claims-v1", pattern=r"^[a-z0-9-]+$")
    amendment_decision: str | None = None
    max_passages_per_paper: int = Field(default=8, ge=1, le=8)
    max_candidates_per_paper: int = Field(default=12, ge=1, le=12)
    max_requests_per_paper: int = Field(default=4, ge=1, le=8)
    candidates_per_request: int = Field(default=2, ge=1, le=2)
    max_passage_tokens: int = Field(default=600, ge=100, le=900)
    context_tokens: int = 4096
    output_tokens: int = 1024
    initial_review_minutes: int = Field(default=20, ge=1, le=20)
    selections: dict[str, list[PassageSelector]]

    @model_validator(mode="after")
    def bounded_selections(self) -> "ExtractionPlan":
        """Reject empty or over-cap selection before model creation or requests."""
        if any(not selectors or len(selectors) > min(self.max_passages_per_paper, self.max_requests_per_paper)
               for selectors in self.selections.values()):
            raise ValueError("Passage/request selection exceeds the configured cap")
        return self


class ProposedClaim(Contract):
    """An unapproved scientific assertion plus proposed names, not canonical entity merges."""

    kind: Literal["evaluation", "finding"]
    statement: str = Field(min_length=10, max_length=600)
    method: str | None
    method_aliases: list[str] = Field(max_length=4)
    dataset: str | None
    dataset_aliases: list[str] = Field(max_length=4)
    conditions: dict[str, str | None]
    quotes: list[str] = Field(min_length=1, max_length=3)

    @model_validator(mode="after")
    def quote_bounds(self) -> "ProposedClaim":
        """Small supporting quotations keep review and later fact bundles bounded."""
        if any(not 10 <= len(quote) <= 360 for quote in self.quotes):
            raise ValueError("Supporting quote must contain 10-360 exact source characters")
        return self


class ExtractionResponse(Contract):
    """The server receives this two-candidate JSON schema on every bounded request."""

    candidates: list[ProposedClaim] = Field(max_length=2)
    no_claim_reason: str | None = None
