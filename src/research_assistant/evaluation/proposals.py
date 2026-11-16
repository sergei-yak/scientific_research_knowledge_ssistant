"""Public-only M5.5 proposals and authoring receipts, never frozen-run authorization.

These contracts perform no filesystem/service access and never enable generation.
The historical freeze/runner contracts remain unchanged.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import PureWindowsPath
from typing import Literal

from pydantic import Field, model_validator

from research_assistant.contracts import Contract, fingerprint

HEX = r'^[a-f0-9]{64}$'
MODES = ('vector', 'hybrid', 'hybrid_facts', 'graph')
PROFILES = (('A0', 'baseline', 'reference'), ('A1', 'retrieval-v2', 'reference'),
            ('A2', 'retrieval-v2', 'cross_encoder'))
CATEGORIES = ('direct', 'cross_paper', 'multi_hop', 'unanswerable')


class ProposedCondition(Contract):
    """Identify a complete policy, not a mode label that collapses different arms."""

    condition_id: str
    arm_id: Literal['A0', 'A1', 'A2']
    mode: Literal['vector', 'hybrid', 'hybrid_facts', 'graph']
    profile_id: Literal['baseline', 'retrieval-v2']
    selector_id: Literal['reference', 'cross_encoder']


def matched_conditions() -> list[ProposedCondition]:
    """The proposed full matched design retains all three previously defined policies."""
    return [ProposedCondition(condition_id=arm+'-'+mode, arm_id=arm, mode=mode,
            profile_id=profile, selector_id=selector) for arm, profile, selector in PROFILES for mode in MODES]


class MatchedStudyProposal(Contract):
    """A bounded reviewable design; deliberately not accepted by the execution runner."""

    format: Literal['matched-v2-study-proposal-v1'] = 'matched-v2-study-proposal-v1'
    status: Literal['proposal_not_authorization'] = 'proposal_not_authorization'
    conditions: list[ProposedCondition] = Field(default_factory=matched_conditions)
    development_questions: Literal[8] = 8
    fresh_heldout_questions: Literal[16] = 16
    question_count: Literal[24] = 24
    generation_request_limit: Literal[288] = 288
    retrieval_request_limit: Literal[288] = 288
    output_tokens: Literal[512] = 512
    context_tokens: Literal[4096] = 4096
    evidence_units: Literal[6] = 6
    evidence_estimated_tokens: Literal[1800] = 1800
    concurrency: Literal[1] = 1
    retries: Literal[0] = 0
    paid_budget_usd: Literal[0] = 0
    extra_encoder_reads: Literal[0] = 0
    order_seed: Literal[5551] = 5551
    prior_negative_gate_disclosed: Literal[True] = True
    final_execution_authorized: Literal[False] = False

    @model_validator(mode='after')
    def matched_policies(self) -> MatchedStudyProposal:
        """Reject mode-only labels, policy substitution, omitted controls and reordered arms."""
        if self.conditions != matched_conditions():
            raise ValueError('Proposal requires exact A0/A1/A2 profiles/selectors and ordered four-mode conditions')
        if self.question_count*len(self.conditions) != self.generation_request_limit:
            raise ValueError('Every condition/question pair must fit the proposed request cap')
        return self


class EvaluatorAuthoringScope(Contract):
    """Precisely scoped private authoring proposal; path checks are lexical, with zero I/O."""

    format: Literal['fresh-evaluator-authoring-scope-v1'] = 'fresh-evaluator-authoring-scope-v1'
    developer_root: str
    baseline_root: str
    output_root: str
    retired_questions_file: str
    public_bundle_manifest: str
    public_bundle_manifest_sha256: str = Field(pattern=HEX)
    task_file: str
    task_sha256: str = Field(pattern=HEX)
    fresh_question_count: Literal[16] = 16
    per_category: dict[str, int] = Field(default_factory=lambda: {key:4 for key in CATEGORIES})
    no_development_chat_history: Literal[True] = True
    retired_access: Literal['exact_stripped_questions_file_only'] = 'exact_stripped_questions_file_only'
    retired_gold_answers_scores_reveals_allowed: Literal[False] = False
    private_output_overwrite_allowed: Literal[False] = False
    provider_calls: Literal[0] = 0
    retrieval_calls: Literal[0] = 0
    paid_calls: Literal[0] = 0
    application_writes: Literal[0] = 0
    final_execution_authorized: Literal[False] = False

    @model_validator(mode='after')
    def external_paths_and_bindings(self) -> EvaluatorAuthoringScope:
        """Reject ambiguous/private-in-repo scopes without touching any private path."""
        paths = [PureWindowsPath(value) for value in (self.developer_root, self.baseline_root,
                  self.output_root, self.retired_questions_file, self.public_bundle_manifest, self.task_file)]
        if any(not p.is_absolute() or '..' in p.parts for p in paths):
            raise ValueError('Scope needs explicit absolute Windows paths without parent traversal')
        developer, baseline, output, retired, bundle, task = paths
        if any(output==root or output.is_relative_to(root) or root.is_relative_to(output)
               for root in (developer, baseline, retired.parent)):
            raise ValueError('Fresh private outputs must be outside development/baseline/retired roots')
        if any(retired==root or retired.is_relative_to(root) for root in (developer, baseline)):
            raise ValueError('Retired screening input must remain external')
        if retired.name!='questions.jsonl' or output==retired.parent:
            raise ValueError('Only the exact retired stripped-question file may be screened')
        if not bundle.is_relative_to(developer) or not task.is_relative_to(developer):
            raise ValueError('Public author inputs/task must belong to the implementation checkout')
        if self.per_category != {key:4 for key in CATEGORIES}:
            raise ValueError('Fresh authoring requires four questions per category')
        if self.public_bundle_manifest_sha256=='0'*64 or self.task_sha256=='0'*64:
            raise ValueError('Placeholder commitments cannot authorize authoring')
        return self


class EvaluatorAuthoringAuthorization(Contract):
    """A real human response can authorize this authoring scope only, never a final run."""

    format: Literal['fresh-evaluator-authoring-approval-v1'] = 'fresh-evaluator-authoring-approval-v1'
    origin: Literal['human_chat']
    scope_sha256: str = Field(pattern=HEX)
    reviewer: str = Field(min_length=1)
    received_at: datetime
    verbatim_response: str = Field(min_length=1)
    approved: Literal[True]
    final_execution_authorized: Literal[False] = False

    @model_validator(mode='after')
    def human_provenance(self) -> EvaluatorAuthoringAuthorization:
        """Unknown or inferred human decisions/timestamps are not valid approvals."""
        if (self.received_at.tzinfo is None or not self.reviewer.strip()
                or not self.verbatim_response.strip() or self.scope_sha256=='0'*64):
            raise ValueError('Explicit timezone-aware human provenance and a real scope hash are required')
        return self


def check_authoring_authorization(scope: EvaluatorAuthoringScope, receipt: EvaluatorAuthoringAuthorization) -> dict:
    """Bind the exact proposal to a real receipt before dispatch; perform no private I/O."""
    if receipt.scope_sha256 != fingerprint(scope.model_dump(mode='json')):
        raise ValueError('Human authoring receipt belongs to a different exact scope')
    return {'authoring_scope_authorized': True, 'final_execution_authorized': False,
            'scope_sha256': receipt.scope_sha256, 'reviewer': receipt.reviewer}
