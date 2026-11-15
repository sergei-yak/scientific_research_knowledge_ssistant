"""V2 contracts, immutable legacy bindings, real failure boundaries and fallback telemetry."""
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from research_assistant.contracts import ExperimentScope, QueryRequest, fingerprint
from research_assistant.graph.scope import guard_development_write
from research_assistant.graph.templates_v2 import traversal_templates_v2
from research_assistant.ingestion.sources import source_identity
from research_assistant.pipeline import run_query
from research_assistant.retrieval.anchors import graph_anchors, unambiguous_matches
from research_assistant.retrieval.profiles import load_scope, reference_profile, validate_scope
from research_assistant.retrieval.service import retrieve_modes
from research_assistant.review.contracts import EntityDefinition, mapping_identity
from research_assistant.review.facts import eligible, projection
from research_assistant.review.store import append_event, import_decisions, review_lock
from research_assistant.settings import Settings
from test_controlled_retrieval import Repo, Encoder, CORPUS
from test_review_workflow import fixture, human


def scoped_fixture(tmp_path,monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path/'.git').write_text('gitdir: fixture',encoding='utf-8')
    repo=Repo();repo.catalog.head='c'*64
    root=tmp_path/'data/scopes';root.mkdir(parents=True)
    review=tmp_path/'data/reviews/fixture'
    target='dbu-m4-recovery-m5dev-'+'a'*12
    value=dict(profile_id='retrieval-v2',scope_id='m5dev-'+'a'*12,corpus_id=CORPUS,
        source_chunks_sha256=source_identity(repo.chunks),review_head=repo.catalog.head,
        review_directory=str(review),target_id=target,snapshot_sha256='a'*64,target_uri='bolt://127.0.0.1:12345',
        container_id='b'*64,image_id='sha256:'+'c'*64,volumes=[target+'_neo4j_data',target+'_neo4j_logs'],
        baseline_root=str(tmp_path/'baseline'),baseline_graph_sha256='d'*64)
    (root/'retrieval-v2.json').write_text(json.dumps(value),encoding='utf-8')
    request=QueryRequest(question='anchor',corpus_id=CORPUS,profile_id='retrieval-v2',scope_file='data/scopes/retrieval-v2.json')
    settings=Settings(neo4j_uri=value['target_uri'])
    monkeypatch.setattr('research_assistant.retrieval.profiles.attest_target',lambda *args:{
        'container_id':value['container_id'],'image_id':value['image_id'],'volumes':sorted(value['volumes'])})
    row={'scope':value['scope_id'],'profile':value['profile_id'],'frozen':False,'binding':fingerprint(value)}
    repo.tx=SimpleNamespace(run=lambda *args,**kwargs:SimpleNamespace(single=lambda:row))
    return request,settings,review,repo,value,row


def test_default_and_selector_contracts_and_unavailable_synthesis():
    request=QueryRequest(question='anchor',corpus_id=CORPUS)
    assert request.profile_id=='baseline' and request.selector_id=='reference'
    assert reference_profile('retrieval-v2')==reference_profile('retrieval-v2')
    assert reference_profile('baseline').policy_sha256!=reference_profile('retrieval-v2').policy_sha256
    with pytest.raises(ValidationError):
        QueryRequest(question='anchor',corpus_id=CORPUS,selector_id='unapproved-model')
    with pytest.raises(ValueError,match='retrieval-only'):
        run_query(request.model_copy(update={'profile_id':'retrieval-v2'}),Settings(),generate=True)


def test_scope_rejects_external_path_before_reading(tmp_path):
    request=QueryRequest(question='anchor',corpus_id=CORPUS,profile_id='retrieval-v2',scope_file=str(tmp_path/'private.json'))
    with pytest.raises(ValueError,match='inside this worktree'):
        load_scope(request)


@pytest.mark.parametrize('change',['target','review','source','head','database_scope','frozen','profile','container','snapshot_binding'])
def test_scope_mismatch_fails_closed(tmp_path,monkeypatch,change):
    request,settings,review,repo,value,row=scoped_fixture(tmp_path,monkeypatch)
    if change=='target':settings=settings.model_copy(update={'neo4j_uri':'bolt://127.0.0.1:7687'})
    if change=='review':review=review.parent/'other'
    if change=='source':repo.chunks={}
    if change=='head':repo.catalog.head='d'*64
    if change=='database_scope':row['scope']='another'
    if change=='frozen':row['frozen']=True
    if change=='profile':request=request.model_copy(update={'corpus_id':'f'*64})
    if change=='snapshot_binding':
        path=tmp_path/request.scope_file
        revised={**value,'snapshot_sha256':'e'*64}
        path.write_text(json.dumps(revised),encoding='utf-8')
    if change=='container':monkeypatch.setattr('research_assistant.retrieval.profiles.attest_target',lambda *args:{'container_id':'f'*64,'image_id':value['image_id'],'volumes':sorted(value['volumes'])})
    with pytest.raises(ValueError,match='scope|mismatch|identity'):
        validate_scope(request,settings,review,repo.chunks,repo.catalog,repo)


def test_exact_scope_is_accepted_and_old_target_writes_rejected(tmp_path,monkeypatch):
    request,settings,review,repo,value,_=scoped_fixture(tmp_path,monkeypatch)
    assert validate_scope(request,settings,review,repo.chunks,repo.catalog,repo).scope_id==value['scope_id']
    with pytest.raises(ValueError,match='outside the isolated'):
        guard_development_write(Settings())


def test_anchor_caps_longest_alias_unicode_and_ambiguity():
    repo=Repo()
    for identity,name in [('m1','Alpha'),('m2','Alpha Beta'),('m3','Ambiguous One'),('m4','Ambiguous Two')]:
        repo.catalog.entities[identity]=EntityDefinition(id=identity,kind='method',name=name,aliases=['MA'] if identity in ('m3','m4') else [])
    assert unambiguous_matches('Use \uff2d\uff21.',repo.catalog.entities)=={}
    evidence=[repo.facts['base-fact']['evidence']]
    from research_assistant.contracts import EvidenceItem
    items=[EvidenceItem.model_validate(evidence[0]).model_copy(update={'id':str(i)}) for i in range(6)]
    anchors,hits,shown,expansion=graph_anchors('Alpha Beta and SharedSet',items,repo.catalog)
    assert len(anchors)==4 and len({a['id'] for a in anchors})==4
    assert [a['entity_id'] for a in anchors if a['type']=='entity']==['m2','dataset-shared']
    assert expansion['method']==['m2'] and expansion['dataset']==['dataset-shared']
    assert 'm1' in hits


def test_v2_static_routes_have_union_wide_caps_and_no_mentions_promotion():
    routes=traversal_templates_v2(CORPUS)
    assert set(routes)=={'shared_method','shared_dataset','citation','finding'}
    for sql in routes.values():
        assert sql.count('LIMIT 5')==1 and sql.rfind('ORDER BY')<sql.rfind('LIMIT 5')
        assert 'MENTIONS' not in sql and '*..' not in sql and '*1..' not in sql
        assert 'experiment_scope_id:$scope_id' in sql and 't.reporting_paper_id=tp.id' in sql
    assert 'REPORTS_FINDING|REPORTS_EVALUATION' in routes['shared_method']
    assert 'USING INDEX e:Method(id)' in routes['shared_method']
    assert 'USING INDEX e:Dataset(id)' in routes['shared_dataset']
    with pytest.raises(ValueError):traversal_templates_v2('untrusted` schema')


def v2(repo,mode='graph'):
    old=repo.fact_vectors
    repo.fact_vectors=lambda *args,**kwargs:old(*args)
    old_traverse=repo.traverse
    repo.traverse=lambda *args,**kwargs:old_traverse(*args)
    return retrieve_modes(QueryRequest(question='SharedSet anchor',corpus_id=CORPUS,mode=mode),
        repo,Encoder(),repo.chunks,None if mode=='hybrid' else repo.catalog,'fixture',
        profile_id='retrieval-v2',scope_id='synthetic')


@pytest.mark.parametrize('oversized',[False,True])
def test_actual_prefallback_traces_survive_exact_fallback(oversized):
    repo=Repo()
    if oversized:repo.facts['target-fact']['evidence']['claim_text']='Large claim '*4000
    else:repo.paths=False
    baseline=v2(Repo(),'hybrid_facts')
    result=v2(repo)
    assert result.context_sha256==baseline.context_sha256 and result.evidence==baseline.evidence
    assert result.effective_mode=='hybrid_facts'
    assert 'pre_fallback_candidate_trace' in result.audit
    if oversized:
        row=next(r for r in result.audit['pre_fallback_candidate_trace'] if r['candidate_id']=='target-fact')
        assert not row['selected'] and row['exclusion_reason']=='token_budget'
        assert not row['baseline_member'] and row['estimated_tokens']>1800
    else:assert result.audit['new_graph_candidates']==[]


def test_baseline_pool_parity_and_new_source_bound_graph_addition():
    repo=Repo();baseline=v2(repo,'hybrid_facts');graph=v2(Repo())
    assert baseline.audit['channel_rankings']==graph.audit['channel_rankings']
    assert graph.effective_mode=='graph' and graph.audit['selected_graph_additions']==['target-fact']
    assert graph.audit['generated_rows']<=80 and len(graph.audit['anchors'])<=4
    assert len(graph.evidence)<=6 and graph.estimated_tokens<=1800


def test_new_role_changes_bindings_requires_new_decision_and_revokes(tmp_path):
    root=tmp_path/'synthetic';old,chunks=fixture(root)
    legacy=old.model_dump();assert 'relation_roles' not in legacy
    assert old.sha256==fingerprint(legacy)
    dataset=EntityDefinition(id='dataset-test',kind='dataset',name='TestSet',aliases=[])
    entities=[*old.entities,dataset]
    draft=old.draft.model_copy(update={'dataset':'TestSet'})
    roles={dataset.id:'ABOUT_DATASET'}
    revision=old.model_copy(update={'revision':2,'predecessor_sha256':old.sha256,'draft':draft,
        'entities':entities,'relation_roles':roles,'entity_revision':mapping_identity(entities,roles)})
    assert revision.sha256!=old.sha256 and revision.entity_revision!=old.entity_revision
    definitions={e.id:e for e in entities}
    assert not eligible(revision,human(old),chunks,definitions)
    assert eligible(revision,human(revision),chunks,definitions)
    with review_lock(root):append_event(root,'revision',revision.model_dump(mode='json'))
    assert projection(root,chunks)['facts']==[]
    import_decisions(root,[human(revision)],chunks)
    assert projection(root,chunks)['facts'][0]['relation_roles']==roles
    import_decisions(root,[human(revision,'needs_review',1)],chunks)
    assert projection(root,chunks)['facts']==[]


@pytest.mark.parametrize('error',['stale','timeout','owner'])
def test_v2_failures_remain_errors_instead_of_mode_fallback(error):
    repo=Repo();repo.error=error
    with pytest.raises((ValueError,TimeoutError)):v2(repo)


def test_union_wide_row_overflow_is_rejected():
    repo=Repo();old=repo.traverse
    repo.traverse=lambda *args: (old(*args)[0]*6,None)
    with pytest.raises(ValueError,match='union-wide row bound'):v2(repo)
