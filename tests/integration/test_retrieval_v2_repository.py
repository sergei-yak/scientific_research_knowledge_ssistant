"""Native V2 proof on UUID-owned synthetic records in the isolated development server."""
import json
import os
import uuid
from datetime import datetime,timezone,timedelta
from pathlib import Path

import pytest

from research_assistant.contracts import Chunk,PaperManifestEntry,QueryRequest,SourceSpanRef,fingerprint,text_sha
from research_assistant.extraction.contracts import ProposedClaim
from research_assistant.graph.repository import PROJECT,corpus_names
from research_assistant.graph.reviews import fact_names
from research_assistant.graph.search import SearchRepository,search_names,plan_metrics
from research_assistant.graph.templates_v2 import traversal_templates_v2
from research_assistant.pipeline import write_immutable
from research_assistant.retrieval.catalog import ReviewCatalog
from research_assistant.retrieval.service import retrieve_modes
from research_assistant.review.contracts import EntityDefinition,HumanDecision,ReviewRevision,mapping_identity
from research_assistant.review.facts import projection
from research_assistant.review.store import append_event,import_decisions,review_lock
from research_assistant.settings import Settings

NEAR=[1.0]+[0.0]*383
FAR=[0.0,1.0]+[0.0]*382


class FixtureEncoder:
    """Controlled vectors test native membership; no model-quality claim."""
    def encode(self,texts):return [NEAR for _ in texts]


@pytest.mark.integration
@pytest.mark.skipif(os.getenv('RUN_V2_SMOKE')!='1',reason='Set RUN_V2_SMOKE=1 on the isolated development target')
def test_finding_entity_routes_roles_caps_plans_and_revocation(tmp_path):
    token=uuid.uuid4().hex
    project=PROJECT+'-v2-fixture-'+token
    corpus=fingerprint(['v2-fixture',token])
    label,vector=corpus_names(corpus)
    _,fv,ft=fact_names(corpus)
    ct,*_=search_names(corpus)
    repo=SearchRepository(Settings.from_env(),project=project)
    root=tmp_path/'review';root.mkdir()
    (root/'config.json').write_text(json.dumps({'corpus_id':corpus}),encoding='utf-8')
    method=EntityDefinition(id='method-'+token,kind='method',name='FixtureMethod',aliases=['lookupmethod'])
    dataset=EntityDefinition(id='dataset-'+token,kind='dataset',name='SharedSet',aliases=['lookupdataset'])
    focus=EntityDefinition(id='focus-'+token,kind='dataset',name='SpecialFocus',aliases=['TargetHint'])
    pa,pb='paper-a-'+token,'paper-b-'+token
    chunks,revisions={},[]
    try:
        with repo.driver.session(database=repo.database) as session:
            session.run('CREATE (c:Corpus {id:$id,project:$project,ready:true,frozen:false,experiment_scope_id:"synthetic",retrieval_profile_id:"retrieval-v2"})',id=corpus,project=project).consume()
            for number in range(22):
                remote=number>=14;paper_id=pb if remote else pa
                definitions=([method,dataset] if number==0 else [method,focus] if number==14 else [dataset] if number in (15,16)
                             else [method] if number>=17 else [])
                roles={dataset.id:'ABOUT_DATASET'} if number in (0,15) else None
                text=('anchor FixtureMethod SharedSet source evidence.' if number==0 else
                      'FixtureMethod SpecialFocus remote supported result.' if number==14 else
                      'SharedSet remote dataset evidence.' if number in (15,16) else
                      f'FixtureMethod remote supported result {number}.' if remote else f'anchor FixtureMethod source detail {number}.')
                key='chunk-'+token+'-'+str(number)
                chunk=Chunk(chunk_id=key,paper_id=paper_id,source_sha256='a'*64,source_url='https://example.invalid/synthetic',
                    page=number+1,section='Synthetic',page_start=0,page_end=len(text),text=text,text_sha256=text_sha(text),
                    parser_version='fixture',chunker_version='fixture',mini_tokens=20,mpnet_tokens=20)
                chunks[key]=chunk
                paper=PaperManifestEntry(paper_id=paper_id,title='SYNTHETIC ONLY',source_url=chunk.source_url,source_sha256=chunk.source_sha256,
                    local_path='unused.pdf',rights='Synthetic',rights_url=chunk.source_url,document_type='primary_study',selected_pages=[number+1],selection_reason='Test only')
                draft=ProposedClaim(kind='finding',statement=text,method=method.name if method in definitions else None,
                    method_aliases=method.aliases if method in definitions else [],
                    dataset=next((d.name for d in definitions if d.kind=='dataset'),None),
                    dataset_aliases=next((d.aliases for d in definitions if d.kind=='dataset'),[]),conditions={},quotes=[text])
                revision=ReviewRevision(claim_id='claim-'+token+'-'+str(number),revision=1,paper=paper,draft=draft,
                    support=[SourceSpanRef(paper_id=paper_id,source_sha256=chunk.source_sha256,chunk_id=key,start=0,end=len(text),quote_sha256=text_sha(text))],
                    validation_errors=[],entities=definitions,entity_revision=mapping_identity(definitions,roles),relation_roles=roles,change_reason='Synthetic fixture; no real approval')
                revisions.append(revision)
                with review_lock(root):append_event(root,'revision',revision.model_dump(mode='json'))
                session.run(f'MATCH (c:Corpus {{id:$corpus,project:$project}}) MERGE (p:Paper {{id:$paper}}) '
                    'SET p.project=$project,p.source_sha256=$sha '
                    f'CREATE (n:Chunk:`{label}` {{id:$id,project:$project,text:$text,source_json:$source,embedding_384:$embedding,encoder_revision:"fixture"}}) '
                    'MERGE (c)-[:HAS_PAPER]->(p) MERGE (p)-[:HAS_CHUNK]->(n)',corpus=corpus,project=project,paper=paper_id,sha=chunk.source_sha256,
                    id=key,text=text,source=chunk.model_dump_json(),embedding=FAR if remote else NEAR).consume()
            session.run(f'CREATE VECTOR INDEX `{vector}` FOR (n:`{label}`) ON n.embedding_384 OPTIONS {{indexConfig:{{`vector.dimensions`:384,`vector.similarity_function`:"cosine"}}}}').consume()
            session.run('CALL db.awaitIndex($name,120)',name=vector).consume()
        decisions=[HumanDecision(claim_id=r.claim_id,claim_revision=1,revision_sha256=r.sha256,source_sha256=r.paper.source_sha256,
            entity_revision=r.entity_revision,reviewer='SYNTHETIC FIXTURE',reviewed_at=datetime(2026,11,15,tzinfo=timezone.utc),
            review_time_note='Synthetic; not measured',reason='Synthetic test only',decision='approved',origin='human_csv',provenance_sha256='b'*64) for r in revisions]
        import_decisions(root,decisions,chunks)
        review=projection(root,chunks)
        def publish():
            repo.publish(corpus,review,[FAR if f['paper_id']==pb else NEAR for f in review['facts']],'fixture')
        publish();repo.prepare_indexes(corpus)
        catalog=ReviewCatalog.from_review(corpus,review)
        def retrieve(mode='graph',question='anchor TargetHint'):
            return retrieve_modes(QueryRequest(question=question,corpus_id=corpus,mode=mode),repo,FixtureEncoder(),chunks,catalog,'fixture',
                                  profile_id='retrieval-v2',scope_id='synthetic')
        target=next(f['id'] for f in review['facts'] if f['claim_id']==revisions[14].claim_id)
        baseline=retrieve('hybrid_facts');graph=retrieve()
        assert target not in {r['id'] for r in baseline.audit['fusion']}
        assert graph.audit['channel_rankings']==baseline.audit['channel_rankings']
        assert target in graph.audit['selected_graph_additions'] and graph.effective_mode=='graph'
        assert any(row['fact_id']==target for call in graph.audit['graph_calls'] if call['parameters']['anchor_type']=='evidence'
                   and call['template']=='shared_method' for row in call['rows'])
        assert all(r.draft.kind=='finding' for r in revisions)  # No Evaluation prerequisite exists in this corpus.
        direct=retrieve(question='anchor lookupmethod')
        assert any(row['fact_id']==target for call in direct.audit['graph_calls'] if call['parameters']['anchor_type']=='entity' for row in call['rows'])
        with repo.driver.session(database=repo.database) as session:
            session.run('MATCH (p:Paper {id:$a}),(q:Paper {id:$b}) CREATE (p)-[:CITES {corpus_id:$corpus}]->(q)',
                        a=pa,b=pb,corpus=corpus).consume()
        params={'project':project,'corpus':corpus,'head':catalog.head,'scope_id':'synthetic','anchor_type':'evidence','seed_paper':pa,
                'seed_chunks':[revisions[0].support[0].chunk_id],'anchor_entity_id':dataset.id,'anchor_entity_node':fingerprint(dataset.model_dump()),
                'entity_ids':[method.id,dataset.id],'fact_ids':sorted(catalog.facts)}
        plans={}
        for family in traversal_templates_v2(corpus):
            with repo.reading(corpus,catalog.head,30):
                _,explain=repo.traverse(corpus,family,params,'EXPLAIN',profile_id='retrieval-v2')
            with repo.reading(corpus,catalog.head,30):
                rows,profile=repo.traverse(corpus,family,params,'PROFILE',profile_id='retrieval-v2')
            metrics=plan_metrics(profile)
            assert len(rows)<=5 and metrics['total_db_hits']<10000
            assert rows  # Each of the four route families is exercised with supported results.
            assert any('IndexSeek' in str(n['operator']) for n in metrics['operators'])
            assert not any('AllNodesScan' in str(n['operator']) for n in metrics['operators'])
            plans[family]={'explain':plan_metrics(explain),'profile':metrics,'returned_rows':len(rows)}
        mention=next(f['id'] for f in review['facts'] if f['claim_id']==revisions[16].claim_id)
        about=next(f['id'] for f in review['facts'] if f['claim_id']==revisions[15].claim_id)
        with repo.reading(corpus,catalog.head,30):
            rows,_=repo.traverse(corpus,'shared_dataset',params,profile_id='retrieval-v2')
        assert about in {r['fact_id'] for r in rows} and mention not in {r['fact_id'] for r in rows}
        entity_plans={}
        for kind,entity in [('method',method),('dataset',dataset)]:
            ep={**params,'anchor_type':'entity','anchor_entity_id':entity.id,'anchor_entity_node':fingerprint(entity.model_dump())}
            with repo.reading(corpus,catalog.head,30):
                rows,plan=repo.traverse(corpus,'shared_'+kind,ep,'PROFILE',profile_id='retrieval-v2')
            assert len(rows)<=5
            metrics=plan_metrics(plan)
            assert any('IndexSeek' in str(n['operator']) and ('e:'+kind.title()+'(id)') in str(n['arguments']) for n in metrics['operators'])
            entity_plans[kind]={'profile':metrics,'returned_rows':len(rows)}
        # An agent cannot turn an existing MENTIONS edge into authority by editing the graph.
        claim_node=fingerprint([corpus,revisions[16].claim_id,1]);dataset_node=fingerprint(dataset.model_dump())
        with repo.driver.session(database=repo.database) as session:
            session.run('MATCH (n:ReviewedClaim {id:$id}),(d:Dataset {id:$dataset}) CREATE (n)-[:ABOUT_DATASET]->(d)',id=claim_node,dataset=dataset_node).consume()
        with pytest.raises(ValueError,match='relationship role'):retrieve()
        with repo.driver.session(database=repo.database) as session:
            session.run('MATCH (n:ReviewedClaim {id:$id})-[r:ABOUT_DATASET]->() DELETE r',id=claim_node).consume()
        wrong=fingerprint([corpus,revisions[14].claim_id,1])
        with repo.driver.session(database=repo.database) as session:
            session.run('MATCH (n:ReviewedClaim {id:$id}) SET n.reporting_paper_id="wrong-owner"',id=wrong).consume()
        with pytest.raises(ValueError,match='revision/source/owner'):retrieve()
        with repo.driver.session(database=repo.database) as session:
            session.run('MATCH (n:ReviewedClaim {id:$id}) SET n.reporting_paper_id=$paper',id=wrong,paper=pb).consume()
        import_decisions(root,[decisions[14].model_copy(update={'decision':'needs_review','reviewed_at':decisions[14].reviewed_at+timedelta(seconds=1)})],chunks)
        review=projection(root,chunks);catalog=ReviewCatalog.from_review(corpus,review)
        with pytest.raises(ValueError,match='stale'):retrieve()
        publish();revoked=retrieve()
        assert target not in {r['fact_id'] for call in revoked.audit['graph_calls'] for r in call['rows']}
        assert graph.audit['graph_rows']<=80 and len(graph.audit['graph_candidates_retained'])<=40
        assert graph.estimated_tokens<=1800 and len(graph.evidence)<=6
        if os.getenv('M5_FIXTURE_REPORT'):
            write_immutable(Path(os.environ['M5_FIXTURE_REPORT']),json.dumps({'task_id':'M5.2','synthetic_only':True,
                'finding_start_outside_baseline':True,'direct_entity_start_outside_baseline':True,'no_evaluations_required':True,
                'mentions_not_promoted':True,'unapproved_role_rejected':True,'wrong_owner_rejected':True,'stale_and_revoked_rejected':True,
                'graph_rows':graph.audit['graph_rows'],'selected_additions':graph.audit['selected_graph_additions'],
                'plans':plans,'entity_plans':entity_plans,'graph':graph.model_dump()},indent=2)+'\n')
    finally:
        assert project==PROJECT+'-v2-fixture-'+token and len(token)==32
        with repo.driver.session(database=repo.database) as session:
            count=session.run('MATCH (n {project:$project}) RETURN count(n) AS count',project=project).single()['count']
            assert count<200
            for index in (vector,ct,fv,ft):session.run(f'DROP INDEX `{index}` IF EXISTS').consume()
            session.run('MATCH (n {project:$project}) DETACH DELETE n',project=project).consume()
        repo.close()
