"""Development-only public API and shared scoring primitives; no held-out reader or run entry point."""

from __future__ import annotations

import csv
import io
import json
import secrets
import uuid
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Literal

from research_assistant.contracts import (
    Chunk, Contract, DraftAnswer, HumanScore, RunArtifact, fingerprint,
)
from research_assistant.evaluation.development import development_directory
from research_assistant.generation import validate_answer
from research_assistant.pipeline import write_immutable
from research_assistant.retrieval.evidence import validate_context

Condition = Literal['vector', 'hybrid', 'hybrid_facts', 'graph']
CONDITIONS = ('vector', 'hybrid', 'hybrid_facts', 'graph')
SCORE_FIELDS = ('answer_id', 'correctness', 'citation_support', 'correct_abstention', 'reviewer', 'scored_at', 'notes')


class ScoringInput(Contract):
    """Only a question identity and saved run enter export; gold never enters retrieval."""

    question_id: str
    condition: Condition
    run: RunArtifact


def _json(path: Path, value: object) -> None:
    """Use the shared immutable UTF-8 artifact writer."""
    write_immutable(path, json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + '\n')


def build_development_bundle(samples: list[ScoringInput], chunks: dict[str, Chunk], directory: Path) -> dict:
    """Validate complete four-condition pairs and whitelist only scoring content in public files."""
    return _build_bundle(samples, chunks, development_directory(directory), development_only=True)


def _build_bundle(samples: list[ScoringInput], chunks: dict[str, Chunk], directory: Path, *, development_only: bool,
                  matched_policies: dict | None = None) -> dict:
    """Shared export rules; callers establish development or authorized evaluator boundaries first."""
    if directory.exists() or not samples:
        raise ValueError('Choose a new development bundle directory and nonempty samples')
    conditions = CONDITIONS
    if matched_policies is not None:
        from research_assistant.evaluation.proposals import matched_conditions
        expected = {item.condition_id: item for item in matched_conditions()}
        if matched_policies != expected:
            raise ValueError('Blind matched bundle requires the complete twelve frozen policies')
        conditions = tuple(expected)
    grouped: dict[str, list[ScoringInput]] = {}
    for sample in samples:
        grouped.setdefault(sample.question_id, []).append(sample)
    public, reveal = [], []
    for question_id, group in grouped.items():
        if Counter(s.condition for s in group) != Counter(conditions):
            raise ValueError('Every question requires every condition exactly once')
        if len({s.run.request.question for s in group}) != 1:
            raise ValueError('Paired conditions must use the same question')
        for sample in group:
            run = sample.run
            if (run.corpus_manifest.get('corpus_id') != run.request.corpus_id
                    or run.configuration.get('encoder_revision') != run.corpus_manifest.get('encoder_revision')):
                raise ValueError('Saved corpus/encoder bindings are inconsistent')
            policy = matched_policies[sample.condition] if matched_policies is not None else None
            mode = policy.mode if policy is not None else sample.condition
            if policy is not None and (run.request.profile_id, run.request.selector_id) != (policy.profile_id, policy.selector_id):
                raise ValueError('Saved run profile/selector differs from the blinded condition')
            if run.request.mode != mode or run.retrieval.requested_mode != mode:
                raise ValueError('Requested condition does not match saved run')
            if run.result is None or not run.generation_requested:
                raise ValueError('Incomplete/retrieval-only runs cannot be exported as scored answers')
            if run.retrieval.evidence and run.generation is None:
                raise ValueError('Nonempty-context answers require the saved generation response')
            validate_context(run.retrieval, chunks)
            checked = validate_answer(DraftAnswer(answer=run.result.answer,
                citations=[c['evidence_id'] for c in run.result.citations],
                insufficient_evidence=run.result.insufficient_evidence), run.retrieval)
            if checked != run.result:
                raise ValueError('Resolved answer citations differ from saved evidence')
            answer_id = uuid.uuid4().hex
            public.append({'answer_id': answer_id, 'question_id': question_id,
                'question': run.request.question, 'answer': run.result.answer,
                'abstained': run.result.insufficient_evidence,
                'citations': [{'citation': citation['evidence_id'], 'sources': [
                    {'paper_id': ex['paper_id'], 'url': ex['source_url'], 'page': ex['page'], 'quotation': ex['text']}
                    for ex in citation['excerpts']]} for citation in run.result.citations]})
            reveal.append({'answer_id': answer_id, 'question_id': question_id,
                'requested_condition': sample.condition, 'effective_mode': run.retrieval.effective_mode,
                'fallback_reason': run.retrieval.fallback_reason, 'run_id': run.run_id,
                'run_sha256': fingerprint(run.model_dump(mode='json'))})
            if policy is not None:
                reveal[-1].update(arm_id=policy.arm_id, requested_profile=policy.profile_id,
                                  requested_selector=policy.selector_id)
    # Deterministic no-evidence abstention has no provider call, but must not hide a mixed generator.
    nonempty = [s for s in samples if s.run.generation is not None]
    generator_ids = set()
    controls = ('num_ctx', 'num_predict', 'temperature', 'num_batch', 'thinking',
                'retries', 'concurrency', 'purpose', 'prompt_version', 'max_output_tokens')
    for sample in nonempty:
        generation = sample.run.generation
        generator_ids.add(fingerprint({'provider': generation.provider, 'model': generation.model,
            'digest': generation.digest, 'controls': {key: generation.settings.get(key) for key in controls},
            'system_messages': [message for message in generation.messages if message['role'] == 'system'],
            'request_controls': {key: value for key, value in generation.settings.get('request', {}).items() if key != 'input'}}))
    scope_ids = {(s.run.request.corpus_id, s.run.code_revision, s.run.corpus_manifest.get('encoder_revision'),
                  s.run.configuration.get('source_tree_sha256')) for s in samples}
    if len(generator_ids) > 1 or len(scope_ids) != 1:
        raise ValueError('Paired comparison mixes corpus/code/encoder/generator identities')
    secrets.SystemRandom().shuffle(public)
    packet_sha = fingerprint(public)
    _json(directory / 'public/answers.json', public)
    reveal_payload = {'packet_sha256': packet_sha, 'mapping': reveal}
    _json(directory / 'private/reveal.json', reveal_payload)
    _json(directory / 'commitment.json', {'packet_sha256': packet_sha, 'reveal_sha256': fingerprint(reveal_payload)})
    stream = io.StringIO(newline='')
    writer = csv.DictWriter(stream, fieldnames=SCORE_FIELDS)
    writer.writeheader()
    writer.writerows({'answer_id': item['answer_id']} for item in public)
    write_immutable(directory / 'public/scores.csv', stream.getvalue())
    return {'development_only': development_only, 'answers': len(public), 'questions': len(grouped),
            'packet_sha256': packet_sha, 'directory': str(directory), 'human_scores_supplied': 0}


def seal_development_scores(directory: Path, completed_csv: Path) -> dict:
    """Validate a complete human form before reading any reveal mapping; never fill scores."""
    return _seal_scores(development_directory(directory), development_directory(completed_csv))


def _seal_scores(directory: Path, completed_csv: Path) -> dict:
    """Shared complete-form/hash checks; never manufacture reviewer decisions."""
    public = json.loads((directory / 'public/answers.json').read_text(encoding='utf-8'))
    with completed_csv.open(encoding='utf-8-sig', newline='') as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames != list(SCORE_FIELDS):
            raise ValueError('Unexpected scoring columns')
        rows = list(reader)
    expected = {item['answer_id'] for item in public}
    if len(rows) != len(expected) or {r['answer_id'] for r in rows} != expected:
        raise ValueError('Scores must cover every anonymous answer exactly once')
    scores = []
    for row in rows:
        abstention = row['correct_abstention'].strip().lower()
        if abstention not in {'', 'true', 'false'}:
            raise ValueError('Abstention score must be true/false or blank for N/A')
        score = HumanScore.model_validate({**row, 'correctness': float(row['correctness']),
            'citation_support': float(row['citation_support']),
            'correct_abstention': None if not abstention else abstention == 'true'})
        if not score.reviewer.strip() or datetime.fromisoformat(score.scored_at.replace('Z', '+00:00')).tzinfo is None:
            raise ValueError('Scores require a reviewer and timezone-aware timestamp')
        scores.append(score.model_dump(mode='json'))
    commitment = json.loads((directory / 'commitment.json').read_text(encoding='utf-8'))
    if commitment['packet_sha256'] != fingerprint(public):
        raise ValueError('Public packet differs from export commitment')
    payload = {**commitment, 'scores': scores}
    sealed = {**payload, 'sha256': fingerprint(payload)}
    _json(directory / 'scores-sealed.json', sealed)
    return sealed


def reveal_development_scores(directory: Path) -> dict:
    """Join identities only after a complete, hash-bound scoring form has been sealed."""
    return _reveal_scores(development_directory(directory), development_only=True)


def _reveal_scores(directory: Path, *, development_only: bool,
                   comparisons: list[tuple[str, str]] | None = None) -> dict:
    """Shared sealed-score reveal; evaluator access guards belong to its authorized entry point."""
    sealed = json.loads((directory / 'scores-sealed.json').read_text(encoding='utf-8'))
    digest = sealed.pop('sha256')
    public = json.loads((directory / 'public/answers.json').read_text(encoding='utf-8'))
    if digest != fingerprint(sealed) or sealed['packet_sha256'] != fingerprint(public):
        raise ValueError('Sealed scoring/packet hash mismatch')
    mapping = json.loads((directory / 'private/reveal.json').read_text(encoding='utf-8'))
    if (mapping['packet_sha256'] != sealed['packet_sha256']
            or fingerprint(mapping) != sealed['reveal_sha256']):
        raise ValueError('Reveal belongs to a different packet')
    by_id = {item['answer_id']: item for item in mapping['mapping']}
    if len(by_id) != len(public) or set(by_id) != {r['answer_id'] for r in sealed['scores']}:
        raise ValueError('Reveal answer identities mismatch')
    rows = [{**by_id[row['answer_id']], **row} for row in sealed['scores']]
    pairs = {}
    for mode, reference in (comparisons if comparisons is not None else [(mode, 'vector') for mode in CONDITIONS[1:]]):
        outcomes = Counter()
        for question_id in {row['question_id'] for row in rows}:
            group = {r['requested_condition']: r for r in rows if r['question_id'] == question_id}
            difference = group[mode]['correctness'] - group[reference]['correctness']
            outcomes['wins' if difference > 0 else 'losses' if difference < 0 else 'ties'] += 1
        pairs[mode + '_vs_' + reference] = {key: outcomes[key] for key in ('wins', 'ties', 'losses')}
    report = {'development_only': development_only, 'packet_sha256': sealed['packet_sha256'], 'rows': rows,
              'paired_correctness': pairs, 'caveat': 'Descriptive paired counts; no population superiority claim.'}
    _json(directory / 'revealed-scores.json', report)
    return report
