"""Create a fresh M5 development target from a verified baseline; never reset a target."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import time
import uuid

from research_assistant.contracts import fingerprint
from research_assistant.evaluation.freeze import file_sha, load_freeze
from research_assistant.graph.recovery import capture, restore_snapshot, verify_snapshot
from research_assistant.graph.repository import GraphRepository, PROJECT
from research_assistant.ingestion.sources import load_corpus_chunks, source_identity
from research_assistant.pipeline import write_immutable
from research_assistant.retrieval.catalog import load_catalog
from research_assistant.review.store import review_lock
from research_assistant.settings import Settings


def main():
    """Copy bounded public assets and attest a UUID-owned, local-only disposable database."""
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline',type=Path,required=True)
    parser.add_argument('--worktree',type=Path,required=True)
    args=parser.parse_args()
    base,work=args.baseline.resolve(),args.worktree.resolve()
    if Path.cwd().resolve()!=base or base==work or not (work/'.git').is_file():
        raise ValueError('Run with the baseline interpreter, explicitly naming a separate Git worktree')
    freeze=load_freeze(Path('runs/m4-2/freeze-v2.json'))
    snapshot=base/'runs/m4-2/snapshot-v2'
    manifest,_=verify_snapshot(snapshot)
    settings=Settings.from_env()
    before=fingerprint(capture(settings))
    if before!=manifest['source_graph_sha256']:
        raise ValueError('Baseline source graph differs from verified snapshot')
    ident=uuid.uuid4().hex[:12]
    # Retain the existing restore attestation namespace; purpose is explicitly M5 development.
    project='dbu-m4-recovery-m5dev-'+ident
    ports=[]
    for _ in range(2):
        with socket.socket() as probe:
            probe.bind(('127.0.0.1',0));ports.append(probe.getsockname()[1])
    if len(set(ports))!=2:
        raise ValueError('Fresh ports must be distinct')
    for volume in (project+'_neo4j_data',project+'_neo4j_logs'):
        if subprocess.run(['docker','volume','inspect',volume],capture_output=True).returncode==0:
            raise ValueError('UUID volume already exists; refusing reuse')
    output=work/'runs/retrieval-v2/m5-2'/ident
    output.mkdir(parents=True,exist_ok=False)
    copied={}
    for relative,digest in manifest['assets'].items():
        if not relative.startswith('data/'):
            continue
        source=snapshot/'files'/relative
        dest=work/relative
        if dest.exists():raise ValueError('Refusing asset overwrite')
        dest.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(source,dest)
        if file_sha(dest)!=digest:raise ValueError('Copied asset hash mismatch')
        copied[relative]=digest
    # Reconcile all newer accounting bytes without resetting a ledger or copying credentials.
    for source in (base/'data/accounting').glob('*'):
        if source.is_file():
            dest=work/'data/accounting'/source.name
            shutil.copyfile(source,dest)
            copied[str(dest.relative_to(work))]=file_sha(source)
    for root in ('.cache/models','.cache/tiktoken'):
        for source in (base/root).rglob('*'):
            if source.is_file():
                dest=work/source.relative_to(base)
                dest.parent.mkdir(parents=True,exist_ok=True)
                shutil.copyfile(source,dest)
                if file_sha(dest)!=file_sha(source):raise ValueError('Model/cache copy differs')
                copied[str(dest.relative_to(work))]=file_sha(dest)
    # Never copy OpenAI credentials or exhausted authorization flags into the new checkout.
    password=settings.neo4j_password.get_secret_value()
    env_text='\n'.join(['NEO4J_USER='+settings.neo4j_user,'NEO4J_PASSWORD='+password,
        'COMPOSE_PROJECT_NAME='+project,'NEO4J_IMAGE=sha256:42ef3ebfd671ebd01fdebb6dcbe80cf7b45eef2aa3d346ef4132f7ef31e67d2f',
        'NEO4J_READ_ONLY=false',
        f'NEO4J_URI=bolt://127.0.0.1:{ports[0]}',f'NEO4J_BOLT_PORT={ports[0]}',f'NEO4J_HTTP_PORT={ports[1]}',
        'GENERATION_PROVIDER=ollama','GENERATION_MODEL='+settings.generation_model,
        'API_BUDGET_APPROVED=false','API_BUDGET_USD=0','MAX_RETRIES=0','MAX_CONCURRENCY=1'])+'\n'
    write_immutable(work/'.env',env_text)
    image='sha256:42ef3ebfd671ebd01fdebb6dcbe80cf7b45eef2aa3d346ef4132f7ef31e67d2f'
    env={**os.environ,'NEO4J_IMAGE':image,'NEO4J_READ_ONLY':'false','NEO4J_BOLT_PORT':str(ports[0]),'NEO4J_HTTP_PORT':str(ports[1])}
    command=['docker','compose','--env-file',str(work/'.env'),'-p',project,'-f',str(work/'compose.yaml')]
    declaration={'task_id':'M5.2','purpose':'isolated writable development; not final evaluation',
        'baseline':str(base),'worktree':str(work),'project':project,'bolt_port':ports[0],'http_port':ports[1],
        'image_id':image,'snapshot_sha256':file_sha(snapshot/'manifest.json'),'baseline_graph_sha256':before,
        'copied_public_asset_sha256':copied,'new_model_downloads':0,'paid_calls':0,'private_access':False}
    write_immutable(output/'declaration.json',json.dumps(declaration,indent=2)+'\n')
    up=subprocess.run(command+['up','-d','--pull','never','neo4j'],env=env,capture_output=True,text=True,timeout=120)
    write_immutable(output/'startup.log',up.stdout+up.stderr)
    up.check_returncode()
    target=settings.model_copy(update={'neo4j_uri':f'bolt://127.0.0.1:{ports[0]}'})
    ready=False
    for _ in range(30):
        repo=GraphRepository(target)
        try:
            repo.driver.verify_connectivity();ready=True;break
        except Exception:time.sleep(1)
        finally:repo.close()
    if not ready:raise ValueError('Fresh target not ready; preserve for investigation')
    restored=restore_snapshot(snapshot,target,project)
    if restored['image_id']!=image:raise ValueError('Unexpected Docker image')
    os.chdir(work)
    corpus=freeze.corpus_id
    chunks=load_corpus_chunks(corpus)
    review=Path('data/reviews/expansion-v1')
    with review_lock(review):
        catalog=load_catalog(review,corpus,chunks)
        if catalog.head!=freeze.review_head or len(catalog.facts)!=51:raise ValueError('Copied approval scope mismatch')
    scope={'profile_id':'retrieval-v2','scope_id':'m5dev-'+ident,'corpus_id':corpus,
        'source_chunks_sha256':source_identity(chunks),'review_head':catalog.head,
        'review_directory':str(review.resolve()),'target_id':project,'snapshot_sha256':file_sha(snapshot/'manifest.json'),
        'target_uri':target.neo4j_uri,'container_id':restored['container_id'],'image_id':image,
        'volumes':restored['volumes'],'baseline_root':str(base),'baseline_graph_sha256':before}
    # Only this new, attested, exact restored copy becomes writable; claims/history stay unchanged.
    repo=GraphRepository(target)
    try:
        with repo.driver.session(database=repo.database) as session:
            row=session.run('MATCH (c:Corpus {id:$corpus,project:$project,frozen:true}) '
                'SET c.frozen=false,c.experiment_scope_id=$scope,c.retrieval_profile_id="retrieval-v2",c.experiment_scope_sha256=$binding '
                'RETURN c.id AS id',corpus=corpus,project=PROJECT,scope=scope['scope_id'],binding=fingerprint(scope)).single()
            if row is None:raise ValueError('Expected freshly restored frozen corpus was not found')
    finally:repo.close()
    write_immutable(Path('data/scopes/retrieval-v2.json'),json.dumps(scope,indent=2)+'\n')
    after=fingerprint(capture(settings))
    if after!=before:raise ValueError('Baseline changed during isolated setup')
    result={**declaration,'restore':restored,'scope':scope,'baseline_preserved':True,
            'target_graph_sha256_after_scope':fingerprint(capture(target)),'scope_file_sha256':file_sha(Path('data/scopes/retrieval-v2.json'))}
    write_immutable(output/'setup-complete.json',json.dumps(result,indent=2)+'\n')
    print(json.dumps({'output':str(output),'project':project,'scope':str(work/'data/scopes/retrieval-v2.json'),
                      'bolt_port':ports[0],'http_port':ports[1],'baseline_preserved':True}))


if __name__=='__main__':main()
