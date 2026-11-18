"""Fresh matched-study engineering recovery and local capacity checks; no final experiment."""

import argparse
import gc
import json
import os
from pathlib import Path
import socket
import subprocess
import time
import xml.etree.ElementTree as ET

from research_assistant.contracts import fingerprint
from research_assistant.embeddings import Encoder
from research_assistant.evaluation.freeze import file_sha
from research_assistant.evaluation.matched_assets import public_asset
from research_assistant.evaluation.matched_readiness import LEDGER, ReadinessPlan, capacity, claim, load_plan, retrieval_probes, save
from research_assistant.evaluation.matched_scope import FrozenEvaluationScope, inspect_container, prepare_scope
from research_assistant.graph.recovery import attest_target, capture, export_snapshot, require_read_only, restore_snapshot, verify_snapshot
from research_assistant.graph.repository import GraphRepository
from research_assistant.pipeline import write_immutable
from research_assistant.retrieval.reranker import _resident, pinned_scorer
from research_assistant.settings import Settings, configure_caches


def wait_ready(settings: Settings) -> None:
    """Poll connectivity only, never retry a failed retrieval/provider request."""
    deadline = time.monotonic()+180
    while time.monotonic()<deadline:
        repo = GraphRepository(settings)
        try:
            repo.driver.verify_connectivity()
            return
        except Exception:
            time.sleep(2)
        finally:
            repo.close()
    raise RuntimeError('Fresh matched Neo4j did not become ready')


def fresh_target(plan: ReadinessPlan, settings: Settings) -> tuple[list[str], dict]:
    """Verify unused named volumes/container, ports and installed image before creating anything."""
    for port in (plan.bolt_port, plan.http_port):
        with socket.socket() as probe:
            probe.bind(('127.0.0.1',port))
    for kind, name in [('container',plan.project+'-neo4j-1'),
                       ('volume',plan.project+'_neo4j_data'),('volume',plan.project+'_neo4j_logs')]:
        result = subprocess.run(['docker',kind,'inspect',name],capture_output=True,text=True,timeout=20)
        if result.returncode==0 or ('no such '+kind) not in result.stderr.lower():
            raise ValueError('Fresh target ownership check failed; no existing resource may be reused')
    subprocess.run(['docker','image','inspect',plan.image_id],capture_output=True,text=True,timeout=20,check=True)
    env = {**os.environ, 'NEO4J_READ_ONLY':'false', 'NEO4J_IMAGE':plan.image_id,
           'NEO4J_BOLT_PORT':str(plan.bolt_port), 'NEO4J_HTTP_PORT':str(plan.http_port),
           'NEO4J_USER':settings.neo4j_user, 'NEO4J_PASSWORD':settings.neo4j_password.get_secret_value()}
    return ['docker','compose','-p',plan.project,'-f',str(Path('compose.yaml').resolve())],env


def command(command: list[str], env: dict, log: Path, timeout: int) -> None:
    """Run one bounded command and retain output on failure; redact credentials before logging."""
    try:
        result = subprocess.run(command,env=env,capture_output=True,text=True,timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        parts=[part.decode('utf-8',errors='replace') if isinstance(part,bytes) else (part or '')
               for part in (exc.stdout,exc.stderr)]
        text=''.join(parts)+'\nBounded command timed out; not retried.\n'
        write_immutable(log,text.replace(env.get('NEO4J_PASSWORD','\0'),'[REDACTED]'))
        raise
    # Docker startup/pytest outputs contain no configuration dump; still redact known credentials.
    text = result.stdout+result.stderr
    if secret := env.get('NEO4J_PASSWORD'):
        text=text.replace(secret,'[REDACTED]')
    write_immutable(log,text)
    result.check_returncode()


def native_guards(target: Settings, output: Path) -> dict:
    """Exercise and clean UUID-owned baseline/V2 records on the new writable copy only."""
    env = {**os.environ,'NEO4J_URI':target.neo4j_uri,'RUN_V2_SMOKE':'1','RUN_RETRIEVAL_SMOKE':'1',
           'NEO4J_PASSWORD':target.neo4j_password.get_secret_value()}
    report=output/'native.xml'
    command(['uv','run','--locked','--offline','python','-m','pytest','-m','integration',
        'tests/integration/test_graph_retrieval_repository.py','tests/integration/test_retrieval_v2_repository.py',
        '-q','--junitxml='+str(report)],env,output/'native.log',240)
    suites=list(ET.parse(report).getroot().iter('testsuite'))
    counts={key:sum(int(s.get(key,0)) for s in suites) for key in ('tests','failures','errors','skipped')}
    if counts != {'tests':2,'failures':0,'errors':0,'skipped':0}:
        raise ValueError('Fresh native guard checks did not execute/pass both cases')
    return counts


def stop_owned(plan: ReadinessPlan, scope: FrozenEvaluationScope | None, env: dict, output: Path) -> None:
    """Stop only this freshly owned target, including a partially started/exited container."""
    result=subprocess.run(['docker','inspect',plan.project+'-neo4j-1'],capture_output=True,text=True,timeout=20)
    if result.returncode!=0:
        if 'no such' in result.stderr.lower():
            return
        result.check_returncode()
    row=json.loads(result.stdout)[0]
    volumes={m.get('Name') for m in row['Mounts'] if m['Destination'] in {'/data','/logs'}}
    if (row['Config']['Labels'].get('com.docker.compose.project')!=plan.project
            or row['Name']!='/'+plan.project+'-neo4j-1' or row['Image']!=plan.image_id
            or volumes!={plan.project+'_neo4j_data',plan.project+'_neo4j_logs'}
            or (scope is not None and row['Id']!=scope.container_id)):
        raise ValueError('Refusing stop on an unexpected target identity')
    if row['State']['Running']:
        command(['docker','stop',row['Id']],env,output/'stop.log',60)
    if scope is not None:
        inspect_container(scope,running=False)


def parity(working: list[dict], restored: list[dict]) -> list[dict]:
    """Disclose ANN/context differences rather than silently rebuilding or changing ranking."""
    if len(working)!=12 or len(restored)!=12:
        raise ValueError('All twelve engineering conditions must be reported')
    before={row['condition_id']:row for row in working}
    return [{'condition_id':row['condition_id'],
             'both_passed':row['status']==before[row['condition_id']]['status']=='passed',
             'exact_context_equal':row.get('context_sha256')==before[row['condition_id']].get('context_sha256')
                if row['status']==before[row['condition_id']]['status']=='passed' else False,
             'selected_ids_equal':row.get('selected_ids')==before[row['condition_id']].get('selected_ids')
                if row['status']==before[row['condition_id']]['status']=='passed' else False} for row in restored]


def run(plan_path: Path, settings: Settings) -> dict:
    """One new recovery, 24 public engineering reads and two synthetic local adapter probes."""
    plan=load_plan(plan_path,settings)
    root=Path.cwd().resolve()
    output=public_asset(plan.output_directory)
    if output.exists():
        raise ValueError('Use a new readiness output directory; never overwrite prior evidence')
    if fingerprint(capture(settings)) != plan.source_graph_sha256:
        raise ValueError('Working graph changed before readiness')
    commands,env=fresh_target(plan,settings)
    claim(plan,plan_path)
    output.mkdir(parents=True,exist_ok=False)
    target=settings.model_copy(update={'neo4j_uri':f'bolt://127.0.0.1:{plan.bolt_port}'})
    snapshot=output/'snapshot'
    report={'task_id':'M5.5.4','purpose':'matched_readiness_not_final_evaluation',
        'project':plan.project,'target_uri':target.neo4j_uri,'source_uri':settings.neo4j_uri,
        'readiness_plan_sha256':file_sha(plan_path),'complete':False,'matched_readiness_complete':False,
        'target_read_only_proved':False,'final_execution_authorized':False,'private_evaluation_inputs_read':0}
    created=False
    scope=None
    try:
        encoder=Encoder()
        scorer=pinned_scorer()
        report['working']=retrieval_probes(plan,settings,encoder)
        del encoder,scorer
        _resident.cache_clear()
        gc.collect()
        report['export']=export_snapshot(settings,snapshot,Path('data/reviews/expansion-v1'),
                                         freeze_corpus=True,matched_runtime_assets=True)
        manifest,graph=verify_snapshot(snapshot)
        report.update(graph_sha256=manifest['graph_sha256'],snapshot_manifest_sha256=file_sha(snapshot/'manifest.json'))
        created=True
        command(commands+['up','-d','--pull','never','neo4j'],env,output/'start.log',120)
        wait_ready(target)
        report['restore']=restore_snapshot(snapshot,target,plan.project)
        report['image_id']=report['restore']['image_id']
        if report['image_id']!=plan.image_id:
            raise ValueError('Restored image differs from the readiness pin')
        try:
            restore_snapshot(snapshot,target,plan.project)
        except ValueError as exc:
            if 'must be empty' not in str(exc):
                raise
            report['nonempty_restore_refused']=True
        else:
            raise ValueError('Repeated restore was not refused')
        report['native_guards']=native_guards(target,output)
        if capture(target)!=graph:
            raise ValueError('Native guard cleanup changed the restored graph/schema')
        env.update(NEO4J_READ_ONLY='true')
        command(commands+['up','-d','--pull','never','neo4j'],env,output/'readonly.log',120)
        wait_ready(target)
        report['read_only_probe']=require_read_only(target)
        report['target_read_only_proved']=True
        physical={**report,'complete':True,'purpose':'physical_recovery_only_capacity_pending'}
        save(output/'physical-recovery.json',physical)
        prepare_scope(snapshot,output/'physical-recovery.json',settings,output/'scope.json')
        scope=FrozenEvaluationScope.model_validate_json((output/'scope.json').read_bytes())
        inspect_container(scope,running=True)
        os.chdir(snapshot/'files')
        encoder=Encoder()
        scorer=pinned_scorer()
        report['restored']=retrieval_probes(plan,target,encoder,frozen=scope,artifact_directory=output,ledger=root/LEDGER)
        os.chdir(root)
        # Keep reservations/accounting in the original worktree, never a copied ledger.
        report['capacity_checks']=capacity(plan,target,encoder,scorer)
        report['parity']=parity(report['working'],report['restored'])
        report['contexts_equal']=sum(row['exact_context_equal'] for row in report['parity'])
        if capture(target)!=graph or fingerprint(capture(settings))!=plan.source_graph_sha256:
            raise ValueError('Working/restored graph changed during readiness')
        verify_snapshot(snapshot)
        report['copied_runtime_assets_verified']=True
        report['source_preserved']=True
        report['logical_retrieval_requests']=24
        report['generation_requests']=len(report['capacity_checks']['attempts'])
        report['complete']=report['matched_readiness_complete']=(
            report['capacity_checks']['complete'] and all(row['both_passed'] for row in report['parity'])
            and report['contexts_equal']==12)
    except Exception as exc:
        report.update(error_type=type(exc).__name__,error=settings.redact(str(exc)))
    finally:
        os.chdir(root)
        if created:
            try:
                stop_owned(plan,scope,env,output)
                report['target_stopped']=True
            except Exception as exc:
                report.update(target_stopped=False,stop_error=settings.redact(str(exc)))
                report['complete']=report['matched_readiness_complete']=False
        else:
            report['target_stopped']=None
        save(output/'report.json',report)
    return {'complete':report['complete'],'read_only':report['target_read_only_proved'],
            'target_stopped':report['target_stopped'],'report':str(output/'report.json'),
            'final_execution_authorized':False}


def main(argv=None) -> int:
    """Run only an explicit public readiness plan; never accept private paths or final receipts."""
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan',type=Path,required=True)
    args=parser.parse_args(argv)
    configure_caches()
    os.environ.update(HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1')
    try:
        result=run(public_asset(args.plan),Settings.from_env())
        print(json.dumps(result))
        return 0 if result['complete'] else 1
    except Exception as exc:
        print(json.dumps({'complete':False,'error_type':type(exc).__name__,
                          'message':'Readiness declined; inspect named public plan/artifacts. No final execution authorized.'}))
        return 1


if __name__=='__main__':
    raise SystemExit(main())
