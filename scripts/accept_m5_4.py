"""Finalize M5.4 from public receipts, actual tests, source bindings and baseline preservation."""

import json
import subprocess
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

from research_assistant.contracts import RunArtifact, fingerprint
from research_assistant.evaluation.freeze import file_sha
from research_assistant.graph.recovery import capture
from research_assistant.pipeline import code_identity, write_immutable
from research_assistant.product import prepare_output
from research_assistant.retrieval.reranker import verified_manifest
from research_assistant.settings import Settings, configure_caches


def main():
    """No retrieval, generation, scorer inference, private access or graph mutation."""
    root = Path('runs/retrieval-v2/m5-4'); matrix = root/'comparison-v1'; checks = []
    def check(name, value):
        checks.append({'name': name, 'passed': bool(value)})
        if not value:
            raise ValueError(name)
    manifest = json.loads((matrix/'execution-manifest.json').read_text(encoding='utf-8'))
    complete = json.loads((matrix/'execution-complete.json').read_text(encoding='utf-8'))
    scores = json.loads((matrix/'offline-results.json').read_text(encoding='utf-8'))
    for path, sha in manifest['file_sha256'].items():
        check('bound_input:'+path, file_sha(Path(path))==sha)
    check('96_once_only_successes', complete['attempts']==96 and complete['failures']==0 and len(list((matrix/'reservations').glob('*.json')))==96)
    check('all_offline_consistency_checks', scores['checks_passed']==len(scores['checks']) and all(c['passed'] for c in scores['checks']))
    for name, count in [('offline-verified.xml',239),('native.xml',5)]:
        suite = ET.parse(root/name).getroot().find('testsuite')
        check('test_receipt:'+name, int(suite.attrib['tests'])==count and int(suite.attrib['failures'])==int(suite.attrib['errors'])==int(suite.attrib['skipped'])==0)
    settings = Settings.from_env(); scope = manifest['readiness']['scope']
    check('same_development_graph', fingerprint(capture(settings))==manifest['readiness']['graph_sha256'])
    check('pinned_model', verified_manifest().model_dump()==manifest['model'])
    check('same_executable', code_identity()['source_tree_sha256']==manifest['source_tree_sha256'])
    plans = json.loads((matrix/'query-plan-probes.json').read_text(encoding='utf-8'))
    check('24_separate_plan_reads', plans['separate_read_only_executions']==24 and len(plans['results'])==12)
    for probe in plans['results']:
        for kind, result in probe['inspections'].items():
            operators = result['metrics']['operators']
            check('indexed_plan:'+probe['arm']+probe['family']+kind,
                  any('Index' in str(op['operator']) for op in operators) and not any('AllNodesScan' in str(op['operator']) for op in operators))
        check('bounded_rows:'+probe['arm']+probe['family'], probe['inspections']['PROFILE']['returned_rows']<=5)
    native = json.loads((root/'native-v2-plans.json').read_text(encoding='utf-8'))
    check('positive_v2_route_and_revocation_checks', all(native[k] for k in ('finding_start_outside_baseline','direct_entity_start_outside_baseline','no_evaluations_required','mentions_not_promoted','unapproved_role_rejected','wrong_owner_rejected','stale_and_revoked_rejected')))
    ui = json.loads((root/'ui-check.json').read_text(encoding='utf-8'))
    path = Path(ui['run_path']); check('actual_UI_hash', file_sha(path)==ui['run_sha256'])
    run = RunArtifact.model_validate_json(path.read_bytes())
    check('actual_new_explicit_UI_query', run.request.profile_id=='retrieval-v2' and run.request.selector_id=='cross_encoder'
          and run.request.corpus_id==scope['corpus_id'] and run.configuration['source_tree_sha256']==manifest['source_tree_sha256']
          and run.generation is None and run.result is None and not run.generation_requested)
    prepare_output(run, settings, review_directory=Path('data/reviews/expansion-v1'))
    base = Path(scope['baseline_root'])
    code = '''
import json
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
    preserved = json.loads(subprocess.run([str(base/'.venv/Scripts/python.exe'),'-c',code],cwd=base,
        capture_output=True,text=True,check=True,timeout=120).stdout)
    check('118_baseline_files_and_graph', preserved['frozen_files']==118 and preserved['source_graph']==scope['baseline_graph_sha256'])
    for name in ('uv.lock','pyproject.toml'):
        check('unchanged_dependencies:'+name, file_sha(Path(name))==file_sha(base/name))
    stopped = subprocess.run(['docker','inspect','dbu-m4-recovery-edaaed2160a3-neo4j-1','--format','{{.State.Status}}'],capture_output=True,text=True,check=True).stdout.strip()
    check('consumed_target_stopped', stopped=='exited')
    check('whitespace', subprocess.run(['git','diff','--check'],capture_output=True).returncode==0)
    go = any(signal['signal_passed'] for signal in scores['paired_graph_signal'])
    docs = ['AGENTS.md','README.md','IMPLEMENTATION_PLAN.md','project_spec.md','project_spec_submission.md','docs/M5_4_REPORT.md']
    outcome = {'task_id':'M5.4','status':'complete','recorded_at':datetime.now(timezone.utc).isoformat(), **code_identity(),
        'checks_passed':len(checks), 'checks':checks, 'offline_consistency_checks':scores['checks_passed'],
        'offline_passed':239,'integration_deselected':7,'native_passed':5,'retrieval_requests':96,'request_failures':0,
        'additional_UI_requests':1,'separate_plan_reads':24,'baseline_preservation':preserved,
        'graph_signal':scores['paired_graph_signal'],'decision':'go' if go else 'no-go',
        'decision_scope':'Larger fresh Graph answer study under the original-51/catalog route+selector hypothesis only',
        'document_sha256':{p:file_sha(Path(p)) for p in docs},
        'artifact_sha256':{str(p):file_sha(p) for p in root.rglob('*') if p.is_file() and p.suffix not in ('.log',)},
        'generation':0,'paid':0,'extraction':0,'private_access':False,'new_model_downloads':0,'dependency_changes':0,
        'skipped':['Qwen/paid generation','Combined Qwen capacity','New claim enrichment/review','Fresh private/final study'],
        'blockers':[], 'next_task':'M5.5 requires separate gates' if go else 'Report limited/negative Graph result; do not start M5.5/.6 under this hypothesis',
        'new_final_run_authorized':False}
    write_immutable(root/'acceptance-final.json',json.dumps(outcome,indent=2)+'\n')
    print(json.dumps({k:v for k,v in outcome.items() if k not in ('checks','artifact_sha256','document_sha256')},indent=2))


if __name__=='__main__':
    configure_caches(); main()
