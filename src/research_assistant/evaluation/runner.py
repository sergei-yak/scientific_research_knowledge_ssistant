"""Evaluator-controlled frozen execution; private contents never enter console/public reports."""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import json
import hashlib
import os
from pathlib import Path
import random
import statistics
import subprocess
import time
from typing import Literal
from urllib.parse import urlsplit
import uuid

import ollama
from pydantic import Field

from research_assistant.contracts import Contract, EvaluationQuestion, QueryRequest, RetrievalResult
from research_assistant.embeddings import Encoder, MPNetEncoder
from research_assistant.evaluation.blinding import ScoringInput, _build_bundle, _seal_scores, _reveal_scores
from research_assistant.evaluation.development import load_dataset
from research_assistant.evaluation.freeze import FreezeManifest, authorize, file_sha, load_freeze, public_asset
from research_assistant.evaluation.scoring import score_evidence
from research_assistant.graph.recovery import attest_target, capture, require_read_only
from research_assistant.contracts import fingerprint
from research_assistant.ingestion.sources import load_corpus_chunks
from research_assistant.pipeline import QueryExecutionError, code_identity, run_query, write_immutable
from research_assistant.retrieval.embedding_experiment import retrieve_embedding
from research_assistant.retrieval.evidence import estimate_tokens
from research_assistant.settings import Settings, configure_caches


class QuestionPrompt(Contract):
    """Strict stripped input: reference answers/support fields are rejected before inference."""

    question_id: str = Field(min_length=1)
    question: str = Field(min_length=1, max_length=2000)
    split: Literal['development', 'held_out']
    category: Literal['direct', 'cross_paper', 'multi_hop', 'unanswerable']
    secondary_tags: list[str] = Field(default_factory=list)


class RunnerFailure(RuntimeError):
    """Only a private artifact path escapes the evaluator after an authorized failure."""

    def __init__(self, private_report: Path | None) -> None:
        super().__init__('Frozen evaluation stopped; inspect the evaluator-only failure record.')
        self.private_report = str(private_report) if private_report else None


def _json(path: Path, value: object) -> None:
    """Write immutable evaluator records; callers already established directory boundaries."""
    write_immutable(path, json.dumps(value, ensure_ascii=False, indent=2) + '\n')


def _context(freeze_path: Path, approval_path: Path):
    """Authorization precedes even resolving the private root, including grading commands."""
    approval = authorize(approval_path, freeze_path)
    freeze = load_freeze(freeze_path)
    workspace = Path.cwd().resolve()
    private = Path(freeze.private_root).resolve()
    if not private.is_absolute() or private == workspace or private.is_relative_to(workspace):
        raise ValueError('Evaluator files must be external to the development workspace')
    return freeze, approval, private, workspace


def _event(path: Path, event: dict, *, first: bool = False) -> None:
    """Persist conservative reservations; no new output path resets the one-execution ledger."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x' if first else 'a', encoding='utf-8', newline='\n') as handle:
        handle.write(json.dumps({'at': datetime.now(timezone.utc).isoformat(), **event}) + '\n')
        handle.flush()
        os.fsync(handle.fileno())


def _prompts(freeze: FreezeManifest, private: Path, snapshot: Path) -> list[QuestionPrompt]:
    """Read private stripped questions only after authorization; gold remains unopened here."""
    private_questions = (private / 'questions.jsonl').read_bytes()
    if (hashlib.sha256(private_questions).hexdigest() != freeze.heldout_questions_sha256
            or file_sha(private / 'annotations.jsonl') != freeze.heldout_annotations_sha256):
        raise ValueError('Private input bytes differ from the human-validated freeze')
    rows = []
    for path, split, count in ((snapshot / 'files/data/evaluation/development/expansion-v1/questions.jsonl', 'development', 8),
                               (private / 'questions.jsonl', 'held_out', 16)):
        raw = private_questions.decode('utf-8') if split == 'held_out' else path.read_text(encoding='utf-8')
        group = [QuestionPrompt.model_validate_json(line) for line in raw.splitlines()]
        if (len(group) != count or any(row.split != split for row in group)
                or Counter(row.category for row in group) != {key: count // 4 for key in ('direct', 'cross_paper', 'multi_hop', 'unanswerable')}):
            raise ValueError('Question partition/stratification differs from the freeze')
        rows.extend(group)
    if len({row.question_id for row in rows}) != 24 or len({row.question.strip().casefold() for row in rows}) != 24:
        raise ValueError('Duplicate frozen question identity/text')
    return rows


def _target(freeze: FreezeManifest, settings: Settings) -> Settings:
    """Require the frozen local provider and a matching physically read-only restored database."""
    if (settings.generation_provider != freeze.generator_provider or settings.generation_model != freeze.generator_model
            or settings.ollama_base_url != freeze.ollama_base_url or settings.max_retries != 0
            or settings.max_concurrency != 1 or settings.request_timeout_seconds != freeze.request_timeout_seconds
            or settings.graph_query_timeout_seconds != freeze.graph_query_timeout_seconds):
        raise ValueError('Runtime provider/limits differ from the freeze; no automatic substitution')
    model = next((item for item in ollama.Client(host=settings.ollama_base_url, timeout=15).list().models
                  if item.model == freeze.generator_model), None)
    if model is None or model.digest != freeze.generator_digest:
        raise ValueError('Frozen local generator digest is unavailable/changed')
    target = settings.model_copy(update={'neo4j_uri': freeze.target_uri})
    manifest = json.loads((public_asset(freeze.snapshot_directory) / 'manifest.json').read_text(encoding='utf-8'))
    attested = attest_target(target, manifest, freeze.target_project)
    if attested['image_id'] != freeze.docker_image_id or fingerprint(capture(target)) != freeze.graph_sha256:
        raise ValueError('Restored target image/graph differs from the freeze')
    require_read_only(target)
    return target


def _compose(freeze: FreezeManifest, settings: Settings, directory: Path, *, stop: bool = False) -> None:
    """Start/stop only the attested target; never recreate/reset working data or pull an image."""
    proof = json.loads(public_asset(freeze.recovery_report).read_text(encoding='utf-8'))
    env = {**os.environ, 'NEO4J_READ_ONLY': 'true', 'NEO4J_IMAGE': freeze.docker_image_id,
           'NEO4J_BOLT_PORT': str(urlsplit(freeze.target_uri).port), 'NEO4J_HTTP_PORT': str(proof['ports']['http'])}
    command = ['docker', 'compose', '-p', freeze.target_project, '-f', str(Path('compose.yaml').resolve())]
    command += ['stop', 'neo4j'] if stop else ['up', '-d', '--pull', 'never', 'neo4j']
    result = subprocess.run(command, env=env, capture_output=True, text=True, timeout=120)
    write_immutable(directory / ('target-stop.log' if stop else 'target-start.log'), settings.redact(result.stdout + result.stderr))
    result.check_returncode()
    if not stop:
        from research_assistant.graph.repository import GraphRepository
        target = settings.model_copy(update={'neo4j_uri': freeze.target_uri})
        for _ in range(60):
            repo = GraphRepository(target)
            try:
                repo.driver.verify_connectivity()
                return
            except Exception:
                time.sleep(2)
            finally:
                repo.close()
        raise RuntimeError('Read-only target did not become ready')


def _matrix(freeze: FreezeManifest, prompts: list[QuestionPrompt], settings: Settings, encoder,
            directory: Path, ledger: Path) -> list[ScoringInput]:
    """The generator sees only stripped question plus shared retrieved context, never gold."""
    samples = []
    for position, prompt in enumerate(prompts):
        modes = freeze.plan.conditions[position % 4:] + freeze.plan.conditions[:position % 4]
        for mode in modes:
            index = len(samples)
            if index >= freeze.plan.generation_request_limit:
                raise ValueError('Frozen request reservation limit reached')
            _event(ledger, {'event': 'reservation', 'slot': index, 'maximum_requests': 1,
                            'maximum_output_tokens': freeze.plan.output_tokens})
            path = directory / 'runs' / fingerprint(prompt.question_id) / (mode + '.json')
            try:
                run = run_query(QueryRequest(corpus_id=freeze.corpus_id, question=prompt.question, mode=mode),
                    settings, freeze.plan.context_tokens, freeze.plan.output_tokens, freeze.plan.minimum_similarity,
                    Path('data/reviews/expansion-v1'), encoder=encoder)
            except QueryExecutionError as exc:
                _json(path, exc.artifact.model_dump(mode='json'))
                _event(ledger, {'event': 'failed_or_unknown', 'slot': index, 'reservation_retained': True})
                raise
            run.configuration.update(freeze_graph_sha256=freeze.graph_sha256, frozen_code_revision=freeze.code_revision,
                                     order_position=position, query_cache_state='no_explicit_query_warmup')
            _json(path, run.model_dump(mode='json'))
            if run.generation and (run.generation.digest != freeze.generator_digest
                                   or run.generation.provider != freeze.generator_provider):
                raise ValueError('Generator identity changed; preserve the run without scoring it')
            _event(ledger, {'event': 'completed', 'slot': index, 'provider_response': run.generation is not None})
            samples.append(ScoringInput(question_id=prompt.question_id, condition=mode, run=run))
    return samples


def _gold(freeze: FreezeManifest, private: Path, prompts: list[QuestionPrompt]) -> dict[str, EvaluationQuestion]:
    """Gold is parsed only after generation; it never crosses the retrieval/provider boundary."""
    private_gold = (private / 'annotations.jsonl').read_bytes()
    if hashlib.sha256(private_gold).hexdigest() != freeze.heldout_annotations_sha256:
        raise ValueError('Frozen private annotations changed during execution')
    _, entries, _ = load_dataset(Path('data/evaluation/development/expansion-v1'))
    heldout = [EvaluationQuestion.model_validate_json(line) for line in
               private_gold.decode('utf-8').splitlines()]
    all_gold = [entry.gold for entry in entries] + heldout
    by_id = {item.question_id: item for item in all_gold}
    if len(by_id) != 24 or len(all_gold) != 24:
        raise ValueError('Frozen annotations do not cover the complete question set')
    for prompt in prompts:
        item = by_id[prompt.question_id]
        if (item.question, item.split, item.category) != (prompt.question, prompt.split, prompt.category):
            raise ValueError('Question and annotation bindings differ')
    return by_id


def execute(freeze_path: Path, approval_path: Path, settings: Settings, *, start_target: bool = False) -> dict:
    """One durable execution; failures keep all artifacts and require a disclosed amendment to rerun."""
    freeze, approval, private, workspace = _context(freeze_path, approval_path)
    freeze_sha = file_sha(public_asset(freeze_path))
    ledger = private / 'execution-accounting' / (freeze_sha + '.jsonl')
    if ledger.exists():
        raise ValueError('This freeze already started; a new directory/receipt does not reset execution')
    directory = private / 'executions' / approval.authorization_id / uuid.uuid4().hex
    directory.mkdir(parents=True, exist_ok=False)
    started = False
    public_result = None
    try:
        if start_target:
            _compose(freeze, settings, directory)
        target = _target(freeze, settings)
        snapshot = public_asset(freeze.snapshot_directory)
        prompts = _prompts(freeze, private, snapshot)
        mini, mpnet = Encoder(), MPNetEncoder()
        if (mini.revision != freeze.encoder_revisions['all-MiniLM-L6-v2']
                or mpnet.revision != freeze.encoder_revisions['all-mpnet-base-v2']):
            raise ValueError('Runtime encoder revisions changed')
        for prompt in prompts:
            if (len(mini.mini_tokenizer.encode(prompt.question, add_special_tokens=True)) > 256
                    or len(mpnet.model.tokenizer.encode(prompt.question, add_special_tokens=True)) > 384):
                raise ValueError('Frozen question would be truncated by an encoder')
        estimate_tokens('Warm the pinned estimator without using evaluation content.')
        random.Random(freeze.plan.order_seed).shuffle(prompts)
        _event(ledger, {'event': 'start', 'freeze_sha256': freeze_sha,
            'authorization_id': approval.authorization_id, 'directory': str(directory)}, first=True)
        started = True
        os.chdir(snapshot / 'files')
        if code_identity()['source_tree_sha256'] != freeze.source_tree_sha256:
            raise ValueError('Restored executable source differs from the freeze')
        samples = _matrix(freeze, prompts, target, mini, directory, ledger)
        gold, chunks = _gold(freeze, private, prompts), load_corpus_chunks(freeze.corpus_id)
        scores = [{'condition': sample.condition, 'split': gold[sample.question_id].split,
                   'category': gold[sample.question_id].category,
                   'effective_mode': sample.run.retrieval.effective_mode,
                   'fallback_reason': sample.run.retrieval.fallback_reason,
                   'retrieval_ms': sample.run.retrieval.retrieval_ms,
                   'generation_ms': sample.run.generation.elapsed_ms if sample.run.generation else 0,
                   'provider_called': sample.run.generation is not None,
                   **score_evidence(gold[sample.question_id], sample.run.retrieval, chunks)} for sample in samples]
        _json(directory / 'evidence-scores.json', scores)
        comparisons = []
        for position, prompt in enumerate(prompts):
            encoders = ['minilm', 'mpnet'] if position % 2 == 0 else ['mpnet', 'minilm']
            for name in encoders:
                artifact = retrieve_embedding(freeze.corpus_id, prompt.question, name, target,
                                             encoder=mini if name == 'minilm' else mpnet)
                retrieved = RetrievalResult.model_validate(artifact['retrieval'])
                _json(directory / 'encoders' / fingerprint(prompt.question_id) / (name + '.json'), artifact)
                comparisons.append({'encoder': name, 'split': prompt.split, 'category': prompt.category,
                    'retrieval_ms': retrieved.retrieval_ms, 'timing': retrieved.audit,
                    **score_evidence(gold[prompt.question_id], retrieved, chunks)})
        _json(directory / 'encoder-comparison.json', comparisons)
        _build_bundle(samples, chunks, directory / 'blind', development_only=False)
        os.chdir(workspace)
        load_freeze(freeze_path)
        if fingerprint(capture(target)) != freeze.graph_sha256:
            raise ValueError('Frozen graph changed during execution')
        _event(ledger, {'event': 'execution_complete', 'answer_runs': len(samples), 'encoder_reads': len(comparisons)})
        _json(directory / 'execution-complete.json', {'freeze_sha256': freeze_sha, 'answer_runs': 96, 'encoder_reads': 48})
        public_result = {'status': 'awaiting_blind_human_scores', 'answer_runs': 96, 'encoder_reads': 48,
                'freeze_sha256': freeze_sha, 'scoring_packet_directory': str(directory / 'blind/public'),
                'paid_calls': 0, 'condition_results_revealed': False}
        return public_result
    except Exception as exc:
        failure = directory / 'failure.json'
        _json(failure, {'status': 'failed', 'type': type(exc).__name__, 'detail': settings.redact(str(exc)),
                        'execution_started': started, 'reservation_history_preserved': True})
        if started:
            _event(ledger, {'event': 'failed', 'type': type(exc).__name__, 'rerun_requires_amendment': True})
        raise RunnerFailure(failure) from None
    finally:
        os.chdir(workspace)
        if start_target:
            try:
                _compose(freeze, settings, directory, stop=True)
                if public_result is not None:
                    public_result['target_stopped'] = True
            except Exception as exc:
                _json(directory / 'target-stop-failure.json', {'type': type(exc).__name__, 'detail': settings.redact(str(exc))})
                if public_result is not None:
                    public_result['target_stopped'] = False


def _execution_directory(private: Path, freeze_sha: str, authorization_id: str) -> Path:
    """Find only the recorded execution after authorization; never discover arbitrary private files."""
    ledger = private / 'execution-accounting' / (freeze_sha + '.jsonl')
    events = [json.loads(line) for line in ledger.read_text(encoding='utf-8').splitlines()]
    start = events[0]
    directory = Path(start['directory']).resolve()
    if (start['event'] != 'start' or start['freeze_sha256'] != freeze_sha
            or start['authorization_id'] != authorization_id or not directory.is_relative_to(private / 'executions')
            or not any(event['event'] == 'execution_complete' for event in events)):
        raise ValueError('No complete bound execution is available for scoring')
    return directory


def grade(freeze_path: Path, approval_path: Path, *, scores_path: Path | None = None) -> dict:
    """Seal complete real human scores, or reveal only aggregates after the form is sealed."""
    freeze, approval, private, _ = _context(freeze_path, approval_path)
    freeze_sha = file_sha(public_asset(freeze_path))
    directory = _execution_directory(private, freeze_sha, approval.authorization_id)
    try:
        return _grade_bound(directory, freeze_sha, scores_path)
    except Exception as exc:
        failure = directory / ('grading-failure-' + uuid.uuid4().hex + '.json')
        _json(failure, {'type': type(exc).__name__, 'detail': str(exc)})
        raise RunnerFailure(failure) from None


def _grade_bound(directory: Path, freeze_sha: str, scores_path: Path | None) -> dict:
    """Only the authorized wrapper supplies a private execution; failures remain private."""
    if scores_path is not None:
        path = scores_path.resolve()
        if not path.is_relative_to(directory):
            raise ValueError('Human scoring form must stay inside its private execution')
        sealed = _seal_scores(directory / 'blind', path)
        return {'status': 'human_scores_sealed', 'answers': len(sealed['scores']), 'condition_results_revealed': False}
    revealed = _reveal_scores(directory / 'blind', development_only=False)
    evidence = json.loads((directory / 'evidence-scores.json').read_text(encoding='utf-8'))
    encoders = json.loads((directory / 'encoder-comparison.json').read_text(encoding='utf-8'))
    modes = defaultdict(list)
    for row in revealed['rows']:
        modes[row['requested_condition']].append(row)
    result = {'status': 'complete_scored', 'freeze_sha256': freeze_sha,
              'paired_correctness': revealed['paired_correctness'], 'conditions': {}, 'vector_encoders': {},
              'limits': ['AI-authored purposive set with one human validator/scorer unless a second is recorded.',
                         'Descriptive paired counts; no population superiority claim.',
                         'Fresh ANN/provider reruns may differ; saved artifacts are authoritative.']}
    for mode, rows in modes.items():
        recalls = [row['evidence_fact_recall_at_6'] for row in evidence if row['condition'] == mode and row['evidence_fact_recall_at_6'] is not None]
        result['conditions'][mode] = {'answers': len(rows), 'mean_correctness': statistics.mean(row['correctness'] for row in rows),
            'mean_citation_support': statistics.mean(row['citation_support'] for row in rows),
            'correct_abstentions': sum(row['correct_abstention'] is True for row in rows),
            'incorrect_abstentions': sum(row['correct_abstention'] is False for row in rows),
            'mean_evidence_recall_answerable': statistics.mean(recalls),
            'median_retrieval_ms': statistics.median(row['retrieval_ms'] for row in evidence if row['condition'] == mode),
            'fallbacks': sum(bool(row['fallback_reason']) for row in evidence if row['condition'] == mode)}
    result['splits'] = {}
    for split in ('development', 'held_out'):
        ids = {row['question_id'] for row in evidence if row['split'] == split}
        summary = {'questions': len(ids), 'conditions': {}, 'paired_correctness': {}}
        for mode, all_rows in modes.items():
            rows = [row for row in all_rows if row['question_id'] in ids]
            measured = [row for row in evidence if row['split'] == split and row['condition'] == mode]
            recalls = [row['evidence_fact_recall_at_6'] for row in measured if row['evidence_fact_recall_at_6'] is not None]
            summary['conditions'][mode] = {'answers': len(rows),
                'mean_correctness': statistics.mean(row['correctness'] for row in rows),
                'mean_citation_support': statistics.mean(row['citation_support'] for row in rows),
                'mean_evidence_recall_answerable': statistics.mean(recalls),
                'median_retrieval_ms': statistics.median(row['retrieval_ms'] for row in measured),
                'fallbacks': sum(bool(row['fallback_reason']) for row in measured)}
            if mode != 'vector':
                baseline = {row['question_id']: row['correctness'] for row in modes['vector']}
                differences = [row['correctness'] - baseline[row['question_id']] for row in rows]
                summary['paired_correctness'][mode + '_vs_vector'] = {
                    'wins': sum(value > 0 for value in differences), 'ties': sum(value == 0 for value in differences),
                    'losses': sum(value < 0 for value in differences)}
        result['splits'][split] = summary
    for name in ('minilm', 'mpnet'):
        group = [row for row in encoders if row['encoder'] == name]
        recalls = [row['evidence_fact_recall_at_6'] for row in group if row['evidence_fact_recall_at_6'] is not None]
        result['vector_encoders'][name] = {'queries': len(group), 'mean_evidence_recall_answerable': statistics.mean(recalls),
            'median_retrieval_ms': statistics.median(row['retrieval_ms'] for row in group), 'splits': {}}
        for split in ('development', 'held_out'):
            selected = [row for row in group if row['split'] == split]
            recalls = [row['evidence_fact_recall_at_6'] for row in selected if row['evidence_fact_recall_at_6'] is not None]
            result['vector_encoders'][name]['splits'][split] = {'queries': len(selected),
                'mean_evidence_recall_answerable': statistics.mean(recalls),
                'median_retrieval_ms': statistics.median(row['retrieval_ms'] for row in selected)}
    _json(directory / 'aggregate-report.json', result)
    return result


def main(argv: list[str] | None = None) -> int:
    """Only aggregate status/errors reach stdout; all potentially private diagnostics stay external."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation', choices=['run', 'seal', 'reveal'])
    parser.add_argument('--freeze', type=Path, required=True)
    parser.add_argument('--authorization', type=Path, required=True)
    parser.add_argument('--start-target', action='store_true')
    parser.add_argument('--scores', type=Path)
    parser.add_argument('--public-output', type=Path)
    args = parser.parse_args(argv)
    configure_caches()
    try:
        if args.operation == 'run':
            result = execute(args.freeze, args.authorization, Settings.from_env(), start_target=args.start_target)
        elif args.operation == 'seal':
            if args.scores is None:
                raise ValueError('A complete human form is required')
            result = grade(args.freeze, args.authorization, scores_path=args.scores)
        else:
            result = grade(args.freeze, args.authorization)
        if args.public_output:
            _json(public_asset(args.public_output), result)
        print(json.dumps(result))
        return 0
    except Exception as exc:
        print(json.dumps({'status': 'declined_or_failed', 'error_type': type(exc).__name__,
                          'private_failure_artifact': getattr(exc, 'private_report', None),
                          'message': 'No private contents printed; inspect authorized evaluator diagnostics.'}))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
