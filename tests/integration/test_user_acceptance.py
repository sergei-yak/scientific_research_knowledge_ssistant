"""Verify saved public M8.5 operations against live owned sources/indexes; no inference or approvals."""

import csv
import hashlib
import io
import json
import os
from pathlib import Path

import pytest

from research_assistant.collections.store import CollectionRegistry
from research_assistant.collections.workspace import checked_output,verify_collection
from research_assistant.collections.reviews import review_status
from research_assistant.contracts import RunArtifact
from research_assistant.ingestion.sources import load_corpus_chunks
from research_assistant.pipeline import write_immutable
from research_assistant.settings import Settings,configure_caches

pytestmark=[pytest.mark.integration,pytest.mark.skipif(os.getenv('RUN_USER_ACCEPTANCE_VERIFY')!='1',
    reason='Requires the completed bounded public M8.5 workflow manifest and owned live target')]


def test_saved_cross_topic_workflow_sources_exports_and_review_gates(monkeypatch):
    """Replay actual artifacts; never create research gold, a human decision or another model request."""
    configure_caches()
    from research_assistant.embeddings import Encoder
    from research_assistant.llm import OllamaClient
    def forbidden(*args,**kwargs): pytest.fail('Saved-output verification must not encode or generate')
    monkeypatch.setattr(Encoder,'encode',forbidden)
    monkeypatch.setattr(OllamaClient,'_generate',forbidden)
    out=Path('runs/m8/m8-5')
    manifest=json.loads((out/'workflow-manifest-v1.json').read_bytes())
    plan=json.loads((out/'engineering-plan-v1.json').read_bytes())
    registry,settings=CollectionRegistry(),Settings.from_env()
    assert registry.scope.scope_id==plan['scope_id'] and settings.neo4j_uri==plan['target_uri']
    ai=registry.get(plan['existing_collection_id'])
    physics=registry.get(manifest['physics_collection_id'])
    assert ai.collection_id!=physics.collection_id and ai.corpus_id!=physics.corpus_id
    ai_ready=verify_collection(registry,ai.collection_id,settings,ai.sha256)
    physics_ready=verify_collection(registry,physics.collection_id,settings,physics.sha256)
    status=review_status(registry,ai_ready,settings)
    assert status['ready'] and status['approved']==2 and status['review_head']==plan['approved_review_head']
    assert not review_status(registry,physics_ready,settings)['ready']
    assert physics.revision==2 and len(physics.documents)==1 and physics.binding.chunk_count==148
    imports=[j for j in registry.jobs() if j.collection_id==physics.collection_id]
    assert sorted(j.state for j in imports)==['duplicate','failed','ready']
    initial=json.loads((out/'physics-import-proof.json').read_bytes())
    assert initial['head']==physics.sha256 and initial['cold_document_cache']
    assert physics.documents[0].pdf_pages==len(physics.documents[0].indexed_pages)==16
    # Every new chunk still replays to its stored normalized page interval.
    chunks=load_corpus_chunks(physics.corpus_id)
    member=json.loads((Path('data/processed')/physics.corpus_id/'members.json').read_bytes())[0]
    pages={p['page']:p['text'] for line in Path(member['snapshot_path']).with_name('pages.jsonl').read_text(encoding='utf-8').splitlines()
           if (p:=json.loads(line))}
    assert len(chunks)==148
    for chunk in chunks.values(): assert chunk.text==pages[chunk.page][chunk.page_start:chunk.page_end]
    runs={name:RunArtifact.model_validate_json(Path(path).read_bytes()) for name,path in manifest['runs'].items()}
    assert set(runs)=={'ai-vector','ai-hybrid','ai-facts','ai-graph','physics-vector',
                       'physics-hybrid','physics-wrong-topic','ai-wrong-topic','physics-cli-parity'}
    excerpts=0
    for name,run in runs.items():
        collection=physics if name.startswith('physics') else ai
        view,csv_text,ready=checked_output(registry,collection.collection_id,run,settings,collection.sha256)
        assert ready.collection==collection
        assert run.request.profile_id=='baseline' and run.request.selector_id=='reference'
        assert len(run.retrieval.evidence)<=6 and run.retrieval.estimated_tokens<=1800
        assert {ex.paper_id for item in run.retrieval.evidence for ex in item.excerpts}<={d.paper_id for d in collection.documents}
        if run.generation:
            assert run.generation.provider=='ollama' and run.generation.digest==plan['model_digest']
            assert run.generation.settings['num_ctx']==4096 and run.generation.settings['num_predict']==512
            assert run.generation.settings['retries']==0 and run.generation.settings['concurrency']==1
        rows=list(csv.DictReader(io.StringIO(csv_text)))
        actual=[ex for item in run.retrieval.evidence for ex in item.excerpts]
        assert len(rows)==len(actual)
        for row,ex in zip(rows,actual):
            quote=row['quotation'][1:] if 'quotation' in json.loads(row['escaped_fields']) else row['quotation']
            assert quote==ex.text and int(row['page'])==ex.page
            assert row['source_reference']==ready.sources[ex.paper_id].reference
        excerpts+=len(actual)
    assert sum(r.generation is not None for r in runs.values())==6
    assert all(runs[name].result.insufficient_evidence and not runs[name].result.citations
               for name in ['ai-wrong-topic','physics-wrong-topic'])
    assert all(runs[name].result and not runs[name].result.insufficient_evidence and runs[name].result.citations
               for name in ['ai-hybrid','ai-graph','physics-vector','physics-hybrid'])
    assert runs['ai-facts'].retrieval.context==runs['ai-graph'].retrieval.context
    assert runs['ai-graph'].retrieval.requested_mode=='graph'
    assert runs['ai-graph'].retrieval.effective_mode=='hybrid_facts'
    assert runs['ai-graph'].retrieval.fallback_reason=='no_new_eligible_graph_candidates'
    assert not any(i.graph_paths for i in runs['ai-graph'].retrieval.evidence)
    assert sum(i.kind=='approved_fact' for i in runs['ai-facts'].retrieval.evidence)==2
    assert runs['physics-hybrid'].retrieval.context==runs['physics-cli-parity'].retrieval.context
    # Wrong collection binding is rejected before any display/export or synthesis can occur.
    with pytest.raises(ValueError,match='different or changed collection'):
        checked_output(registry,ai.collection_id,runs['physics-hybrid'],settings)
    for name in ['physics-facts-gate','physics-graph-gate']:
        outcome=json.loads((out/(name+'-outcome.json')).read_bytes())
        assert outcome['status']=='refused' and outcome['error']=='ValueError' and 'not ready' in outcome['message']
    exported=RunArtifact.model_validate_json((out/'downloaded-physics.json').read_bytes())
    assert exported==runs['physics-hybrid']
    _,csv_text,_=checked_output(registry,physics.collection_id,exported,settings)
    assert (out/'downloaded-physics.csv').read_bytes()==csv_text.encode('utf-8-sig')
    assert hashlib.sha256((out/'downloaded-physics.pdf').read_bytes()).hexdigest()==physics.documents[0].source_sha256
    exported_ai=RunArtifact.model_validate_json((out/'downloaded-ai-graph.json').read_bytes())
    assert exported_ai==runs['ai-graph']
    _,ai_csv,_=checked_output(registry,ai.collection_id,exported_ai,settings)
    assert (out/'downloaded-ai-graph.csv').read_bytes()==ai_csv.encode('utf-8-sig')
    counters=json.loads((out/'checked-operation-counts.json').read_bytes())
    assert counters=={'imports':3,'download_chains':1,'http_attempts':1,'queries':11,
                     'question_calls':9,'document_calls':1,'document_texts':148,'generations':6}
    # Exercise the actual retained failure through the final UI without submitting any operation.
    from streamlit.testing.v1 import AppTest
    failed=next(j for j in imports if j.state=='failed')
    outcome=json.loads(registry._path('jobs',failed.job_id,'outcome.json').read_bytes())
    app=AppTest.from_file('src/research_assistant/ui/collections_app.py',default_timeout=30)
    app.session_state['user_collection']=physics.collection_id
    app.session_state['last_import']=outcome
    app.run()
    assert not app.exception
    assert any('valid, text-based' in error.value for error in app.error)
    assert all('data\\user-collections' not in error.value for error in app.error)
    assert any('Ready to search' in caption.value for caption in app.caption)
    proof={'status':'passed','public_run_artifacts':len(runs),'replayed_new_source_chunks':len(chunks),
        'exported_excerpt_rows_checked':excerpts,'local_generation_attempts':6,'both_wrong_topic_abstentions':True,
        'four_topic_direct_examples_cited':True,'qualitative_examples_not_a_quality_benchmark':True,
        'current_human_approvals_preserved':2,'physics_fact_graph_gates_refused':True,
        'real_graph_fallback_exact_fact_parity':True,'browser_cli_physics_context_exact':True,
        'actual_exports_match':True,'new_human_decisions':0,'new_research_study':False,'paid_spend':0,
        'private_access':False,'retained_bad_upload_shows_actionable_ui_message':True,
        'no_provider_or_encoder_call_from_this_verifier':True}
    write_immutable(out/'native-acceptance-proof-v1.json',json.dumps(proof,indent=2)+'\n')
