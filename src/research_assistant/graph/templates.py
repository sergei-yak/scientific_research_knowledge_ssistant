"""Four bounded, parameterized read-only routes; only validated corpus labels are interpolated."""

from research_assistant.graph.repository import corpus_names
from research_assistant.graph.reviews import fact_names


def traversal_templates(corpus_id: str) -> dict[str, str]:
    """Return fixed routes with indexed seed anchors and one shared five-row limit per template."""
    chunks, _ = corpus_names(corpus_id)
    facts, _, _ = fact_names(corpus_id)
    start = f"""
MATCH (p:Paper {{id:$seed_paper,project:$project}})-[:HAS_CHUNK]->(s:Chunk)
USING INDEX p:Paper(id)
WHERE s.id IN $seed_chunks AND s:`{chunks}` AND s.project=$project
MATCH (c:Corpus {{id:$corpus,project:$project,ready:true}})-[:HAS_PAPER]->(p)
MATCH (rs:ReviewState {{id:$corpus,project:$project,head_sha256:$head}})
"""
    source_eval = f"""
MATCH (p)-[:REPORTS_EVALUATION]->(se:Evaluation {{project:$project,corpus_id:$corpus,current:true,status:'approved'}})
MATCH (sf:`{facts}` {{active:true,project:$project,corpus_id:$corpus}})-[:REPRESENTS]->(se)
WHERE sf.id IN $fact_ids AND se.reporting_paper_id=p.id AND se.source_sha256=p.source_sha256
"""
    finish = f"""
MATCH (c)-[:HAS_PAPER]->(tp:Paper {{project:$project}})-[:REPORTS_EVALUATION|REPORTS_FINDING]->(t)
MATCH (f:`{facts}` {{active:true,project:$project,corpus_id:$corpus}})-[:REPRESENTS]->(t)
MATCH (t)-[support:SUPPORTED_BY]->(x:Chunk:`{chunks}` {{project:$project}})<-[:HAS_CHUNK]-(tp)
WHERE t.project=$project AND t.corpus_id=$corpus AND t.current=true AND t.status='approved'
  AND t.reporting_paper_id=tp.id AND t.source_sha256=tp.source_sha256
  AND support.source_sha256=tp.source_sha256 AND f.id IN $fact_ids
RETURN DISTINCT f.id AS fact_id,tp.id AS reporting_paper,t.claim_id AS claim_id,t.revision AS revision,
       x.id AS support_chunk,route + [x.id] AS node_ids,entity_ids,direction
ORDER BY reporting_paper,claim_id,support_chunk,fact_id,node_ids
LIMIT 5
"""
    result = {}
    for name, edge, label in (("shared_dataset", "ON_DATASET", "Dataset"),
                              ("shared_method", "OF_METHOD", "Method")):
        body = source_eval + f"""
MATCH (se)-[:{edge}]->(e:{label} {{project:$project}})<-[:{edge}]-(t:Evaluation)
WHERE e.entity_id IN $entity_ids AND t.id<>se.id
WITH c,p,s,t,[s.id,p.id,se.id,e.id,t.id] AS route,[e.entity_id] AS entity_ids,'shared' AS direction
"""
        result[name] = start + body + finish
    citation = """
CALL (p,s) {
  MATCH (p)-[r:CITES {corpus_id:$corpus}]->(other:Paper {project:$project})
  MATCH (other)-[:REPORTS_EVALUATION|REPORTS_FINDING]->(t:ReviewedClaim)
  RETURN t,[s.id,p.id,other.id,t.id] AS route,[] AS entity_ids,'outgoing' AS direction
  UNION ALL
  MATCH (p)<-[r:CITES {corpus_id:$corpus}]-(other:Paper {project:$project})
  MATCH (other)-[:REPORTS_EVALUATION|REPORTS_FINDING]->(t:ReviewedClaim)
  RETURN t,[s.id,p.id,other.id,t.id] AS route,[] AS entity_ids,'incoming' AS direction
}
"""
    result["citation"] = start + citation + finish
    finding = "CALL (p,s) {\n" + source_eval + """
MATCH (se)-[:OF_METHOD]->(e:Method {project:$project})<-[:ABOUT_METHOD]-(t:Finding)
WHERE e.entity_id IN $entity_ids
RETURN t,[s.id,p.id,se.id,e.id,t.id] AS route,[e.entity_id] AS entity_ids,'about_method' AS direction
UNION ALL
""" + source_eval + """
MATCH (se)<-[:ABOUT_EVALUATION]-(t:Finding)
RETURN t,[s.id,p.id,se.id,t.id] AS route,[] AS entity_ids,'about_evaluation' AS direction
}
"""
    result["finding"] = start + finding + finish
    return result
