"""Immutable review revisions and explicit human decisions, distinct from extraction validation."""

from typing import Literal

from pydantic import Field, model_serializer

from research_assistant.contracts import Contract, PaperManifestEntry, SourceSpanRef, fingerprint
from research_assistant.contracts import ReviewDecision as HumanDecision
from research_assistant.extraction.contracts import ProposedClaim


class EntityDefinition(Contract):
    """An explicitly scoped mapping; names/aliases alone never merge entities."""

    id: str
    kind: Literal["method", "dataset"]
    name: str = Field(min_length=1)
    aliases: list[str]

    @property
    def revision(self) -> str:
        """Bind alias spelling and canonical meaning to review eligibility."""
        return fingerprint(self.model_dump())


class ReviewRevision(Contract):
    """An extraction proposal or a subsequent proposed correction, never an approval."""

    claim_id: str
    revision: int = Field(ge=1)
    paper: PaperManifestEntry
    draft: ProposedClaim
    support: list[SourceSpanRef]
    validation_errors: list[str]
    entity_revision: str
    entities: list[EntityDefinition]
    predecessor_sha256: str | None = None
    change_reason: str
    relation_roles: dict[str, Literal['ABOUT_DATASET']] | None = None

    @model_serializer(mode='wrap')
    def preserve_legacy_serialization(self, handler):
        """Old absent-role revisions retain exact journal/decision hashes."""
        value=handler(self)
        if self.relation_roles is None:value.pop('relation_roles',None)
        return value

    @property
    def sha256(self) -> str:
        """Bind everything shown for this revision, including exact supporting spans."""
        return fingerprint(self.model_dump())


# HumanDecision is a descriptive alias of the shared ReviewDecision contract above.
# Keeping one model prevents CSV, chat and future graph consumers from accepting weaker bindings.


def mapping_identity(entities: list[EntityDefinition], roles: dict[str,str] | None = None) -> str:
    """Bind new relationship semantics while preserving legacy entity-only identities."""
    definitions=[e.model_dump() for e in entities]
    return fingerprint(definitions if roles is None else {'entities':definitions,'relation_roles':roles})
