"""Versioned twelve-condition freeze/authorization; public checks never probe private inputs."""

from datetime import datetime, timezone
import json
import re
from pathlib import Path, PureWindowsPath
from typing import Literal

import ollama
from pydantic import Field, model_validator

from research_assistant.contracts import Contract, fingerprint
from research_assistant.evaluation.freeze import file_sha, runtime_versions
from research_assistant.evaluation.matched_assets import public_asset
from research_assistant.evaluation.matched_scope import FrozenEvaluationScope
from research_assistant.evaluation.proposals import MatchedStudyProposal
from research_assistant.evaluation.readiness_v2 import ApprovedSnapshot, load_source_attestation, private_path
from research_assistant.graph.recovery import verify_snapshot
from research_assistant.pipeline import code_identity, write_immutable
from research_assistant.settings import Settings

HEX = r'^[a-f0-9]{64}$'


class MatchedFreeze(Contract):
    """Complete public proposal after real recovery; not authorization to run it."""

    format: Literal['matched-evaluation-freeze-v1'] = 'matched-evaluation-freeze-v1'
    created_at: datetime
    plan: MatchedStudyProposal = Field(default_factory=MatchedStudyProposal)
    scope: FrozenEvaluationScope
    scope_path: str
    scope_file_sha256: str = Field(pattern=HEX)
    source_attestation_path: str
    source_attestation_sha256: str = Field(pattern=HEX)
    approved_inputs: ApprovedSnapshot
    questions_sha256: str = Field(pattern=HEX)
    annotations_sha256: str = Field(pattern=HEX)
    approval_ledger_sha256: str = Field(pattern=HEX)
    development_dataset_sha256: str = Field(pattern=HEX)
    private_root: str
    snapshot_directory: str
    recovery_report: str
    recovery_report_sha256: str = Field(pattern=HEX)
    code_revision: str
    source_tree_sha256: str = Field(pattern=HEX)
    files: dict[str, str] = Field(min_length=1)
    runtime_versions: dict[str, str]
    encoder_revision: str
    reranker_identity: dict
    profile_policy_hashes: dict[str, str]
    generator_provider: Literal['ollama'] = 'ollama'
    generator_model: str = Field(min_length=1)
    generator_digest: str = Field(pattern=HEX)
    ollama_base_url: str
    request_timeout_seconds: float = Field(gt=0, le=600)
    graph_query_timeout_seconds: float = Field(ge=0.001, le=30)
    minimum_similarity: Literal[0.30] = 0.30
    author_outcome_exposure_disclosed: Literal[True] = True
    exploratory_study_only: Literal[True] = True
    final_execution_authorized: Literal[False] = False

    @model_validator(mode='after')
    def complete_proposal(self):
        """Reject placeholder freezes and ambiguous external storage without private I/O."""
        if self.created_at.tzinfo is None:
            raise ValueError('Freeze creation requires timezone')
        Settings(neo4j_uri=self.scope.target_uri, ollama_base_url=self.ollama_base_url)
        root, inputs = private_path(self.private_root), private_path(self.approved_inputs.root)
        if root == inputs or not inputs.is_relative_to(root):
            raise ValueError('The approved input snapshot must be below the fixed evaluator root')
        if root.name != 'retrieval-v2-fresh-v1':
            raise ValueError('Matched study requires the separately authorized fresh evaluator root')
        baseline = private_path(self.scope.baseline_root)
        if root.is_relative_to(baseline) or baseline.is_relative_to(root):
            raise ValueError('Matched evaluator storage must also remain outside the baseline checkout')
        if set(self.profile_policy_hashes) != {'A0', 'A1', 'A2'} or not self.encoder_revision.strip():
            raise ValueError('Complete profile/encoder identities are required')
        hashes = [self.questions_sha256, self.annotations_sha256, self.generator_digest,
                  self.source_tree_sha256, self.approval_ledger_sha256, *self.files.values(), *self.profile_policy_hashes.values()]
        if any(value == '0'*64 or not re.fullmatch(HEX, value) for value in hashes):
            raise ValueError('A matched freeze requires actual non-placeholder commitments')
        return self


class MatchedAuthorization(Contract):
    """New exact-freeze receipt; legacy/authoring/source approvals cannot parse as execution."""

    format: Literal['matched-final-evaluation-approval-v1'] = 'matched-final-evaluation-approval-v1'
    scope: Literal['one_frozen_matched_evaluation'] = 'one_frozen_matched_evaluation'
    origin: Literal['human_chat'] = 'human_chat'
    authorization_id: str = Field(pattern=r'^[a-f0-9]{32}$')
    freeze_file_sha256: str = Field(pattern=HEX)
    reviewer: str = Field(min_length=1)
    received_at: datetime
    verbatim_response: str = Field(min_length=1)
    approved: Literal[True]
    disclosed_post_negative_gate_continuation: Literal[True]
    author_context_exposure_acknowledged: Literal[True]
    generation_request_limit: Literal[288] = 288
    retrieval_request_limit: Literal[288] = 288
    context_tokens: Literal[4096] = 4096
    output_tokens: Literal[512] = 512
    concurrency: Literal[1] = 1
    retries: Literal[0] = 0
    paid_budget_usd: Literal[0] = 0

    @model_validator(mode='after')
    def actual_human(self):
        if (self.received_at.tzinfo is None or not self.reviewer.strip() or not self.verbatim_response.strip()
                or self.freeze_file_sha256 == '0'*64):
            raise ValueError('Actual timezone-aware exact-freeze human continuation is required')
        return self


def authorize(path: Path, freeze_path: Path) -> MatchedAuthorization:
    """Authenticate a new numerical receipt before resolving/statting any evaluator path."""
    raw = json.loads(public_asset(path).read_text(encoding='utf-8'))
    digest = raw.pop('receipt_sha256', None)
    if digest != fingerprint(raw):
        raise ValueError('Matched authorization receipt hash changed')
    receipt = MatchedAuthorization.model_validate(raw)
    if receipt.freeze_file_sha256 != file_sha(public_asset(freeze_path)):
        raise ValueError('Matched authorization belongs to a different freeze')
    return receipt


def load_freeze(path: Path, *, verify_files: bool = True) -> MatchedFreeze:
    """Validate public commitments and recovery evidence only; no private path lookup."""
    freeze = MatchedFreeze.model_validate_json(public_asset(path).read_bytes())
    verify_freeze(freeze, verify_files=verify_files)
    return freeze


def runtime_assets() -> set[Path]:
    """One exact executable/model/config set shared by proposal creation and verification."""
    paths = {Path(name) for name in ('uv.lock', 'pyproject.toml', 'compose.yaml', '.env.example')}
    for directory in ('src/research_assistant', 'scripts', 'tests'):
        paths.update(Path(directory).rglob('*.py'))
    for directory in ('manifests', '.cache/models', '.cache/rerankers', '.cache/tiktoken'):
        paths.update(p for p in Path(directory).rglob('*') if p.is_file() and '__pycache__' not in p.parts)
    return paths


def verify_freeze(freeze: MatchedFreeze, *, verify_files: bool = True) -> None:
    """Revalidate even mutated model instances; check only public assets and lexical private metadata."""
    freeze = MatchedFreeze.model_validate(freeze.model_dump(mode='json'))
    root = private_path(freeze.private_root)
    workspace = PureWindowsPath(str(Path.cwd()))
    if root.is_relative_to(workspace) or workspace.is_relative_to(root):
        raise ValueError('Matched evaluator storage must remain external')
    if workspace == private_path(freeze.scope.baseline_root):
        raise ValueError('Matched evaluation must not execute from the preserved baseline checkout')
    source = load_source_attestation(Path(freeze.source_attestation_path), freeze.source_attestation_sha256)
    bound = source.current_dataset_commitments
    replay = source.source_and_working_replay_bindings
    if (source.approved_external_snapshot != freeze.approved_inputs
            or (bound.questions_file_sha256, bound.annotations_file_sha256, bound.human_approval_ledger_sha256)
               != (freeze.questions_sha256, freeze.annotations_sha256, freeze.approval_ledger_sha256)
            or (replay.corpus_id, replay.review_head, replay.source_chunks_sha256, replay.catalog_sha256,
                replay.development_dataset_sha256) != (freeze.scope.corpus_id, freeze.scope.review_head,
                freeze.scope.source_chunks_sha256, freeze.scope.catalog_sha256, freeze.development_dataset_sha256)):
        raise ValueError('Source-human attestation differs from the matched freeze')
    if file_sha(public_asset(freeze.scope_path)) != freeze.scope_file_sha256:
        raise ValueError('Frozen evaluation scope file changed')
    if FrozenEvaluationScope.model_validate_json(public_asset(freeze.scope_path).read_bytes()) != freeze.scope:
        raise ValueError('Frozen scope declaration differs from its embedded binding')
    if verify_files:
        if runtime_versions() != freeze.runtime_versions or code_identity()['source_tree_sha256'] != freeze.source_tree_sha256:
            raise ValueError('Frozen matched runtime/source changed')
        if set(freeze.files) != {p.as_posix() for p in runtime_assets()}:
            raise ValueError('Matched executable/model/config file set is incomplete or changed')
        for name, digest in freeze.files.items():
            if file_sha(public_asset(name)) != digest:
                raise ValueError('Frozen matched executable/model asset changed')
        snapshot, _ = verify_snapshot(public_asset(freeze.snapshot_directory))
        proof = json.loads(public_asset(freeze.recovery_report).read_text(encoding='utf-8'))
        if (file_sha(public_asset(freeze.snapshot_directory) / 'manifest.json') != freeze.scope.snapshot_manifest_sha256
                or snapshot['graph_sha256'] != freeze.scope.graph_sha256
                or snapshot['review_head'] != freeze.scope.review_head
                or (snapshot.get('freeze_projection') or {}).get('corpus_id') != freeze.scope.corpus_id
                or not snapshot.get('matched_runtime_assets')
                or snapshot['source_tree_sha256'] != freeze.source_tree_sha256
                or file_sha(public_asset(freeze.recovery_report)) != freeze.recovery_report_sha256
                or not proof.get('complete') or not proof.get('target_read_only_proved')
                or proof.get('matched_readiness_complete') is not True
                or (proof.get('capacity_checks') or {}).get('complete') is not True
                or proof.get('logical_retrieval_requests') != 24
                or proof.get('copied_runtime_assets_verified') is not True
                or proof.get('graph_sha256') != freeze.scope.graph_sha256
                or proof.get('snapshot_manifest_sha256') != freeze.scope.snapshot_manifest_sha256
                or proof.get('project') != freeze.scope.target_project
                or proof.get('target_uri') != freeze.scope.target_uri
                or proof.get('image_id') != freeze.scope.image_id):
            raise ValueError('New read-only recovery proof does not match the matched freeze')
        if any(snapshot['assets'].get(name) != digest for name, digest in freeze.files.items()):
            raise ValueError('Copied runtime/config/model bytes differ from the frozen files')
        from research_assistant.retrieval.profiles import retrieval_profile
        from research_assistant.retrieval.reranker import model_identity, verified_manifest
        expected = {arm: retrieval_profile(profile, selector).policy_sha256 for arm, profile, selector in
                    [('A0', 'baseline', 'reference'), ('A1', 'retrieval-v2', 'reference'), ('A2', 'retrieval-v2', 'cross_encoder')]}
        if expected != freeze.profile_policy_hashes or model_identity(verified_manifest()) != freeze.reranker_identity:
            raise ValueError('Frozen policy/reranker identity changed')


def prepare_freeze(*, scope_path: Path, source_attestation_path: Path, source_attestation_sha256: str,
                   snapshot_directory: Path, recovery_report: Path, private_root: str,
                   settings: Settings, output: Path) -> dict:
    """Build a proposal only after real recovery evidence exists; never read held-out inputs."""
    public_asset(output)
    source = load_source_attestation(source_attestation_path, source_attestation_sha256)
    scope = FrozenEvaluationScope.model_validate_json(public_asset(scope_path).read_bytes())
    snapshot, _ = verify_snapshot(public_asset(snapshot_directory))
    if not snapshot.get('matched_runtime_assets'):
        raise ValueError('Matched recovery must include pinned runtime assets')
    if settings.generation_provider != 'ollama' or settings.max_retries != 0 or settings.max_concurrency != 1:
        raise ValueError('Matched proposal requires local zero-retry single-concurrency settings')
    from research_assistant.evaluation.development import load_dataset, review_status
    from research_assistant.embeddings import encoder_artifact
    from research_assistant.retrieval.profiles import retrieval_profile
    from research_assistant.retrieval.reranker import model_identity, verified_manifest
    development, _, _ = load_dataset(Path('data/evaluation/development/expansion-v1'))
    if not review_status(Path('data/evaluation/development/expansion-v1'))['ready']:
        raise ValueError('Public development gold is not currently human-ready')
    installed = next((item for item in ollama.Client(host=settings.ollama_base_url, timeout=15).list().models
                      if item.model == settings.generation_model), None)
    if installed is None:
        raise ValueError('Pinned local generator unavailable; no substitution')
    paths = runtime_assets()
    bound = source.current_dataset_commitments
    identity = code_identity()
    freeze = MatchedFreeze(created_at=datetime.now(timezone.utc), scope=scope, scope_path=scope_path.as_posix(),
        scope_file_sha256=file_sha(public_asset(scope_path)), source_attestation_path=source_attestation_path.as_posix(),
        source_attestation_sha256=source_attestation_sha256, approved_inputs=source.approved_external_snapshot,
        questions_sha256=bound.questions_file_sha256, annotations_sha256=bound.annotations_file_sha256,
        approval_ledger_sha256=bound.human_approval_ledger_sha256, development_dataset_sha256=fingerprint(development),
        private_root=private_root, snapshot_directory=snapshot_directory.as_posix(), recovery_report=recovery_report.as_posix(),
        recovery_report_sha256=file_sha(public_asset(recovery_report)), code_revision=identity['code_revision'],
        source_tree_sha256=identity['source_tree_sha256'], files={p.as_posix(): file_sha(public_asset(p)) for p in sorted(paths)},
        runtime_versions=runtime_versions(), encoder_revision=encoder_artifact('all-MiniLM-L6-v2')[1],
        reranker_identity=model_identity(verified_manifest()), profile_policy_hashes={arm: retrieval_profile(profile, selector).policy_sha256
            for arm, profile, selector in [('A0','baseline','reference'),('A1','retrieval-v2','reference'),('A2','retrieval-v2','cross_encoder')]},
        generator_model=settings.generation_model, generator_digest=installed.digest, ollama_base_url=settings.ollama_base_url,
        request_timeout_seconds=settings.request_timeout_seconds, graph_query_timeout_seconds=settings.graph_query_timeout_seconds)
    # Validate before committing the immutable proposal, including actual proof/source/model bytes.
    verify_freeze(freeze)
    write_immutable(public_asset(output), freeze.model_dump_json(indent=2)+'\n')
    return {'status':'matched_freeze_proposal_authorization_pending', 'freeze_path':str(output),
            'freeze_sha256':file_sha(public_asset(output)), 'maximum_generation_requests':288,
            'maximum_retrieval_requests':288, 'final_execution_authorized':False}
