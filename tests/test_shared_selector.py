"""Cross-mode feature/score/budget tests without downloading or loading neural weights."""
import json
import hashlib
from pathlib import Path
from types import SimpleNamespace

import pytest
import torch

from research_assistant.contracts import QueryRequest
from research_assistant.pipeline import retrieve_vector
from research_assistant.retrieval.catalog import chunk_evidence
from research_assistant.retrieval.profiles import retrieval_profile
from research_assistant.retrieval.reranker import LocalCrossEncoder,RerankerError,verified_manifest
from research_assistant.retrieval.selection import SelectorSession,canonical_text
from research_assistant.retrieval.service import retrieve_modes
from test_controlled_retrieval import Repo,Encoder,source,CORPUS


class ScalarScorer:
    """Content-based fixed synthetic logits; records exactly what the shared interface sees."""
    def __init__(self):self.calls=[]
    def score_pairs(self,pairs):
        self.calls.extend(pairs)
        return [9.0 if 'target-fact' in text else -2.0 for q,text in pairs],[30]*len(pairs)


def session(count=4,scorer=None):
    chunks={str(i):source(str(i),text='Complete synthetic source '+str(i)) for i in range(count)}
    return SelectorSession('Question?',chunks,None,scorer or ScalarScorer()),[chunk_evidence(c) for c in chunks.values()]


def test_88_unique_candidates_include_seed_scoring_and_cache_reuse():
    selector,items=session(89)
    selector.order(items[:48],{i.id:n for n,i in enumerate(items[:48],1)},'baseline')
    selector.order(items[:88],{i.id:n for n,i in enumerate(items[:48],1)},'graph')
    assert len(selector.scorer.calls)==selector.pairs_inferred==88
    assert selector.snapshot()['stages']['graph']['new_pairs_inferred']==40
    selector.order(items[:48],{},'repeat')
    assert len(selector.scorer.calls)==88
    with pytest.raises(RerankerError,match='88 unique'):selector.order(items,{},'overflow')
    assert len(selector.scorer.calls)==88


def test_raw_scores_tie_by_original_rank_then_id_with_no_graph_slot_or_origin_bonus():
    selector,items=session()
    result=selector.order([items[3],items[2],items[1],items[0]],{'2':2,'1':1},'ties')
    assert [i.id for i in result]==['1','2','0','3']
    assert all(v==-2.0 for v in selector.scores.values())


def test_paths_and_pool_membership_do_not_change_features_or_scores():
    first,items=session()
    second,_=session()
    first.order(items[:2],{},'one')
    moved=items[0].model_copy(update={'graph_paths':[{'template':'synthetic'}],'retrieval_origin':'graph','rank':99})
    second.order([items[3],moved],{},'two')
    assert first.features['0']==second.features['0'] and first.scores['0']==second.scores['0']
    assert first.scorer.calls[0]==second.scorer.calls[1]


@pytest.mark.parametrize('failure',['nan','inf','wrong_count','length'])
def test_invalid_model_result_stops_without_fallback_or_partial_cache(failure):
    class Bad:
        def score_pairs(self,pairs):
            if failure=='wrong_count':return [],[]
            return [float(failure) if failure in ('nan','inf') else 2.0]*len(pairs),[513 if failure=='length' else 4]*len(pairs)
    selector,items=session(scorer=Bad())
    with pytest.raises(RerankerError) as error:selector.order(items,{},'bad')
    assert error.value.selection_diagnostics['selection_stage']=='bad'
    assert selector.pairs_inferred==0 and not selector.cache


def test_duplicate_identity_and_changed_feature_are_rejected():
    selector,items=session()
    with pytest.raises(RerankerError,match='Duplicate'):selector.order([items[0],items[0]],{},'duplicate')
    selector.order(items[:1],{},'first')
    selector.question='Different question'
    with pytest.raises(RerankerError,match='changed within'):selector.order(items[:1],{},'changed')


def fake_native(monkeypatch):
    model=object.__new__(LocalCrossEncoder)
    monkeypatch.setattr(LocalCrossEncoder,'_runtime',staticmethod(lambda _:None))
    model.tokenizer=lambda q,p,**kwargs:{'input_ids':torch.zeros((1,len(q.split())+len(p.split())+3),dtype=torch.long)}
    class Network:
        calls=0
        def __call__(self,**kwargs):
            self.calls+=1
            return SimpleNamespace(logits=torch.tensor([[3.25]]))
    model.model=Network()
    return model


def test_native_pair_preflight_rejects_without_silent_truncation_or_any_forward(monkeypatch):
    model=fake_native(monkeypatch)
    with pytest.raises(RerankerError,match='512-token'):
        model.score_pairs([('short','short'),('x '*510,'y')])
    assert model.model.calls==0
    scores,lengths=model.score_pairs([('x '*508,'y')])
    assert lengths==[512] and scores==[3.25] and model.model.calls==1
    with pytest.raises(RerankerError,match='pair bound'):model.score_pairs([('q','p')]*89)


def complete_repo():
    repo=Repo()
    for key,fact in repo.facts.items():fact['embedding_text']=json.dumps({'paper':fact['paper_id'],'assertion':key})
    old=repo.fact_vectors;repo.fact_vectors=lambda *args,**kwargs:old(*args)
    old_traverse=repo.traverse;repo.traverse=lambda *args,**kwargs:old_traverse(*args)
    return repo


def scored_mode(repo,mode):
    selector=SelectorSession('SharedSet anchor',repo.chunks,repo.catalog,ScalarScorer())
    result=retrieve_modes(QueryRequest(question='SharedSet anchor',corpus_id=CORPUS,mode=mode),repo,Encoder(),repo.chunks,
        None if mode=='hybrid' else repo.catalog,'fixture',profile_id='retrieval-v2',scope_id='synthetic',selector=selector)
    return result,selector


def test_same_fact_features_scores_across_ablation_and_graph_and_identical_fallback():
    ablation,a=scored_mode(complete_repo(),'hybrid_facts')
    repo=complete_repo();repo.paths=False
    graph,g=scored_mode(repo,'graph')
    assert a.features==g.features and a.scores==g.scores
    for key in ('context','evidence','aliases','estimated_tokens','context_sha256','candidates'):
        assert getattr(graph,key)==getattr(ablation,key)
    assert graph.effective_mode=='hybrid_facts' and graph.audit['selection']['pairs_inferred']==2
    assert graph.audit['selection']['stages']['graph']['new_pairs_inferred']==0


def test_supported_new_graph_candidate_can_be_selected_and_model_failure_never_falls_back():
    result,selector=scored_mode(complete_repo(),'graph')
    assert result.evidence[0].id=='target-fact' and result.effective_mode=='graph'
    assert result.audit['selection']['pairs_inferred']==3
    repo=complete_repo()
    class Broken:
        def score_pairs(self,pairs):raise RerankerError('Synthetic unavailable model')
    selector=SelectorSession('SharedSet',repo.chunks,repo.catalog,Broken())
    with pytest.raises(RerankerError,match='unavailable model'):
        retrieve_modes(QueryRequest(question='SharedSet',corpus_id=CORPUS,mode='graph'),repo,Encoder(),repo.chunks,repo.catalog,
                       'fixture',profile_id='retrieval-v2',scope_id='synthetic',selector=selector)


def test_high_model_score_never_overrides_atomic_budget_and_fallback_is_exact():
    repo=complete_repo()
    repo.facts['target-fact']['evidence']['claim_text']='Synthetic oversized fact. '*4000
    graph,_=scored_mode(repo,'graph')
    ablation,_=scored_mode(complete_repo(),'hybrid_facts')
    assert graph.effective_mode=='hybrid_facts'
    for field in ('context','context_sha256','evidence','aliases','estimated_tokens','candidates'):
        assert getattr(graph,field)==getattr(ablation,field)
    row=next(r for r in graph.audit['selection']['stages']['graph']['candidate_trace'] if r['candidate_id']=='target-fact')
    assert row['score']==9.0 and row['exclusion_reason']=='token_budget' and not row['selected']


def test_fact_canonical_input_is_approved_embedding_text_and_rejects_changed_claim():
    repo=complete_repo()
    from research_assistant.contracts import EvidenceItem
    fact=repo.facts['base-fact'];item=EvidenceItem.model_validate(fact['evidence'])
    assert canonical_text(item,repo.chunks,repo.catalog)==fact['embedding_text']
    with pytest.raises(ValueError,match='approved revision'):
        canonical_text(item.model_copy(update={'claim_text':'Changed'}),repo.chunks,repo.catalog)
    raw=chunk_evidence(repo.chunks['chunk-base'])
    with pytest.raises(RerankerError,match='full source'):
        canonical_text(raw.model_copy(update={'excerpts':[]}),repo.chunks,repo.catalog)


def test_vector_eligibility_is_applied_before_the_same_selector_and_packer():
    chunks={'1':source('1'),'2':source('2')}
    repo=SimpleNamespace(vector_candidates=lambda *args:[(chunks['1'],0.8),(chunks['2'],0.2)])
    selector=SelectorSession('q',chunks,None,ScalarScorer())
    result=retrieve_vector(QueryRequest(question='q',corpus_id=CORPUS),repo,Encoder(),selector=selector)
    assert len(selector.scorer.calls)==1 and result.candidates[1]['reason']=='similarity_threshold'
    assert result.audit['selection']['unique_candidates']==1


def test_reference_is_independent_of_model_readiness_and_baseline_cannot_claim_reranking(monkeypatch):
    monkeypatch.setattr('research_assistant.retrieval.reranker.verified_manifest',lambda:pytest.fail('Reference must not load reranker'))
    assert retrieval_profile('baseline').selector_id=='reference'
    assert retrieval_profile('retrieval-v2').selector_id=='reference'
    with pytest.raises(ValueError,match='combination'):retrieval_profile('baseline','cross_encoder')


@pytest.mark.parametrize('change',['weight','runtime','directory','file_set'])
def test_pinned_asset_and_runtime_tampering_fails_before_inference(tmp_path,monkeypatch,change):
    manifest=json.loads(Path('manifests/reranker-msmarco-minilm-l6-v1.json').read_text(encoding='utf-8'))
    monkeypatch.chdir(tmp_path)
    directory=tmp_path/'.cache/rerankers/synthetic';directory.mkdir(parents=True)
    files={}
    for name in manifest['files']:
        (directory/name).write_bytes(b'SYNTHETIC TEST DATA')
        files[name]=hashlib.sha256(b'SYNTHETIC TEST DATA').hexdigest()
    manifest.update(asset_directory='.cache/rerankers/synthetic',files=files,asset_bytes=len(b'SYNTHETIC TEST DATA')*len(files))
    if change=='weight':(directory/'model.safetensors').write_bytes(b'CORRUPT')
    if change=='runtime':manifest['runtime_versions']['torch']='0.0.invalid'
    if change=='directory':manifest['asset_directory']='../private'
    if change=='file_set':manifest['files']['arbitrary.py']='a'*64
    path=Path('manifests/reranker-msmarco-minilm-l6-v1.json');path.parent.mkdir()
    path.write_text(json.dumps(manifest),encoding='utf-8')
    expected={'weight':'asset changed','runtime':'runtime differs','directory':'directory/file set','file_set':'directory/file set'}
    with pytest.raises(RerankerError,match=expected[change]):verified_manifest()


def test_concurrent_inference_fails_explicitly_and_lock_survives_errors(monkeypatch):
    from research_assistant.retrieval.reranker import _INFERENCE_LOCK
    model=fake_native(monkeypatch)
    assert _INFERENCE_LOCK.acquire(blocking=False)
    try:
        with pytest.raises(RerankerError,match='concurrent'):model.score_pairs([('q','p')])
        assert model.model.calls==0
    finally:_INFERENCE_LOCK.release()
    assert model.score_pairs([('q','p')])[0]==[3.25]


def test_cli_failure_artifact_preserves_selector_diagnostics_without_mode_fallback(tmp_path,monkeypatch):
    from research_assistant.__main__ import main
    from research_assistant.settings import Settings
    monkeypatch.setattr(Settings,'from_env',classmethod(lambda cls:Settings()))
    def failure(*args,**kwargs):
        raise RerankerError('Synthetic oversized pair',{'status':'failed','stage':'native_length','native_pair_tokens':513,'new_pairs_inferred':0})
    monkeypatch.setattr('research_assistant.pipeline.run_query',failure)
    target=tmp_path/'failed.json'
    assert main(['retrieve','--corpus',CORPUS,'--question','Synthetic question','--profile','retrieval-v2',
                 '--selector','cross_encoder','--scope-file','data/scopes/synthetic.json','--output',str(target)])==1
    receipt=json.loads(target.read_text(encoding='utf-8'))
    assert receipt['status']=='failed' and receipt['selection_diagnostics']['stage']=='native_length'
    assert receipt['selection_diagnostics']['new_pairs_inferred']==0 and 'effective_mode' not in receipt
