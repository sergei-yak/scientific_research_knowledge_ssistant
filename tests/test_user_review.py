"""Synthetic human UI inputs only: no actual paper or genuine human approval is fabricated."""

from contextlib import contextmanager
import json
import io
from types import SimpleNamespace
from uuid import uuid4

import pytest

from research_assistant.collections import proposals, reviews, workspace
from research_assistant.extraction.contracts import ExtractionResponse, ProposedClaim
from research_assistant.ingestion.sources import load_corpus_chunks
from research_assistant.review.facts import projection
from research_assistant.review.store import state
from test_user_workspace import scene, prepare_ui, button, ask


@pytest.fixture
def review_scene(scene,monkeypatch):
    from research_assistant.graph import reviews as graph_reviews
    monkeypatch.setattr(reviews,'verify_collection',workspace.verify_collection)
    monkeypatch.setattr(proposals,'verify_collection',workspace.verify_collection)
    stored = {}
    class Repo:
        def __init__(self,*args): pass
        def publish(self,corpus,review,vectors,revision):
            stored[corpus] = review
            return {'active_facts':len(review['facts'])}
        def active_facts(self,corpus,head):
            if stored[corpus]['review_head'] != head: raise ValueError('Stale graph')
            return stored[corpus]['facts']
        @contextmanager
        def reading(self,corpus,head,*args):
            if corpus not in stored or stored[corpus]['review_head']!=head: raise ValueError('Stale graph')
            yield self
        def check_indexes(self,*args): pass
        def fact_vectors(self,catalog,*args): return {k:[1.0]+[0.0]*383 for k in catalog.facts}
        def close(self): pass
    monkeypatch.setattr(graph_reviews,'ReviewRepository',Repo)
    monkeypatch.setattr(reviews,'SearchRepository',Repo)
    scene.stored_review = stored
    return scene


def proposal(scene,**changes):
    chunk = next(iter(load_corpus_chunks(scene.row.corpus_id).values()))
    values = dict(kind='finding',statement=chunk.text,method='Fixture method',method_aliases=[],
                  dataset=None,dataset_aliases=[],conditions={'metric':None},quotes=[chunk.text])
    values.update(changes)
    return reviews.propose_claim(scene.registry,scene.row.collection_id,scene.row.sha256,
        ProposedClaim(**values),chunk.chunk_id,scene.settings)


def present(scene,revision):
    return reviews.present_claim(scene.registry,scene.row.collection_id,scene.row.sha256,
        revision.claim_id,scene.settings)


def decide(scene,shown,decision='approved',**changes):
    values = dict(presentation_sha256=shown.sha256,reviewer='SYNTHETIC UI TEST',decision=decision,
        reason='Synthetic source support test only',confirmed=True)
    values.update(changes)
    return reviews.record_decision(scene.registry,scene.row.collection_id,scene.row.sha256,
        shown,reviews.UIResponse(**values),scene.settings)


def ready(scene): return workspace.verify_collection(scene.registry,scene.row.collection_id,scene.settings)


def publish(scene):
    directory = scene.registry.review_directory(scene.row)
    return reviews.publish_review(scene.registry,scene.row.collection_id,scene.row.sha256,
        state(directory)['head'],scene.settings,encoder_factory=lambda:scene.encoder)


def test_proposal_is_not_approval_and_full_presentation_replays(review_scene):
    s = review_scene
    revision = proposal(s)
    directory = s.registry.review_directory(s.row)
    assert not projection(directory,load_corpus_chunks(s.row.corpus_id))['facts']
    shown = present(s,revision)
    assert shown.revision == revision and shown.excerpts[0].text == revision.draft.quotes[0]
    assert not shown.errors
    assert reviews.ReviewPresentation.model_validate_json((directory/'presentations'/(shown.sha256+'.json')).read_bytes()) == shown
    assert not reviews.review_status(s.registry,ready(s),s.settings)['ready']
    with pytest.raises(ValueError,match='not ready'): ask(s,mode='graph')


@pytest.mark.parametrize('change',[{'confirmed':False},{'presentation_sha256':'a'*64},
    {'reviewer':' '},{'reason':' '}])
def test_incomplete_or_mismatched_human_input_cannot_approve(review_scene,change):
    s = review_scene
    shown = present(s,proposal(s))
    with pytest.raises(ValueError): decide(s,shown,**change)
    assert not state(s.registry.review_directory(s.row))['decisions']


def test_changed_review_head_and_cross_collection_presentation_rejected(review_scene):
    s = review_scene
    shown = present(s,proposal(s))
    proposal(s,statement='A different synthetic proposal with the same exact quotation.')
    with pytest.raises(ValueError,match='changed after'): decide(s,shown)
    other = s.indexed(name='Other',text='A different synthetic paper and collection.')
    response = reviews.UIResponse(presentation_sha256=shown.sha256,reviewer='SYNTHETIC',decision='approved',reason='Fixture',confirmed=True)
    with pytest.raises(ValueError,match='another collection'):
        reviews.record_decision(s.registry,other.collection_id,other.sha256,shown,response,s.settings)


def test_invalid_quote_needs_correction_not_automatic_approval(review_scene):
    s = review_scene
    shown = present(s,proposal(s,quotes=['An invented quotation absent from the source.']))
    assert shown.errors
    with pytest.raises(ValueError,match='invalid/unresolved'): decide(s,shown)
    decide(s,shown,'needs_review')
    assert not projection(s.registry.review_directory(s.row),load_corpus_chunks(s.row.corpus_id))['facts']


def test_decision_index_publication_revocation_and_fresh_revision(review_scene):
    s = review_scene
    revision = proposal(s)
    decide(s,present(s,revision))
    directory = s.registry.review_directory(s.row)
    decision = state(directory)['decisions'][(revision.claim_id,1)][0]
    assert decision.origin=='human_ui' and decision.review_seconds is None and decision.reviewed_at.tzinfo
    assert (directory/'human-inputs'/(decision.provenance_sha256+'.json')).exists()
    assert not reviews.review_status(s.registry,ready(s),s.settings)['ready']
    assert publish(s)['verified_active_facts']==1
    assert reviews.review_status(s.registry,ready(s),s.settings)['ready']
    decide(s,present(s,revision),'needs_review')
    with pytest.raises(ValueError,match='not ready'): ask(s,mode='hybrid_facts')
    assert publish(s)['verified_active_facts']==0
    chunk = next(iter(load_corpus_chunks(s.row.corpus_id).values()))
    revised = reviews.propose_claim(s.registry,s.row.collection_id,s.row.sha256,revision.draft,
        chunk.chunk_id,s.settings,supersedes=revision.claim_id,expected_revision=revision.sha256)
    assert revised.revision==2 and revised.predecessor_sha256==revision.sha256
    assert (revised.claim_id,2) not in state(directory)['decisions']
    with pytest.raises(ValueError): decide(s,present(s,revision).model_copy(update={'revision':revision}))


def test_entity_identity_sharing_is_explicit_and_alias_edit_invalidates_old_binding(review_scene):
    s = review_scene
    first = proposal(s,kind='evaluation',dataset='Fixture set')
    chunk = next(iter(load_corpus_chunks(s.row.corpus_id).values()))
    dataset = next(e for e in first.entities if e.kind=='dataset')
    draft = first.draft.model_copy(update={'statement':'A second qualified synthetic evaluation.'})
    linked = reviews.propose_claim(s.registry,s.row.collection_id,s.row.sha256,draft,chunk.chunk_id,s.settings,
                                  entity_ids={'dataset':dataset.id})
    assert next(e.id for e in linked.entities if e.kind=='dataset')==dataset.id
    with pytest.raises(ValueError,match='outside this collection'):
        reviews.propose_claim(s.registry,s.row.collection_id,s.row.sha256,draft,chunk.chunk_id,s.settings,
                             entity_ids={'dataset':'foreign'})
    decide(s,present(s,first))
    altered = first.draft.model_copy(update={'method_aliases':['FM']})
    reviews.propose_claim(s.registry,s.row.collection_id,s.row.sha256,altered,chunk.chunk_id,s.settings,
                         supersedes=first.claim_id,expected_revision=first.sha256)
    assert not projection(s.registry.review_directory(s.row),load_corpus_chunks(s.row.corpus_id))['facts']


class LocalDraftClient:
    """Schema-valid synthetic provider result; no neural or network operation."""
    model,digest,last_result = 'synthetic-local','f'*64,None
    def __init__(self,draft=None,fail=False): self.draft,self.fail=draft,fail
    def generate_structured(self,schema,messages):
        if self.fail: raise RuntimeError('Synthetic provider failure')
        response = schema(candidates=[self.draft] if self.draft else [],no_claim_reason=None if self.draft else 'Synthetic empty response')
        return response,SimpleNamespace(model_dump=lambda **kwargs:{'provider':'synthetic','messages':messages})


def test_extraction_drafts_are_unapproved_and_caps_span_collections(review_scene,monkeypatch):
    s = review_scene
    chunk = next(iter(load_corpus_chunks(s.row.corpus_id).values()))
    draft = ProposedClaim(kind='finding',statement=chunk.text,method=None,method_aliases=[],dataset=None,
        dataset_aliases=[],quotes=[chunk.text],conditions={})
    factory = lambda *a,**k:LocalDraftClient(draft)
    result = proposals.extract_proposals(s.registry,s.row.collection_id,s.row.sha256,chunk.chunk_id,s.settings,client_factory=factory)
    assert result['status']=='completed' and result['approved']==0 and len(result['claims'])==1
    assert not state(s.registry.review_directory(s.row))['decisions']
    budget = proposals.extraction_budget(s.registry,chunk.source_sha256)
    assert budget['requests_remaining']==7 and budget['candidates_remaining']==11
    from research_assistant.ingestion import user_import
    from test_user_imports import inline_inspector
    other = s.registry.create('Same bytes elsewhere')
    raw = s.registry._path('sources',chunk.source_sha256+'.pdf').read_bytes()
    monkeypatch.setitem(user_import.run_import.__kwdefaults__,'inspector',inline_inspector)
    monkeypatch.setitem(user_import.run_import.__kwdefaults__,'write_guard',lambda settings:None)
    workspace.import_collection(s.registry,other.collection_id,other.sha256,[('same.pdf',io.BytesIO(raw))],[],
        s.settings,encoder_factory=lambda:s.encoder)
    other = s.registry.get(other.collection_id)
    assert other.documents[0].source_sha256 == chunk.source_sha256
    assert proposals.extraction_budget(s.registry,other.documents[0].source_sha256)['requests_remaining']==7
    assert not (s.registry.review_directory(other)/'config.json').exists()


def test_failed_interrupted_and_inherited_extraction_never_reset_allowance(review_scene,monkeypatch):
    s = review_scene
    chunk = next(iter(load_corpus_chunks(s.row.corpus_id).values()))
    result = proposals.extract_proposals(s.registry,s.row.collection_id,s.row.sha256,chunk.chunk_id,s.settings,
        client_factory=lambda *a,**k:LocalDraftClient(fail=True))
    assert result['status']=='failed'
    assert proposals.extraction_budget(s.registry,chunk.source_sha256)['candidates_remaining']==10
    proposals._append(s.registry,chunk.source_sha256,'reserved',{'id':uuid4().hex,'chunk_id':chunk.chunk_id,'allowance':2})
    budget = proposals.extraction_budget(s.registry,chunk.source_sha256)
    assert budget['unknown_attempts']==1 and budget['requests_remaining']==6 and budget['candidates_remaining']==8
    monkeypatch.setattr(proposals,'prior_usage',lambda:{'format':'user-review-prior-usage-v1','sources':{
        'a'*64:{'requests':8,'candidates':12,'passages':8}}})
    assert proposals.extraction_budget(s.registry,'a'*64)['requests_remaining']==0
    with pytest.raises(ValueError,match='policy/history changed'):
        proposals.extraction_budget(s.registry,chunk.source_sha256)


def test_extraction_rejects_paid_provider_without_touching_sources(review_scene,monkeypatch):
    s = review_scene
    monkeypatch.setattr(proposals,'verify_collection',lambda *a,**k:pytest.fail('No source work'))
    with pytest.raises(ValueError,match='no paid allowance'):
        proposals.extract_proposals(s.registry,s.row.collection_id,s.row.sha256,'none',
            s.settings.model_copy(update={'extraction_provider':'openai'}))


def test_actual_review_ui_requires_explicit_fields_and_keeps_approval_separate_from_publication(review_scene,monkeypatch):
    s = review_scene
    revision = proposal(s)
    app = prepare_ui(s,monkeypatch).run()
    assert not app.exception
    assert next(x for x in app.selectbox if x.label=='Your decision').value is None
    button(app,'Save my decision').click().run()
    assert not state(s.registry.review_directory(s.row))['decisions']
    next(x for x in app.text_input if x.label=='Reviewer name').set_value('SYNTHETIC UI TEST')
    next(x for x in app.selectbox if x.label=='Your decision').set_value('approved')
    next(x for x in app.text_area if x.label=='Your reason').set_value('Synthetic source support only')
    next(x for x in app.checkbox if x.label.startswith('I reviewed this exact')).check()
    button(app,'Save my decision').click().run()
    assert not app.exception
    assert state(s.registry.review_directory(s.row))['decisions']
    assert next(x for x in app.selectbox if x.label=='Retrieval mode').options==['Vector','Hybrid']
    button(app,'Update reviewed index').click().run()
    assert not app.exception
    assert next(x for x in app.selectbox if x.label=='Retrieval mode').options==[
        'Vector','Hybrid','Hybrid + Approved Facts','Graph']


def test_failed_publication_keeps_human_history_and_blocks_fact_modes(review_scene,monkeypatch):
    s = review_scene
    revision = proposal(s)
    decide(s,present(s,revision))
    before = state(s.registry.review_directory(s.row))
    def down(*a,**k): raise RuntimeError('Synthetic unavailable index')
    monkeypatch.setattr(reviews,'synchronize_review',down)
    with pytest.raises(RuntimeError): publish(s)
    assert state(s.registry.review_directory(s.row))['head']==before['head']
    assert not reviews.review_status(s.registry,ready(s),s.settings)['ready']
    with pytest.raises(ValueError,match='not ready'): ask(s,mode='graph')
    assert not s.calls


def test_review_and_extraction_operations_respect_workspace_lock(review_scene):
    s = review_scene
    with s.registry.query_lock():
        with pytest.raises(FileExistsError): proposal(s)
        with pytest.raises(ValueError,match='question is running'):
            s.registry.queue(s.row.collection_id,s.row.sha256,())
    assert not state(s.registry.review_directory(s.row))['current']


def test_journal_corruption_and_missing_configuration_cannot_reset_caps(review_scene):
    s = review_scene
    chunk = next(iter(load_corpus_chunks(s.row.corpus_id).values()))
    proposals.extract_proposals(s.registry,s.row.collection_id,s.row.sha256,chunk.chunk_id,s.settings,
                               client_factory=lambda *a,**k:LocalDraftClient())
    directory = proposals.extraction_budget(s.registry,chunk.source_sha256)['directory']
    path = directory/'events/000001.json'
    raw = path.read_bytes()
    row = json.loads(raw)
    row['payload']['allowance'] = 0
    path.write_text(json.dumps(row),encoding='utf-8')
    with pytest.raises(ValueError,match='chain changed'):
        proposals.extraction_budget(s.registry,chunk.source_sha256)
    path.write_bytes(raw)
    (directory/'config.json').unlink()
    with pytest.raises(ValueError,match='configuration missing'):
        proposals.extraction_budget(s.registry,chunk.source_sha256)


def test_manual_editor_saves_a_pending_source_bound_proposal(review_scene,monkeypatch):
    s = review_scene
    app = prepare_ui(s,monkeypatch).run()
    next(x for x in app.checkbox if x.label=='Enter or correct a proposal manually').check().run()
    chunk = next(iter(load_corpus_chunks(s.row.corpus_id).values()))
    next(x for x in app.text_area if x.label=='Proposed claim').set_value(chunk.text)
    next(x for x in app.text_area if x.label.startswith('Exact quotation(s)')).set_value(chunk.text)
    button(app,'Save unapproved proposal').click().run()
    assert not app.exception and not s.calls
    current = state(s.registry.review_directory(s.row))
    assert len(current['current'])==1 and not current['decisions']
    assert any(x.label=='Your decision' and x.value is None for x in app.selectbox)


def test_review_cli_uses_same_source_and_presentation_contract(review_scene,capsys):
    from research_assistant.collections.__main__ import main
    s = review_scene
    chunk = next(iter(load_corpus_chunks(s.row.corpus_id).values()))
    draft = ProposedClaim(kind='finding',statement=chunk.text,quotes=[chunk.text],method=None,
        method_aliases=[],dataset=None,dataset_aliases=[],conditions={})
    from pathlib import Path
    Path('draft.json').write_text(draft.model_dump_json(),encoding='utf-8')
    common = ['--collection',s.row.collection_id,'--expected-head',s.row.sha256]
    assert main(['review-propose',*common,'--draft','draft.json','--chunk-id',chunk.chunk_id])==0
    revision = json.loads(capsys.readouterr().out)
    assert main(['review-present',*common,'--claim',revision['claim_id'],'--output','shown.json'])==0
    shown = reviews.ReviewPresentation.model_validate_json(Path('shown.json').read_bytes())
    assert shown.revision.draft==draft and not shown.errors
    assert not state(s.registry.review_directory(s.row))['decisions']


def test_cli_failed_extraction_is_a_failure_exit_not_success(review_scene,monkeypatch,capsys):
    from research_assistant.collections.__main__ import main
    s=review_scene
    monkeypatch.setattr(proposals,'extract_proposals',lambda *a,**k:{'status':'failed','message':'Synthetic provider failure','claims':[]})
    assert main(['review-extract','--collection',s.row.collection_id,'--expected-head',s.row.sha256,
                 '--chunk-id','synthetic-chunk'])==1
    assert json.loads(capsys.readouterr().out)['status']=='failed'
