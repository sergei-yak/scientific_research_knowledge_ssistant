"""Four static route families; unions share one ordered five-row cap."""
from research_assistant.graph.repository import corpus_names
from research_assistant.graph.reviews import fact_names


def traversal_templates_v2(corpus_id: str) -> dict[str,str]:
    """Allow reviewed Finding/Evaluation or indexed direct-entity starts, never MENTIONS."""
    chunks,_=corpus_names(corpus_id)
    facts,_,_=fact_names(corpus_id)
    common='''
MATCH (c:Corpus {id:$corpus,project:$project,ready:true,experiment_scope_id:$scope_id,retrieval_profile_id:'retrieval-v2'})
MATCH (rs:ReviewState {id:$corpus,project:$project,head_sha256:$head})
'''
    seed=f'''
MATCH (p:Paper {{id:$seed_paper,project:$project}})-[:HAS_CHUNK]->(s:Chunk:`{chunks}` {{project:$project}})
USING INDEX p:Paper(id)
WHERE $anchor_type='evidence' AND s.id IN $seed_chunks
MATCH (c)-[:HAS_PAPER]->(p)
'''
    source=f'''
MATCH (p)-[:REPORTS_FINDING|REPORTS_EVALUATION]->(sc:ReviewedClaim {{project:$project,corpus_id:$corpus,current:true,status:'approved'}})
MATCH (sf:`{facts}` {{active:true,project:$project,corpus_id:$corpus}})-[:REPRESENTS]->(sc)
WHERE sf.id IN $fact_ids AND sc.reporting_paper_id=p.id AND sc.source_sha256=p.source_sha256
'''
    finish=f'''
MATCH (c)-[:HAS_PAPER]->(tp:Paper {{project:$project}})-[:REPORTS_EVALUATION|REPORTS_FINDING]->(t:ReviewedClaim)
MATCH (f:`{facts}` {{active:true,project:$project,corpus_id:$corpus}})-[:REPRESENTS]->(t)
MATCH (t)-[support:SUPPORTED_BY]->(x:Chunk:`{chunks}` {{project:$project}})<-[:HAS_CHUNK]-(tp)
WHERE t.project=$project AND t.corpus_id=$corpus AND t.current=true AND t.status='approved'
  AND t.reporting_paper_id=tp.id AND t.source_sha256=tp.source_sha256
  AND support.source_sha256=tp.source_sha256 AND f.id IN $fact_ids
RETURN DISTINCT f.id AS fact_id,tp.id AS reporting_paper,t.claim_id AS claim_id,t.revision AS revision,
       x.id AS support_chunk,route + [x.id] AS node_ids,entity_ids,direction
ORDER BY reporting_paper,claim_id,support_chunk,fact_id,node_ids
LIMIT 5
'''
    result={}
    for name,label,edges,ev,fi in [('shared_method','Method','OF_METHOD|ABOUT_METHOD','OF_METHOD','ABOUT_METHOD'),
                                 ('shared_dataset','Dataset','ON_DATASET|ABOUT_DATASET','ON_DATASET','ABOUT_DATASET')]:
        role=lambda node,rel: f"(({node}:Evaluation AND type({rel})='{ev}') OR ({node}:Finding AND type({rel})='{fi}'))"
        evidence=seed+source+f'''
MATCH (sc)-[sr:{edges}]->(e:{label} {{project:$project}})<-[tr:{edges}]-(t:ReviewedClaim)
WHERE e.entity_id IN $entity_ids AND t.id<>sc.id AND {role('sc','sr')} AND {role('t','tr')}
RETURN t,[s.id,p.id,sc.id,e.id,t.id] AS route,[e.entity_id] AS entity_ids,'shared' AS direction
'''
        direct=f'''
MATCH (e:{label} {{id:$anchor_entity_node,project:$project}})
USING INDEX e:{label}(id)
WHERE $anchor_type='entity' AND e.entity_id=$anchor_entity_id AND e.entity_id IN $entity_ids
MATCH (e)<-[tr:{edges}]-(t:ReviewedClaim)
WHERE {role('t','tr')}
RETURN t,[e.id,t.id] AS route,[e.entity_id] AS entity_ids,'entity_start' AS direction
'''
        result[name]=common+'CALL (c) {\n'+evidence+'UNION ALL\n'+direct+'}\n'+finish
    result['citation']=common+seed+'''
CALL (p,s) {
 MATCH (p)-[r:CITES {corpus_id:$corpus}]->(other:Paper {project:$project})
 MATCH (other)-[:REPORTS_EVALUATION|REPORTS_FINDING]->(t:ReviewedClaim)
 RETURN t,[s.id,p.id,other.id,t.id] AS route,[] AS entity_ids,'outgoing' AS direction
 UNION ALL
 MATCH (p)<-[r:CITES {corpus_id:$corpus}]-(other:Paper {project:$project})
 MATCH (other)-[:REPORTS_EVALUATION|REPORTS_FINDING]->(t:ReviewedClaim)
 RETURN t,[s.id,p.id,other.id,t.id] AS route,[] AS entity_ids,'incoming' AS direction
}
'''+finish
    # Reviewed method linkage connects Findings/Evaluations. Unbound ABOUT_EVALUATION edges
    # are not interpreted as approvals; the original catalog has no such approved target mapping.
    result['finding']=common+seed+source+'''
MATCH (sc)-[sr:OF_METHOD|ABOUT_METHOD]->(e:Method {project:$project})<-[tr:OF_METHOD|ABOUT_METHOD]-(t:ReviewedClaim)
WHERE e.entity_id IN $entity_ids AND sc.id<>t.id AND (sc:Finding OR t:Finding)
 AND ((sc:Evaluation AND type(sr)='OF_METHOD') OR (sc:Finding AND type(sr)='ABOUT_METHOD'))
 AND ((t:Evaluation AND type(tr)='OF_METHOD') OR (t:Finding AND type(tr)='ABOUT_METHOD'))
WITH c,t,[s.id,p.id,sc.id,e.id,t.id] AS route,[e.entity_id] AS entity_ids,'finding_method_link' AS direction
'''+finish
    return result
