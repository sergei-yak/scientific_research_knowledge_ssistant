"""UUID-owned native traversal proof, isolated from production human approvals."""

import json
import os
from datetime import datetime, timezone, timedelta
from pathlib import Path
import time
import uuid

import pytest
from neo4j.exceptions import Neo4jError

from research_assistant.contracts import Chunk, PaperManifestEntry, QueryRequest, SourceSpanRef, fingerprint, text_sha
from research_assistant.extraction.contracts import ProposedClaim
from research_assistant.graph.repository import PROJECT, corpus_names
from research_assistant.graph.search import SearchRepository, search_names, plan_metrics
from research_assistant.graph.reviews import fact_names
from research_assistant.graph.templates import traversal_templates
from research_assistant.pipeline import write_immutable,code_identity
from research_assistant.retrieval.catalog import ReviewCatalog
from research_assistant.retrieval.service import retrieve_modes
from research_assistant.review.contracts import EntityDefinition, HumanDecision, ReviewRevision
from research_assistant.review.facts import projection
from research_assistant.review.store import append_event, import_decisions, review_lock
from research_assistant.settings import Settings

NEAR=[1.0]+[0.0]*383
FAR=[0.0,1.0]+[0.0]*382


class FixtureEncoder:
    """Intentional unit vectors control native ANN membership; no neural/LLM performance claim."""

    def encode(self,texts):
        return [NEAR for _ in texts]


@pytest.mark.integration
@pytest.mark.skipif(os.getenv('RUN_RETRIEVAL_SMOKE')!='1',reason='Set RUN_RETRIEVAL_SMOKE=1 for isolated native traversal proof')
def test_native_pool_expansion_plans_guards_and_timeout(tmp_path):
    token=uuid.uuid4().hex
    project=PROJECT+'-retrieval-fixture-'+token
    corpus=fingerprint(['retrieval-fixture',token])
    source_label,vector_index=corpus_names(corpus)
    active_label,fact_vector,fact_text=fact_names(corpus)
    chunk_text,*_=search_names(corpus)
    repo=SearchRepository(Settings.from_env(),project=project)
    root=tmp_path/'review'
    root.mkdir()
    (root/'config.json').write_text(json.dumps({'corpus_id':corpus}),encoding='utf-8')
    method=EntityDefinition(id='method-'+token,kind='method',name='FixtureMethod',aliases=['lookupmethod'])
    dataset=EntityDefinition(id='dataset-'+token,kind='dataset',name='SharedSet',aliases=['lookupdataset'])
    paper_a,paper_b='paper-a-'+token,'paper-b-'+token
    chunks,revisions={},[]
    result_report={}
    try:
        with repo.driver.session(database=repo.database) as session:
            snapshot={'corpus_id':corpus,'encoder_revision':'fixture-encoder'}
            session.run('CREATE (c:Corpus {id:$id,project:$project,ready:true,frozen:false,snapshot_json:$snapshot})',
                        id=corpus,project=project,snapshot=json.dumps(snapshot)).consume()
            for number in range(17):
                # Fourteen near source facts dominate both native top-12 lists. Remote targets do not contain "anchor".
                remote=number>=14
                paper_id=paper_b if remote else paper_a
                text=(f'Remote supported result {number}.' if remote else f'anchor SharedSet source detail {number}.')
                key=f'chunk-{token}-{number}'
                source=Chunk(chunk_id=key,paper_id=paper_id,source_sha256='a'*64,
                    source_url='https://example.invalid/synthetic',page=number+1,section='Synthetic',
                    page_start=0,page_end=len(text),text=text,text_sha256=text_sha(text),
                    parser_version='fixture',chunker_version='fixture',mini_tokens=20,mpnet_tokens=20)
                chunks[key]=source
                paper=PaperManifestEntry(paper_id=paper_id,title='SYNTHETIC FIXTURE ONLY',source_url=source.source_url,
                    source_sha256=source.source_sha256,local_path='unused.pdf',rights='Synthetic',rights_url=source.source_url,
                    document_type='primary_study',selected_pages=[number+1],selection_reason='Synthetic test')
                evaluation=number in (0,14)
                definitions=[method,dataset] if evaluation else [method] if number==15 else []
                draft=ProposedClaim(kind='evaluation' if evaluation else 'finding',statement=text,
                    method=method.name if definitions else None,method_aliases=method.aliases if definitions else [],
                    dataset=dataset.name if evaluation else None,dataset_aliases=dataset.aliases if evaluation else [],
                    conditions={'protocol':'remote' if remote else 'source'},quotes=[text])
                revision=ReviewRevision(claim_id=f'claim-{token}-{number}',revision=1,paper=paper,draft=draft,
                    support=[SourceSpanRef(paper_id=paper_id,source_sha256=source.source_sha256,chunk_id=key,
                        start=0,end=len(text),quote_sha256=text_sha(text))],validation_errors=[],
                    entity_revision=fingerprint([e.model_dump() for e in definitions]),entities=definitions,
                    change_reason='Synthetic fixture only; no real human decision')
                revisions.append(revision)
                with review_lock(root):
                    append_event(root,'revision',revision.model_dump(mode='json'))
                session.run(f'MATCH (c:Corpus {{id:$corpus,project:$project}}) '
                    'MERGE (p:Paper {id:$paper}) SET p.project=$project,p.source_sha256=$sha '
                    f'CREATE (n:Chunk:`{source_label}` {{id:$id,project:$project,text:$text,source_json:$source,'
                    'embedding_384:$vector,encoder_revision:"fixture-encoder"}) '
                    'MERGE (c)-[:HAS_PAPER]->(p) MERGE (p)-[:HAS_CHUNK]->(n)',
                    corpus=corpus,project=project,paper=paper_id,sha=source.source_sha256,id=key,text=text,
                    source=source.model_dump_json(),vector=FAR if remote else NEAR).consume()
            session.run(f'CREATE VECTOR INDEX `{vector_index}` FOR (n:`{source_label}`) ON n.embedding_384 '
                        'OPTIONS {indexConfig:{`vector.dimensions`:384,`vector.similarity_function`:"cosine"}}').consume()
            session.run('CALL db.awaitIndex($name,120)',name=vector_index).consume()
        decisions=[HumanDecision(claim_id=r.claim_id,claim_revision=1,revision_sha256=r.sha256,
            source_sha256=r.paper.source_sha256,entity_revision=r.entity_revision,
            reviewer='SYNTHETIC FIXTURE',reviewed_at=datetime(2026,11,8,tzinfo=timezone.utc),
            review_time_note='Synthetic only; not measured',reason='Synthetic test only',decision='approved',
            origin='human_csv',provenance_sha256='b'*64) for r in revisions]
        import_decisions(root,decisions,chunks)
        review=projection(root,chunks)
        repo.publish(corpus,review,[FAR if f['paper_id']==paper_b else NEAR for f in review['facts']],'fixture-encoder')
        repo.prepare_indexes(corpus)
        source_eval=fingerprint([corpus,revisions[0].claim_id,1])
        finding=fingerprint([corpus,revisions[15].claim_id,1])
        with repo.driver.session(database=repo.database) as session:
            # Explicit fixture ground truth exercises the optional evaluation-specific finding route.
            session.run('MATCH (f:Finding {id:$finding,project:$project}),(e:Evaluation {id:$evaluation,project:$project}) '
                        'CREATE (f)-[:ABOUT_EVALUATION]->(e)',finding=finding,evaluation=source_eval,project=project).consume()
            session.run('MATCH (a:Paper {id:$a,project:$project}),(b:Paper {id:$b,project:$project}) '
                        'CREATE (a)-[:CITES {corpus_id:$corpus}]->(b),(b)-[:CITES {corpus_id:$corpus}]->(a)',
                        a=paper_a,b=paper_b,project=project,corpus=corpus).consume()
        catalog=ReviewCatalog.from_review(corpus,review)
        def retrieve(mode):
            return retrieve_modes(QueryRequest(question='anchor lookupmethod lookupdataset',corpus_id=corpus,mode=mode),repo,FixtureEncoder(),
                                  chunks,catalog if mode!='hybrid' else None,'fixture-encoder')
        baseline=retrieve('hybrid_facts')
        graph=retrieve('graph')
        target=next(f['id'] for f in review['facts'] if f['claim_id']==revisions[14].claim_id)
        baseline_pool={row['id'] for row in baseline.audit['fusion']}
        assert target not in baseline_pool
        assert graph.audit['channel_rankings']==baseline.audit['channel_rankings']
        remote_items=[e for e in graph.evidence if e.paper_ids==[paper_b]]
        assert graph.effective_mode=='graph' and remote_items
        assert any(e.id not in baseline_pool and e.graph_paths for e in remote_items)
        assert graph.audit['graph_rows']<=80 and len(graph.audit['graph_candidates_retained'])<=40
        assert graph.estimated_tokens<=1800 and len(graph.evidence)<=6
        params={'project':project,'corpus':corpus,'head':catalog.head,'seed_paper':paper_a,
                'seed_chunks':[revisions[0].support[0].chunk_id], 'entity_ids':[method.id,dataset.id],
                'fact_ids':sorted(catalog.facts)}
        inspected={}
        for name in traversal_templates(corpus):
            with repo.reading(corpus,catalog.head,30):
                _,explain=repo.traverse(corpus,name,params,'EXPLAIN')
            with repo.reading(corpus,catalog.head,30):
                rows,profile=repo.traverse(corpus,name,params,'PROFILE')
            metrics=plan_metrics(profile)
            operators=[n['operator'] for n in metrics['operators']]
            assert rows and len(rows)<=5 and any('IndexSeek' in op for op in operators)
            assert not any('AllNodesScan' in op for op in operators)
            assert metrics['maximum_operator_rows']>=len(rows)>0
            inspected[name]={'explain':explain,'profile':profile,'metrics':metrics,'returned_rows':rows}
        assert any(row['direction']=='about_evaluation' for row in inspected['finding']['returned_rows'])
        assert {row['direction'] for row in inspected['citation']['returned_rows']}=={'incoming','outgoing'}
        with pytest.raises(ValueError,match='stale'):
            with repo.reading(corpus,'f'*64,30):
                pass
        with repo.driver.session(database=repo.database) as session:
            session.run('MATCH (n:ReviewedClaim {id:$id,project:$project}) SET n.reporting_paper_id="wrong-paper"',
                        id=fingerprint([corpus,revisions[14].claim_id,1]),project=project).consume()
        try:
            with pytest.raises(ValueError,match='owner/content'):
                retrieve('graph')
        finally:
            with repo.driver.session(database=repo.database) as session:
                session.run('MATCH (n:ReviewedClaim {id:$id,project:$project}) SET n.reporting_paper_id=$paper',
                            id=fingerprint([corpus,revisions[14].claim_id,1]),project=project,paper=paper_b).consume()
        target_node=fingerprint([corpus,revisions[14].claim_id,1])
        dataset_node=fingerprint(dataset.model_dump())
        bad_dataset='bad-dataset-'+token
        with repo.driver.session(database=repo.database) as session:
            session.run('MATCH (n:Evaluation {id:$id,project:$project})-[r:ON_DATASET]->(:Dataset) '
                        'DELETE r CREATE (bad:Dataset {id:$bad,project:$project}), (n)-[:ON_DATASET]->(bad)',
                        id=target_node,project=project,bad=bad_dataset).consume()
        try:
            with pytest.raises(ValueError,match='entity relationships'):
                retrieve('graph')
        finally:
            with repo.driver.session(database=repo.database) as session:
                session.run('MATCH (n:Evaluation {id:$id,project:$project})-[r:ON_DATASET]->(bad:Dataset {id:$bad}),'
                            '(d:Dataset {id:$dataset,project:$project}) DELETE r MERGE (n)-[:ON_DATASET]->(d)',
                            id=target_node,project=project,bad=bad_dataset,dataset=dataset_node).consume()
        revoked=decisions[14].model_copy(update={'decision':'needs_review','reviewed_at':decisions[14].reviewed_at+timedelta(seconds=1)})
        import_decisions(root,[revoked],chunks)
        new_review=projection(root,chunks)
        catalog=ReviewCatalog.from_review(corpus,new_review)
        with pytest.raises(ValueError,match='stale'):
            retrieve('graph')
        repo.publish(corpus,new_review,[FAR if f['paper_id']==paper_b else NEAR for f in new_review['facts']],'fixture-encoder')
        after_revoke=retrieve('graph')
        assert target not in {row['id'] for row in after_revoke.audit['fusion']}
        assert target not in {row['fact_id'] for call in after_revoke.audit['graph_calls'] for row in call['rows']}
        # Give the server's timeout monitor a bounded idle interval; no expensive data scan is needed.
        timeout_started=time.perf_counter()
        with pytest.raises(Neo4jError) as timeout_error:
            with repo.reading(corpus,None,0.001):
                repo.tx.run('RETURN 1 AS ready').consume()
                time.sleep(3)
                repo.tx.run('RETURN 1 AS after_deadline').consume()
        assert 'TimedOut' in timeout_error.value.code
        result_report={'task_id':'M3.1',**code_identity(),'fixture_project':project,'new_cross_paper_evidence':True,
            'target_outside_hybrid_facts_pool':target not in baseline_pool,
            'baseline_pool':sorted(baseline_pool),'graph_evidence':[e.model_dump() for e in graph.evidence],
            'graph_rows':graph.audit['graph_rows'],'graph_retained':len(graph.audit['graph_candidates_retained']),
            'estimated_tokens':graph.estimated_tokens,'plans':inspected,
            'stale_head_rejected':True,'wrong_paper_rejected':True,
            'wrong_dataset_rejected':True,'revoked_fact_absent_from_all_channels_and_paths':True,
            'timeout':{'code':timeout_error.value.code,'wall_ms':(time.perf_counter()-timeout_started)*1000}}
        if os.getenv('M3_FIXTURE_REPORT'):
            write_immutable(Path(os.environ['M3_FIXTURE_REPORT']),json.dumps(result_report,indent=2)+'\n')
    finally:
        assert project==PROJECT+'-retrieval-fixture-'+token and len(token)==32
        with repo.driver.session(database=repo.database) as session:
            count=session.run('MATCH (n {project:$project}) RETURN count(n) AS count',project=project).single()['count']
            assert count<200
            for index in (vector_index,chunk_text,fact_vector,fact_text):
                session.run(f'DROP INDEX `{index}` IF EXISTS').consume()
            session.run('MATCH (n {project:$project}) DETACH DELETE n',project=project).consume()
        repo.close()
