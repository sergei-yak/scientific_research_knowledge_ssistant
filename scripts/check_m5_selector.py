"""M5.3 one-question engineering gate; no gold, generation or M5.4 matrix."""
import json
from pathlib import Path

from research_assistant.contracts import QueryRequest,fingerprint
from research_assistant.embeddings import Encoder
from research_assistant.graph.recovery import capture
from research_assistant.ingestion.sources import load_corpus_chunks
from research_assistant.pipeline import run_query,write_immutable,code_identity
from research_assistant.product import prepare_output
from research_assistant.retrieval.catalog import load_catalog
from research_assistant.review.store import review_lock
from research_assistant.settings import Settings,configure_caches


def main():
    """Exercise matched selector modes and repeatable shared scores, not answer quality."""
    configure_caches()
    root=Path('runs/retrieval-v2/m5-3/engineering-smoke')
    if root.exists():raise ValueError('Keep immutable outputs; use a new engineering directory')
    scope=json.loads(Path('data/scopes/retrieval-v2.json').read_text(encoding='utf-8'))
    settings=Settings.from_env();before=fingerprint(capture(settings))
    review=Path('data/reviews/expansion-v1');chunks=load_corpus_chunks(scope['corpus_id'])
    with review_lock(review):catalog=load_catalog(review,scope['corpus_id'],chunks)
    assert len(catalog.facts)==51 and catalog.head==scope['review_head']
    encoder=Encoder();runs={};rows=[];common={}
    question='Which methods were evaluated on MuSiQue? Cite at least two reporting papers and qualify benchmark comparability.'
    for selector in ('reference','cross_encoder'):
        for mode in ('vector','hybrid','hybrid_facts','graph'):
            request=QueryRequest(question=question,corpus_id=scope['corpus_id'],profile_id='retrieval-v2',selector_id=selector,
                                 scope_file='data/scopes/retrieval-v2.json',mode=mode)
            run=run_query(request,settings,review_directory=review,generate=False,encoder=encoder)
            prepare_output(run,settings,review_directory=review)
            assert run.generation is None and run.result is None
            write_immutable(root/selector/(mode+'.json'),run.model_dump_json(indent=2)+'\n')
            runs[selector,mode]=run
            record={'selector':selector,'mode':mode,'effective_mode':run.retrieval.effective_mode,
                'context_sha256':run.retrieval.context_sha256,'units':len(run.retrieval.evidence),
                'tokens':run.retrieval.estimated_tokens,'request_elapsed_ms':run.retrieval.audit['request_elapsed_ms'],
                'graph_rows':run.retrieval.audit.get('graph_rows'),'graph_additions':run.retrieval.audit.get('selected_graph_additions')}
            if selector=='cross_encoder':
                audit=run.retrieval.audit['selection']
                assert audit['unique_candidates']<=88 and audit['pairs_inferred']<=88
                for stage in audit['stages'].values():
                    for item in stage['rows']:
                        key=item['feature_sha256']
                        assert key not in common or common[key]==item['score']
                        common[key]=item['score']
                record.update(unique_candidates=audit['unique_candidates'],pairs_inferred=audit['pairs_inferred'])
            rows.append(record);print(json.dumps(record),flush=True)
    for selector in ('reference','cross_encoder'):
        graph=runs[selector,'graph'].retrieval
        if graph.fallback_reason:
            ablation=runs[selector,'hybrid_facts'].retrieval
            for field in ('context','context_sha256','evidence','aliases','estimated_tokens','candidates'):
                assert getattr(graph,field)==getattr(ablation,field)
    for mode in ('vector','hybrid','hybrid_facts','graph'):
        old=json.loads((Path('runs/retrieval-v2/m5-2/engineering-smoke/retrieval-v2')/(mode+'.json')).read_text(encoding='utf-8'))
        assert runs['reference',mode].retrieval.context_sha256==old['retrieval']['context_sha256']
    assert fingerprint(capture(settings))==before
    result={'task_id':'M5.3','engineering_only':True,**code_identity(),'retrieval_runs':8,'common_scored_features':len(common),
        'exact_common_scores_across_modes':True,'reference_context_parity_with_M5_2':4,'graph_sha256':before,
        'review_head':catalog.head,'catalog_sha256':fingerprint(catalog.facts),'approved_facts':51,
        'generation_calls':0,'private_access':False,'gold_read':False,'results':rows}
    write_immutable(root/'summary.json',json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k!='results'}),flush=True)


if __name__=='__main__':main()
