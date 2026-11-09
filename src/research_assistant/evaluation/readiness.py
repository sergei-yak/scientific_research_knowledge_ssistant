"""Public evaluator attestations validate declared readiness without opening private inputs."""

from datetime import datetime
from typing import Literal

from pydantic import Field, model_validator

from research_assistant.contracts import Contract

CATEGORIES = ('direct', 'cross_paper', 'multi_hop', 'unanswerable')


class EvaluatorAttestation(Contract):
    """An evaluator's statement and commitments; validation is not independent gold verification."""

    task_id: Literal['M4.1'] = 'M4.1'
    evaluator: str = Field(min_length=1)
    validated_at: datetime
    corpus_id: str = Field(pattern=r'^[a-f0-9]{64}$')
    review_head: str = Field(pattern=r'^[a-f0-9]{64}$')
    development_dataset_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    heldout_questions_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    heldout_annotations_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    development_counts: dict[str, int]
    heldout_counts: dict[str, int]
    independent_source_support_validated: Literal[True]
    corpus_scoped_unanswerability_validated: Literal[True]
    private_inputs_external_to_development: Literal[True]
    private_content_exposed_to_development: bool
    exposure_notes: str

    @model_validator(mode='after')
    def stratified_and_attributed(self) -> 'EvaluatorAttestation':
        """Require the exact 8/16 stratification and explicit attribution/time/exposure record."""
        if (not self.evaluator.strip() or self.validated_at.tzinfo is None
                or self.development_counts != {category: 2 for category in CATEGORIES}
                or self.heldout_counts != {category: 4 for category in CATEGORIES}):
            raise ValueError('Require a named evaluator, timezone and exact 8/16 stratification')
        hashes = [self.corpus_id, self.review_head, self.development_dataset_sha256,
                  self.heldout_questions_sha256, self.heldout_annotations_sha256]
        if any(value == '0' * 64 for value in hashes):
            raise ValueError('Placeholder hashes are not readiness evidence')
        if self.private_content_exposed_to_development and not self.exposure_notes.strip():
            raise ValueError('Any exposure requires an explicit correction record')
        return self


def check_attestation(value: EvaluatorAttestation, corpus_id: str, review_head: str, development_sha256: str) -> dict:
    """Compare public bindings only; never list, search, resolve or read external private paths."""
    if (value.corpus_id != corpus_id or value.review_head != review_head
            or value.development_dataset_sha256 != development_sha256):
        raise ValueError('Evaluator attestation belongs to a different corpus/review/development version')
    return {'status': 'attested', 'independently_verified_private_content': False,
            'final_evaluation_authorized': False,
            'exposure_requires_resolution_before_freeze': value.private_content_exposed_to_development,
            'evaluator': value.evaluator, 'total_questions': 24, 'development_questions': 8, 'heldout_questions': 16}
