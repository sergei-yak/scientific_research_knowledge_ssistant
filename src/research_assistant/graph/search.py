"""Explicit search-index setup and bounded, review-head-checked read transactions."""

from contextlib import contextmanager
import json

from neo4j import READ_ACCESS

from research_assistant.contracts import Chunk, EvidenceItem, fingerprint
from research_assistant.graph.repository import corpus_names
from research_assistant.graph.reviews import ReviewRepository, fact_names
from research_assistant.graph.templates import traversal_templates
from research_assistant.retrieval.catalog import ReviewCatalog, cosine, lexical_query
from research_assistant.review.contracts import EntityDefinition
from research_assistant.ingestion.sources import verified_chunk


def search_names(corpus_id: str) -> tuple[str, str, str]:
    """Keep corpus text separate; shared entity indexes retain historical definitions."""
    corpus_names(corpus_id)
    return 'ra_chunks_text_' + corpus_id[:16], 'ra_method_aliases', 'ra_dataset_aliases'


def plan_metrics(plan: dict) -> dict:
    """Inspect actual operator cardinalities and database work, separately from final row limits."""
    nodes = []
    def visit(node):
        nodes.append({'operator':node.get('operatorType'), 'rows':node.get('rows'),
                      'db_hits':node.get('dbHits'), 'arguments':node.get('args',node.get('arguments'))})
        for child in node.get('children',[]):
            visit(child)
    visit(plan)
    return {'operators':nodes, 'total_db_hits':sum(n['db_hits'] or 0 for n in nodes),
            'maximum_operator_rows':max((n['rows'] or 0 for n in nodes),default=0)}


class SearchRepository(ReviewRepository):
    """One read-only transaction per retrieval; setup is a distinct explicit operation."""

    tx = None

    def snapshot(self, corpus_id: str) -> dict:
        """Read one ready owned corpus, including an isolated fixture's explicit project."""
        corpus_names(corpus_id)
        with self.driver.session(database=self.database, default_access_mode=READ_ACCESS) as session:
            row = session.run('MATCH (c:Corpus {id:$id,project:$project,ready:true}) RETURN c.snapshot_json AS snapshot',
                              id=corpus_id, project=self.project).single()
        if row is None:
            raise ValueError('Corpus does not exist or ingestion is not ready')
        return json.loads(row['snapshot'])

    def prepare_indexes(self, corpus_id: str) -> dict:
        """Add indexes only; never reset volumes, replace sources or change human decisions."""
        from research_assistant.graph.scope import guard_development_write
        guard_development_write(self.settings)
        label, _ = corpus_names(corpus_id)
        chunk_text, method_alias, dataset_alias = search_names(corpus_id)
        with self.driver.session(database=self.database) as session:
            row = session.run("MATCH (c:Corpus {id:$id,project:$project,ready:true}) RETURN properties(c)['frozen'] AS frozen",
                              id=corpus_id, project=self.project).single()
            if row is None or row['frozen']:
                raise ValueError('Search setup target is missing, unready or frozen')
            session.run(f'CREATE FULLTEXT INDEX `{chunk_text}` IF NOT EXISTS FOR (n:`{label}`) ON EACH [n.text]').consume()
            for name, kind in ((method_alias, 'Method'), (dataset_alias, 'Dataset')):
                session.run(f'CREATE FULLTEXT INDEX `{name}` IF NOT EXISTS FOR (n:{kind}) ON EACH [n.canonical_name,n.aliases]').consume()
            for name in (chunk_text, method_alias, dataset_alias):
                session.run('CALL db.awaitIndex($name,120)', name=name).consume()
            indexes = session.run('SHOW INDEXES YIELD name,state WHERE name IN $names RETURN name,state ORDER BY name',
                                  names=[chunk_text, method_alias, dataset_alias]).data()
        return {'corpus_id':corpus_id, 'indexes':indexes, 'source_or_claim_mutations':0}

    @contextmanager
    def reading(self, corpus_id: str, head: str | None, timeout: float):
        """Enforce a configurable overall transaction deadline; failures never become mode fallback."""
        if not 0.001 <= timeout <= 30:
            raise ValueError('Graph query timeout must be between 0.001 and 30 seconds')
        if self.tx is not None:
            raise ValueError('Nested retrieval transactions are not allowed')
        with self.driver.session(database=self.database, default_access_mode=READ_ACCESS) as session:
            with session.begin_transaction(timeout=timeout) as tx:
                self.tx = tx
                try:
                    self.check_head(corpus_id, head)
                    yield self
                    self.check_head(corpus_id, head)
                finally:
                    self.tx = None

    def check_head(self, corpus_id: str, head: str | None) -> None:
        """Check before and after reads; a stale approval projection is an explicit error."""
        if head is None:
            return
        row = self.tx.run('MATCH (r:ReviewState {id:$id,project:$project}) RETURN r.head_sha256 AS head',
                          id=corpus_id, project=self.project).single()
        if row is None or row['head'] != head:
            raise ValueError('Review projection is stale; synchronize before retrieval')

    def check_indexes(self, corpus_id: str, facts: bool) -> None:
        """Queries require ONLINE indexes; index creation is never an implicit retrieval side effect."""
        _, chunk_vector = corpus_names(corpus_id)
        chunk_text, *aliases = search_names(corpus_id)
        names = [chunk_vector,chunk_text] + aliases
        if facts:
            _, fv, ft = fact_names(corpus_id)
            names += [fv,ft]
        rows = self.tx.run('SHOW INDEXES YIELD name,state WHERE name IN $names RETURN name,state', names=names).data()
        if {r['name'] for r in rows if r['state']=='ONLINE'} != set(names):
            raise ValueError('Required retrieval indexes are unavailable; run explicit search-setup')

    def fact_vectors(self, catalog: ReviewCatalog, chunks: dict[str, Chunk], revision: str,
                     *, strict_roles: bool = False) -> dict[str, list[float]]:
        """Compare graph materialization with the shared authoritative projection, including support/owners."""
        label, _, _ = fact_names(catalog.corpus_id)
        rows = self.tx.run(f'''
MATCH (f:`{label}` {{project:$project,corpus_id:$corpus,active:true}})-[:REPRESENTS]->(n:ReviewedClaim)
OPTIONAL MATCH (p:Paper)-[:REPORTS_EVALUATION|REPORTS_FINDING]->(n)
WITH f,n,collect(DISTINCT p.id) AS owners
RETURN properties(f) AS fact,properties(n) AS claim,owners,
 [(n)-[r:SUPPORTED_BY]->(s:Chunk) | {{id:s.id,source:s.source_json,start:r.start,end:r.end,sha:r.source_sha256}}] AS support,
 [(n)-[r]->(e) WHERE type(r) IN ['OF_METHOD','ON_DATASET','ABOUT_METHOD','MENTIONS','ABOUT_DATASET']
   AND (e:Method OR e:Dataset) | properties(e)] AS entities,
 [(n)-[r]->(e) WHERE (e:Method OR e:Dataset) | {{id:e.id,role:type(r)}}] AS entity_roles
''', project=self.project, corpus=catalog.corpus_id).data()
        if len(rows) != len(catalog.facts) or {row['fact']['id'] for row in rows} != set(catalog.facts):
            raise ValueError('Active graph facts differ from the current review projection')
        vectors = {}
        for row in rows:
            stored, claim = row['fact'], row['claim']
            expected = catalog.facts[stored['id']]
            expected_evidence = EvidenceItem.model_validate(expected['evidence'])
            if (row['owners'] != [expected['paper_id']] or claim.get('project') != self.project
                    or claim.get('id') != fingerprint([catalog.corpus_id,expected['claim_id'],expected['claim_revision']])
                    or claim.get('corpus_id') != catalog.corpus_id or not claim.get('current')
                    or claim.get('status') != 'approved' or claim.get('reporting_paper_id') != expected['paper_id']
                    or claim.get('source_sha256') != expected['source_sha256']
                    or claim.get('claim_id') != expected['claim_id'] or claim.get('revision') != expected['claim_revision']
                    or claim.get('text') != expected['claim_text'] or claim.get('entity_revision') != expected['entity_revision']
                    or stored.get('revision_sha256') != expected['revision_sha256']
                    or stored.get('approval_revision') != expected['decision_id']
                    or stored.get('claim_id') != expected['claim_id'] or stored.get('claim_revision') != expected['claim_revision']
                    or stored.get('representation_version') != expected['representation_version']
                    or stored.get('embedding_text') != expected['embedding_text']
                    or stored.get('rendered_text') != expected['rendered_text']
                    or stored.get('search_text') != expected['rendered_text']
                    or stored.get('encoder_revision') != revision
                    or EvidenceItem.model_validate_json(stored['evidence_json']) != expected_evidence
                    or json.loads(claim['conditions_json']) != expected_evidence.conditions):
                raise ValueError('Graph fact revision/source/owner/content is inconsistent')
            actual_support = set()
            for support in row['support']:
                source = verified_chunk(support['source'],chunks)
                if source.chunk_id != support['id']:
                    raise ValueError('Graph fact support source changed')
                actual_support.add((support['id'],support['start'],support['end'],support['sha']))
            expected_support = {(e.chunk_id,e.start,e.end,e.source_sha256) for e in expected_evidence.excerpts}
            if actual_support != expected_support:
                raise ValueError('Graph fact support relationships changed')
            entities = {e['id']:e for e in row['entities']}
            if strict_roles:
                expected_roles=[]
                for definition in expected['entities']:
                    edge=(('OF_METHOD' if definition['kind']=='method' else 'ON_DATASET') if expected['kind']=='evaluation'
                          else ('ABOUT_METHOD' if definition['kind']=='method' else 'MENTIONS'))
                    edge=expected.get('relation_roles',{}).get(definition['id'],edge)
                    expected_roles.append((fingerprint(definition),edge))
                if sorted((r['id'],r['role']) for r in row['entity_roles'])!=sorted(expected_roles):
                    raise ValueError('Graph relationship role differs from its exact approved mapping')
            if set(entities) != {fingerprint(e) for e in expected['entities']}:
                raise ValueError('Graph fact entity relationships changed')
            for definition in expected['entities']:
                identity = fingerprint(definition)
                entity = entities[identity]
                if (entity['project'] != self.project or entity['entity_id'] != definition['id']
                        or entity['canonical_name'] != definition['name'] or entity['aliases'] != definition['aliases']
                        or entity['alias_revision'] != EntityDefinition.model_validate(definition).revision
                        or claim.get(definition['kind'] + '_id') != identity):
                    raise ValueError('Graph alias/entity identity changed')
            cosine(stored['embedding_384'], stored['embedding_384'])
            vectors[stored['id']] = stored['embedding_384']
        return vectors

    def ranked(self, corpus_id: str, kind: str, channel: str, query: list[float], text: str,
               revision: str, fact_ids: list[str]) -> list[dict]:
        """Return at most twelve candidates; semantic ANN overfetch 24 is reranked by actual cosine."""
        if kind not in {'chunk','fact'} or channel not in {'vector','text'}:
            raise ValueError('Unknown retrieval channel')
        label, chunk_vector = corpus_names(corpus_id)
        chunk_text, _, _ = search_names(corpus_id)
        active, fact_vector, fact_text = fact_names(corpus_id)
        index = (chunk_vector if channel=='vector' else chunk_text) if kind=='chunk' else (fact_vector if channel=='vector' else fact_text)
        native = ('CALL db.index.vector.queryNodes($index,24,$vector)' if channel=='vector' else
                  'CALL db.index.fulltext.queryNodes($index,$text)')
        if channel=='text' and not lexical_query(text):
            return []
        guard = f'node:`{label}`' if kind=='chunk' else f'node:`{active}` AND node.active=true AND node.id IN $fact_ids'
        rows = self.tx.run(native + ' YIELD node,score WHERE node.project=$project AND ' + guard +
            ' RETURN node.id AS id,node.source_json AS source,node.embedding_384 AS vector,node.encoder_revision AS revision,score '
            'ORDER BY score DESC,id LIMIT $limit',index=index,vector=query,text=lexical_query(text),
            project=self.project,fact_ids=fact_ids,limit=24 if channel=='vector' else 12).data()
        for row in rows:
            if row['revision'] != revision:
                raise ValueError('Search vector uses a different encoder revision')
            row['similarity'] = cosine(query,row['vector'])
        if channel=='vector':
            rows.sort(key=lambda row:(-row['similarity'],row['id']))
        return rows[:12]

    def traverse(self, corpus_id: str, template: str, params: dict, explain: str = '',
                 profile_id: str = 'baseline') -> tuple[list[dict], dict | None]:
        """Execute one fixed template, optionally collecting its read-only EXPLAIN/PROFILE summary."""
        if explain not in {'','EXPLAIN','PROFILE'}:
            raise ValueError('Invalid query inspection mode')
        if profile_id == 'retrieval-v2':
            from research_assistant.graph.templates_v2 import traversal_templates_v2
            query = traversal_templates_v2(corpus_id)[template]
        elif profile_id == 'baseline':
            query = traversal_templates(corpus_id)[template]
        else:
            raise ValueError('Unknown retrieval profile')
        result = self.tx.run((explain+' ' if explain else '') + query, **params)
        rows = result.data()
        summary = result.consume()
        if len(rows)>5:
            raise ValueError('Graph template exceeded its row bound')
        return rows, summary.profile if explain=='PROFILE' else summary.plan if explain else None
