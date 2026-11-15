"""Product views and exports over actual assembled evidence; no additional retrieval or approval."""

from __future__ import annotations

import csv
import io
import json
from pathlib import Path

from pydantic import Field

from research_assistant.contracts import Contract, DraftAnswer, EvidenceItem, RunArtifact
from research_assistant.generation import validate_answer
from research_assistant.graph.search import SearchRepository
from research_assistant.ingestion.sources import load_corpus_chunks
from research_assistant.retrieval.catalog import ReviewCatalog, alias_matches, checked_fact, load_catalog
from research_assistant.retrieval.evidence import validate_context
from research_assistant.review.store import review_lock
from research_assistant.settings import Settings

PILOT_CORPUS = '74260b76836e297402fd7d25804a70eba873de0a00327260b0d348964eb4e329'
WORKFLOWS = {
    'discovery': 'Which methods were evaluated on MuSiQue? Cite at least two reporting papers and qualify benchmark comparability.',
    'comparison': 'Compare the original HippoRAG and HippoRAG 2 evaluations on MuSiQue. What versions, splits, metrics and protocols are reported or unknown?',
    'limitations': 'What limitations do the original HippoRAG authors report about NER, OpenIE and scaling beyond the tested benchmarks?',
    'ask': '',
}
COMPARISON_FIELDS = ('dataset', 'dataset_version', 'split', 'metric', 'protocol')


class ProductView(Contract):
    """A presentation projection, never additional model context or a scientific score."""

    workflow: str
    status: str
    rows: list[dict[str, str]] = Field(default_factory=list)
    notices: list[str] = Field(default_factory=list)
    paper_count: int = 0
    method_count: int = 0


def validate_run(run: RunArtifact, settings: Settings,
                 review_directory: Path = Path('data/reviews/pilot')) -> ReviewCatalog | None:
    """Recheck stored results before display/export; stale approvals and service errors fail closed."""
    chunks = load_corpus_chunks(run.request.corpus_id)
    validate_context(run.retrieval, chunks)
    if run.request.mode != run.retrieval.requested_mode:
        raise ValueError('Requested mode differs from the saved retrieval')
    result = run.retrieval
    if run.request.profile_id=='baseline' and run.request.selector_id!='reference':
        raise ValueError('Saved baseline profile cannot claim a reranker selector')
    if run.request.profile_id=='retrieval-v2':
        from research_assistant.retrieval.profiles import retrieval_profile, validate_scope
        with review_lock(review_directory):
            scoped_catalog=load_catalog(review_directory,run.request.corpus_id,chunks)
            scoped_repo=SearchRepository(settings)
            try:
                scope=validate_scope(run.request,settings,review_directory,chunks,scoped_catalog,scoped_repo)
            finally:
                scoped_repo.close()
        if (result.audit.get('profile')!=retrieval_profile('retrieval-v2',run.request.selector_id).model_dump()
                or result.audit.get('experiment_scope')!=scope.model_dump()
                or run.configuration.get('profile')!=result.audit['profile']
                or run.configuration.get('experiment_scope')!=scope.model_dump()
                or result.audit.get('requested_profile')!='retrieval-v2'
                or result.audit.get('effective_profile')!='retrieval-v2'):
            raise ValueError('Saved profile/selector/scope provenance differs from the validated request')
    elif result.audit.get('requested_profile')=='retrieval-v2':
        raise ValueError('Saved requested profile differs from retrieval provenance')
    if result.fallback_reason:
        if (run.request.mode != 'graph' or result.effective_mode != 'hybrid_facts'
                or result.fallback_reason not in {'no_new_eligible_graph_candidates', 'graph_candidates_not_selected_within_budget'}
                or any(item.graph_paths for item in result.evidence)):
            raise ValueError('Saved fallback identity is inconsistent')
    elif result.effective_mode != result.requested_mode:
        raise ValueError('Effective mode changed without an explicit fallback reason')
    if run.result is not None:
        answer = validate_answer(DraftAnswer(answer=run.result.answer,
            insufficient_evidence=run.result.insufficient_evidence,
            citations=[citation['evidence_id'] for citation in run.result.citations]), result)
        if answer != run.result:
            raise ValueError('Saved answer citations differ from the rendered evidence')
    needs_review = run.request.mode in {'hybrid_facts', 'graph'} or any(
        item.kind == 'approved_fact' for item in run.retrieval.evidence)
    if not needs_review:
        return None
    with review_lock(review_directory):
        catalog = load_catalog(review_directory, run.request.corpus_id, chunks)
        if run.retrieval.audit.get('review_head') != catalog.head:
            raise ValueError('Review head changed since retrieval; rerun the query before display/export')
        repo = SearchRepository(settings)
        try:
            snapshot = repo.snapshot(run.request.corpus_id)
            if snapshot != run.corpus_manifest:
                raise ValueError('Corpus manifest changed since retrieval')
            with repo.reading(run.request.corpus_id, catalog.head, settings.graph_query_timeout_seconds):
                if run.request.profile_id=='retrieval-v2':repo.fact_vectors(catalog,chunks,snapshot['encoder_revision'],strict_roles=True)
                else:repo.fact_vectors(catalog, chunks, snapshot['encoder_revision'])
                for item in run.retrieval.evidence:
                    if item.kind == 'approved_fact':
                        checked_fact(item, catalog)
        finally:
            repo.close()
    return catalog


def known(value: str | None) -> str:
    """Render absent or explicitly unknown conditions consistently."""
    return value if value and value.strip().casefold() not in {'unknown', 'none', 'not reported', 'n/a'} else 'unknown'


def comparison_notices(rows: list[dict[str, str]]) -> list[str]:
    """Qualify each missing/incompatible comparison axis without inferring compatibility."""
    notices = []
    for field in COMPARISON_FIELDS:
        values = {known(row.get(field)) for row in rows}
        if not values or 'unknown' in values:
            notices.append(f'{field}: missing information; comparability is unverified.')
        if len(values - {'unknown'}) > 1:
            notices.append(f'{field}: reported conditions differ; do not combine these evaluations.')
    notices.append('No controlled numerical ranking is established. Matching benchmark names alone do not establish comparable scores.')
    return notices


def build_view(run: RunArtifact, catalog: ReviewCatalog | None) -> ProductView:
    """Group only selected approved claims; raw excerpts remain visible separately in every workflow."""
    rows, methods, papers = [], set(), set()
    mentioned = alias_matches(run.request.question, catalog.entities) if catalog else set()
    requested_datasets = {key for key in mentioned if catalog.entities[key].kind == 'dataset'}
    requested_methods = {key for key in mentioned if catalog.entities[key].kind == 'method'}
    for item in run.retrieval.evidence:
        if item.kind != 'approved_fact':
            continue
        fact = checked_fact(item, catalog)
        entity_ids = {entity['id'] for entity in fact['entities']}
        if requested_datasets and not requested_datasets.intersection(entity_ids):
            continue
        if requested_methods and not requested_methods.intersection(entity_ids):
            continue
        if run.workflow in {'discovery', 'comparison'} and fact['kind'] != 'evaluation':
            continue
        if run.workflow == 'limitations' and fact['kind'] != 'finding':
            continue
        method_entities = [entity for entity in fact['entities'] if entity['kind'] == 'method']
        methods.update(entity['id'] for entity in method_entities)
        papers.update(item.paper_ids)
        citations = '; '.join(f'{ex.source_url.split("#")[0]}#page={ex.page}' for ex in item.excerpts)
        rows.append({'paper': item.paper_ids[0], 'method': known(item.conditions.get('method')),
                     **{field: known(item.conditions.get(field)) for field in COMPARISON_FIELDS},
                     'claim': item.claim_text, 'claim_id': item.approved_claim_ids[0],
                     'kind': fact['kind'], 'citations': citations,
                     'conditions': json.dumps(item.conditions, ensure_ascii=False, sort_keys=True)})
    notices = ['Only evidence selected for this query is shown. Missing rows do not prove a paper lacks a method, result or limitation.']
    if run.workflow == 'comparison':
        notices.extend(comparison_notices(rows))
    enough = bool(run.retrieval.evidence) if run.workflow == 'ask' else bool(rows)
    if run.workflow == 'discovery':
        enough = len(papers) >= 2 and bool(methods)
    elif run.workflow == 'comparison':
        enough = len(papers) >= 2
    if run.workflow == 'limitations':
        notices.append('These are approved paper-reported findings. Relevance to the requested limitation must be checked against the quotations.')
    return ProductView(workflow=run.workflow, status='evidence available' if enough else 'partial evidence',
                       rows=rows, notices=notices, paper_count=len(papers), method_count=len(methods))


def evidence_csv(run: RunArtifact) -> str:
    """Serialize actual excerpts with reversible formula escaping; call only after validate_run."""
    fields = ['run_id', 'requested_mode', 'effective_mode', 'fallback_reason', 'context_sha256',
              'evidence_id', 'kind', 'paper', 'source_url', 'page', 'claim_id', 'claim_revision',
              'claim', 'condition', 'quotation', 'chunk_id', 'source_sha256', 'start', 'end',
              'graph_paths', 'escaped_fields']
    output = io.StringIO(newline='')
    writer = csv.DictWriter(output, fieldnames=fields, lineterminator='\n')
    writer.writeheader()
    for item in run.retrieval.evidence:
        for excerpt in item.excerpts:
            row = dict(run_id=run.run_id, requested_mode=run.retrieval.requested_mode,
                       effective_mode=run.retrieval.effective_mode, fallback_reason=run.retrieval.fallback_reason or '',
                       context_sha256=run.retrieval.context_sha256, evidence_id=item.id, kind=item.kind,
                       paper=excerpt.paper_id, source_url=excerpt.source_url, page=str(excerpt.page),
                       claim_id=';'.join(item.approved_claim_ids), claim_revision=str(item.claim_revision or ''),
                       claim=item.claim_text or '', condition=json.dumps(item.conditions, ensure_ascii=False, sort_keys=True),
                       quotation=excerpt.text, chunk_id=excerpt.chunk_id, source_sha256=excerpt.source_sha256,
                       start=str(excerpt.start), end=str(excerpt.end), graph_paths=json.dumps(item.graph_paths, ensure_ascii=False, sort_keys=True))
            escaped = []
            for field, value in row.items():
                if value.lstrip().startswith(('=', '+', '-', '@')) or value.startswith(('\t', '\r', '\n', "'")):
                    row[field] = "'" + value
                    escaped.append(field)
            row['escaped_fields'] = json.dumps(escaped)
            writer.writerow(row)
    return output.getvalue()


def prepare_output(run: RunArtifact, settings: Settings,
                   review_directory: Path = Path('data/reviews/pilot')) -> tuple[ProductView, str]:
    """Single checked product/export boundary shared by CLI and Streamlit."""
    catalog = validate_run(run, settings, review_directory)
    return build_view(run, catalog), evidence_csv(run)
