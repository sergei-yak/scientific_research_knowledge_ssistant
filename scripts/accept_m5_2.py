"""Finalize M5.2 from public saved runs, current metadata and original baseline commitments."""
import ast
import json
import subprocess
import sys
from datetime import datetime,timezone
from pathlib import Path
import xml.etree.ElementTree as ET

from research_assistant.contracts import RunArtifact,fingerprint
from research_assistant.evaluation.freeze import file_sha
from research_assistant.graph.recovery import capture
from research_assistant.graph.search import SearchRepository
from research_assistant.ingestion.sources import load_corpus_chunks,source_identity
from research_assistant.pipeline import code_identity,write_immutable
from research_assistant.product import prepare_output
from research_assistant.retrieval.catalog import load_catalog
from research_assistant.review.store import review_lock
from research_assistant.settings import Settings


def main():
    """No generation, new retrieval, private paths, final runner or resets."""
    root=Path('runs/retrieval-v2/m5-2')
    scope=json.loads(Path('data/scopes/retrieval-v2.json').read_text(encoding='utf-8'))
    base=Path(scope['baseline_root']);settings=Settings.from_env();checks=[]
    def check(name,value):
        checks.append({'name':name,'passed':bool(value)})
        if not value:raise ValueError(name)
    before=capture(settings)
    check('expected_isolated_graph',fingerprint(before)=='58a501badf4c47b7e1ab7fbc606a393ba953c342ec5fc2cceafa419bb6bc10fe')
    normalized=json.loads(json.dumps(before))
    for node in normalized['nodes']:
        if 'Corpus' in node['labels'] and node['properties']['id']==scope['corpus_id']:
            for key in ('experiment_scope_id','retrieval_profile_id','experiment_scope_sha256'):
                node['properties'].pop(key)
    check('copy_differs_only_in_declared_control_metadata',fingerprint(normalized)==scope['baseline_graph_sha256'])
    for report,count in [('offline-scope-bound-final.xml',213),('native-complete.xml',4)]:
        suite=ET.parse(root/report).getroot().find('testsuite')
        check('test_receipt:'+report,suite is not None and int(suite.attrib['tests'])==count
              and int(suite.attrib['failures'])==0 and int(suite.attrib['errors'])==0)
    chunks=load_corpus_chunks(scope['corpus_id']);review=Path('data/reviews/expansion-v1')
    with review_lock(review):
        catalog=load_catalog(review,scope['corpus_id'],chunks)
        check('51_original_facts_and_head',len(catalog.facts)==51 and catalog.head==scope['review_head'])
        check('original_catalog_bytes',fingerprint(catalog.facts)=='8f0ad62ac6f6d190ef15b981d3bececa9d777203bac61d8b82361a3394004989')
        repo=SearchRepository(settings)
        try:
            with repo.reading(scope['corpus_id'],catalog.head,30):
                repo.check_indexes(scope['corpus_id'],True)
                repo.fact_vectors(catalog,chunks,'1110a243fdf4706b3f48f1d95db1a4f5529b4d41',strict_roles=True)
        finally:repo.close()
    check('source_identity',source_identity(chunks)==scope['source_chunks_sha256'])
    paths=sorted((root/'engineering-smoke').glob('*/*.json'))+[root/'cli-graph.json']+sorted(Path('runs/ui').glob('*/run.json'))
    runs=[]
    for path in paths:
        run=RunArtifact.model_validate_json(path.read_bytes())
        prepare_output(run,settings,review_directory=review)
        check('saved_run:'+str(path),not run.generation_requested and run.generation is None and run.result is None
              and len(run.retrieval.evidence)<=6 and run.retrieval.estimated_tokens<=1800)
        if run.request.profile_id=='retrieval-v2' and run.request.mode=='graph':
            audit=run.retrieval.audit
            check('actual_prefallback_trace:'+str(path),len(audit['pre_fallback_candidate_trace'])>=len(run.retrieval.evidence)
                  and audit['graph_rows']<=80 and len(audit['graph_candidates_retained'])<=40)
        runs.append((path,run))
    current=code_identity()
    ui=[(p,r) for p,r in runs if str(p).startswith('runs\\ui') or str(p).startswith('runs/ui')]
    check('actual_final_ui_current_code',any(r.configuration['source_tree_sha256']==current['source_tree_sha256'] for p,r in ui))
    for path,run in runs:
        if run.request.profile_id=='retrieval-v2':
            bad=run.model_copy(deep=True)
            bad.configuration['profile']['policy_sha256']='f'*64
            try:prepare_output(bad,settings,review_directory=review)
            except ValueError as exc:check('tampered_export_rejected','profile/selector/scope' in str(exc))
            else:raise ValueError('Tampered profile reached export')
            break
    for path in Path('src/research_assistant/retrieval').glob('*.py'):
        tree=ast.parse(path.read_text(encoding='utf-8'))
        check('no_gold_import:'+path.name,all(not (isinstance(n,ast.ImportFrom) and n.module and n.module.startswith('research_assistant.evaluation'))
              for n in ast.walk(tree)))
    for name in ('uv.lock','pyproject.toml','project_spec.md','project_spec_submission.md'):
        check('unchanged_requirement_dependency:'+name,file_sha(Path(name))==file_sha(base/name))
    freeze=json.loads((base/'runs/m4-2/freeze-v2.json').read_text(encoding='utf-8'))
    models=0
    for relative,digest in freeze['files'].items():
        if relative.startswith('.cache/'):
            check('copied_model_asset:'+relative,file_sha(Path(relative))==digest);models+=1
    for path in (base/'data/accounting').glob('*'):
        if path.is_file():check('current_accounting_preserved:'+path.name,file_sha(Path('data/accounting')/path.name)==file_sha(path))
    for name in ('.env','data/scopes/retrieval-v2.json','runs/retrieval-v2/m5-2'):
        check('ignored_local_asset:'+name,subprocess.run(['git','check-ignore',name],capture_output=True).returncode==0)
    check('git_diff_check',subprocess.run(['git','diff','--check'],capture_output=True).returncode==0)
    config=json.loads(subprocess.run(['docker','compose','config','--format','json'],capture_output=True,text=True,check=True).stdout)
    check('compose_default_is_isolated',config['name']==scope['target_id'])
    check('graph_preserved_during_acceptance',capture(settings)==before)
    baseline_code='''import json
from pathlib import Path
from research_assistant.evaluation.freeze import load_freeze,file_sha
from research_assistant.graph.recovery import capture
from research_assistant.contracts import fingerprint
from research_assistant.settings import Settings
f=load_freeze(Path('runs/m4-2/freeze-v2.json'))
h=json.loads(Path('runs/m4-3/handoff-complete-scored.json').read_text(encoding='utf-8'))
assert file_sha(Path(h['final_report']))==h['final_report_sha256']
assert file_sha(Path('runs/m4-3/acceptance-final.json'))==h['acceptance_final_sha256']
print(json.dumps({'frozen_files':len(f.files),'graph_sha256':fingerprint(capture(Settings.from_env())),'report_and_acceptance_unchanged':True}))
'''
    baseline=subprocess.run([str(base/'.venv/Scripts/python.exe'),'-c',baseline_code],cwd=base,capture_output=True,text=True,timeout=120,check=True)
    baseline=json.loads(baseline.stdout)
    check('original_frozen_bytes_report_and_graph',baseline['frozen_files']==118 and baseline['graph_sha256']==scope['baseline_graph_sha256'])
    target=subprocess.run(['docker','inspect','dbu-m4-recovery-edaaed2160a3-neo4j-1','--format','{{.State.Status}}'],capture_output=True,text=True,check=True)
    check('consumed_target_still_stopped',target.stdout.strip()=='exited')
    artifacts={str(p):file_sha(p) for p in root.rglob('*') if p.is_file() and not p.name.endswith('.log')}
    for p,r in ui:artifacts[str(p)]=file_sha(p)
    result={'task_id':'M5.2','status':'complete','recorded_at':datetime.now(timezone.utc).isoformat(),**current,
        'worktree':str(Path.cwd()),'baseline':str(base),'checks_passed':len(checks),'checks':checks,'baseline_preservation':baseline,
        'offline_passed':213,'offline_integration_deselected':6,'native_cases_passed':4,'model_assets_reverified':models,
        'real_catalog_engineering_runs_validated':len(runs),'ui_runs':len(ui),'scope_sha256':fingerprint(scope),
        'target_graph_sha256':fingerprint(before),'source_sha256':source_identity(chunks),'catalog_sha256':fingerprint(catalog.facts),
        'approved_claims':51,'review_head':catalog.head,'artifact_sha256':artifacts,
        'implementation_sha256':{str(p):file_sha(p) for prefix in ('src','tests','scripts') for p in Path(prefix).rglob('*.py')},
        'document_sha256':{name:file_sha(Path(name)) for name in ('AGENTS.md','README.md','IMPLEMENTATION_PLAN.md','docs/M5_2_REPORT.md')},
        'generation_calls':0,'paid_calls':0,'extraction_calls':0,'private_access':False,'new_model_downloads':0,
        'skipped':['Reranker model/adapter/inference','Full M5.4 development matrix','Claim enrichment/human review','Generation/paid integration probes','Private/final evaluation'],
        'blockers':[],'next_task':'M5.3; not started','new_final_run_authorized':False}
    write_immutable(root/'acceptance-final.json',json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k not in ('checks','artifact_sha256','implementation_sha256','document_sha256')}))


if __name__=='__main__':main()
