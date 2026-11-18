"""Synthetic-only readiness budgets, source isolation and recovery preparation guards."""

from contextlib import nullcontext
from datetime import datetime,timezone
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from research_assistant.evaluation import matched_readiness as probes,matched_recovery as recovery
from research_assistant.settings import Settings


def fixture(tmp_path,monkeypatch):
    """Use only pytest-owned public metadata and synthetic fake model/target identifiers."""
    monkeypatch.chdir(tmp_path)
    plan=probes.ReadinessPlan(created_at=datetime.now(timezone.utc),project='dbu-m4-recovery-m5eval-'+'1'*12,
        bolt_port=18661,http_port=18662,output_directory='runs/retrieval-v2/m5-5/SYNTHETIC',
        source_scope_file_sha256='a'*64,source_graph_sha256='b'*64,source_tree_sha256='c'*64,
        generator_model='SYNTHETIC',generator_digest='d'*64,ollama_base_url='http://127.0.0.1:11434',image_id='sha256:'+'e'*64)
    path=Path('runs/retrieval-v2/m5-5/SYNTHETIC-plan.json')
    probes.save(path,plan.model_dump(mode='json'))
    return plan,path


@pytest.mark.parametrize('field,value',[
    ('generation_requests',3),('logical_retrieval_requests',25),('output_tokens',1024),
    ('concurrency',2),('retries',1),('paid_budget_usd',.01),('private_inputs_permitted',True),
    ('final_execution_authorized',True),('bolt_port',7687),('bolt_port',9765),
    ('project','dbu-m4-recovery-m5dev-'+'1'*12),('generator_digest','0'*64),
    ('ollama_base_url','https://external.invalid'),('request_timeout_seconds',181)])
def test_readiness_plan_rejects_expanded_or_ambiguous_scope(tmp_path,monkeypatch,field,value):
    plan,_=fixture(tmp_path,monkeypatch)
    with pytest.raises(ValueError):probes.ReadinessPlan.model_validate({**plan.model_dump(),field:value})


def test_durable_task_and_attempt_caps_survive_new_output_and_failed_attempts(tmp_path,monkeypatch):
    plan,path=fixture(tmp_path,monkeypatch)
    probes.claim(plan,path)
    probes.reserve(plan,'generation','synthetic-1')
    probes.reserve(plan,'generation','synthetic-2')
    with pytest.raises(ValueError):probes.reserve(plan,'generation','synthetic-3')
    with pytest.raises(ValueError):probes.reserve(plan,'generation','synthetic-1')
    changed=plan.model_copy(update={'output_directory':'runs/retrieval-v2/m5-5/SYNTHETIC-elsewhere'})
    with pytest.raises(FileExistsError):probes.claim(changed,path)
    with pytest.raises(ValueError):probes.reserve(changed,'retrieval','synthetic')
    with pytest.raises(ValueError):probes.reserve(plan.model_copy(update={'generation_requests':999}),'generation','synthetic')
    assert len(Path(probes.LEDGER).read_text().splitlines())==3


def test_copied_working_directory_keeps_reservations_in_original_ledger(tmp_path,monkeypatch):
    plan,path=fixture(tmp_path,monkeypatch)
    probes.claim(plan,path)
    original=Path(probes.LEDGER).resolve()
    copied=tmp_path/'SYNTHETIC-copy';copied.mkdir()
    monkeypatch.chdir(copied)
    probes.reserve(plan,'retrieval','restored-synthetic',ledger=original)
    assert not Path(probes.LEDGER).exists()
    assert json.loads(original.read_text().splitlines()[-1])['label']=='restored-synthetic'


def test_positive_public_plan_preflight_accepts_named_artifact_root_without_private_io(tmp_path,monkeypatch):
    plan,path=fixture(tmp_path,monkeypatch)
    source=Path(plan.source_scope_path);source.parent.mkdir(parents=True);source.write_text('SYNTHETIC scope')
    plan.source_scope_file_sha256=probes.file_sha(source)
    path.write_text(plan.model_dump_json())
    scope=SimpleNamespace(target_uri='bolt://127.0.0.1:18660',target_id='SYNTHETIC',image_id=plan.image_id,
                          container_id='a'*64,volumes=['SYNTHETIC-data','SYNTHETIC-logs'])
    monkeypatch.setattr(probes.ExperimentScope,'model_validate_json',lambda *a:scope)
    monkeypatch.setattr(probes,'code_identity',lambda:{'source_tree_sha256':plan.source_tree_sha256})
    monkeypatch.setattr(probes,'attest_target',lambda *a:{'container_id':scope.container_id,
        'image_id':scope.image_id,'volumes':scope.volumes})
    model=SimpleNamespace(model=plan.generator_model,digest=plan.generator_digest)
    monkeypatch.setattr(probes.ollama,'Client',lambda **k:SimpleNamespace(list=lambda:SimpleNamespace(models=[model])))
    settings=Settings(neo4j_uri=scope.target_uri,generation_model=plan.generator_model)
    assert probes.load_plan(path,settings)==plan
    assert not probes.LEDGER.exists()


@pytest.mark.parametrize('failure',[False,True])
def test_capacity_uses_two_bounded_synthetic_calls_and_preserves_failures(tmp_path,monkeypatch,failure):
    plan,path=fixture(tmp_path,monkeypatch);probes.claim(plan,path)
    calls=[]
    response=SimpleNamespace(text='READY',digest=plan.generator_digest,model_dump=lambda **k:{'SYNTHETIC':'provider result'})
    class Client:
        last_result=response
        def generate_text(self,messages):
            calls.append(messages)
            if failure:raise ValueError('SYNTHETIC failed or unknown request')
            return response
        def generate_structured(self,schema,messages):
            calls.append(messages)
            return SimpleNamespace(status='ok',value=2),response
    def client(settings,**kwargs):
        assert kwargs=={'context_tokens':4096,'output_tokens':512}
        return Client()
    monkeypatch.setattr(probes,'create_client',client)
    monkeypatch.setattr(probes,'check_resources',lambda:{'SYNTHETIC':True})
    monkeypatch.setattr(probes,'resource_samples',lambda:nullcontext([{'SYNTHETIC':'sample'}]))
    active=SimpleNamespace(digest=plan.generator_digest,context_length=4096,model_dump=lambda **k:{'SYNTHETIC':'resident'})
    monkeypatch.setattr(probes.ollama,'Client',lambda **k:SimpleNamespace(ps=lambda:SimpleNamespace(models=[active])))
    result=probes.capacity(plan,Settings(generation_model='SYNTHETIC'),
        SimpleNamespace(encode=lambda texts:[[0]*384]),SimpleNamespace(score_pairs=lambda pairs:([1,0],[8,8])))
    assert result['complete'] is not failure
    assert len(calls)==len(result['attempts'])==(1 if failure else 2)
    assert result['attempts'][0]['resource_samples']==[{'SYNTHETIC':'sample'}]
    if failure:assert result['last_provider_result']=={'SYNTHETIC':'provider result'}


def test_recovery_never_reuses_existing_container_or_volume(tmp_path,monkeypatch):
    plan,_=fixture(tmp_path,monkeypatch)
    monkeypatch.setattr(recovery.subprocess,'run',lambda *a,**k:SimpleNamespace(returncode=0,stderr=''))
    with pytest.raises(ValueError,match='no existing resource'):recovery.fresh_target(plan,Settings())


def test_native_cases_must_really_execute_without_skips(tmp_path,monkeypatch):
    def command(args,env,log,timeout,**kwargs):
        Path(args[-1].split('=',1)[1]).write_text('<testsuites><testsuite tests="2" failures="0" errors="0" skipped="1"/></testsuites>')
    monkeypatch.setattr(recovery,'command',command)
    with pytest.raises(ValueError,match='execute/pass'):recovery.native_guards(Settings(),tmp_path)


def test_explicit_harness_continuation_retains_request_caps_and_cannot_replay(tmp_path,monkeypatch):
    plan,path=fixture(tmp_path,monkeypatch);probes.claim(plan,path)
    for i in range(12):probes.reserve(plan,'retrieval','working-'+str(i))
    amendment=probes.EngineeringContinuation(prior_plan_path=str(path),prior_plan_sha256=probes.file_sha(path),
        prior_report_path='runs/retrieval-v2/m5-5/SYNTHETIC/report.json',prior_report_sha256='a'*64,
        prior_native_xml_sha256='b'*64,
        reason='native fixtures must run in verified recovery copy, preserving working write guard')
    continued=plan.model_copy(update={'continuation':amendment,'native_fixture_attempt_limit':4,
        'output_directory':'runs/retrieval-v2/m5-5/SYNTHETIC-corrected'})
    probes.claim(continued,path)
    for i in range(12):probes.reserve(continued,'retrieval','restored-'+str(i))
    with pytest.raises(ValueError):probes.reserve(continued,'retrieval','extra')
    probes.reserve(continued,'generation','first');probes.reserve(continued,'generation','second')
    with pytest.raises(ValueError):probes.reserve(continued,'generation','extra')
    with pytest.raises(ValueError):probes.claim(continued,path)
    rows=[json.loads(line) for line in probes.LEDGER.read_text().splitlines()]
    assert sum(r.get('kind')=='retrieval' for r in rows)==24
    assert sum(r.get('kind')=='generation' for r in rows)==2


def test_native_harness_uses_copied_sources_and_current_locked_interpreter(tmp_path,monkeypatch):
    copied=tmp_path/'SYNTHETIC-copy';copied.mkdir()
    calls=[]
    def command(args,env,log,timeout,**kwargs):
        calls.append((args,env,kwargs))
        Path(args[-1].split('=',1)[1]).write_text('<testsuites><testsuite tests="2" failures="0" errors="0" skipped="0"/></testsuites>')
    monkeypatch.setattr(recovery,'command',command)
    assert recovery.native_guards(Settings(),tmp_path,copied)['tests']==2
    args,env,kwargs=calls[0]
    assert args[:3]==[recovery.sys.executable,'-m','pytest']
    assert kwargs['cwd']==copied and env['PYTHONPATH']==str(copied/'src')


def test_parity_reports_failures_and_differences_without_changing_evidence():
    working=[{'condition_id':str(i),'status':'passed','context_sha256':'x','selected_ids':[i]} for i in range(12)]
    restored=[dict(row) for row in working]
    restored[0].update(context_sha256='different')
    restored[1].update(status='failed')
    result=recovery.parity(working,restored)
    assert sum(r['exact_context_equal'] for r in result)==10
    assert sum(r['both_passed'] for r in result)==11
    assert restored[0]['context_sha256']=='different'


def test_timeout_diagnostics_are_retained_without_credentials(tmp_path,monkeypatch):
    def timeout(*a,**k):
        raise recovery.subprocess.TimeoutExpired('SYNTHETIC',1,output=b'SYNTHETIC password',stderr=b'timeout')
    monkeypatch.setattr(recovery.subprocess,'run',timeout)
    path=tmp_path/'SYNTHETIC.log'
    with pytest.raises(recovery.subprocess.TimeoutExpired):
        recovery.command(['SYNTHETIC'],{'NEO4J_PASSWORD':'password'},path,1)
    assert 'password' not in path.read_text() and 'not retried' in path.read_text()


@pytest.mark.parametrize('change',['project','image','volume'])
def test_shutdown_never_acts_on_wrong_owned_target(tmp_path,monkeypatch,change):
    plan,_=fixture(tmp_path,monkeypatch)
    row={'Id':'a'*64,'Name':'/'+plan.project+'-neo4j-1','Image':plan.image_id,
        'Config':{'Labels':{'com.docker.compose.project':plan.project}},
        'State':{'Running':True},'Mounts':[{'Name':plan.project+'_neo4j_data','Destination':'/data'},
            {'Name':plan.project+'_neo4j_logs','Destination':'/logs'}]}
    if change=='project':row['Config']['Labels']['com.docker.compose.project']='SYNTHETIC-other'
    if change=='image':row['Image']='sha256:'+'f'*64
    if change=='volume':row['Mounts'][0]['Name']='SYNTHETIC-other'
    monkeypatch.setattr(recovery.subprocess,'run',lambda *a,**k:SimpleNamespace(returncode=0,stdout=json.dumps([row])))
    monkeypatch.setattr(recovery,'command',lambda *a:pytest.fail('Unexpected lifecycle write'))
    with pytest.raises(ValueError,match='unexpected target'):recovery.stop_owned(plan,None,{},tmp_path)
