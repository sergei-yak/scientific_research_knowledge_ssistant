"""Bounded M8.4 proof with UUID synthetic PDFs/vectors/decisions; never real human approval."""

import io
import json
import os
import re
from pathlib import Path
from uuid import uuid4

import pymupdf
import pytest

from research_assistant.collections.store import CollectionRegistry
from research_assistant.collections import reviews, workspace
from research_assistant.contracts import fingerprint
from research_assistant.extraction.contracts import ProposedClaim
from research_assistant.ingestion.sources import load_corpus_chunks
from research_assistant.pipeline import write_immutable
from research_assistant.review.store import state
from research_assistant.settings import Settings, configure_caches

pytestmark = [pytest.mark.integration,pytest.mark.skipif(os.getenv('RUN_USER_REVIEW_SMOKE')!='1',
    reason='Needs the prospective M8.4 plan and exact owned target')]


class FixtureTokenizer:
    """Whitespace token windows for synthetic short test sentences only."""
    def encode(self,text,add_special_tokens=True): return [0]*(len(text.split())+(2 if add_special_tokens else 0))
    def __call__(self,text,**kwargs): return {'offset_mapping':[(m.start(),m.end()) for m in re.finditer(r'\S+',text)]}


class SyntheticEncoder:
    """Deterministic unit vectors exercise real indexes/traversal, never neural quality."""
    revision,mpnet_revision = 'm8-review-synthetic-vector-v1','m8-review-synthetic-token-v1'
    mini_tokenizer,mpnet_tokenizer = FixtureTokenizer(),FixtureTokenizer()
    def encode(self,texts):
        return [[1.0]+[0.0]*383 if 'anchor' in text else [0.0,1.0]+[0.0]*382 for text in texts]


def pdf(texts):
    document = pymupdf.open()
    for text in texts: document.new_page().insert_textbox(pymupdf.Rect(60,60,500,700),text)
    raw = document.tobytes()
    document.close()
    return io.BytesIO(raw)


def test_native_collection_human_gate_graph_path_revocation_and_publication():
    configure_caches()
    out = Path('runs/m8/m8-4')
    plan = json.loads((out/'engineering-plan-v1.json').read_bytes())
    registry,settings = CollectionRegistry(),Settings.from_env()
    assert registry.scope.scope_id==plan['scope_id'] and settings.neo4j_uri==plan['target_uri']
    old = sorted(out.glob('native-start-*.json'))
    assert len(old)<plan['max_native_fixture_invocations']
    token = uuid4().hex
    write_immutable(out/('native-start-'+token+'.json'),json.dumps({'uuid':token,'plan_sha256':fingerprint(plan)})+'\n')
    collection = registry.create('TEST ONLY M8.4 synthetic '+token[:8])
    encoder = SyntheticEncoder()
    near = [f'anchor SharedSet FixtureMethod source setup. Synthetic {token}.' if number==0 else
            f'anchor background passage {number}. Synthetic {token}.' for number in range(12)]
    far = [f'Remote FixtureMethod evaluated on SharedSet. Synthetic {token}.',
           f'Remote method limitations require further validation. Synthetic {token}.']
    imported = workspace.import_collection(registry,collection.collection_id,collection.sha256,
        [('SYNTHETIC-near-'+token+'.pdf',pdf(near)),('SYNTHETIC-remote-'+token+'.pdf',pdf(far))],[],settings,
        encoder_factory=lambda:encoder)
    assert imported['status']=='ready'
    collection = registry.get(collection.collection_id)
    chunks = sorted(load_corpus_chunks(collection.corpus_id).values(),key=lambda c:(c.paper_id,c.page))
    first = next(c for c in chunks if 'source setup' in c.text)
    def propose(chunk,kind='finding',bindings=None):
        evaluation = kind=='evaluation'
        draft = ProposedClaim(kind=kind,statement=chunk.text,quotes=[chunk.text],
            method='FixtureMethod' if evaluation else None,method_aliases=['lookupmethod'] if evaluation else [],
            dataset='SharedSet' if evaluation else None,dataset_aliases=['lookupdataset'] if evaluation else [],conditions={})
        revision = reviews.propose_claim(registry,collection.collection_id,collection.sha256,draft,chunk.chunk_id,settings,
                                        entity_ids=bindings)
        shown = reviews.present_claim(registry,collection.collection_id,collection.sha256,revision.claim_id,settings)
        assert not shown.errors
        reviews.record_decision(registry,collection.collection_id,collection.sha256,shown,
            reviews.UIResponse(presentation_sha256=shown.sha256,reviewer='SYNTHETIC NATIVE TEST ONLY',
                decision='approved',reason='Synthetic pipeline fixture, not a real human annotation',confirmed=True),settings)
        return revision
    source = propose(first,'evaluation')
    bindings = {e.kind:e.id for e in source.entities}
    target = None
    for chunk in chunks:
        if chunk.chunk_id==first.chunk_id: continue
        revision = propose(chunk,'evaluation' if 'Remote FixtureMethod' in chunk.text else 'finding',bindings if 'Remote FixtureMethod' in chunk.text else None)
        if 'Remote FixtureMethod' in chunk.text: target = revision
    directory = registry.review_directory(collection)
    head = state(directory)['head']
    with pytest.raises(ValueError,match='not ready'):
        workspace.query_collection(registry,collection.collection_id,collection.sha256,
            'anchor lookupmethod lookupdataset','graph',settings,encoder=encoder)
    published = reviews.publish_review(registry,collection.collection_id,collection.sha256,head,settings,
                                       encoder_factory=lambda:encoder)
    assert published['verified_active_facts']==14
    def query(mode):
        return workspace.query_collection(registry,collection.collection_id,collection.sha256,
            'anchor lookupmethod lookupdataset',mode,settings,encoder=encoder)
    facts,graph = query('hybrid_facts'),query('graph')
    assert target is not None
    target_items = [item for item in graph.retrieval.evidence if target.claim_id in item.approved_claim_ids]
    assert graph.retrieval.effective_mode=='graph' and target_items and target_items[0].graph_paths
    assert target.claim_id not in {key for item in facts.retrieval.evidence for key in item.approved_claim_ids}
    assert graph.retrieval.audit['channel_rankings']==facts.retrieval.audit['channel_rankings']
    assert len(graph.retrieval.evidence)<=6 and graph.retrieval.estimated_tokens<=1800
    # Revoke every synthetic approval; retained fixture data must not masquerade as real reviewed evidence.
    for revision in list(state(directory)['current'].values()):
        shown = reviews.present_claim(registry,collection.collection_id,collection.sha256,revision.claim_id,settings)
        reviews.record_decision(registry,collection.collection_id,collection.sha256,shown,
            reviews.UIResponse(presentation_sha256=shown.sha256,reviewer='SYNTHETIC NATIVE TEST ONLY',
                decision='needs_review',reason='End synthetic fixture eligibility; preserve all history',confirmed=True),settings)
    with pytest.raises(ValueError,match='not ready'):
        workspace.checked_output(registry,collection.collection_id,graph,settings)
    result = reviews.publish_review(registry,collection.collection_id,collection.sha256,state(directory)['head'],settings)
    assert result['verified_active_facts']==0
    proof = {'status':'passed','uuid':token,'collection_id':collection.collection_id,'import_jobs':1,
        'synthetic_documents':2,'synthetic_claims':14,'real_human_approvals':0,'all_synthetic_approvals_revoked':True,
        'positive_graph_path':True,'novel_selected_claim':target.claim_id,'stale_export_refused':True,
        'actual_fact_run':facts.run_id,'actual_graph_run':graph.run_id,'paid_spend':0,'real_model_requests':0,
        'fixture_retained':True,'graph_paths':target_items[0].graph_paths}
    write_immutable(out/('native-proof-'+token+'.json'),json.dumps(proof,indent=2)+'\n')
