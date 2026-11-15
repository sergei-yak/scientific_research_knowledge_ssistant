"""Finalize the M5.3 gate from public artifacts and current source/model/approval bindings."""
import ast
import json
import math
import re
import subprocess
import xml.etree.ElementTree as ET
from datetime import datetime,timezone
from pathlib import Path

from transformers import AutoTokenizer

from research_assistant.contracts import EvidenceItem,RunArtifact,fingerprint
from research_assistant.evaluation.freeze import file_sha
from research_assistant.graph.recovery import capture
from research_assistant.graph.search import SearchRepository
from research_assistant.ingestion.sources import load_corpus_chunks
from research_assistant.pipeline import code_identity,write_immutable
from research_assistant.product import prepare_output
from research_assistant.retrieval.catalog import chunk_evidence,load_catalog
from research_assistant.retrieval.reranker import verified_manifest,model_identity
from research_assistant.retrieval.selection import canonical_text
from research_assistant.review.store import review_lock
from research_assistant.settings import Settings


def main():
    """No new retrieval, neural scoring, generation, private reads or graph writes."""
    root=Path('runs/retrieval-v2/m5-3');checks=[]
    def check(name,value):
        checks.append({'name':name,'passed':bool(value)})
        if not value:raise ValueError(name)
    manifest=verified_manifest();scope=json.loads(Path('data/scopes/retrieval-v2.json').read_text(encoding='utf-8'))
    base=Path(scope['baseline_root']);settings=Settings.from_env();before=capture(settings)
    check('unchanged_development_graph',fingerprint(before)=='58a501badf4c47b7e1ab7fbc606a393ba953c342ec5fc2cceafa419bb6bc10fe')
    for name,count in [('offline-final.xml',235),('native-verified.xml',5)]:
        suite=ET.parse(root/name).getroot().find('testsuite')
        check('passed_test_receipt:'+name,int(suite.attrib['tests'])==count and int(suite.attrib['failures'])==int(suite.attrib['errors'])==0)
    preflight=json.loads((root/'model-preflight-v1/compatibility.json').read_text(encoding='utf-8'))
    check('pre_adapter_gate',preflight['status']=='passed' and preflight['adapter_implemented'] is False
          and preflight['model_manifest_sha256']==fingerprint(manifest.model_dump()))
    check('88_real_preflight_pairs',len(preflight['raw_logits'])==88 and all(math.isfinite(s) for s in preflight['raw_logits']))
    chunks=load_corpus_chunks(scope['corpus_id']);review=Path('data/reviews/expansion-v1')
    with review_lock(review):
        catalog=load_catalog(review,scope['corpus_id'],chunks)
        check('51_original_approved_facts',len(catalog.facts)==51 and catalog.head==scope['review_head'])
        check('unchanged_catalog',fingerprint(catalog.facts)=='8f0ad62ac6f6d190ef15b981d3bececa9d777203bac61d8b82361a3394004989')
        repo=SearchRepository(settings)
        try:
            with repo.reading(scope['corpus_id'],catalog.head,30):
                repo.check_indexes(scope['corpus_id'],True)
                repo.fact_vectors(catalog,chunks,'1110a243fdf4706b3f48f1d95db1a4f5529b4d41',strict_roles=True)
        finally:repo.close()
    paths=sorted((root/'engineering-smoke').glob('*/*.json'))+[root/'cli-reranked-graph.json']
    ui=[]
    for path in Path('runs/ui').glob('*/run.json'):
        raw=json.loads(path.read_text(encoding='utf-8'))
        if raw['request'].get('selector_id')=='cross_encoder':ui.append(path)
    check('one_actual_reranker_UI_run',len(ui)==1);paths+=ui
    tokenizer=AutoTokenizer.from_pretrained(manifest.asset_directory,local_files_only=True,trust_remote_code=False)
    common={};runs=[]
    for path in paths:
        run=RunArtifact.model_validate_json(path.read_bytes());prepare_output(run,settings,review_directory=review)
        check('retrieval_only:'+str(path),not run.generation_requested and run.generation is None and run.result is None)
        check('assembled_bounds:'+str(path),len(run.retrieval.evidence)<=6 and run.retrieval.estimated_tokens<=1800)
        if run.request.selector_id=='cross_encoder':
            check('model_identity:'+str(path),run.retrieval.audit['profile']['model_identity']==model_identity(manifest))
            selection=run.retrieval.audit['selection']
            check('88_bound:'+str(path),selection['unique_candidates']<=88 and selection['pairs_inferred']<=88)
            for stage in selection['stages'].values():
                for row in stage['rows']:
                    item=(EvidenceItem.model_validate(catalog.facts[row['id']]['evidence']) if row['id'] in catalog.facts
                          else chunk_evidence(chunks[row['id']]))
                    text=canonical_text(item,chunks,catalog)
                    feature=fingerprint([run.request.question,text])
                    length=len(tokenizer(run.request.question,text,truncation=False)['input_ids'])
                    check('actual_feature_native_score:'+feature[:16],feature==row['feature_sha256'] and length==row['native_pair_tokens']<=512
                          and math.isfinite(row['score']) and (feature not in common or common[feature]==row['score']))
                    common[feature]=row['score']
        runs.append(run)
    check('10_public_engineering_runs',len(runs)==10)
    current=code_identity()
    check('actual_UI_uses_current_code',RunArtifact.model_validate_json(ui[0].read_bytes()).configuration['source_tree_sha256']==current['source_tree_sha256'])
    for path in Path('src/research_assistant/retrieval').glob('*.py'):
        tree=ast.parse(path.read_text(encoding='utf-8'))
        check('no_gold_import:'+path.name,not any(isinstance(n,ast.ImportFrom) and (n.module or '').startswith('research_assistant.evaluation') for n in ast.walk(tree)))
    archive=json.loads((root/'v6-2-archive-proof.json').read_text(encoding='utf-8'))
    for path,digest in archive['files'].items():check('6.2_archive:'+path,file_sha(Path(path))==digest)
    for name in ('uv.lock','pyproject.toml','docs/baselines/project_spec_v6_1.md','docs/baselines/project_spec_submission_v6_1.md'):
        check('unchanged_dependency_baseline:'+name,file_sha(Path(name))==file_sha(base/name))
    old=json.loads((base/'runs/m4-2/freeze-v2.json').read_text(encoding='utf-8'))
    for path,digest in old['files'].items():
        if path.startswith('.cache/'):check('original_model_asset:'+path,file_sha(Path(path))==digest)
    for path in (base/'data/accounting').glob('*'):
        if path.is_file():check('accounting_preserved:'+path.name,file_sha(Path('data/accounting')/path.name)==file_sha(path))
    for name in ('project_spec.md','project_spec_submission.md'):
        text=Path(name).read_text(encoding='utf-8')
        check('6.3_exact_assignment_headers:'+name,text.count('## 1. Project Overview & Context')==1
              and all(header in text for header in ['## 2. The Technology Stack','## 3. Core Features & MVP (Minimum Viable Product)',
                  '## 4. Data Architecture & State Management','## 5. AI System Rules & Aesthetics (The "Vibe")']) and 'Version 6.3' in text)
    plan=Path('IMPLEMENTATION_PLAN.md').read_text(encoding='utf-8')
    check('only_M5_3_complete','- [x] **M5.3 —' in plan and all('- [ ] **'+t+' —' in plan for t in ('M5.4','M5.5','M5.6')))
    check('source_graph_preserved_through_acceptance',capture(settings)==before)
    code='''import json
from pathlib import Path
from research_assistant.evaluation.freeze import load_freeze,file_sha
from research_assistant.graph.recovery import capture
from research_assistant.contracts import fingerprint
from research_assistant.settings import Settings
f=load_freeze(Path('runs/m4-2/freeze-v2.json'))
h=json.loads(Path('runs/m4-3/handoff-complete-scored.json').read_text(encoding='utf-8'))
assert file_sha(Path(h['final_report']))==h['final_report_sha256']
assert file_sha(Path('runs/m4-3/acceptance-final.json'))==h['acceptance_final_sha256']
print(json.dumps({'frozen_files':len(f.files),'source_graph':fingerprint(capture(Settings.from_env())),'final_report_unchanged':True}))
'''
    preserved=json.loads(subprocess.run([str(base/'.venv/Scripts/python.exe'),'-c',code],cwd=base,capture_output=True,text=True,check=True,timeout=120).stdout)
    check('118_original_frozen_files_and_graph',preserved['frozen_files']==118 and preserved['source_graph']==scope['baseline_graph_sha256'])
    stopped=subprocess.run(['docker','inspect','dbu-m4-recovery-edaaed2160a3-neo4j-1','--format','{{.State.Status}}'],capture_output=True,text=True,check=True).stdout.strip()
    check('consumed_target_stopped',stopped=='exited')
    check('git_diff_check',subprocess.run(['git','diff','--check'],capture_output=True).returncode==0)
    artifacts={str(p):file_sha(p) for p in root.rglob('*') if p.is_file() and not p.name.endswith('.log')}
    for path in ui:artifacts[str(path)]=file_sha(path)
    docs=['AGENTS.md','README.md','IMPLEMENTATION_PLAN.md','project_spec.md','project_spec_submission.md','docs/M5_3_REPORT.md',
          'manifests/M5_3_MODEL_DECISION.md','manifests/reranker-msmarco-minilm-l6-v1.json']
    result={'task_id':'M5.3','status':'complete','recorded_at':datetime.now(timezone.utc).isoformat(),**current,
        'checks_passed':len(checks),'checks':checks,'baseline_preservation':preserved,'offline_passed':235,'integration_deselected':7,
        'native_passed':5,'validated_engineering_runs':10,'distinct_actual_scored_features':len(common),'model_identity':model_identity(manifest),
        'artifact_sha256':artifacts,'document_sha256':{p:file_sha(Path(p)) for p in docs},
        'implementation_sha256':{str(p):file_sha(p) for prefix in ('src','tests','scripts') for p in Path(prefix).rglob('*.py')},
        'generation_calls':0,'paid_calls':0,'extraction_calls':0,'private_access':False,'new_model_downloads':1,
        'dependency_changes':0,'skipped':['M5.4 full matrix/gold recall/go-no-go','Claim enrichment/review','Generation/paid probes','Private/final evaluation'],
        'blockers':[],'next_task':'M5.4; not started','new_final_run_authorized':False}
    write_immutable(root/'acceptance-final.json',json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k not in ('checks','artifact_sha256','document_sha256','implementation_sha256')}))


if __name__=='__main__':main()
