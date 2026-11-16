"""Build public-only M5.5 readiness inputs; never inspect or create private evaluation files."""

import json
import subprocess
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import ollama

from research_assistant.contracts import fingerprint
from research_assistant.evaluation.development import load_dataset, review_status
from research_assistant.evaluation.freeze import file_sha, runtime_versions
from research_assistant.graph.recovery import capture
from research_assistant.graph.search import SearchRepository
from research_assistant.ingestion.sources import source_identity
from research_assistant.pipeline import code_identity, write_immutable
from research_assistant.retrieval.catalog import load_catalog
from research_assistant.retrieval.profiles import validate_scope
from research_assistant.contracts import QueryRequest
from research_assistant.retrieval.reranker import verified_manifest
from research_assistant.review.store import review_lock
from research_assistant.settings import Settings, configure_caches

ROOT = Path('runs/retrieval-v2/m5-5/readiness-v1')
PUBLIC = ROOT/'evaluator-public-bundle'


def save(path, value):
    """Exclusive public JSON receipt; never overwrite an earlier preparation."""
    write_immutable(path, json.dumps(value, indent=2, ensure_ascii=False)+'\n')


def main():
    """Verify existing local assets, export source-only author inputs, disclose every pending gate."""
    if ROOT.exists():
        raise ValueError('Existing immutable preparation; create a disclosed new version')
    configure_caches(); settings = Settings.from_env()
    scope = json.loads(Path('data/scopes/retrieval-v2.json').read_text(encoding='utf-8'))
    devdir = Path('data/evaluation/development/expansion-v1')
    development, entries, chunks = load_dataset(devdir)
    human = review_status(devdir)
    assert human['ready'] and len(entries)==8 and len(chunks)==1427
    review = Path('data/reviews/expansion-v1')
    with review_lock(review):
        catalog = load_catalog(review, scope['corpus_id'], chunks)
        repo = SearchRepository(settings)
        try:
            validate_scope(QueryRequest(question='M5.5 public readiness', corpus_id=scope['corpus_id'],
                profile_id='retrieval-v2', scope_file='data/scopes/retrieval-v2.json'), settings, review, chunks, catalog, repo)
            snapshot = repo.snapshot(scope['corpus_id'])
            with repo.reading(scope['corpus_id'], catalog.head, 30):
                repo.check_indexes(scope['corpus_id'], True)
                repo.fact_vectors(catalog, chunks, snapshot['encoder_revision'], strict_roles=True)
        finally:
            repo.close()
    assert len(catalog.facts)==51 and catalog.head==scope['review_head']
    assert fingerprint(catalog.facts)=='8f0ad62ac6f6d190ef15b981d3bececa9d777203bac61d8b82361a3394004989'
    assert source_identity(chunks)==scope['source_chunks_sha256']
    graph = capture(settings)
    assert fingerprint(graph)=='58a501badf4c47b7e1ab7fbc606a393ba953c342ec5fc2cceafa419bb6bc10fe'
    m54 = Path('runs/retrieval-v2/m5-4/comparison-v1/execution-manifest.json')
    previous = json.loads(m54.read_text(encoding='utf-8'))
    for path, sha in previous['file_sha256'].items():
        assert file_sha(Path(path))==sha, path
    model = verified_manifest()
    assert model.model_dump()==previous['model']
    assert settings.generation_provider=='ollama' and settings.max_retries==0 and settings.max_concurrency==1
    installed = next((m for m in ollama.Client(host=settings.ollama_base_url,timeout=15).list().models
                      if m.model==settings.generation_model),None)
    assert installed is not None
    stopped = subprocess.run(['docker','inspect','dbu-m4-recovery-edaaed2160a3-neo4j-1',
        '--format','{{.State.Status}}'],capture_output=True,text=True,check=True).stdout.strip()
    assert stopped=='exited'
    base = Path(scope['baseline_root'])
    code = '''
import json
from pathlib import Path
from research_assistant.evaluation.freeze import load_freeze
from research_assistant.graph.recovery import capture
from research_assistant.contracts import fingerprint
from research_assistant.settings import Settings
f=load_freeze(Path('runs/m4-2/freeze-v2.json'))
print(json.dumps({'frozen_files':len(f.files),'source_graph_sha256':fingerprint(capture(Settings.from_env()))}))
'''
    baseline = json.loads(subprocess.run([str(base/'.venv/Scripts/python.exe'),'-c',code],cwd=base,
        capture_output=True,text=True,check=True,timeout=120).stdout)
    assert baseline['frozen_files']==118 and baseline['source_graph_sha256']==scope['baseline_graph_sha256']
    # Only source and current approval data go into this author bundle. No development
    # answers, rankings, generated answers, metrics, old attestations or private paths.
    write_immutable(PUBLIC/'chunks.jsonl',''.join(chunks[key].model_dump_json()+'\n' for key in sorted(chunks)))
    write_immutable(PUBLIC/'approved-facts.jsonl',''.join(json.dumps(catalog.facts[key],ensure_ascii=False)+'\n' for key in sorted(catalog.facts)))
    write_immutable(PUBLIC/'development-questions.jsonl',(devdir/'questions.jsonl').read_text(encoding='utf-8'))
    papers = defaultdict(list)
    for chunk in chunks.values():
        papers[chunk.paper_id].append(chunk)
    titles = {node['properties']['id']:node['properties'].get('title') for node in graph['nodes'] if 'Paper' in node['labels']}
    coverage = [{'paper_id':paper,'title':titles.get(paper),'source_sha256':sorted({c.source_sha256 for c in rows}),
                 'indexed_pdf_pages':sorted({c.page for c in rows}), 'chunks':len(rows),
                 'source_urls':sorted({c.source_url for c in rows})} for paper,rows in sorted(papers.items())]
    assert len(coverage)==20
    save(PUBLIC/'source-coverage.json',{'papers':coverage,'source_chunks_sha256':source_identity(chunks),
        'warning':'Indexed normalized prose only. Parsed section labels/flattened numeric tables are unverified. No absence conclusion outside the indexed pages.'})
    write_immutable(PUBLIC/'pilot-pdf-inspection.md',Path('docs/M2_PDF_INSPECTION.md').read_text(encoding='utf-8'))
    write_immutable(PUBLIC/'evaluation-contracts.py.txt',Path('src/research_assistant/contracts.py').read_text(encoding='utf-8'))
    public_manifest = {'format':'m5-5-public-author-inputs-v1','corpus_id':scope['corpus_id'],
        'review_head':catalog.head,'catalog_sha256':fingerprint(catalog.facts),
        'source_chunks_sha256':source_identity(chunks),'development_dataset_sha256':fingerprint(development),
        'files':{p.name:file_sha(p) for p in sorted(PUBLIC.iterdir())},
        'contains_private_inputs':False,'contains_development_gold':False,'contains_retrieval_results':False,
        'human_gold_approval_inherited':False,'final_execution_authorized':False}
    save(PUBLIC/'manifest.json',public_manifest)
    outcome = {'task_id':'M5.5.1','status':'public_preparation_passed_private_and_freeze_gates_pending',
        'recorded_at':datetime.now(timezone.utc).isoformat(),**code_identity(),
        'public_bundle_manifest_sha256':file_sha(PUBLIC/'manifest.json'),'public_bundle':str(PUBLIC),
        'source_chunks':len(chunks),'papers':len(coverage),'approved_facts':len(catalog.facts),
        'review_head':catalog.head,'catalog_sha256':fingerprint(catalog.facts),
        'development_human_ready':human['ready'],'development_dataset_sha256':fingerprint(development),
        'graph_sha256':fingerprint(graph),'index_schema_sha256':fingerprint(graph['indexes']),
        'baseline':baseline,'consumed_target_stopped':True,'m5_4_inputs_preserved':True,
        'runtime':runtime_versions(),'reranker_manifest_sha256':fingerprint(model.model_dump()),
        'generator':{'provider':settings.generation_provider,'model':settings.generation_model,'installed_digest':installed.digest,
                     'service_list_passed':True,'fresh_inference_tested':False},
        'preparation_policy':'User requested M5.5 after reported no-go; readiness preparation only. Negative outcome retained; no automatic final-study continuation.',
        'pending':['Explicit fresh evaluator/retired-prompt screening scope','Fresh 16-question draft and real human gold review',
            'Versioned profile-aware evaluation contracts/runner and read-only scope support',
            'Local generation/reranker resource readiness under a recorded bounded probe plan',
            'Fresh isolated read-only recovery proof','Exact final manifest/limits and separate human final-run authorization'],
        'matrix_retrievals':0,'generation_requests':0,'paid_calls':0,'new_downloads':0,'private_paths_accessed':False,
        'private_author_dispatched':False,'new_freeze_created':False,'final_execution_authorized':False,
        'model_or_corpus_changes':0,'graph_writes':0}
    save(ROOT/'public-preflight.json',outcome)
    print(json.dumps({k:outcome[k] for k in ('task_id','status','papers','source_chunks','approved_facts','m5_4_inputs_preserved','baseline','generation_requests','private_paths_accessed','new_freeze_created')}))


if __name__=='__main__':
    main()
