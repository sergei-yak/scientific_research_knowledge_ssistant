"""Bounded one-question engineering check; not the M5.4 development comparison."""
import json
from pathlib import Path

from research_assistant.contracts import QueryRequest,fingerprint
from research_assistant.embeddings import Encoder
from research_assistant.graph.recovery import capture
from research_assistant.ingestion.sources import load_corpus_chunks,source_identity
from research_assistant.pipeline import run_query,write_immutable,code_identity
from research_assistant.product import prepare_output
from research_assistant.retrieval.catalog import load_catalog
from research_assistant.review.store import review_lock
from research_assistant.settings import Settings,configure_caches


def main():
    """Check all four mode boundaries with shared cached MiniLM; zero provider/gold inputs."""
    configure_caches()
    scope=json.loads(Path('data/scopes/retrieval-v2.json').read_text(encoding='utf-8'))
    root=Path('runs/retrieval-v2/m5-2/engineering-smoke')
    if root.exists():raise ValueError('Use a new immutable engineering output directory')
    settings=Settings.from_env();before=fingerprint(capture(settings))
    chunks=load_corpus_chunks(scope['corpus_id'])
    review=Path('data/reviews/expansion-v1')
    with review_lock(review):
        catalog=load_catalog(review,scope['corpus_id'],chunks)
        assert len(catalog.facts)==51 and catalog.head==scope['review_head']
        assert fingerprint(catalog.facts)=='8f0ad62ac6f6d190ef15b981d3bececa9d777203bac61d8b82361a3394004989'
    encoder=Encoder();runs={};results=[]
    question='Which methods were evaluated on MuSiQue? Cite at least two reporting papers and qualify benchmark comparability.'
    for profile in ('baseline','retrieval-v2'):
        for mode in ('vector','hybrid','hybrid_facts','graph'):
            request=QueryRequest(question=question,corpus_id=scope['corpus_id'],mode=mode,profile_id=profile,
                scope_file='data/scopes/retrieval-v2.json' if profile=='retrieval-v2' else None)
            run=run_query(request,settings,review_directory=review,generate=False,encoder=encoder)
            view,csv=prepare_output(run,settings,review_directory=review)
            assert run.generation is None and run.result is None
            assert len(run.retrieval.evidence)<=6 and run.retrieval.estimated_tokens<=1800
            write_immutable(root/profile/(mode+'.json'),run.model_dump_json(indent=2)+'\n')
            write_immutable(root/profile/(mode+'.csv'),csv)
            runs[profile,mode]=run
            results.append({'profile':profile,'mode':mode,'effective_mode':run.retrieval.effective_mode,
                'context_sha256':run.retrieval.context_sha256,'tokens':run.retrieval.estimated_tokens,'units':len(run.retrieval.evidence),
                'product_status':view.status,'approved_papers':view.paper_count,
                'graph_rows':run.retrieval.audit.get('graph_rows'),'selected_graph_additions':run.retrieval.audit.get('selected_graph_additions')})
    for mode in ('vector','hybrid','hybrid_facts'):
        assert runs['baseline',mode].retrieval.context_sha256==runs['retrieval-v2',mode].retrieval.context_sha256
    graph=runs['retrieval-v2','graph'].retrieval
    if graph.fallback_reason:
        ablation=runs['retrieval-v2','hybrid_facts'].retrieval
        assert all(getattr(graph,k)==getattr(ablation,k) for k in ('context','context_sha256','evidence','aliases','estimated_tokens','candidates'))
    assert fingerprint(capture(settings))==before
    summary={'task_id':'M5.2','engineering_only':True,**code_identity(),'retrieval_reads':8,'generation_calls':0,
        'gold_inputs':False,'private_access':False,'paid_calls':0,'approved_claims':51,'review_head':catalog.head,
        'catalog_sha256':fingerprint(catalog.facts),'source_sha256':source_identity(chunks),'target_graph_sha256':before,
        'unchanged_reference_non_graph_contexts':3,'results':results}
    write_immutable(root/'summary.json',json.dumps(summary,indent=2)+'\n')
    print(json.dumps(summary))


if __name__=='__main__':main()
