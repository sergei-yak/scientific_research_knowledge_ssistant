"""Adversarial source, ranking, graph budget and exact fallback boundaries."""

from contextlib import contextmanager

import pytest

from research_assistant.contracts import Chunk, EvidenceItem, QueryRequest, SourceExcerpt, text_sha
from research_assistant.retrieval.catalog import ReviewCatalog, alias_matches, chunk_evidence, cosine, lexical_query
from research_assistant.retrieval.service import retrieve_modes
from research_assistant.review.contracts import EntityDefinition
from research_assistant.graph.templates import traversal_templates

CORPUS='a'*64
VECTOR=[1.0]+[0.0]*383


class Encoder:
    def encode(self,texts):
        return [VECTOR for _ in texts]


def source(key,paper='paper-a',text='Anchor SharedSet evidence.'):
    return Chunk(chunk_id=key,paper_id=paper,source_sha256='b'*64,source_url='https://example.invalid',
        page=1,section='Synthetic',page_start=0,page_end=len(text),text=text,text_sha256=text_sha(text),
        parser_version='test',chunker_version='test',mini_tokens=20,mpnet_tokens=20)


def fact(key,chunk):
    item=EvidenceItem(id=key,kind='approved_fact',approved_claim_ids=['claim-'+key],claim_revision=1,
        claim_text=chunk.text,conditions={'dataset':'SharedSet'},excerpts=chunk_evidence(chunk).excerpts,
        retrieval_origin='approved_fact')
    return {'id':key,'claim_id':'claim-'+key,'claim_revision':1,'paper_id':chunk.paper_id,
            'evidence':item.model_dump(),'entities':[]}


class Repo:
    project='SYNTHETIC'

    def __init__(self):
        self.chunks={'chunk-base':source('chunk-base')}
        self.facts={'base-fact':fact('base-fact',self.chunks['chunk-base']),
                    'target-fact':fact('target-fact',source('chunk-target','paper-b'))}
        entity=EntityDefinition(id='dataset-shared',kind='dataset',name='SharedSet',aliases=['SS'])
        self.catalog=ReviewCatalog(CORPUS,'h'*64,self.facts,{entity.id:entity})
        self.paths=True
        self.error=None
        self.calls=0

    @contextmanager
    def reading(self,corpus,head,timeout):
        if self.error=='stale':
            raise ValueError('Review projection is stale')
        yield self

    def check_indexes(self,*args):
        pass

    def fact_vectors(self,*args):
        return {key:VECTOR for key in self.facts}

    def ranked(self,corpus,kind,channel,*args):
        keys=['chunk-base'] if kind=='chunk' else ['base-fact']
        return [{'id':key,'source':self.chunks[key].model_dump_json() if kind=='chunk' else None,
                 'vector':VECTOR,'score':500 if channel=='text' else 0.99,'similarity':1.0} for key in keys]

    def traverse(self,corpus,template,params):
        if self.error=='timeout':
            raise TimeoutError('Synthetic query deadline')
        self.calls+=1
        if not self.paths:
            return [],None
        f=self.facts['target-fact']
        row={'fact_id':f['id'],'reporting_paper':f['paper_id'],'claim_id':f['claim_id'],
             'revision':1,'support_chunk':'chunk-target',
             'node_ids':['chunk-base','paper-a','eval-a','entity','eval-b','chunk-target'],
             'entity_ids':['dataset-shared'],'direction':'shared'}
        if self.error=='owner':
            row['reporting_paper']='wrong-paper'
        if template=='citation':
            row['node_ids']=['chunk-base','paper-a','paper-b','eval-b','chunk-target']
        return [row],None


def run(repo,mode='graph',question='SharedSet evidence?'):
    return retrieve_modes(QueryRequest(question=question,corpus_id=CORPUS,mode=mode),repo,Encoder(),
        repo.chunks,None if mode=='hybrid' else repo.catalog,'fixture')


def test_real_expansion_adds_a_new_paper_outside_the_identical_four_channel_pool():
    repo=Repo()
    baseline=run(repo,'hybrid_facts')
    graph=run(repo)
    assert baseline.audit['channel_rankings']==graph.audit['channel_rankings']
    assert 'target-fact' not in {row['id'] for row in baseline.audit['fusion']}
    target=next(e for e in graph.evidence if e.id=='target-fact')
    assert target.paper_ids==['paper-b'] and target.graph_paths[0]['length']==4
    assert target.graph_paths[0]['template']=='citation'
    assert graph.effective_mode=='graph' and graph.fallback_reason is None
    assert graph.estimated_tokens<=1800 and len(graph.evidence)<=6


@pytest.mark.parametrize('oversized',[False,True])
def test_no_new_surviving_item_returns_exact_baseline_evidence_and_context(oversized):
    repo=Repo()
    baseline=run(repo,'hybrid_facts')
    if oversized:
        repo.facts['target-fact']['evidence']['claim_text']='Very large source-backed synthetic claim. '*4000
    else:
        repo.paths=False
    result=run(repo)
    assert result.requested_mode=='graph' and result.effective_mode=='hybrid_facts'
    assert result.fallback_reason==('graph_candidates_not_selected_within_budget' if oversized else 'no_new_eligible_graph_candidates')
    for field in ['evidence','context','aliases','estimated_tokens','context_sha256','candidates']:
        assert getattr(result,field)==getattr(baseline,field)


@pytest.mark.parametrize('error',['stale','timeout','owner'])
def test_unavailable_or_contaminated_graph_is_an_error_not_silent_fallback(error):
    repo=Repo()
    repo.error=error
    with pytest.raises((ValueError,TimeoutError)):
        run(repo)


def test_hybrid_has_only_chunk_channels_and_never_loads_or_traverses_facts():
    repo=Repo()
    repo.fact_vectors=lambda *args:pytest.fail('Hybrid must not read approved facts')
    result=run(repo,'hybrid')
    assert set(result.audit['channel_rankings'])=={'chunk_vector','chunk_text'}
    assert all(item.kind=='chunk' for item in result.evidence) and repo.calls==0


def test_seed_fallback_aliases_never_increase_question_overlap():
    repo=Repo()
    result=run(repo,question='anchor evidence')
    assert result.audit['question_entity_ids']==[]
    assert result.audit['expansion_entity_ids']==['dataset-shared']
    assert all(row['question_entity_overlap']==0 for row in result.audit['merged_ranking'])


def test_method_mentions_do_not_suppress_a_dataset_explicitly_shown_in_seeds():
    repo=Repo()
    method=EntityDefinition(id='method-one',kind='method',name='MethodOne',aliases=[])
    repo.catalog.entities[method.id]=method
    result=run(repo,question='MethodOne evidence')
    assert result.audit['question_entity_ids']==['method-one']
    assert result.audit['expansion_entities_by_kind']=={'method':['method-one'],'dataset':['dataset-shared']}
    assert all('dataset-shared' in call['parameters']['entity_ids'] for call in result.audit['graph_calls'])
    assert all(row['question_entity_overlap']==0 for row in result.audit['merged_ranking'])


def test_alias_normalization_boundaries_and_ambiguity_are_not_name_based_merges():
    a=EntityDefinition(id='one',kind='method',name='Method One',aliases=['MA'])
    b=EntityDefinition(id='two',kind='method',name='Method Two',aliases=['MA'])
    entities={a.id:a,b.id:b}
    assert alias_matches('Use \uff2d\uff21.',entities)=={'one','two'}
    assert alias_matches('use small systems',entities)==set()
    assert lexical_query('a:b OR *:* "x"')=='"a" OR "b" OR "or" OR "x"'


def test_source_mismatch_rejects_both_raw_and_fused_queries():
    repo=Repo()
    expected=repo.chunks.copy()
    repo.chunks['chunk-base']=source('chunk-base',text='Changed source text.')
    with pytest.raises(ValueError,match='immutable source cache'):
        retrieve_modes(QueryRequest(question='anchor',corpus_id=CORPUS,mode='hybrid'),repo,Encoder(),expected,None,'fixture')


def test_four_fixed_routes_have_ordered_limits_and_safe_schema_identifiers():
    templates=traversal_templates(CORPUS)
    assert set(templates)=={'shared_dataset','shared_method','citation','finding'}
    for query in templates.values():
        assert 'USING INDEX p:Paper(id)' in query and query.rfind('ORDER BY')<query.rfind('LIMIT 5')
        assert 'head_sha256:$head' in query and 't.reporting_paper_id=tp.id' in query
        assert '*1..' not in query and '*..' not in query
    with pytest.raises(ValueError):
        traversal_templates('bad` arbitrary Cypher')


def test_graph_limits_four_seeds_eighty_rows_and_forty_unique_targets():
    repo=Repo()
    for number in range(8):
        key=f'chunk-{number}'
        repo.chunks[key]=source(key).model_copy(update={'page':number+2})
    def ranked(corpus,kind,channel,*args):
        if kind=='fact':
            return []
        return [{'id':key,'source':c.model_dump_json(),'vector':VECTOR,'score':1,'similarity':1}
                for key,c in sorted(repo.chunks.items())]
    repo.ranked=ranked
    for number in range(80):
        repo.facts[f'g-{number}']=fact(f'g-{number}',source(f'target-{number}','paper-b'))
    def traverse(corpus,template,params):
        start=repo.calls*5
        repo.calls+=1
        return [{'fact_id':f'g-{n}','reporting_paper':'paper-b','claim_id':f'claim-g-{n}','revision':1,
                 'support_chunk':f'target-{n}','node_ids':['s','p','q','t',f'target-{n}'],
                 'entity_ids':[],'direction':'synthetic'} for n in range(start,start+5)],None
    repo.traverse=traverse
    result=run(repo)
    assert repo.calls==16 and result.audit['graph_rows']==80
    assert len(result.audit['graph_candidates_retained'])==40
    assert len(result.evidence)<=6 and result.estimated_tokens<=1800


def test_invalid_vectors_fail_before_comparing_ranking_scores():
    with pytest.raises(ValueError,match='vector'):
        cosine(VECTOR,[float('nan')]*384)
    with pytest.raises(ValueError,match='vector'):
        cosine(VECTOR,[1.0]*768)


def test_question_alias_overlap_precedes_cosine_and_all_rendered_paths_count():
    repo=Repo()
    method=EntityDefinition(id='method-new',kind='method',name='NewMethod',aliases=[])
    repo.catalog.entities[method.id]=method
    repo.facts['target-fact']['evidence']['claim_text']='NewMethod uses SharedSet in this synthetic study.'
    repo.fact_vectors=lambda *args:{'base-fact':VECTOR,'target-fact':[0.0,1.0]+[0.0]*382}
    result=run(repo,question='NewMethod SharedSet')
    assert result.evidence[0].id=='target-fact'
    assert '"paths":' in result.context
    from research_assistant.retrieval.evidence import estimate_tokens
    assert estimate_tokens(result.context)==result.estimated_tokens<=1800


@pytest.mark.parametrize('timeout',[0,0.0001,31,float('nan')])
def test_timeout_configuration_cannot_disable_or_exceed_the_deadline(timeout):
    from pydantic import ValidationError
    from research_assistant.settings import Settings
    with pytest.raises(ValidationError):
        Settings(graph_query_timeout_seconds=timeout)


def test_ask_service_uses_the_selected_mode_and_exact_shared_context(monkeypatch):
    import research_assistant.pipeline as pipeline
    import research_assistant.retrieval.service as service
    from research_assistant.contracts import AnswerResult
    from research_assistant.settings import Settings
    repo=Repo()
    result=run(repo)
    snapshot={'encoder_revision':'fixture'}
    monkeypatch.setattr(service,'retrieve_request',lambda *args:(snapshot,result))
    monkeypatch.setattr(pipeline,'code_identity',lambda:{'code_revision':'test','code_dirty':False,'source_tree_sha256':'x'})
    monkeypatch.setattr(pipeline,'check_resources',lambda:{})
    monkeypatch.setattr(pipeline,'OllamaClient',lambda *args:object())
    def answer(question,retrieval,client):
        assert retrieval is result and retrieval.context==result.context
        assert retrieval.requested_mode=='graph' and client is not None
        return AnswerResult(answer='Synthetic answer',insufficient_evidence=True,citations=[]),None
    monkeypatch.setattr(pipeline,'answer_question',answer)
    artifact=pipeline.ask_question(QueryRequest(question='SharedSet',corpus_id=CORPUS,mode='graph'),Settings())
    assert artifact.retrieval is result and artifact.request.mode=='graph'
