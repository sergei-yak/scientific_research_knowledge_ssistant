"""Public freeze commitments and one-run authorization; never open private evaluation inputs."""

from __future__ import annotations

import hashlib
import importlib.metadata
import json
import platform
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

import ollama
from pydantic import Field, model_validator

from research_assistant.contracts import Contract, fingerprint
from research_assistant.evaluation.development import load_dataset, review_status
from research_assistant.evaluation.readiness import EvaluatorAttestation, check_attestation
from research_assistant.graph.recovery import verify_snapshot
from research_assistant.pipeline import code_identity, write_immutable
from research_assistant.settings import Settings
from research_assistant.smoke import encoder_artifact

HEX = r'^[a-f0-9]{64}$'


class RunPlan(Contract):
    """Conservative upper bounds include failed attempts; no automatic retries or paid access."""

    question_count: Literal[24] = 24
    conditions: list[str] = ['vector', 'hybrid', 'hybrid_facts', 'graph']
    generation_request_limit: Literal[96] = 96
    retrieval_request_limit: Literal[144] = 144
    output_tokens: Literal[512] = 512
    context_tokens: Literal[4096] = 4096
    concurrency: Literal[1] = 1
    retries: Literal[0] = 0
    paid_budget_usd: Literal[0] = 0
    minimum_similarity: Literal[0.3] = 0.3
    order_seed: int = Field(default=4431, ge=0, le=2**32-1)
    order: Literal['seeded_questions_rotating_conditions'] = 'seeded_questions_rotating_conditions'
    encoder_comparison: Literal['separate_vector_only_alternating_encoders'] = 'separate_vector_only_alternating_encoders'

    @model_validator(mode='after')
    def fixed_conditions(self) -> RunPlan:
        """The four MiniLM conditions are controlled; MPNet never generates answers."""
        if self.conditions != ['vector', 'hybrid', 'hybrid_facts', 'graph']:
            raise ValueError('The frozen condition list changed')
        return self


class FreezeManifest(Contract):
    """Public commitments only; it has no private questions, answers or source spans."""

    format: Literal['research-freeze-v1'] = 'research-freeze-v1'
    created_at: datetime
    corpus_id: str = Field(pattern=HEX)
    review_head: str = Field(pattern=HEX)
    development_dataset_sha256: str = Field(pattern=HEX)
    readiness_path: str
    readiness_file_sha256: str = Field(pattern=HEX)
    heldout_questions_sha256: str = Field(pattern=HEX)
    heldout_annotations_sha256: str = Field(pattern=HEX)
    private_root: str
    snapshot_directory: str
    snapshot_manifest_sha256: str = Field(pattern=HEX)
    graph_sha256: str = Field(pattern=HEX)
    recovery_report: str
    recovery_report_sha256: str = Field(pattern=HEX)
    target_uri: str
    target_project: str = Field(pattern=r'^dbu-m4-recovery-[a-z0-9-]+$')
    docker_image_id: str
    code_revision: str
    source_tree_sha256: str = Field(pattern=HEX)
    files: dict[str, str]
    encoder_revisions: dict[str, str]
    runtime_versions: dict[str, str]
    generator_provider: Literal['ollama'] = 'ollama'
    generator_model: str
    generator_digest: str = Field(pattern=HEX)
    ollama_base_url: str
    request_timeout_seconds: float = Field(gt=0, le=600)
    graph_query_timeout_seconds: float = Field(ge=0.001, le=30)
    plan: RunPlan = Field(default_factory=RunPlan)
    prior_private_exposure: Literal[False] = False
    amends_freeze_sha256: str | None = None


class FinalRunAuthorization(Contract):
    """An explicit human receipt binds exactly one frozen study and all numerical limits."""

    format: Literal['final-evaluation-approval-v1'] = 'final-evaluation-approval-v1'
    scope: Literal['one_frozen_evaluation'] = 'one_frozen_evaluation'
    origin: Literal['human_chat'] = 'human_chat'
    authorization_id: str = Field(pattern=r'^[a-f0-9]{32}$')
    freeze_file_sha256: str = Field(pattern=HEX)
    reviewer: str = Field(min_length=1)
    received_at: datetime
    verbatim_response: str = Field(min_length=1)
    approved: Literal[True]
    generation_request_limit: Literal[96] = 96
    output_tokens: Literal[512] = 512
    context_tokens: Literal[4096] = 4096
    concurrency: Literal[1] = 1
    retries: Literal[0] = 0
    paid_budget_usd: Literal[0] = 0

    @model_validator(mode='after')
    def explicit_human(self) -> FinalRunAuthorization:
        """Reject missing human provenance/time; a credential or readiness receipt is insufficient."""
        if self.received_at.tzinfo is None or not self.reviewer.strip() or not self.verbatim_response.strip():
            raise ValueError('Explicit timezone-aware human final-run authorization is required')
        return self


def file_sha(path: Path) -> str:
    """Hash exact bytes; callers establish the public/private I/O boundary first."""
    digest = hashlib.sha256()
    with path.open('rb') as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def runtime_versions() -> dict[str, str]:
    """Pin the interpreter and inference/scoring/storage libraries without network access."""
    return {'python': platform.python_version(), **{name: importlib.metadata.version(name) for name in
        ('torch', 'numpy', 'sentence-transformers', 'transformers', 'neo4j', 'ollama', 'pydantic', 'tiktoken', 'PyMuPDF', 'openai')}}


def public_asset(value: str | Path) -> Path:
    """Allow only named repository assets; reject external paths before reading their content."""
    path = Path(value)
    root = Path.cwd().resolve()
    if path.is_absolute():
        try:
            path = path.relative_to(root)
        except ValueError:
            raise ValueError('Public freeze input must be inside the repository') from None
    if '..' in path.parts or path.name == '.env' or (path.name.startswith('.env.') and path.name != '.env.example'):
        raise ValueError('Unsafe public freeze asset')
    allowed = ('src/research_assistant/', 'scripts/', 'tests/', 'manifests/', 'runs/m4-1/', 'runs/m4-2/', 'runs/m4-3/', '.cache/models/', '.cache/tiktoken/')
    if path.as_posix() not in {'uv.lock', 'pyproject.toml', 'compose.yaml', '.env.example'} and not path.as_posix().startswith(allowed):
        raise ValueError('Public freeze asset is outside the explicit allowlist')
    resolved = path.resolve()
    if not resolved.is_relative_to(root) or any((root / Path(*path.parts[:i])).is_symlink() for i in range(1, len(path.parts)+1)):
        raise ValueError('Public freeze asset escapes the repository')
    return resolved


def load_freeze(path: Path, *, verify_files: bool = True) -> FreezeManifest:
    """Validate public commitments/code/model assets; this never looks up private input paths."""
    freeze = FreezeManifest.model_validate_json(public_asset(path).read_bytes())
    if freeze.created_at.tzinfo is None:
        raise ValueError('Freeze timestamp requires timezone')
    if verify_files:
        if freeze.runtime_versions != runtime_versions():
            raise ValueError('Frozen interpreter/library versions changed')
        if code_identity()['source_tree_sha256'] != freeze.source_tree_sha256:
            raise ValueError('Frozen source tree changed')
        for name, expected in freeze.files.items():
            if not re.fullmatch(HEX, expected) or file_sha(public_asset(name)) != expected:
                raise ValueError('Frozen executable/model asset changed')
        if file_sha(public_asset(freeze.readiness_path)) != freeze.readiness_file_sha256:
            raise ValueError('Public readiness commitment changed')
        snapshot_path = public_asset(freeze.snapshot_directory)
        snapshot, _ = verify_snapshot(snapshot_path)
        if (file_sha(snapshot_path / 'manifest.json') != freeze.snapshot_manifest_sha256
                or snapshot['graph_sha256'] != freeze.graph_sha256):
            raise ValueError('Frozen graph/snapshot commitment changed')
        if file_sha(public_asset(freeze.recovery_report)) != freeze.recovery_report_sha256:
            raise ValueError('Recovery proof changed')
    return freeze


def authorize(path: Path, freeze_path: Path) -> FinalRunAuthorization:
    """Fail before private path access unless the exact freeze has a complete human receipt."""
    raw = json.loads(public_asset(path).read_text(encoding='utf-8'))
    digest = raw.pop('receipt_sha256', None)
    if digest != fingerprint(raw):
        raise ValueError('Final-run approval receipt hash changed')
    approval = FinalRunAuthorization.model_validate(raw)
    if approval.freeze_file_sha256 != file_sha(public_asset(freeze_path)):
        raise ValueError('Authorization belongs to a different freeze')
    return approval


def prepare_freeze(snapshot_directory: Path, recovery_report: Path, settings: Settings,
                   private_root: str, output: Path) -> dict:
    """Pin public state after recovery proof; produce a proposal without granting execution."""
    public_asset(output)
    readiness_path = Path('runs/m4-1/evaluation-readiness-manifest.json')
    readiness = json.loads(public_asset(readiness_path).read_text(encoding='utf-8'))
    manifest, _, _ = load_dataset(Path('data/evaluation/development/expansion-v1'))
    gold = review_status(Path('data/evaluation/development/expansion-v1'))
    attestation = EvaluatorAttestation.model_validate_json(public_asset(readiness['attestation']['path']).read_bytes())
    checked = check_attestation(attestation, manifest['corpus_id'], readiness['review_head'], gold['dataset_sha256'])
    if not gold['ready'] or checked['exposure_requires_resolution_before_freeze']:
        raise ValueError('Human readiness/exposure is unresolved')
    snapshot, _ = verify_snapshot(public_asset(snapshot_directory))
    proof = json.loads(public_asset(recovery_report).read_text(encoding='utf-8'))
    if (not proof['complete'] or not proof['target_read_only_proved']
            or proof['graph_sha256'] != snapshot['graph_sha256']
            or proof['snapshot_manifest_sha256'] != file_sha(public_asset(snapshot_directory) / 'manifest.json')
            or snapshot['review_head'] != readiness['review_head']
            or (snapshot.get('freeze_projection') or {}).get('corpus_id') != readiness['corpus_id']):
        raise ValueError('Expanded frozen recovery proof does not match current readiness')
    if settings.generation_provider != 'ollama':
        raise ValueError('This zero-paid-budget proposal requires the explicitly chosen local provider')
    client = ollama.Client(host=settings.ollama_base_url, timeout=15)
    installed = next((model for model in client.list().models if model.model == settings.generation_model), None)
    if installed is None:
        raise ValueError('Selected local generator is unavailable; no substitution')
    paths = {Path('uv.lock'), Path('pyproject.toml'), Path('compose.yaml'), Path('.env.example')}
    for directory in ('src/research_assistant', 'scripts', 'tests'):
        paths.update(Path(directory).rglob('*.py'))
    revisions = {}
    for name in ('all-MiniLM-L6-v2', 'all-mpnet-base-v2'):
        model_path, revision = encoder_artifact(name)
        revisions[name] = revision
        paths.add(model_path.parent / 'manifest.json')
        paths.update(path for path in model_path.rglob('*') if path.is_file() and path.suffix in {'.json', '.txt', '.safetensors'})
    paths.update(path for path in Path('.cache/tiktoken').iterdir() if path.is_file())
    identity = code_identity()
    if snapshot['source_tree_sha256'] != identity['source_tree_sha256']:
        raise ValueError('Executable code changed after the recovery snapshot')
    freeze = FreezeManifest(created_at=datetime.now(timezone.utc), corpus_id=readiness['corpus_id'],
        review_head=readiness['review_head'], development_dataset_sha256=gold['dataset_sha256'],
        readiness_path=readiness_path.as_posix(), readiness_file_sha256=file_sha(public_asset(readiness_path)),
        heldout_questions_sha256=attestation.heldout_questions_sha256,
        heldout_annotations_sha256=attestation.heldout_annotations_sha256, private_root=private_root,
        snapshot_directory=snapshot_directory.as_posix(), snapshot_manifest_sha256=file_sha(public_asset(snapshot_directory) / 'manifest.json'),
        graph_sha256=snapshot['graph_sha256'], recovery_report=recovery_report.as_posix(),
        recovery_report_sha256=file_sha(public_asset(recovery_report)), target_uri=proof['target_uri'],
        target_project=proof['project'], docker_image_id=proof['image_id'],
        code_revision=identity['code_revision'], source_tree_sha256=identity['source_tree_sha256'],
        files={path.as_posix(): file_sha(public_asset(path)) for path in sorted(paths)},
        encoder_revisions=revisions, runtime_versions=runtime_versions(), generator_model=settings.generation_model,
        generator_digest=installed.digest, ollama_base_url=settings.ollama_base_url,
        request_timeout_seconds=settings.request_timeout_seconds,
        graph_query_timeout_seconds=settings.graph_query_timeout_seconds)
    write_immutable(output, freeze.model_dump_json(indent=2) + '\n')
    return {'task_id': 'M4.2.4', 'status': 'freeze_proposal_ready_authorization_pending',
            'freeze_path': str(output), 'freeze_file_sha256': file_sha(output),
            'plan': freeze.plan.model_dump(), 'final_evaluation_authorized': False}
