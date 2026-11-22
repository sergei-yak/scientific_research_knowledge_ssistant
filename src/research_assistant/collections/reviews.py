"""Collection-owned proposal, human presentation/decision and reviewed-index services."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import unicodedata

from pydantic import Field

from research_assistant.collections.contracts import ImmutableContract
from research_assistant.collections.workspace import verify_collection
from research_assistant.contracts import PaperManifestEntry, SourceExcerpt, fingerprint
from research_assistant.extraction.contracts import ProposedClaim
from research_assistant.extraction.pilot import validate_candidate
from research_assistant.graph.reviews import synchronize_review
from research_assistant.graph.search import SearchRepository
from research_assistant.ingestion.sources import load_corpus_chunks
from research_assistant.pipeline import write_immutable
from research_assistant.retrieval.catalog import ReviewCatalog
from research_assistant.review.contracts import EntityDefinition, HumanDecision, ReviewRevision, mapping_identity
from research_assistant.review.facts import projection
from research_assistant.review.store import (
    append_event, import_decisions, propose_revision, review_lock, state, validate_revision,
)

FACT_MODES = {'hybrid_facts': 'Hybrid + Approved Facts', 'graph': 'Graph'}


class ReviewPresentation(ImmutableContract):
    """Exactly displayed collection, review head, proposal, source spans and errors."""

    collection_marker: dict
    review_head: str
    revision: ReviewRevision
    excerpts: list[SourceExcerpt]
    errors: list[str]

    @property
    def sha256(self) -> str:
        """Bind every displayed field, including the proposed mappings and exact quotations."""
        return fingerprint(self.model_dump(mode='json'))


class UIResponse(ImmutableContract):
    """Explicit human input; no defaults that could manufacture approval or measured time."""

    presentation_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    reviewer: str = Field(min_length=1, max_length=160)
    decision: str = Field(pattern=r'^(approved|rejected|needs_review)$')
    reason: str = Field(min_length=1, max_length=2000)
    confirmed: bool
    review_seconds: float | None = Field(default=None, ge=0, allow_inf_nan=False)


def review_directory(registry, ready, *, create=False) -> Path:
    """Require owned, unredirected journal paths and exact collection/configuration binding."""
    directory = registry.review_directory(ready.collection)
    if directory.exists() and any(p.resolve() != p for p in directory.rglob('*')):
        raise ValueError('Review history contains a redirected path')
    config = directory / 'config.json'
    expected = {'format': 'user-collection-review-v1', 'corpus_id': ready.collection.corpus_id,
                'collection_marker': ready.marker}
    if config.exists():
        if json.loads(config.read_bytes()) != expected:
            raise ValueError('Review history belongs to a different collection/revision/scope')
    elif create:
        if directory.exists() and any(directory.iterdir()):
            raise ValueError('Review configuration is missing; preserve history for investigation')
        with review_lock(directory):
            write_immutable(config, json.dumps(expected, indent=2) + '\n')
    elif directory.exists() and any(directory.iterdir()):
        raise ValueError('Review configuration is missing')
    return directory


def review_status(registry, ready, settings) -> dict:
    """Report pending/invalid/stale separately; fact modes need current valid graph materialization."""
    directory = review_directory(registry, ready)
    empty = {'review_head': '0' * 64, 'claims': 0, 'approved': 0, 'statuses': [],
             'entities': [], 'ready': False, 'reason': 'No approved claims in this collection yet'}
    if not (directory / 'config.json').exists():
        return empty
    with review_lock(directory):
        chunks = load_corpus_chunks(ready.collection.corpus_id)
        reviewed = projection(directory, chunks)
        current = state(directory)
        result = {**empty, 'review_head': reviewed['review_head'],
            'claims': len(reviewed['statuses']), 'approved': len(reviewed['facts']),
            'statuses': reviewed['statuses'],
            'entities': [e.model_dump() for e in current['entities'].values()]}
        if not reviewed['facts']:
            return result
        repo = SearchRepository(settings)
        try:
            catalog = ReviewCatalog.from_review(ready.collection.corpus_id, reviewed)
            with repo.reading(catalog.corpus_id, catalog.head, settings.graph_query_timeout_seconds):
                repo.check_indexes(catalog.corpus_id, True)
                repo.fact_vectors(catalog, chunks, ready.snapshot['encoder_revision'])
        except Exception as exc:
            result['reason'] = 'Reviewed index unavailable or stale: ' + settings.redact(str(exc))
            return result
        finally:
            repo.close()
        return {**result, 'ready': True, 'reason': None}


def require_fact_ready(registry, ready, settings) -> None:
    """Never treat an unapproved, stale or failed index as an empty successful graph search."""
    status = review_status(registry, ready, settings)
    if not status['ready']:
        raise ValueError('Fact/Graph review is not ready: ' + status['reason'])


def _register(registry, ready, draft: ProposedClaim, chunk_id: str, entity_ids: dict[str, str],
              supersedes: str | None, expected_revision: str | None, origin: str) -> ReviewRevision:
    """Share exact-quotation validation and immutable revision registration for manual/model drafts."""
    draft = ProposedClaim.model_validate(draft.model_dump())
    if set(entity_ids) - {'method', 'dataset'}:
        raise ValueError('Unknown entity kind')
    directory = review_directory(registry, ready, create=True)
    chunks = load_corpus_chunks(ready.collection.corpus_id)
    chunk = chunks.get(chunk_id)
    if chunk is None:
        raise ValueError('Selected passage is outside this collection')
    current = state(directory)
    definitions = []
    for kind in ('method', 'dataset'):
        name = getattr(draft, kind)
        if not name:
            if entity_ids.get(kind): raise ValueError('An unknown name cannot bind an entity')
            continue
        selected = entity_ids.get(kind)
        if selected:
            entity = current['entities'].get(selected)
            if entity is None or entity.kind != kind:
                raise ValueError('Entity binding is outside this collection or has the wrong kind')
            if getattr(draft, kind + '_aliases') != entity.aliases:
                raise ValueError('Using an existing identity requires its exact displayed aliases')
        else:
            normalized = unicodedata.normalize('NFKC', name).casefold().strip()
            entity = EntityDefinition(id=kind + ':user:' + fingerprint([
                ready.collection.collection_id, chunk.paper_id, kind, normalized]),
                kind=kind, name=name, aliases=getattr(draft, kind + '_aliases'))
            existing = current['entities'].get(entity.id)
            if existing and existing != entity and not supersedes:
                raise ValueError('Changing aliases requires a revision, not a new proposal')
        definitions.append(entity)
    paper = next(p for p in ready.snapshot['papers'] if p['paper_id'] == chunk.paper_id)
    candidate = validate_candidate(draft, paper, {'id':chunk.chunk_id, 'paper_id':chunk.paper_id,
        'page':chunk.page, 'start':chunk.page_start, 'text':chunk.text}, list(chunks.values()))
    support = candidate['claim']['support'] if candidate['claim'] else []
    old = current['current'].get(supersedes) if supersedes else None
    if supersedes and (old is None or old.sha256 != expected_revision or old.paper.paper_id != chunk.paper_id):
        raise ValueError('Correction must extend the exact current claim and reporting paper')
    revision = ReviewRevision(claim_id=old.claim_id if old else candidate['claim_id'],
        revision=old.revision+1 if old else 1, predecessor_sha256=old.sha256 if old else None,
        paper=PaperManifestEntry.model_validate(paper), draft=draft, support=support,
        validation_errors=candidate['validation_errors'], entities=definitions,
        entity_revision=mapping_identity(definitions), change_reason=origin + '; pending human review')
    if old:
        propose_revision(directory, revision, chunks)
    else:
        with review_lock(directory):
            existing = state(directory)['current'].get(revision.claim_id)
            if existing:
                return existing
            if sum(r.paper.paper_id == chunk.paper_id for r in state(directory)['current'].values()) >= 12:
                raise ValueError('At most 12 current proposals per paper; correct an existing claim instead')
            append_event(directory, 'revision', revision.model_dump(mode='json'))
    return revision


def propose_claim(registry, collection_id, expected_head, draft, chunk_id, settings, *,
                  entity_ids=None, supersedes=None, expected_revision=None) -> ReviewRevision:
    """Register a manual/corrected proposal only; never record a human approval."""
    with registry.query_lock():
        ready = verify_collection(registry, collection_id, settings, expected_head)
        return _register(registry, ready, draft, chunk_id, entity_ids or {}, supersedes,
                         expected_revision, 'User-entered source-bound proposal')


def present_claim(registry, collection_id, expected_head, claim_id, settings) -> ReviewPresentation:
    """Save an immutable full presentation before collecting a human verdict."""
    with registry.query_lock():
        ready = verify_collection(registry, collection_id, settings, expected_head)
        directory = review_directory(registry, ready)
        with review_lock(directory):
            current = state(directory)
            revision = current['current'][claim_id]
            chunks = load_corpus_chunks(ready.collection.corpus_id)
            excerpts = [SourceExcerpt(chunk_id=s.chunk_id, paper_id=s.paper_id,
                source_sha256=s.source_sha256, source_url=chunks[s.chunk_id].source_url,
                page=chunks[s.chunk_id].page, section=chunks[s.chunk_id].section,
                chunk_page_start=chunks[s.chunk_id].page_start, start=s.start, end=s.end,
                text=chunks[s.chunk_id].text[s.start:s.end]) for s in revision.support]
            shown = ReviewPresentation(collection_marker=ready.marker, review_head=current['head'],
                revision=revision, excerpts=excerpts,
                errors=validate_revision(revision, chunks, current['entities']))
            write_immutable(directory/'presentations'/(shown.sha256+'.json'), shown.model_dump_json(indent=2)+'\n')
            return shown


def record_decision(registry, collection_id, expected_head, presentation, response, settings) -> dict:
    """Save genuine UI input against unchanged displayed bindings; index publication is separate."""
    shown = ReviewPresentation.model_validate(presentation.model_dump())
    response = UIResponse.model_validate(response.model_dump())
    if not response.confirmed or response.presentation_sha256 != shown.sha256:
        raise ValueError('Confirm the exact displayed claim, sources and mappings before submitting')
    with registry.query_lock():
        ready = verify_collection(registry, collection_id, settings, expected_head)
        if ready.marker != shown.collection_marker:
            raise ValueError('Displayed review belongs to another collection/revision')
        directory = review_directory(registry, ready)
        presentation_path = directory/'presentations'/(shown.sha256+'.json')
        if not presentation_path.exists():
            raise ValueError('The exact review presentation was not saved; reopen the claim')
        saved = ReviewPresentation.model_validate_json(presentation_path.read_bytes())
        current = state(directory)
        if saved != shown or current['head'] != shown.review_head:
            raise ValueError('Review changed after presentation; reopen the claim before deciding')
        receipt = {'presentation_sha256':shown.sha256, 'response':response.model_dump(mode='json'),
                   'received_at':datetime.now(timezone.utc).isoformat()}
        digest = fingerprint(receipt)
        write_immutable(directory/'human-inputs'/(digest+'.json'),json.dumps(receipt,indent=2)+'\n')
        revision = shown.revision
        decision = HumanDecision(claim_id=revision.claim_id, claim_revision=revision.revision,
            revision_sha256=revision.sha256, source_sha256=revision.paper.source_sha256,
            entity_revision=revision.entity_revision, reviewer=response.reviewer.strip(),
            reviewed_at=receipt['received_at'], review_seconds=response.review_seconds,
            review_time_note='Human-entered seconds' if response.review_seconds is not None else 'Not measured',
            decision=response.decision, reason=response.reason.strip(), origin='human_ui', provenance_sha256=digest)
        return import_decisions(directory,[decision],load_corpus_chunks(ready.collection.corpus_id))


def publish_review(registry, collection_id, expected_head, expected_review_head, settings, *, encoder_factory=None) -> dict:
    """Explicitly rebuild the approved index; a publication failure leaves the journal intact/stale."""
    with registry.query_lock():
        ready = verify_collection(registry, collection_id, settings, expected_head)
        directory = review_directory(registry, ready)
        if state(directory)['head'] != expected_review_head:
            raise ValueError('Review changed; inspect its current state before publishing')
        options = {'encoder_factory':encoder_factory} if encoder_factory is not None else {}
        return synchronize_review(directory,settings,**options)
