"""Bounded public-only engineering probes; no held-out data or final-run authority."""

from contextlib import contextmanager
from datetime import datetime, timezone
import json
from pathlib import Path
from threading import Event, Thread
from typing import Literal

import ollama
from pydantic import Field, model_validator

from research_assistant.contracts import Contract, ExperimentScope, QueryRequest, fingerprint
from research_assistant.evaluation.freeze import file_sha
from research_assistant.evaluation.matched_assets import public_asset
from research_assistant.evaluation.matched_scope import FrozenEvaluationScope, validate_frozen_scope
from research_assistant.evaluation.proposals import matched_conditions
from research_assistant.evaluation.runner import _event
from research_assistant.graph.recovery import attest_target
from research_assistant.llm import create_client
from research_assistant.pipeline import code_identity, write_immutable
from research_assistant.product import WORKFLOWS
from research_assistant.retrieval.profiles import validate_scope
from research_assistant.retrieval.service import retrieve_guarded
from research_assistant.settings import Settings
from research_assistant.smoke import ProbeAnswer, check_resources

HEX = r'^[a-f0-9]{64}$'
LEDGER = Path('data/accounting/m5-5-4-readiness.jsonl')


class ReadinessPlan(Contract):
    """Fixed local preparation allowance, independent of all final-study receipts."""

    format: Literal['m5-5-4-local-readiness-plan-v1'] = 'm5-5-4-local-readiness-plan-v1'
    created_at: datetime
    user_direction: Literal['ok, doo next step'] = 'ok, doo next step'
    task_id: Literal['M5.5.4'] = 'M5.5.4'
    project: str = Field(pattern=r'^dbu-m4-recovery-m5eval-[a-f0-9]{12}$')
    bolt_port: int = Field(ge=1024, le=65535)
    http_port: int = Field(ge=1024, le=65535)
    output_directory: str
    source_scope_path: Literal['data/scopes/retrieval-v2.json'] = 'data/scopes/retrieval-v2.json'
    source_scope_file_sha256: str = Field(pattern=HEX)
    source_graph_sha256: str = Field(pattern=HEX)
    source_tree_sha256: str = Field(pattern=HEX)
    generator_model: str = Field(min_length=1)
    generator_digest: str = Field(pattern=HEX)
    ollama_base_url: str
    image_id: str = Field(pattern=r'^sha256:[a-f0-9]{64}$')
    generation_requests: Literal[2] = 2
    logical_retrieval_requests: Literal[24] = 24
    native_fixture_cases: Literal[2] = 2
    extra_capacity_reranker_pairs: Literal[4] = 4
    context_tokens: Literal[4096] = 4096
    output_tokens: Literal[512] = 512
    request_timeout_seconds: float = Field(default=180, gt=0, le=180)
    graph_query_timeout_seconds: float = Field(default=30, ge=0.001, le=30)
    concurrency: Literal[1] = 1
    retries: Literal[0] = 0
    paid_budget_usd: Literal[0] = 0
    private_inputs_permitted: Literal[False] = False
    final_execution_authorized: Literal[False] = False

    @model_validator(mode='after')
    def exact_local_scope(self):
        """Reject ambiguous ports, placeholders and nonlocal provider metadata."""
        if self.created_at.tzinfo is None or self.bolt_port == self.http_port:
            raise ValueError('Readiness needs distinct ports and a timezone-aware plan')
        if {self.bolt_port, self.http_port} & {7687, 7474, 9765, 9475, 60395, 60396, 8502}:
            raise ValueError('Readiness must use fresh ports outside retained services')
        if any(value == '0'*64 for value in (self.source_scope_file_sha256, self.source_graph_sha256,
                                             self.source_tree_sha256, self.generator_digest)):
            raise ValueError('Actual readiness commitments are required')
        Settings(ollama_base_url=self.ollama_base_url)
        return self


def save(path: Path, value: object) -> None:
    """Write a new allowlisted public engineering artifact; never overwrite a receipt."""
    write_immutable(public_asset(path), json.dumps(value, ensure_ascii=False, indent=2)+'\n')


def load_plan(path: Path, settings: Settings) -> ReadinessPlan:
    """Validate public plan/current executable/configuration before any live request."""
    plan = ReadinessPlan.model_validate_json(public_asset(path).read_bytes())
    scope = ExperimentScope.model_validate_json(Path(plan.source_scope_path).read_bytes())
    if (file_sha(Path(plan.source_scope_path)) != plan.source_scope_file_sha256
            or code_identity()['source_tree_sha256'] != plan.source_tree_sha256
            or settings.neo4j_uri != scope.target_uri or plan.image_id != scope.image_id
            or settings.generation_provider != 'ollama' or settings.generation_model != plan.generator_model
            or settings.ollama_base_url != plan.ollama_base_url
            or settings.request_timeout_seconds != plan.request_timeout_seconds
            or settings.graph_query_timeout_seconds != plan.graph_query_timeout_seconds
            or settings.max_retries != 0 or settings.max_concurrency != 1):
        raise ValueError('Readiness executable, source or local provider controls changed')
    output=public_asset(plan.output_directory)
    allowed=public_asset('runs/retrieval-v2/m5-5')
    if output==allowed or not output.is_relative_to(allowed):
        raise ValueError('Readiness output must be a new M5.5 artifact directory')
    physical=attest_target(settings, {'source_uri':'bolt://127.0.0.1:7687'}, scope.target_id)
    if (physical['container_id']!=scope.container_id or physical['image_id']!=scope.image_id
            or physical['volumes']!=sorted(scope.volumes)):
        raise ValueError('Working physical scope changed before readiness')
    model = next((m for m in ollama.Client(host=plan.ollama_base_url, timeout=15).list().models
                  if m.model == plan.generator_model), None)
    if model is None or model.digest != plan.generator_digest:
        raise ValueError('Readiness generator identity changed; no substitution/pull')
    return plan


def claim(plan: ReadinessPlan, path: Path) -> None:
    """A single durable task claim: new plan/output names cannot reset this allowance."""
    plan=ReadinessPlan.model_validate(plan.model_dump(mode='json'))
    _event(LEDGER, {'event':'start', 'task_id':plan.task_id, 'plan_sha256':file_sha(path),
                    'output_directory':plan.output_directory}, first=True)


def reserve(plan: ReadinessPlan, kind: str, label: str, *, ledger: Path = LEDGER) -> None:
    """Persist every attempt before work, including failed or unknown requests."""
    plan=ReadinessPlan.model_validate(plan.model_dump(mode='json'))
    limits = {'generation':plan.generation_requests, 'retrieval':plan.logical_retrieval_requests}
    if kind not in limits:
        raise ValueError('Unknown readiness reservation')
    rows = [json.loads(line) for line in ledger.read_text(encoding='utf-8').splitlines()]
    if (not rows or rows[0]['event']!='start' or rows[0]['output_directory']!=plan.output_directory
            or any(row.get('event')=='reservation' and row.get('kind')==kind and row.get('label')==label for row in rows)
            or sum(row.get('event')=='reservation' and row.get('kind')==kind for row in rows) >= limits[kind]):
        raise ValueError('Readiness allowance consumed, duplicated or belongs to another task')
    _event(ledger, {'event':'reservation', 'kind':kind, 'label':label,
                    'maximum_output_tokens':plan.output_tokens if kind=='generation' else 0})


@contextmanager
def resource_samples():
    """Sample host/GPU allocation while a bounded probe runs; samples are not exact peaks."""
    stop, rows = Event(), []
    def sample():
        while not stop.is_set():
            try:
                rows.append({'at':datetime.now(timezone.utc).isoformat(), **check_resources()})
            except Exception as exc:
                rows.append({'sampling_error':type(exc).__name__})
            if stop.wait(1):
                break
    worker = Thread(target=sample, daemon=True)
    worker.start()
    try:
        yield rows
    finally:
        stop.set()
        worker.join(timeout=20)


def capacity(plan: ReadinessPlan, settings: Settings, encoder, scorer) -> dict:
    """Two synthetic adapter requests with Neo4j/CPU models resident; never scientific answers."""
    client = create_client(settings, context_tokens=plan.context_tokens, output_tokens=plan.output_tokens)
    client.prompt_version = 'm5-5-4-synthetic-readiness-v1'
    result = {'complete':False, 'attempts':[], 'resources_before':check_resources()}
    prompts = [
        [{'role':'user', 'content':'This is a synthetic software readiness test. Reply with the single word READY.'}],
        [{'role':'system', 'content':'Synthetic software test. Ignore the filler; return JSON with status="ok" and value=2.'},
         {'role':'user', 'content':('Synthetic neutral capacity filler. '*330)+'\nReturn status="ok" and value=2.'}],
    ]
    try:
        for index, messages in enumerate(prompts, 1):
            reserve(plan, 'generation', 'adapter-'+str(index))
            row = {'probe':index, 'status':'failed', 'reservation_retained':True}
            result['attempts'].append(row)
            with resource_samples() as samples:
                if index == 1:
                    response = client.generate_text(messages)
                    if response.text.strip().upper()!='READY':
                        raise ValueError('Text readiness marker was incorrect')
                else:
                    parsed, response = client.generate_structured(ProbeAnswer, messages)
                    if parsed.status!='ok' or parsed.value!=2:
                        raise ValueError('Structured readiness values were incorrect')
                if response.digest != plan.generator_digest:
                    raise ValueError('Readiness response model digest changed')
                vectors = encoder.encode(['Synthetic simultaneous resident CPU encoder check.'])
                scores, lengths = scorer.score_pairs([
                    ('synthetic software readiness', 'Synthetic software readiness check.'),
                    ('synthetic software readiness', 'Unrelated synthetic filler.')])
                resident = ollama.Client(host=plan.ollama_base_url, timeout=15).ps().models
                active = next((m for m in resident if m.digest==plan.generator_digest), None)
                if active is None or active.context_length != plan.context_tokens:
                    raise ValueError('Expected local Qwen context is not resident')
                row.update(status='passed', response=response.model_dump(mode='json'),
                    resident_model=active.model_dump(mode='json'), encoder_dimension=len(vectors[0]),
                    reranker_scores=scores, reranker_pair_lengths=lengths)
            row['resource_samples'] = samples
        result['complete'] = True
    except Exception as exc:
        if result['attempts']:
            result['attempts'][-1]['resource_samples'] = locals().get('samples', [])
        result.update(error_type=type(exc).__name__, error=settings.redact(str(exc)),
            last_provider_result=client.last_result.model_dump(mode='json') if client.last_result else None)
    result['resources_after'] = check_resources()
    return result


def retrieval_probes(plan: ReadinessPlan, settings: Settings, encoder, *, frozen: FrozenEvaluationScope | None = None,
                     artifact_directory: Path | None = None, ledger: Path = LEDGER) -> list[dict]:
    """One fixed public workflow question across twelve policies, without gold/scoring/generation."""
    stage = 'restored' if frozen is not None else 'working'
    # Recovery validates this absolute output before changing into copied inputs,
    # as the legacy recovery workflow does. Only fixed policy filenames follow.
    output = artifact_directory if artifact_directory is not None else public_asset(plan.output_directory)
    source = ExperimentScope.model_validate_json(Path(plan.source_scope_path).read_bytes()) if frozen is None else None
    corpus = frozen.corpus_id if frozen else source.corpus_id
    rows = []
    for policy in matched_conditions():
        request = QueryRequest(question=WORKFLOWS['discovery'], corpus_id=corpus, mode=policy.mode,
            profile_id=policy.profile_id, selector_id=policy.selector_id,
            scope_file=plan.source_scope_path if policy.profile_id=='retrieval-v2' else None)
        reserve(plan, 'retrieval', stage+'-'+policy.condition_id, ledger=ledger)
        try:
            def guard(req, *args):
                if frozen is not None:
                    return validate_frozen_scope(frozen, req, *args)
                physical_request = req.model_copy(update={'profile_id':'retrieval-v2', 'scope_file':plan.source_scope_path})
                return validate_scope(physical_request, *args)
            snapshot, retrieved = retrieve_guarded(request, settings, Path('data/reviews/expansion-v1'), .30, encoder, guard)
            if not retrieved.evidence or len(retrieved.evidence)>6 or retrieved.estimated_tokens>1800:
                raise ValueError('Readiness evidence budget/availability failed')
            artifact = {
                'task_id':'M5.5.4', 'engineering_probe_not_quality_evaluation':True,
                'request':request.model_dump(mode='json'), 'snapshot':snapshot,
                'retrieval':retrieved.model_dump(mode='json')}
            write_immutable(output/stage/(policy.condition_id+'.json'), json.dumps(artifact,indent=2)+'\n')
            rows.append({'condition_id':policy.condition_id, 'status':'passed',
                'context_sha256':retrieved.context_sha256, 'selected_ids':[i.id for i in retrieved.evidence],
                'effective_mode':retrieved.effective_mode, 'fallback_reason':retrieved.fallback_reason})
        except Exception as exc:
            rows.append({'condition_id':policy.condition_id, 'status':'failed', 'error_type':type(exc).__name__,
                         'error':settings.redact(str(exc)), 'reservation_retained':True})
    return rows
