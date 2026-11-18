"""Separate exact-authorized matched evaluator; normal application V2 generation stays disabled."""

import argparse
from collections import Counter
import json
import os
from pathlib import Path
import statistics
import stat
import subprocess
import time
import uuid

import ollama

from research_assistant.contracts import Contract, EvaluationQuestion, QueryRequest, RunArtifact, fingerprint
from research_assistant.embeddings import Encoder
from research_assistant.evaluation.blinding import _build_bundle, _seal_scores, _reveal_scores
from research_assistant.evaluation.development import load_dataset
from research_assistant.evaluation.freeze import file_sha
from research_assistant.evaluation.matched_assets import public_asset
from research_assistant.evaluation.matched_freeze import authorize, load_freeze
from research_assistant.evaluation.matched_permits import _register_study, _issue_slot, validate_slot
from research_assistant.evaluation.matched_scope import validate_frozen_scope, inspect_container
from research_assistant.evaluation.proposals import matched_conditions
from research_assistant.evaluation.runner import QuestionPrompt, RunnerFailure, _event, _json
from research_assistant.evaluation.scheduling import QuestionKey, build_proposed_schedule
from research_assistant.evaluation.scoring import score_evidence
from research_assistant.graph.recovery import attest_target, capture, require_read_only
from research_assistant.ingestion.sources import load_corpus_chunks
from research_assistant.pipeline import QueryExecutionError, _finish_query, code_identity
from research_assistant.retrieval.service import retrieve_guarded
from research_assistant.settings import Settings, configure_caches

PRIMARY = ('A2-graph', 'A2-hybrid_facts')
COMPARISONS = [PRIMARY, ('A1-graph', 'A1-hybrid_facts')]
COMPARISONS += [('A2-'+mode, 'A1-'+mode) for mode in ('vector','hybrid','hybrid_facts','graph')]
COMPARISONS += [('A1-'+mode, 'A0-'+mode) for mode in ('vector','hybrid','hybrid_facts','graph')]


class MatchedScoringInput(Contract):
    """Full condition identity remains external until real human score sealing."""

    question_id: str
    condition: str
    run: RunArtifact


def _context(freeze_path: Path, authorization_path: Path):
    """Numerical human receipt and full public freeze verification precede private path resolution."""
    authorization = authorize(authorization_path, freeze_path)
    freeze = load_freeze(freeze_path)
    workspace = Path.cwd().resolve()
    private = _private_asset(Path(freeze.private_root), Path(freeze.private_root))
    inputs = _private_asset(Path(freeze.approved_inputs.root), private)
    if private == workspace or private.is_relative_to(workspace) or inputs == private or not inputs.is_relative_to(private):
        raise ValueError('Matched evaluator storage/input snapshot must remain external')
    return freeze, authorization, private, workspace


def _private_asset(value: Path, root: Path) -> Path:
    """Authorized runner only: reject escapes/reparse points before opening evaluator contents."""
    path, root = value.absolute(), root.absolute()
    if '..' in path.parts or not path.is_relative_to(root):
        raise ValueError('Evaluator asset escapes its exact authorized root')
    for component in [*reversed(path.parents),path]:
        try:info=component.lstat()
        except FileNotFoundError:continue
        if stat.S_ISLNK(info.st_mode) or getattr(info,'st_file_attributes',0)&getattr(stat,'FILE_ATTRIBUTE_REPARSE_POINT',0x400):
            raise ValueError('Evaluator assets may not use symlinks/junctions')
    resolved=path.resolve()
    if not resolved.is_relative_to(root.resolve()):
        raise ValueError('Evaluator asset resolved outside its root')
    return resolved


def _prompts(freeze) -> list[QuestionPrompt]:
    """Parse stripped prompts after authorization; preflight gold/ledger bytes without parsing gold."""
    private=Path(freeze.private_root)
    if (file_sha(_private_asset(Path(freeze.approved_inputs.annotations),private)) != freeze.annotations_sha256
            or file_sha(_private_asset(Path(freeze.approved_inputs.human_approval_ledger),private)) != freeze.approval_ledger_sha256
            or file_sha(_private_asset(Path(freeze.approved_inputs.questions),private)) != freeze.questions_sha256):
        raise ValueError('Approved private input bytes changed')
    rows = []
    dev = public_asset(freeze.snapshot_directory) / 'files/data/evaluation/development/expansion-v1/questions.jsonl'
    for path, split, count in ((dev, 'development', 8), (_private_asset(Path(freeze.approved_inputs.questions),private), 'held_out', 16)):
        group = [QuestionPrompt.model_validate_json(line) for line in path.read_text(encoding='utf-8').splitlines()]
        if len(group) != count or any(row.split != split for row in group) or Counter(row.category for row in group) != {
                key: count//4 for key in ('direct','cross_paper','multi_hop','unanswerable')}:
            raise ValueError('Matched question partition/strata changed')
        rows.extend(group)
    if len({p.question_id for p in rows}) != 24 or len({p.question.strip().casefold() for p in rows}) != 24:
        raise ValueError('Matched question identities/texts must be unique')
    return rows


def _target(freeze, settings: Settings) -> Settings:
    """Verify the new physical read-only target and exact generator before creating any permit."""
    if (settings.generation_provider != 'ollama' or settings.generation_model != freeze.generator_model
            or settings.ollama_base_url != freeze.ollama_base_url or settings.max_retries != 0
            or settings.max_concurrency != 1 or settings.request_timeout_seconds != freeze.request_timeout_seconds
            or settings.graph_query_timeout_seconds != freeze.graph_query_timeout_seconds):
        raise ValueError('Matched runtime/provider limits changed')
    model = next((item for item in ollama.Client(host=settings.ollama_base_url, timeout=15).list().models
                  if item.model == freeze.generator_model), None)
    if model is None or model.digest != freeze.generator_digest:
        raise ValueError('Frozen generator unavailable/changed; no substitution')
    target = settings.model_copy(update={'neo4j_uri':freeze.scope.target_uri})
    physical = attest_target(target, {'source_uri':freeze.scope.source_uri}, freeze.scope.target_project)
    if (physical['container_id'] != freeze.scope.container_id or physical['image_id'] != freeze.scope.image_id
            or physical['volumes'] != sorted(freeze.scope.volumes)
            or fingerprint(capture(target)) != freeze.scope.graph_sha256):
        raise ValueError('Matched target graph/container identity changed')
    require_read_only(target)
    return target


def run_matched_query(request, settings, freeze, permit, encoder):
    """Only a reserved opaque permit reaches common retrieval/generation; no global V2 switch."""
    bound = validate_slot(permit, request, settings, freeze.plan.context_tokens, freeze.plan.output_tokens, freeze.minimum_similarity)
    if bound != freeze:
        raise ValueError('Matched query freeze differs from the issued slot permit')
    def guard(*args):
        return validate_frozen_scope(freeze.scope, *args)
    snapshot, retrieval = retrieve_guarded(request, settings, Path(freeze.scope.review_directory),
                                          freeze.minimum_similarity, encoder, guard)
    return _finish_query(request, settings, snapshot, retrieval, code_identity(), freeze.plan.context_tokens,
                         freeze.plan.output_tokens, freeze.minimum_similarity, generate=True,
                         workflow='ask', evaluation_permit=permit)


def _matrix(freeze, prompts, settings, encoder, directory, ledger, grant):
    """Persist a reservation before every one of the 288 policy/question slots, zero retries."""
    keys = [QuestionKey(question_id=p.question_id, split=p.split, category=p.category) for p in prompts]
    slots = build_proposed_schedule(keys, freeze.plan)
    _json(directory/'schedule.json', [slot.model_dump(mode='json') for slot in slots])
    by_id = {p.question_id:p for p in prompts}
    samples = []
    for slot in slots:
        prompt, policy = by_id[slot.question.question_id], slot.condition
        request = QueryRequest(question=prompt.question, corpus_id=freeze.scope.corpus_id, mode=policy.mode,
            profile_id=policy.profile_id, selector_id=policy.selector_id,
            scope_file=freeze.scope_path if policy.profile_id=='retrieval-v2' else None)
        _event(ledger, {'event':'reservation', 'slot':slot.slot_index, 'slot_identity':slot.slot_identity,
            'maximum_generation_requests':1, 'maximum_retrieval_requests':1, 'maximum_output_tokens':512})
        permit = _issue_slot(grant, slot, request, reservation_persisted=True)
        path = directory/'runs'/fingerprint(prompt.question_id)/(policy.condition_id+'.json')
        try:
            run = run_matched_query(request, settings, freeze, permit, encoder)
        except QueryExecutionError as exc:
            _json(path, exc.artifact.model_dump(mode='json'))
            _event(ledger, {'event':'failed_or_unknown', 'slot':slot.slot_index, 'reservation_retained':True})
            raise
        except Exception:
            _event(ledger, {'event':'failed_or_unknown', 'slot':slot.slot_index, 'reservation_retained':True})
            raise
        run.configuration.update(condition_id=policy.condition_id, arm_id=policy.arm_id,
            freeze_graph_sha256=freeze.scope.graph_sha256, frozen_code_revision=freeze.code_revision,
            slot_index=slot.slot_index, slot_identity=slot.slot_identity,
            query_cache_state='no_explicit_query_warmup; resident_models; per-request selector cache')
        _json(path, run.model_dump(mode='json'))
        if run.generation and (run.generation.digest != freeze.generator_digest or
                               run.generation.provider != 'ollama' or run.generation.model != freeze.generator_model):
            raise ValueError('Matched response generator identity changed')
        _event(ledger, {'event':'completed', 'slot':slot.slot_index, 'provider_response':run.generation is not None})
        samples.append(MatchedScoringInput(question_id=prompt.question_id, condition=policy.condition_id, run=run))
    return samples


def _gold(freeze, prompts):
    """Only after the matrix finishes, parse frozen gold; never pass it to retrieval or a provider."""
    path = _private_asset(Path(freeze.approved_inputs.annotations),Path(freeze.private_root))
    if file_sha(path) != freeze.annotations_sha256:
        raise ValueError('Matched gold changed during generation')
    _, development, _ = load_dataset(Path('data/evaluation/development/expansion-v1'))
    rows = [entry.gold for entry in development] + [EvaluationQuestion.model_validate_json(line)
            for line in path.read_text(encoding='utf-8').splitlines()]
    by_id = {q.question_id:q for q in rows}
    if len(rows) != len(by_id) or set(by_id) != {p.question_id for p in prompts}:
        raise ValueError('Matched gold is not the complete frozen question set')
    for p in prompts:
        q = by_id[p.question_id]
        if (q.question, q.split, q.category) != (p.question, p.split, p.category):
            raise ValueError('Matched question/gold binding differs')
    return by_id


def _lifecycle(freeze, settings, directory, *, stop=False):
    """Only start/stop the exact retained scope container; no Compose recreation/restore/pull."""
    inspect_container(freeze.scope,running=stop)
    command=['docker','stop' if stop else 'start',freeze.scope.container_id]
    result=subprocess.run(command,capture_output=True,text=True,timeout=60,check=True)
    _json(directory/('target-stop.json' if stop else 'target-start.json'),
          {'command':command[:2],'container_id':freeze.scope.container_id,'completed':result.returncode==0})
    if not stop:
        from research_assistant.graph.repository import GraphRepository
        target=settings.model_copy(update={'neo4j_uri':freeze.scope.target_uri})
        for _ in range(60):
            repo=GraphRepository(target)
            try:
                repo.driver.verify_connectivity()
                return
            except Exception:
                time.sleep(1)
            finally:repo.close()
        raise ValueError('Matched read-only target did not become ready')


def execute(freeze_path: Path, authorization_path: Path, settings: Settings, *, start_target: bool=False) -> dict:
    """One durable study on an already verified running target; startup is an explicit separate operation."""
    freeze, approval, private, workspace = _context(freeze_path, authorization_path)
    freeze_path = public_asset(freeze_path)
    freeze_sha = file_sha(freeze_path)
    ledger = _private_asset(private/'matched-execution-accounting'/(freeze_sha+'.jsonl'),private)
    if ledger.exists():
        raise ValueError('Matched freeze already started; new receipts/directories never reset it')
    directory = _private_asset(private/'matched-executions'/approval.authorization_id/uuid.uuid4().hex,private)
    directory.mkdir(parents=True, exist_ok=False)
    # Claim before private input reads, target preparation or inference. A failed
    # attempt is retained and cannot be automatically resumed/retried.
    _event(ledger, {'event':'start', 'freeze_sha256':freeze_sha, 'authorization_id':approval.authorization_id,
                    'directory':str(directory)}, first=True)
    result = None
    try:
        if start_target:_lifecycle(freeze,settings,directory)
        target = _target(freeze, settings)
        prompts = _prompts(freeze)
        encoder = Encoder()
        if encoder.revision != freeze.encoder_revision:
            raise ValueError('Matched query encoder revision changed')
        for prompt in prompts:
            if len(encoder.mini_tokenizer.encode(prompt.question, add_special_tokens=True)) > 256:
                raise ValueError('Matched question would be truncated')
        grant = _register_study(freeze, freeze_sha, approval)
        os.chdir(public_asset(freeze.snapshot_directory)/'files')
        if code_identity()['source_tree_sha256'] != freeze.source_tree_sha256:
            raise ValueError('Copied matched executable/source changed')
        samples = _matrix(freeze, prompts, target, encoder, directory, ledger, grant)
        gold, chunks = _gold(freeze, prompts), load_corpus_chunks(freeze.scope.corpus_id)
        scores = [{'question_id':sample.question_id, 'condition':sample.condition,
                   'split':gold[sample.question_id].split, 'category':gold[sample.question_id].category,
                   'effective_mode':sample.run.retrieval.effective_mode,
                   'fallback_reason':sample.run.retrieval.fallback_reason,
                   'retrieval_ms':sample.run.retrieval.retrieval_ms,
                   'request_elapsed_ms':sample.run.retrieval.audit.get('request_elapsed_ms'),
                   'generation_ms':sample.run.generation.elapsed_ms if sample.run.generation else 0,
                   'provider_called':sample.run.generation is not None,
                   **score_evidence(gold[sample.question_id], sample.run.retrieval, chunks)} for sample in samples]
        _json(directory/'evidence-scores.json', scores)
        _build_bundle(samples, chunks, directory/'blind', development_only=False,
                      matched_policies={p.condition_id:p for p in matched_conditions()})
        os.chdir(workspace)
        load_freeze(freeze_path)
        if fingerprint(capture(target)) != freeze.scope.graph_sha256:
            raise ValueError('Matched read-only graph changed during execution')
        _event(ledger, {'event':'execution_complete', 'answer_runs':len(samples), 'extra_encoder_reads':0})
        _json(directory/'execution-complete.json', {'freeze_sha256':freeze_sha, 'answer_runs':288, 'extra_encoder_reads':0})
        result = {'status':'awaiting_blind_human_scores', 'answer_runs':288, 'extra_encoder_reads':0,
                'freeze_sha256':freeze_sha, 'scoring_packet_directory':str(directory/'blind/public'),
                'paid_calls':0, 'condition_results_revealed':False}
        return result
    except Exception as exc:
        failure = directory/'failure.json'
        _json(failure, {'type':type(exc).__name__, 'detail':settings.redact(str(exc)),
                       'reservation_history_preserved':True, 'rerun_requires_disclosed_amendment':True})
        _event(ledger, {'event':'failed', 'type':type(exc).__name__})
        raise RunnerFailure(failure) from None
    finally:
        os.chdir(workspace)
        if start_target:
            try:
                _lifecycle(freeze,settings,directory,stop=True)
                if result is not None:result['target_stopped']=True
            except Exception as exc:
                _json(directory/'target-stop-failure.json',{'type':type(exc).__name__,'detail':settings.redact(str(exc))})
                if result is not None:result['target_stopped']=False


def _execution(private, freeze_sha, authorization_id):
    """Only the exact completed durable execution may be scored; never enumerate private directories."""
    ledger = _private_asset(private/'matched-execution-accounting'/(freeze_sha+'.jsonl'),private)
    events = [json.loads(line) for line in ledger.read_text(encoding='utf-8').splitlines()]
    start = events[0]
    directory = _private_asset(Path(start['directory']),private)
    reservations = [event.get('slot') for event in events if event['event']=='reservation']
    completed = [event.get('slot') for event in events if event['event']=='completed']
    expected = list(range(1,289))
    if (start['event']!='start' or start['freeze_sha256']!=freeze_sha or start['authorization_id']!=authorization_id
            or not directory.is_relative_to(private/'matched-executions')
            or reservations != expected or completed != expected
            or events[-1]['event']!='execution_complete'
            or any(event['event'] in {'failed','failed_or_unknown'} for event in events)):
        raise ValueError('No completed bound matched execution exists')
    completion = json.loads(_private_asset(directory/'execution-complete.json',directory).read_text(encoding='utf-8'))
    if completion != {'freeze_sha256':freeze_sha,'answer_runs':288,'extra_encoder_reads':0}:
        raise ValueError('Matched completion record differs from the durable execution')
    return directory


def grade(freeze_path: Path, authorization_path: Path, *, scores_path: Path | None = None) -> dict:
    """Reuse the same strict real-human seal and guarded reveal; expose full policy labels only afterwards."""
    freeze, approval, private, _ = _context(freeze_path, authorization_path)
    digest = file_sha(public_asset(freeze_path))
    directory = _execution(private, digest, approval.authorization_id)
    try:
        # Guard every shared helper input/output before that helper opens it.
        # A scoring form or nested packet symlink must not escape the execution.
        names = ['blind/public/answers.json', 'blind/commitment.json', 'blind/scores-sealed.json']
        if scores_path is None:
            names += ['blind/private/reveal.json', 'blind/revealed-scores.json',
                      'evidence-scores.json', 'aggregate-report.json']
        for name in names:
            _private_asset(directory/name, directory)
        if scores_path is not None:
            path = _private_asset(scores_path, directory)
            sealed = _seal_scores(directory/'blind', path)
            return {'status':'human_scores_sealed', 'answers':len(sealed['scores']), 'condition_results_revealed':False}
        revealed = _reveal_scores(directory/'blind', development_only=False, comparisons=COMPARISONS)
        evidence = json.loads((directory/'evidence-scores.json').read_text(encoding='utf-8'))
        report = {'status':'complete_scored', 'freeze_sha256':digest, 'conditions':{}, 'splits':{},
            'primary_contrast':PRIMARY[0]+'_vs_'+PRIMARY[1], 'paired_correctness':revealed['paired_correctness'],
            'limits':['Exploratory source-author outcome exposure; human review does not remove selection bias.',
                      'Negative development gate retained; no population superiority claim.',
                      'Selector contrasts are end-to-end policies, including changed Graph anchors.']}
        for split in (None, 'development', 'held_out'):
            ids = {row['question_id'] for row in evidence if split is None or row['split']==split}
            summary = {'conditions':{}, 'questions':len(ids), 'paired_correctness':{}}
            for policy in matched_conditions():
                rows = [row for row in revealed['rows'] if row['question_id'] in ids and row['requested_condition']==policy.condition_id]
                measured = [row for row in evidence if row['question_id'] in ids and row['condition']==policy.condition_id]
                recalls = [row['evidence_fact_recall_at_6'] for row in measured if row['evidence_fact_recall_at_6'] is not None]
                summary['conditions'][policy.condition_id] = {'answers':len(rows), 'arm_id':policy.arm_id,
                    'profile_id':policy.profile_id, 'selector_id':policy.selector_id, 'mode':policy.mode,
                    'mean_correctness':statistics.mean(row['correctness'] for row in rows),
                    'mean_citation_support':statistics.mean(row['citation_support'] for row in rows),
                    'mean_evidence_recall_answerable':statistics.mean(recalls) if recalls else None,
                    'median_retrieval_ms':statistics.median(row['retrieval_ms'] for row in measured),
                    'fallbacks':sum(bool(row['fallback_reason']) for row in measured)}
            for left, right in COMPARISONS:
                paired = {qid:{row['requested_condition']:row['correctness'] for row in revealed['rows'] if row['question_id']==qid} for qid in ids}
                delta = [row[left]-row[right] for row in paired.values()]
                summary['paired_correctness'][left+'_vs_'+right] = {'wins':sum(d>0 for d in delta), 'ties':sum(d==0 for d in delta), 'losses':sum(d<0 for d in delta)}
            if split is None:report['conditions']=summary['conditions']
            else:report['splits'][split]=summary
        _json(directory/'aggregate-report.json', report)
        return report
    except Exception as exc:
        path = directory/('grading-failure-'+uuid.uuid4().hex+'.json')
        _json(path, {'type':type(exc).__name__, 'detail':str(exc)})
        raise RunnerFailure(path) from None


def main(argv=None):
    """Only generic status/aggregate reports leave this dedicated authorized evaluator entry point."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation', choices=['run','seal','reveal','verify'])
    parser.add_argument('--freeze', type=Path, required=True)
    parser.add_argument('--authorization', type=Path)
    parser.add_argument('--scores', type=Path)
    parser.add_argument('--start-target', action='store_true')
    args = parser.parse_args(argv)
    configure_caches()
    try:
        if args.operation == 'verify':
            load_freeze(args.freeze)
            result = {'status':'public_freeze_verified', 'execution_authorized':False}
        else:
            if args.authorization is None:raise ValueError('Exact matched final authorization required')
            if args.operation=='run':result=execute(args.freeze,args.authorization,Settings.from_env(),start_target=args.start_target)
            elif args.operation=='seal':
                if args.scores is None:raise ValueError('A complete real human score form is required')
                result=grade(args.freeze,args.authorization,scores_path=args.scores)
            else:result=grade(args.freeze,args.authorization)
        print(json.dumps(result))
        return 0
    except Exception as exc:
        print(json.dumps({'status':'declined_or_failed', 'error_type':type(exc).__name__,
            'private_failure_artifact':getattr(exc,'private_report',None),
            'message':'No private contents printed; inspect authorized evaluator diagnostics.'}))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
