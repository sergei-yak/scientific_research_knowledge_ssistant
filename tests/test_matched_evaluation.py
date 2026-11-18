"""SYNTHETIC ONLY: matched-study privacy, policy, once-only execution and blind scoring."""

from collections import Counter
from datetime import datetime, timezone
import copy
import csv
import json
from pathlib import Path
from types import SimpleNamespace
from contextlib import nullcontext

import pytest

from research_assistant.contracts import DraftAnswer, EvaluationQuestion, GoldFact, LLMResult, QueryRequest, SourceSpanRef, fingerprint, text_sha
from research_assistant.evaluation import matched_freeze as guards, matched_runner as runner, matched_scope as scopes
from research_assistant.evaluation.matched_assets import public_asset
from research_assistant.evaluation.matched_freeze import MatchedAuthorization, MatchedFreeze
from research_assistant.evaluation.matched_permits import SlotPermit, StudyGrant, _issue_slot, _register_study, validate_slot
from research_assistant.evaluation.matched_scope import FrozenEvaluationScope
from research_assistant.evaluation.proposals import MatchedStudyProposal
from research_assistant.evaluation.readiness_v2 import SourceHumanAttestation, load_source_attestation
from research_assistant.evaluation.scheduling import QuestionKey, build_proposed_schedule
from research_assistant.generation import validate_answer
from research_assistant.settings import Settings
from test_product import fixture_run

FIXTURE = Path(__file__).parent/'fixtures/matched_source_synthetic.json'


def write(path, value):
    """Write only pytest-owned synthetic fixtures, never production/evaluator artifacts."""
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,indent=2),encoding='utf-8')


def receipt(path, freeze_path, **changes):
    raw=MatchedAuthorization(authorization_id='1'*32,freeze_file_sha256=guards.file_sha(freeze_path),
        reviewer='SYNTHETIC TEST ONLY',received_at=datetime.now(timezone.utc),verbatim_response='SYNTHETIC permission only',
        approved=True,disclosed_post_negative_gate_continuation=True,author_context_exposure_acknowledged=True).model_dump(mode='json')
    raw.update(changes)
    write(path,{**raw,'receipt_sha256':fingerprint(raw)})


def synthetic_setup(tmp_path,monkeypatch):
    """A new temporary workspace and evaluator root with synthetic prompts/gold/receipts."""
    work=tmp_path/'workspace';work.mkdir()
    private=tmp_path/'retrieval-v2-fresh-v1';inputs=private/'approved-v2';inputs.mkdir(parents=True)
    raw=json.loads(FIXTURE.read_text(encoding='utf-8'))
    monkeypatch.chdir(work)
    prefix=Path('runs/retrieval-v2/m5-5')
    snapshot=prefix/'snapshot';(snapshot/'files').mkdir(parents=True)
    write(snapshot/'manifest.json',{'SYNTHETIC':'snapshot'})
    groups={}
    for split,n in [('development',2),('held_out',4)]:
        groups[split]=[{'question_id':f'SYNTHETIC-{split}-{category}-{i}',
            'question':f'SYNTHETIC {split} {category} question {i}?','split':split,'category':category}
            for category in ('direct','cross_paper','multi_hop','unanswerable') for i in range(n)]
    dev=snapshot/'files/data/evaluation/development/expansion-v1/questions.jsonl';dev.parent.mkdir(parents=True)
    dev.write_text(''.join(json.dumps(row)+'\n' for row in groups['development']))
    (inputs/'questions.jsonl').write_text(''.join(json.dumps(row)+'\n' for row in groups['held_out']))
    (inputs/'annotations.jsonl').write_text('SYNTHETIC SECRET GOLD: parse only after288generation slots')
    (inputs/'HUMAN_APPROVAL_LEDGER.jsonl').write_text('SYNTHETIC ledger, not real human approvals')
    for key,value in raw['approved_external_snapshot'].items():
        raw['approved_external_snapshot'][key]=str(inputs if key=='root' else inputs/Path(value.replace('\\','/')).name)
    raw['actual_human_evidence']['new_response_preserved_copy_path']=str(private/'SYNTHETIC-response.json')
    commits=raw['current_dataset_commitments']
    commits['questions_file_sha256']=guards.file_sha(inputs/'questions.jsonl')
    commits['annotations_file_sha256']=guards.file_sha(inputs/'annotations.jsonl')
    commits['human_approval_ledger_sha256']=guards.file_sha(inputs/'HUMAN_APPROVAL_LEDGER.jsonl')
    source=prefix/'source.json';write(source,raw)
    scope=FrozenEvaluationScope(scope_id='m5eval-'+'1'*12,corpus_id='a'*64,source_chunks_sha256='a'*64,
        review_head='a'*64,catalog_sha256='a'*64,baseline_root=str(tmp_path/'baseline'),
        source_uri='bolt://127.0.0.1:60395',target_uri='bolt://127.0.0.1:18659',
        target_project='dbu-m4-recovery-m5eval-'+'1'*12,container_id='c'*64,image_id='sha256:'+'d'*64,
        volumes=['dbu-m4-recovery-m5eval-'+'1'*12+'_neo4j_data','dbu-m4-recovery-m5eval-'+'1'*12+'_neo4j_logs'],
        graph_sha256=fingerprint({'SYNTHETIC':'graph'}),snapshot_manifest_sha256=guards.file_sha(snapshot/'manifest.json'),
        projection_scope_id='m5dev-'+'2'*12,projection_scope_sha256='e'*64)
    scopepath=prefix/'scope.json';write(scopepath,scope.model_dump(mode='json'))
    tracked=Path('uv.lock');tracked.write_text('SYNTHETIC frozen lock')
    proof=prefix/'recovery.json';write(proof,{'complete':True,'target_read_only_proved':True,
        'matched_readiness_complete':True,'capacity_checks':{'complete':True},
        'logical_retrieval_requests':24,'copied_runtime_assets_verified':True,
        'graph_sha256':scope.graph_sha256,'snapshot_manifest_sha256':scope.snapshot_manifest_sha256,
        'project':scope.target_project,'target_uri':scope.target_uri,'image_id':scope.image_id})
    settings=Settings(generation_provider='ollama',generation_model='synthetic',max_retries=0,max_concurrency=1)
    freeze=MatchedFreeze(created_at=datetime.now(timezone.utc),scope=scope,scope_path=scopepath.as_posix(),
        scope_file_sha256=guards.file_sha(scopepath),source_attestation_path=source.as_posix(),source_attestation_sha256=guards.file_sha(source),
        approved_inputs=SourceHumanAttestation.model_validate(raw).approved_external_snapshot,
        questions_sha256=commits['questions_file_sha256'],annotations_sha256=commits['annotations_file_sha256'],
        approval_ledger_sha256=commits['human_approval_ledger_sha256'],development_dataset_sha256='a'*64,
        private_root=str(private),snapshot_directory=snapshot.as_posix(),recovery_report=proof.as_posix(),
        recovery_report_sha256=guards.file_sha(proof),code_revision='SYNTHETIC',source_tree_sha256='a'*64,
        files={tracked.as_posix():guards.file_sha(tracked)},runtime_versions={},encoder_revision='encoder',
        reranker_identity={'SYNTHETIC':True},profile_policy_hashes={arm:'a'*64 for arm in ('A0','A1','A2')},
        generator_model='synthetic',generator_digest='d'*64,ollama_base_url=settings.ollama_base_url,
        request_timeout_seconds=settings.request_timeout_seconds,graph_query_timeout_seconds=settings.graph_query_timeout_seconds)
    fp=prefix/'freeze.json';write(fp,freeze.model_dump(mode='json'))
    auth=prefix/'authorization.json';receipt(auth,fp)
    return SimpleNamespace(freeze=freeze,fp=fp,auth=auth,private=private,settings=settings,raw=raw,source=source,
                           scopepath=scopepath,snapshot=snapshot,groups=groups,proof=proof,work=work)


def test_typed_source_adapter_is_public_only_and_preserves_limitations(tmp_path,monkeypatch):
    x=synthetic_setup(tmp_path,monkeypatch)
    old=Path.resolve
    def checked(path,*args,**kwargs):
        assert not str(path).startswith(str(x.private)), 'Private path resolution during public adapter'
        return old(path,*args,**kwargs)
    monkeypatch.setattr(Path,'resolve',checked)
    source=load_source_attestation(x.source,guards.file_sha(x.source))
    assert source.counts.approved==16 and source.final_execution_authorized is False
    assert source.timing.actual_new_total_review_minutes is None
    assert source.correction_novelty_and_exposure_limits['clean_outcome_blind_authorship_claim_allowed'] is False


@pytest.mark.parametrize('section,key,value',[
    ('counts','approved',15),('counts','needs_review',1),
    ('actual_human_evidence','actual_required_new_declaration_checkbox_acknowledgments',0),
    ('actual_human_evidence','approval_is_from_actual_human_receipts_not_mechanical_validation_alone',False),
    ('correction_novelty_and_exposure_limits','clean_outcome_blind_authorship_claim_allowed',True),
    ('remaining_gates','final_generation_or_paid_or_experiment_authorization',True),
    ('declaration_lineage','current_declaration_condition_satisfied_by_genuine_new_human_checkbox',False),
])
def test_invalid_source_approval_exposure_and_declaration_are_rejected(section,key,value):
    raw=json.loads(FIXTURE.read_text());raw[section][key]=value
    with pytest.raises(ValueError):SourceHumanAttestation.model_validate(raw)


def test_source_extra_gold_fields_and_changed_public_hash_are_rejected(tmp_path,monkeypatch):
    x=synthetic_setup(tmp_path,monkeypatch)
    raw=copy.deepcopy(x.raw);raw['reference_answer']='SYNTHETIC SECRET'
    with pytest.raises(ValueError):SourceHumanAttestation.model_validate(raw)
    with pytest.raises(ValueError,match='commitment changed'):load_source_attestation(x.source,'f'*64)


@pytest.mark.parametrize('name',['../escape.json','.env','data/reviews/private.json','runs/m4-2/freeze-v2.json','C:/SYNTHETIC/external.json'])
def test_matched_public_boundary_rejects_unlisted_old_private_secret_inputs(tmp_path,monkeypatch,name):
    monkeypatch.chdir(tmp_path)
    with pytest.raises(ValueError):public_asset(name)


def test_new_asset_boundary_does_not_widen_the_legacy_reader(tmp_path,monkeypatch):
    from research_assistant.evaluation.freeze import public_asset as legacy
    monkeypatch.chdir(tmp_path)
    assert public_asset('runs/retrieval-v2/m5-5/proposal.json').is_relative_to(tmp_path)
    with pytest.raises(ValueError):legacy('runs/retrieval-v2/m5-5/proposal.json')


@pytest.mark.parametrize('field,value',[('output_tokens',1024),('generation_request_limit',96),('retries',1),
    ('paid_budget_usd',1),('disclosed_post_negative_gate_continuation',False),('author_context_exposure_acknowledged',False)])
def test_matched_authorization_limits_precede_private_context(tmp_path,monkeypatch,field,value):
    monkeypatch.chdir(tmp_path)
    fp=Path('runs/retrieval-v2/m5-5/freeze.json');write(fp,{})
    auth=fp.with_name('auth.json');receipt(auth,fp,**{field:value})
    monkeypatch.setattr(runner,'load_freeze',lambda *a,**k:pytest.fail('Reached freeze/private context before valid approval'))
    with pytest.raises(ValueError):runner.execute(fp,auth,Settings())


def test_missing_and_legacy_approvals_fail_before_private_io(tmp_path,monkeypatch):
    from research_assistant.evaluation.freeze import FinalRunAuthorization
    monkeypatch.chdir(tmp_path);fp=Path('runs/retrieval-v2/m5-5/freeze.json');write(fp,{})
    monkeypatch.setattr(runner,'load_freeze',lambda *a,**k:pytest.fail('Reached private context'))
    with pytest.raises(FileNotFoundError):runner.execute(fp,fp.with_name('missing.json'),Settings())
    legacy=FinalRunAuthorization(authorization_id='1'*32,freeze_file_sha256=guards.file_sha(fp),reviewer='SYNTHETIC',
        received_at=datetime.now(timezone.utc),verbatim_response='SYNTHETIC old study only',approved=True).model_dump(mode='json')
    auth=fp.with_name('legacy.json');write(auth,{**legacy,'receipt_sha256':fingerprint(legacy)})
    with pytest.raises(ValueError):runner.execute(fp,auth,Settings())


def test_public_freeze_binds_real_source_and_scope_without_private_reads(tmp_path,monkeypatch):
    x=synthetic_setup(tmp_path,monkeypatch)
    assert guards.load_freeze(x.fp,verify_files=False).annotations_sha256==x.freeze.annotations_sha256
    raw=x.freeze.model_dump(mode='json');raw['annotations_sha256']='e'*64;write(x.fp,raw)
    with pytest.raises(ValueError,match='attestation differs'):guards.load_freeze(x.fp,verify_files=False)


@pytest.mark.parametrize('field,value',[('target_uri','bolt://127.0.0.1:7687'),('target_uri','bolt://127.0.0.1:9765'),
    ('target_uri','bolt://remote.invalid:18659'),('target_project','dbu-m4-recovery-edaaed2160a3'),('frozen',False)])
def test_frozen_scope_cannot_repoint_to_old_working_or_remote_targets(tmp_path,monkeypatch,field,value):
    x=synthetic_setup(tmp_path,monkeypatch)
    raw=x.freeze.scope.model_dump(mode='json');raw[field]=value
    with pytest.raises(ValueError):FrozenEvaluationScope.model_validate(raw)


def test_incomplete_runtime_file_set_and_mutated_plan_fail(tmp_path,monkeypatch):
    x=synthetic_setup(tmp_path,monkeypatch)
    monkeypatch.setattr(guards,'runtime_versions',lambda:{})
    monkeypatch.setattr(guards,'code_identity',lambda:{'source_tree_sha256':'a'*64})
    with pytest.raises(ValueError,match='file set is incomplete'):guards.load_freeze(x.fp)
    bad=x.freeze.model_copy(deep=True);bad.plan=bad.plan.model_copy(update={'generation_request_limit':1})
    with pytest.raises(ValueError):guards.verify_freeze(bad,verify_files=False)


def test_single_use_opaque_permit_cannot_be_constructed_copied_or_rebound(tmp_path,monkeypatch):
    x=synthetic_setup(tmp_path,monkeypatch)
    authorization=guards.authorize(x.auth,x.fp)
    keys=[QuestionKey(**{k:row[k] for k in ('question_id','split','category')}) for rows in x.groups.values() for row in rows]
    slot=build_proposed_schedule(keys,x.freeze.plan)[0]
    request=QueryRequest(question='SYNTHETIC question',corpus_id=x.freeze.scope.corpus_id,
        mode=slot.condition.mode,profile_id=slot.condition.profile_id,selector_id=slot.condition.selector_id)
    settings=x.settings.model_copy(update={'neo4j_uri':x.freeze.scope.target_uri})
    with pytest.raises(ValueError):validate_slot(SlotPermit(),request,settings,4096,512,.3)
    with pytest.raises(ValueError):_issue_slot(StudyGrant(),slot,request,reservation_persisted=True)
    grant=_register_study(x.freeze,guards.file_sha(x.fp),authorization)
    with pytest.raises(ValueError):_issue_slot(grant,slot,request,reservation_persisted=False)
    permit=_issue_slot(grant,slot,request,reservation_persisted=True)
    changed=request.model_copy(update={'question':'SYNTHETIC altered'})
    with pytest.raises(ValueError):validate_slot(permit,changed,settings,4096,512,.3)
    with pytest.raises(ValueError):validate_slot(copy.copy(permit),request,settings,4096,512,.3)
    with pytest.raises(ValueError):validate_slot(permit,request,settings,4096,1024,.3)
    validate_slot(permit,request,settings,4096,512,.3,consume=True)
    with pytest.raises(ValueError):validate_slot(permit,request,settings,4096,512,.3)
    with pytest.raises(ValueError):_issue_slot(grant,slot,request,reservation_persisted=True)


def execute_fixture(x,monkeypatch,*,fail_at=None):
    original=guards.load_freeze
    monkeypatch.setattr(runner,'load_freeze',lambda path:original(path,verify_files=False))
    target=x.settings.model_copy(update={'neo4j_uri':x.freeze.scope.target_uri})
    monkeypatch.setattr(runner,'_target',lambda *a:target)
    monkeypatch.setattr(runner,'Encoder',lambda:SimpleNamespace(revision='encoder',mini_tokenizer=SimpleNamespace(encode=lambda *a,**k:[1,2])))
    monkeypatch.setattr(runner,'code_identity',lambda:{'source_tree_sha256':'a'*64})
    monkeypatch.setattr(runner,'capture',lambda settings:{'SYNTHETIC':'graph'})
    base,_,chunks=fixture_run();source=next(iter(chunks.values()))
    span=SourceSpanRef(paper_id=source.paper_id,source_sha256=source.source_sha256,chunk_id=source.chunk_id,
        start=0,end=len(source.text),quote_sha256=text_sha(source.text))
    gold={}
    for rows in x.groups.values():
        for row in rows:
            absent=row['category']=='unanswerable'
            gold[row['question_id']]=EvaluationQuestion(**row,reference_answer='SYNTHETIC SECRET GOLD',
                facts=[] if absent else [GoldFact(fact_id='SYNTHETIC-fact',statement='SYNTHETIC supported fact',support_sets=[[span]])],
                sufficient_fact_sets=[] if absent else [['SYNTHETIC-fact']])
    calls=[]
    def query(request,settings,freeze,permit,encoder):
        assert 'SECRET' not in request.question
        validate_slot(permit,request,settings,4096,512,.3,consume=True)
        calls.append(request)
        if len(calls)==fail_at:raise RuntimeError('SYNTHETIC PRIVATE failure')
        run=base.model_copy(deep=True);run.request=request;run.run_id='SYNTHETIC-'+str(len(calls))
        run.corpus_manifest.update(corpus_id=request.corpus_id,encoder_revision='encoder')
        run.configuration.update(encoder_revision='encoder',source_tree_sha256='a'*64)
        run.retrieval.requested_mode=run.retrieval.effective_mode=request.mode
        run.generation_requested=True
        run.generation=LLMResult(text='SYNTHETIC response',provider='ollama',model='synthetic',digest='d'*64,
            elapsed_ms=1,usage={'output_tokens':1},settings={},messages=[])
        run.result=validate_answer(DraftAnswer(answer='SYNTHETIC supported report',citations=['E1'],insufficient_evidence=False),run.retrieval)
        return run
    monkeypatch.setattr(runner,'run_matched_query',query)
    def after_generation(*args):
        assert len(calls)==288,'Gold parsed before all generation slots completed'
        return gold
    monkeypatch.setattr(runner,'_gold',after_generation)
    monkeypatch.setattr(runner,'load_corpus_chunks',lambda corpus:chunks)
    return calls


def test_complete_synthetic_288_run_once_only_then_human_seal_and_condition_reveal(tmp_path,monkeypatch):
    x=synthetic_setup(tmp_path,monkeypatch);calls=execute_fixture(x,monkeypatch)
    try:result=runner.execute(x.fp,x.auth,x.settings)
    except runner.RunnerFailure as exc:pytest.fail(Path(exc.private_report).read_text()) # pytest-owned SYNTHETIC only
    assert len(calls)==result['answer_runs']==288 and result['extra_encoder_reads']==0
    assert all(len(set((r.profile_id,r.selector_id,r.mode) for r in calls[i:i+12]))==12 for i in range(0,288,12))
    with pytest.raises(ValueError,match='already started'):runner.execute(x.fp,x.auth,x.settings)
    replacement=x.auth.with_name('replacement.json');receipt(replacement,x.fp,authorization_id='2'*32)
    with pytest.raises(ValueError,match='already started'):runner.execute(x.fp,replacement,x.settings)
    packet=Path(result['scoring_packet_directory'])
    public=json.loads((packet/'answers.json').read_text())
    assert len(public)==288 and all(set(row)=={'answer_id','question_id','question','answer','abstained','citations'} for row in public)
    with pytest.raises(runner.RunnerFailure):runner.grade(x.fp,x.auth)
    with pytest.raises(runner.RunnerFailure):runner.grade(x.fp,x.auth,scores_path=packet/'scores.csv')
    with (packet/'scores.csv').open(newline='') as f:rows=list(csv.DictReader(f))
    for row in rows:row.update(correctness='1',citation_support='1',correct_abstention='',reviewer='SYNTHETIC TEST ONLY',scored_at='2020-01-01T00:00:00Z',notes='SYNTHETIC fixture scores, never real human')
    completed=packet/'SYNTHETIC-completed.csv'
    with completed.open('w',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=rows[0]);writer.writeheader();writer.writerows(rows)
    assert runner.grade(x.fp,x.auth,scores_path=completed)['answers']==288
    report=runner.grade(x.fp,x.auth)
    assert len(report['conditions'])==12 and report['primary_contrast']=='A2-graph_vs_A2-hybrid_facts'
    assert report['splits']['development']['questions']==8 and report['splits']['held_out']['questions']==16
    assert report['paired_correctness'][report['primary_contrast']]=={'wins':0,'ties':24,'losses':0}
    assert 'SYNTHETIC SECRET' not in json.dumps(report)


def test_failed_reservation_is_retained_and_study_cannot_resume(tmp_path,monkeypatch):
    x=synthetic_setup(tmp_path,monkeypatch);calls=execute_fixture(x,monkeypatch,fail_at=2)
    with pytest.raises(runner.RunnerFailure):runner.execute(x.fp,x.auth,x.settings)
    with pytest.raises(ValueError,match='already started'):runner.execute(x.fp,x.auth,x.settings)
    assert len(calls)==2
    ledger=x.private/'matched-execution-accounting'/(guards.file_sha(x.fp)+'.jsonl')
    events=[json.loads(line) for line in ledger.read_text().splitlines()]
    assert sum(row['event']=='reservation' for row in events)==2
    assert any(row['event']=='failed_or_unknown' and row['reservation_retained'] for row in events)


def test_console_diagnostics_never_echo_private_exception_content(monkeypatch,capsys):
    monkeypatch.setattr(runner,'execute',lambda *a,**k:(_ for _ in ()).throw(ValueError('SYNTHETIC SECRET GOLD')))
    assert runner.main(['run','--freeze','runs/retrieval-v2/m5-5/freeze.json','--authorization','runs/retrieval-v2/m5-5/auth.json'])==1
    assert 'SYNTHETIC SECRET' not in capsys.readouterr().out


@pytest.mark.parametrize('change',['endpoint','head','sources','catalog','container','writable','unfrozen','projection','binding'])
def test_frozen_scope_checks_actual_ownership_and_read_only_refusal(tmp_path,monkeypatch,change):
    from research_assistant.ingestion.sources import source_identity
    x=synthetic_setup(tmp_path,monkeypatch)
    _,catalog,chunks=fixture_run();catalog.head=x.freeze.scope.review_head
    scope=x.freeze.scope.model_copy(update={'source_chunks_sha256':source_identity(chunks),'catalog_sha256':fingerprint(catalog.facts)})
    settings=x.settings.model_copy(update={'neo4j_uri':scope.target_uri})
    row={'scope':scope.projection_scope_id,'profile':'retrieval-v2','frozen':True,'binding':scope.projection_scope_sha256}
    repo=SimpleNamespace(project='SYNTHETIC',reading=lambda *a:nullcontext(),tx=SimpleNamespace(run=lambda *a,**k:SimpleNamespace(single=lambda:row)))
    physical={'container_id':scope.container_id,'image_id':scope.image_id,'volumes':sorted(scope.volumes)}
    monkeypatch.setattr(scopes,'attest_target',lambda *a:physical)
    monkeypatch.setattr(scopes,'require_read_only',lambda *a:{'write_refused':True})
    request=QueryRequest(question='SYNTHETIC',corpus_id=scope.corpus_id,profile_id='retrieval-v2')
    assert scopes.validate_frozen_scope(scope,request,settings,Path(scope.review_directory),chunks,catalog,repo)==scope
    if change=='endpoint':settings=settings.model_copy(update={'neo4j_uri':'bolt://127.0.0.1:60395'})
    if change=='head':catalog.head='f'*64
    if change=='sources':chunks={}
    if change=='catalog':catalog.facts={}
    if change=='container':physical['container_id']='f'*64
    if change=='writable':monkeypatch.setattr(scopes,'require_read_only',lambda *a:(_ for _ in ()).throw(ValueError('SYNTHETIC writable target')))
    if change=='unfrozen':row['frozen']=False
    if change=='projection':row['scope']='m5dev-'+'f'*12
    if change=='binding':row['binding']='f'*64
    with pytest.raises(ValueError):scopes.validate_frozen_scope(scope,request,settings,Path(scope.review_directory),chunks,catalog,repo)


@pytest.mark.parametrize('change',['image','volume','port','readonly','name','state'])
def test_lifecycle_inspects_exact_retained_container_without_creating_it(tmp_path,monkeypatch,change):
    x=synthetic_setup(tmp_path,monkeypatch);scope=x.freeze.scope
    row={'Id':scope.container_id,'Image':scope.image_id,'Name':'/'+scope.target_project+'-neo4j-1',
        'Config':{'Labels':{'com.docker.compose.project':scope.target_project},
                  'Env':['NEO4J_server_databases_default__to__read__only=true']},
        'Mounts':[{'Name':scope.volumes[0],'Destination':'/data'},{'Name':scope.volumes[1],'Destination':'/logs'}],
        'State':{'Running':False},'HostConfig':{'PortBindings':{'7687/tcp':[{'HostIp':'127.0.0.1','HostPort':'18659'}]}}}
    calls=[]
    monkeypatch.setattr(scopes.subprocess,'run',lambda command,**k:(calls.append(command) or SimpleNamespace(stdout=json.dumps([row]))))
    scopes.inspect_container(scope,running=False)
    assert calls[0]==['docker','inspect',scope.container_id]
    if change=='image':row['Image']='sha256:'+'f'*64
    if change=='volume':row['Mounts'][0]['Name']='SYNTHETIC wrong volume'
    if change=='port':row['HostConfig']['PortBindings']['7687/tcp'][0]['HostPort']='7687'
    if change=='readonly':row['Config']['Env']=[]
    if change=='name':row['Name']='/SYNTHETIC-other'
    if change=='state':row['State']['Running']=True
    with pytest.raises(ValueError):scopes.inspect_container(scope,running=False)
    assert all(command[:2]==['docker','inspect'] for command in calls)


def test_v2_generation_stays_unavailable_to_application_and_unissued_keys(tmp_path,monkeypatch):
    from research_assistant import pipeline
    x=synthetic_setup(tmp_path,monkeypatch)
    request=QueryRequest(question='SYNTHETIC',corpus_id=x.freeze.scope.corpus_id,profile_id='retrieval-v2',scope_file=x.freeze.scope_path)
    monkeypatch.setattr(pipeline,'create_client',lambda *a:pytest.fail('Unissued application generation reached provider factory'))
    with pytest.raises(ValueError,match='retrieval-only'):pipeline.run_query(request,x.settings)
    base,_,_=fixture_run()
    with pytest.raises(ValueError):pipeline._finish_query(request,x.settings,base.corpus_manifest,base.retrieval,{},4096,512,.3,generate=True,workflow='ask')


def test_real_common_generation_path_requires_valid_permit_and_preserves_failures(tmp_path,monkeypatch):
    from research_assistant import pipeline
    x=synthetic_setup(tmp_path,monkeypatch)
    keys=[QuestionKey(**{k:row[k] for k in ('question_id','split','category')}) for rows in x.groups.values() for row in rows]
    slots=build_proposed_schedule(keys,x.freeze.plan)
    slot=next(s for s in slots if s.condition.profile_id=='retrieval-v2' and s.condition.selector_id=='reference')
    grant=_register_study(x.freeze,guards.file_sha(x.fp),guards.authorize(x.auth,x.fp))
    request=QueryRequest(question='SYNTHETIC actual common path',corpus_id=x.freeze.scope.corpus_id,
        mode=slot.condition.mode,profile_id=slot.condition.profile_id,selector_id=slot.condition.selector_id,scope_file=x.freeze.scope_path)
    target=x.settings.model_copy(update={'neo4j_uri':x.freeze.scope.target_uri})
    permit=_issue_slot(grant,slot,request,reservation_persisted=True)
    base,_,_=fixture_run();base.corpus_manifest.update(corpus_id=request.corpus_id)
    base.retrieval.requested_mode=request.mode
    base.retrieval.audit.update(profile={'profile_id':'retrieval-v2'},experiment_scope=x.freeze.scope.model_dump())
    guard_calls=[]
    def retrieval(req,settings,review,minimum,encoder,guard):
        guard(req,settings,review,None,None,None)
        return base.corpus_manifest,base.retrieval
    monkeypatch.setattr(runner,'retrieve_guarded',retrieval)
    monkeypatch.setattr(runner,'validate_frozen_scope',lambda scope,*a:guard_calls.append(scope))
    monkeypatch.setattr(runner,'code_identity',lambda:{'code_revision':'SYNTHETIC','code_dirty':False,'source_tree_sha256':'a'*64})
    monkeypatch.setattr(pipeline,'check_resources',lambda:{})
    calls=[]
    class Client:
        last_result=None
        def generate_structured(self,schema,messages):
            calls.append(messages)
            assert 'SECRET' not in json.dumps(messages)
            self.last_result=LLMResult(text='SYNTHETIC raw',provider='ollama',model='synthetic',digest='d'*64,
                elapsed_ms=1,usage={},settings={},messages=messages)
            return DraftAnswer(answer='SYNTHETIC supported',citations=['E1'],insufficient_evidence=False),self.last_result
    client=Client();monkeypatch.setattr(pipeline,'create_client',lambda *a:client)
    run=runner.run_matched_query(request,target,x.freeze,permit,object())
    assert len(calls)==1 and len(guard_calls)==1 and run.generation.text=='SYNTHETIC raw'
    assert run.workflow=='ask' and run.configuration['experiment_scope']['frozen'] is True
    with pytest.raises(ValueError):runner.run_matched_query(request,target,x.freeze,permit,object())


def test_complete_public_file_coverage_and_copied_runtime_proof(tmp_path,monkeypatch):
    from research_assistant.retrieval import profiles,reranker
    x=synthetic_setup(tmp_path,monkeypatch)
    paths=set()
    for name in ['uv.lock','pyproject.toml','compose.yaml','.env.example']:
        p=Path(name);p.write_text('SYNTHETIC runtime '+name);paths.add(p)
    x.freeze.files={p.as_posix():guards.file_sha(p) for p in paths}
    write(x.fp,x.freeze.model_dump(mode='json'))
    manifest={'graph_sha256':x.freeze.scope.graph_sha256,'review_head':x.freeze.scope.review_head,
        'freeze_projection':{'corpus_id':x.freeze.scope.corpus_id},'matched_runtime_assets':True,
        'source_tree_sha256':x.freeze.source_tree_sha256,'assets':dict(x.freeze.files)}
    monkeypatch.setattr(guards,'runtime_versions',lambda:{})
    monkeypatch.setattr(guards,'runtime_assets',lambda:paths)
    monkeypatch.setattr(guards,'code_identity',lambda:{'source_tree_sha256':'a'*64})
    monkeypatch.setattr(guards,'verify_snapshot',lambda *a:(manifest,{}))
    monkeypatch.setattr(profiles,'retrieval_profile',lambda *a:SimpleNamespace(policy_sha256='a'*64))
    monkeypatch.setattr(reranker,'verified_manifest',lambda:object())
    monkeypatch.setattr(reranker,'model_identity',lambda *a:{'SYNTHETIC':True})
    assert guards.load_freeze(x.fp).scope==x.freeze.scope
    proof=json.loads(x.proof.read_text())
    proof['capacity_checks']['complete']=False
    write(x.proof,proof)
    x.freeze.recovery_report_sha256=guards.file_sha(x.proof)
    write(x.fp,x.freeze.model_dump(mode='json'))
    with pytest.raises(ValueError,match='read-only recovery proof'):guards.load_freeze(x.fp)
    proof['capacity_checks']['complete']=True
    write(x.proof,proof)
    x.freeze.recovery_report_sha256=guards.file_sha(x.proof)
    write(x.fp,x.freeze.model_dump(mode='json'))
    manifest['assets']['uv.lock']='f'*64
    with pytest.raises(ValueError,match='Copied runtime'):guards.load_freeze(x.fp)
    manifest['assets']['uv.lock']=x.freeze.files['uv.lock']
    Path('uv.lock').write_text('SYNTHETIC changed')
    with pytest.raises(ValueError,match='asset changed'):guards.load_freeze(x.fp)


@pytest.mark.parametrize('profile',['baseline','retrieval-v2'])
def test_shared_retrieval_keeps_projection_lineage_and_checks_both_boundaries(tmp_path,monkeypatch,profile):
    from research_assistant.retrieval import service
    x=synthetic_setup(tmp_path,monkeypatch)
    base,catalog,chunks=fixture_run()
    repo=SimpleNamespace(snapshot=lambda corpus:{'encoder_revision':'SYNTHETIC-encoder'},close=lambda:None)
    monkeypatch.setattr(service,'load_corpus_chunks',lambda corpus:chunks)
    monkeypatch.setattr(service,'review_lock',lambda directory:nullcontext())
    monkeypatch.setattr(service,'load_catalog',lambda *a:catalog)
    monkeypatch.setattr(service,'SearchRepository',lambda settings:repo)
    monkeypatch.setattr(service,'validate_scope',lambda *a:pytest.fail('Frozen request used development-only guard'))
    policies=[]
    def retrieve(*args,**kwargs):
        policies.append(kwargs)
        return base.retrieval.model_copy(deep=True)
    monkeypatch.setattr(service,'retrieve_modes',retrieve)
    calls=[]
    def guard(*args):
        calls.append(args)
        return x.freeze.scope
    request=QueryRequest(question='SYNTHETIC',corpus_id=x.freeze.scope.corpus_id,mode='graph',profile_id=profile)
    _,result=service.retrieve_guarded(request,x.settings,Path('data/reviews/expansion-v1'),.3,
        SimpleNamespace(revision='SYNTHETIC-encoder'),guard)
    assert len(calls)==2
    assert policies[0]['profile_id']==profile
    assert policies[0]['scope_id']==x.freeze.scope.projection_scope_id
    assert result.audit['experiment_scope']['scope_id']==x.freeze.scope.scope_id


@pytest.mark.parametrize('nested',['blind/public/answers.json','blind/public/SYNTHETIC-completed.csv'])
def test_scoring_rejects_nested_windows_reparse_points_before_shared_helpers(tmp_path,monkeypatch,nested):
    x=synthetic_setup(tmp_path,monkeypatch)
    execute_fixture(x,monkeypatch)
    result=runner.execute(x.fp,x.auth,x.settings)
    packet=Path(result['scoring_packet_directory'])
    directory=packet.parent.parent
    blocked=directory/nested
    original=Path.lstat
    def lstat(path):
        if path==blocked:
            return SimpleNamespace(st_mode=0,st_file_attributes=0x400)
        return original(path)
    monkeypatch.setattr(Path,'lstat',lstat)
    monkeypatch.setattr(runner,'_seal_scores',lambda *a:pytest.fail('Unsafe nested packet reached score reader'))
    with pytest.raises(runner.RunnerFailure) as failure:
        runner.grade(x.fp,x.auth,scores_path=packet/'SYNTHETIC-completed.csv')
    assert 'symlinks/junctions' in Path(failure.value.private_report).read_text()


@pytest.mark.parametrize('change',['missing_slot','duplicate_slot','late_failure','wrong_completion'])
def test_scoring_requires_complete_successful_durable_execution(tmp_path,monkeypatch,change):
    x=synthetic_setup(tmp_path,monkeypatch)
    execute_fixture(x,monkeypatch)
    result=runner.execute(x.fp,x.auth,x.settings)
    digest=guards.file_sha(x.fp)
    ledger=x.private/'matched-execution-accounting'/(digest+'.jsonl')
    events=[json.loads(line) for line in ledger.read_text().splitlines()]
    if change=='missing_slot':events=[e for e in events if not(e['event']=='completed' and e['slot']==288)]
    if change=='duplicate_slot':events.insert(-1,next(e for e in events if e['event']=='completed'))
    if change=='late_failure':events.append({'event':'failed','type':'SYNTHETIC retained failure'})
    if change=='wrong_completion':
        directory=Path(result['scoring_packet_directory']).parent.parent
        write(directory/'execution-complete.json',{'SYNTHETIC':'incomplete'})
    # Deliberately corrupt only pytest-owned synthetic execution records.
    ledger.write_text(''.join(json.dumps(event)+'\n' for event in events))
    with pytest.raises(ValueError):runner._execution(x.private,digest,'1'*32)


@pytest.mark.parametrize('matched_assets',[False,True])
def test_new_snapshot_export_copies_pinned_runtime_only_when_requested(tmp_path,monkeypatch,matched_assets):
    from research_assistant.graph import recovery,search
    from research_assistant.ingestion import sources
    from research_assistant.retrieval import catalog,reranker
    from research_assistant import smoke
    from test_recovery import graph
    monkeypatch.chdir(tmp_path)
    corpus='a'*64
    source_graph=graph()
    source_graph['nodes'].append({'key':'Corpus:'+corpus,'labels':['Corpus'],
        'properties':{'id':corpus,'project':recovery.PROJECT,'ready':True,'frozen':False}})
    before=fingerprint(source_graph)
    Path('data/processed',corpus).mkdir(parents=True)
    review=Path('data/reviews/expansion-v1')
    write(review/'config.json',{'corpus_id':corpus})
    for name in ['pyproject.toml','uv.lock','compose.yaml','.env.example','.streamlit/config.toml',
                 'README.md','project_spec.md','project_spec_submission.md','IMPLEMENTATION_PLAN.md','AGENTS.md']:
        path=Path(name);path.parent.mkdir(parents=True,exist_ok=True);path.write_text('SYNTHETIC '+name)
    for name in ['.cache/models/SYNTHETIC/weights.bin','.cache/rerankers/SYNTHETIC/model.bin','.cache/tiktoken/SYNTHETIC']:
        path=Path(name);path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(b'SYNTHETIC cached runtime')
    Path('.env').write_text('SYNTHETIC SECRET: must not be copied')
    fake=SimpleNamespace(corpus_id=corpus,head='b'*64,facts={})
    repo=SimpleNamespace(snapshot=lambda *a:{'encoder_revision':'SYNTHETIC'},
        reading=lambda *a:nullcontext(),fact_vectors=lambda *a:{},close=lambda:None)
    monkeypatch.setattr(recovery,'review_lock',lambda *a:nullcontext())
    monkeypatch.setattr(recovery,'capture',lambda *a:source_graph)
    monkeypatch.setattr(recovery,'code_identity',lambda:{'source_tree_sha256':'c'*64,'code_revision':'SYNTHETIC','code_dirty':False})
    monkeypatch.setattr(search,'SearchRepository',lambda *a:repo)
    monkeypatch.setattr(sources,'load_corpus_chunks',lambda *a:{})
    monkeypatch.setattr(catalog,'load_catalog',lambda *a:fake)
    monkeypatch.setattr(reranker,'verified_manifest',lambda:{'SYNTHETIC':True})
    monkeypatch.setattr(smoke,'encoder_artifact',lambda *a:('SYNTHETIC','SYNTHETIC',384))
    output=Path('runs/retrieval-v2/m5-5/SYNTHETIC-snapshot')
    recovery.export_snapshot(Settings(),output,review,freeze_corpus=True,matched_runtime_assets=matched_assets)
    manifest,copied=recovery.verify_snapshot(output)
    assert bool(manifest.get('matched_runtime_assets')) is matched_assets
    assert (output/'files/.cache/rerankers/SYNTHETIC/model.bin').exists() is matched_assets
    assert '.env' not in manifest['assets']
    assert copied['nodes'][-1]['properties']['frozen'] is True
    assert fingerprint(source_graph)==before
    with pytest.raises(ValueError,match='never overwrite'):
        recovery.export_snapshot(Settings(),output,review,matched_runtime_assets=matched_assets)
