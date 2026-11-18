"""Typed public adapter for actual M5.5 source/human evidence; zero private filesystem I/O."""

from datetime import datetime
from pathlib import Path, PureWindowsPath
import json
from typing import Literal

from pydantic import Field, model_validator

from research_assistant.contracts import Contract
from research_assistant.evaluation.freeze import file_sha
from research_assistant.evaluation.matched_assets import public_asset

HEX = r'^[a-f0-9]{64}$'


def private_path(value: str) -> PureWindowsPath:
    """Check external metadata lexically only: do not stat/resolve an evaluator path."""
    path = PureWindowsPath(value)
    if (not path.is_absolute() or len(path.drive) != 2 or path.drive[1] != ':'
            or '..' in path.parts or any(':' in part for part in path.parts[1:])):
        raise ValueError('Evaluator metadata requires canonical absolute local Windows paths')
    return path


class ApprovedSnapshot(Contract):
    """Named immutable evaluator assets; path validation performs no filesystem operations."""

    root: str
    questions: str
    annotations: str
    human_approval_ledger: str
    current_human_state: str
    old_nine_approval_lineage: str
    revision_and_exposure_lineage: str
    source_bundle_manifest: str
    snapshot_commitments: str

    @model_validator(mode='after')
    def contained(self):
        """All approved assets must be distinct descendants of the attested snapshot."""
        root = private_path(self.root)
        paths = [private_path(value) for key, value in self.model_dump().items() if key != 'root']
        if any(path == root or not path.is_relative_to(root) for path in paths) or len(set(paths)) != len(paths):
            raise ValueError('Approved snapshot paths must be distinct descendants')
        if private_path(self.questions).name != 'questions.jsonl' or private_path(self.annotations).name != 'annotations.jsonl':
            raise ValueError('Unexpected stripped-question/annotation assets')
        return self


class SourceCounts(Contract):
    held_out_questions: Literal[16]
    approved: Literal[16]
    needs_review: Literal[0]
    rejected: Literal[0]
    per_category: dict[str, int]
    unchanged_prior_approval_lineages: Literal[9]
    new_actual_user_approvals: Literal[7]
    corrected_annotation_bindings_freshly_human_approved: Literal[3]
    question_text_changes: Literal[0]

    @model_validator(mode='after')
    def strata(self):
        if self.per_category != {key: 4 for key in ('direct', 'cross_paper', 'multi_hop', 'unanswerable')}:
            raise ValueError('Source attestation must cover all sixteen stratified approvals')
        return self


class SourceCommitments(Contract):
    questions_file_sha256: str = Field(pattern=HEX)
    annotations_file_sha256: str = Field(pattern=HEX)
    old_annotations_file_sha256: str = Field(pattern=HEX)
    human_approval_ledger_sha256: str = Field(pattern=HEX)
    current_human_state_sha256: str = Field(pattern=HEX)
    nine_original_approval_lineage_sha256: str = Field(pattern=HEX)
    revision_exposure_lineage_sha256: str = Field(pattern=HEX)
    approved_snapshot_commitments_sha256: str = Field(pattern=HEX)
    original_packet_index_sha256: str = Field(pattern=HEX)
    current_review_bindings_sha256: str = Field(pattern=HEX)
    exact_review_package_outcome_sha256: str = Field(pattern=HEX)


class SourceReplay(Contract):
    corpus_id: str = Field(pattern=HEX)
    source_chunks: Literal[1427]
    source_chunks_sha256: str = Field(pattern=HEX)
    source_chunks_jsonl_file_sha256: str = Field(pattern=HEX)
    source_bundle_manifest_sha256: str = Field(pattern=HEX)
    review_head: str = Field(pattern=HEX)
    catalog_sha256: str = Field(pattern=HEX)
    approved_catalog_claims: Literal[51]
    development_dataset_sha256: str = Field(pattern=HEX)
    development_questions_human_validated: Literal[8]
    development_ready_in_public_replay: Literal[True]
    working_source_review_development_replay_receipt_sha256: str = Field(pattern=HEX)
    working_source_replay_recorded_at_utc: datetime
    review_lock_normally_acquired_and_released: Literal[True]
    live_graph_service_or_provider_readiness_claimed: Literal[False]


class HumanEvidence(Contract):
    reviewer: str = Field(min_length=1)
    new_response_actual_source_sha256: str = Field(pattern=HEX)
    new_response_preserved_copy_sha256: str = Field(pattern=HEX)
    new_response_preserved_copy_path: str
    new_intake_receipt_sha256: str = Field(pattern=HEX)
    new_actual_decision_records_sha256: str = Field(pattern=HEX)
    prior_nine_current_state_receipt_sha256: str = Field(pattern=HEX)
    prior_scope_chat_confirmation_receipt_sha256: str = Field(pattern=HEX)
    new_human_source_declaration_acknowledgment_sha256: str = Field(pattern=HEX)
    explicit_new_approved_choices_with_nonblank_reasons: Literal[7]
    actual_required_new_declaration_checkbox_acknowledgments: Literal[1]
    scope_confirmed_by_intact_requested_browser_export: Literal[True]
    no_redundant_second_acknowledgment_requested: Literal[True]
    approval_is_from_actual_human_receipts_not_mechanical_validation_alone: Literal[True]

    @model_validator(mode='after')
    def actual_receipt(self):
        if not self.reviewer.strip() or self.new_response_actual_source_sha256 != self.new_response_preserved_copy_sha256:
            raise ValueError('Actual reviewer and byte-preserved response are required')
        private_path(self.new_response_preserved_copy_path)
        return self


class SourceTiming(Contract):
    actual_new_total_review_minutes: float | None = Field(ge=0)
    actual_new_review_session_timestamp: datetime | None
    actual_new_per_question_review_minutes: dict[str, float] | None
    browser_exported_at_utc_as_supplied: datetime
    upload_receipt_recorded_at_utc: datetime
    source_review_duration_not_inferred_from_export_or_receipt_time: Literal[True]
    complete_sixteen_item_total_review_minutes: float | None = Field(ge=0)
    historical_known_partial_batch_minutes: str
    historical_partial_time_coverage: str
    user_facing_date_context: str
    user_timezone_context: str


class SourceChecks(Contract):
    package_returned_item_bindings_verified: Literal[7]
    source_bundle_file_hashes_verified: Literal[6]
    source_chunk_contracts_verified: Literal[1427]
    catalog_source_units_verified: Literal[51]
    exact_prior_approved_item_and_receipt_lineages_verified: Literal[9]
    stripped_question_bindings_verified: Literal[16]
    current_registered_gold_spans_verified: int = Field(gt=0)
    positive_exact_source_budget_feasibility_verified: Literal[12]
    immutable_human_approved_absence_audits_verified: Literal[4]
    saved_absence_match_rows_identity_verified: int = Field(ge=0)
    protected_retained_files_unchanged: int = Field(gt=0)
    new_explicit_human_approvals_verified: Literal[7]
    new_human_source_declaration_acknowledgments_verified: Literal[1]


def _flags(actual: dict, yes: tuple[str, ...], no: tuple[str, ...] = ()) -> None:
    """Require explicit policy fields and reject extras, absent values or truthy strings."""
    expected = {**{key: True for key in yes}, **{key: False for key in no}}
    if actual.keys() != expected.keys() or any(type(actual[key]) is not bool or actual[key] != value for key, value in expected.items()):
        raise ValueError('Attestation policy/provenance fields changed')


class SourceHumanAttestation(Contract):
    """Attested annotation readiness only; never a final-run permission or private loader."""

    format: Literal['m5-5-3-source-human-readiness-attestation-v1']
    attestation_kind: Literal['current_source_and_actual_human_annotation_readiness_only']
    created_at_utc: datetime
    scope_sha256: str = Field(pattern=HEX)
    annotation_gate_ready: Literal[True]
    runner_compatible_readiness_verified: Literal[False]
    final_freeze_ready: Literal[False]
    final_execution_authorized: Literal[False]
    versioned_runner_readiness_adapter_status: str
    counts: SourceCounts
    approved_external_snapshot: ApprovedSnapshot
    current_dataset_commitments: SourceCommitments
    source_and_working_replay_bindings: SourceReplay
    actual_human_evidence: HumanEvidence
    declaration_lineage: dict
    timing: SourceTiming
    checks: SourceChecks
    correction_novelty_and_exposure_limits: dict
    preservation: dict
    remaining_gates: dict
    no_provider_model_retrieval_graph_generation_paid_download_operations: Literal[True]
    shared_tracked_docs_or_application_writes: Literal[0]

    @model_validator(mode='after')
    def policy_and_provenance(self):
        """Preserve the real exposure/unknown-time record instead of manufacturing clean readiness."""
        _flags(self.declaration_lineage, ('historical_incomplete_declaration_files_unchanged',
            'old_missing_declarations_not_invented_or_inserted',
            'current_declaration_condition_satisfied_by_genuine_new_human_checkbox',
            'independent_PDF_binary_rehash_not_claimed_or_required'))
        _flags(self.correction_novelty_and_exposure_limits, ('AI_authored_annotations',
            'actual_human_approval_evidence_retained', 'three_source_bound_corrections_disclosed',
            'old_nine_individual_annotation_and_receipt_bindings_identical',
            'old_nine_not_silently_rebound_to_edited_content', 'question_file_byte_identical_to_original_screened_set',
            'saved_original_question_screen_commitment_retained', 'author_startup_development_outcome_context_exposed',
            'explicit_exploratory_limitation_and_correction_lineage_preserved', 'procedural_context_separation_not_OS_enforced'),
            ('new_novelty_claim_made', 'retired_root_or_prompt_reread_in_this_import', 'clean_outcome_blind_authorship_claim_allowed'))
        if self.preservation != {'old_question_annotation_packet_form_CSV_review_source_receipt_files_overwritten': 0,
                'prior_approved_count_preserved_exactly': 9, 'new_scientific_revisions_during_this_import': 0,
                'private_snapshot_is_additive': True, 'raw_source_and_human_notes_not_in_public_attestation': True}:
            raise ValueError('Original annotation/approval preservation is not attested')
        _flags(self.remaining_gates, ('annotation_gate_ready', 'versioned_compatibility_adapter_pending',
            'original_negative_development_gate_not_overridden'), ('runner_compatible_readiness_verified',
            'final_freeze_ready', 'final_generation_or_paid_or_experiment_authorization'))
        dates = (self.created_at_utc, self.source_and_working_replay_bindings.working_source_replay_recorded_at_utc,
                 self.timing.browser_exported_at_utc_as_supplied, self.timing.upload_receipt_recorded_at_utc,
                 self.timing.actual_new_review_session_timestamp)
        if any(value is not None and value.tzinfo is None for value in dates):
            raise ValueError('Actual attestation timestamps require timezone')
        if any(value == '0'*64 for value in self.current_dataset_commitments.model_dump().values()) or self.scope_sha256 == '0'*64:
            raise ValueError('Placeholder source commitments are not readiness')
        return self


def load_source_attestation(path: Path, expected_sha256: str) -> SourceHumanAttestation:
    """Read/validate one hash-bound public attestation, without probing any external path."""
    resolved = public_asset(path)
    if expected_sha256 == '0'*64 or file_sha(resolved) != expected_sha256:
        raise ValueError('Source/human attestation commitment changed')
    attestation = SourceHumanAttestation.model_validate_json(resolved.read_bytes())
    root = private_path(attestation.approved_external_snapshot.root)
    if root.is_relative_to(PureWindowsPath(str(Path.cwd()))) or PureWindowsPath(str(Path.cwd())).is_relative_to(root):
        raise ValueError('Approved evaluator snapshot must remain external')
    return attestation
