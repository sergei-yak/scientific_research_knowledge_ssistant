"""Explicit additive MPNet indexing; baseline vectors and corpus identity remain intact."""

import json

import numpy as np
from neo4j import Query

from research_assistant.contracts import Chunk, fingerprint
from research_assistant.graph.repository import GraphRepository, PROJECT, corpus_names
from research_assistant.ingestion.sources import load_corpus_chunks, source_identity


def mpnet_index(corpus_id: str) -> str:
    """Derive only a project-owned, corpus-hash schema name."""
    corpus_names(corpus_id)
    return 'ra_mpnet_' + corpus_id[:16]


class MPNetRepository(GraphRepository):
    """Reuse baseline ANN/cosine/source contracts with a distinct 768-D property/index."""

    def _index_ready(self, session, corpus_id: str, *, allow_missing: bool = False) -> None:
        """Reject a colliding index definition; a missing/offline index is never a fallback."""
        label, _ = corpus_names(corpus_id)
        row = session.run('SHOW INDEXES YIELD name,state,labelsOrTypes,properties,options '
                          'WHERE name=$name RETURN *', name=mpnet_index(corpus_id)).single()
        if row is None and allow_missing:
            return
        if row is None:
            raise ValueError('MPNet index is unavailable; run explicit embedding setup')
        config = row['options'].get('indexConfig', {})
        if (row['labelsOrTypes'] != [label] or row['properties'] != ['embedding_768']
                or config.get('vector.dimensions') != 768
                or str(config.get('vector.similarity_function')).lower() != 'cosine'):
            raise ValueError('MPNet index definition conflicts with the frozen condition')
        if not allow_missing and row['state'] != 'ONLINE':
            raise ValueError('MPNet index is not ONLINE')

    def setup(self, corpus_id: str, chunks: dict[str, Chunk], vectors: list[list[float]], manifest: dict) -> dict:
        """Add only verified 768-D fields; refuse conflicts, frozen corpora and source mismatch."""
        label, _ = corpus_names(corpus_id)
        array = np.asarray(vectors, dtype=float)
        if (array.shape != (len(chunks), 768) or not np.isfinite(array).all()
                or not np.allclose(np.linalg.norm(array, axis=1), 1, atol=1e-5)):
            raise ValueError('Invalid MPNet ingestion vectors')
        if (manifest['corpus_id'] != corpus_id or manifest['source_chunks_sha256'] != source_identity(chunks)
                or manifest['dimensions'] != 768 or manifest['vectors_sha256'] != fingerprint(vectors)):
            raise ValueError('MPNet manifest does not match the unchanged source corpus')
        self.snapshot(corpus_id)
        encoded = json.dumps(manifest, sort_keys=True)
        with self.driver.session(database=self.database) as session:
            state = session.run('MATCH (c:Corpus {id:$id,project:$project,ready:true}) '
                "RETURN c.frozen AS frozen,properties(c)['mpnet_manifest_json'] AS experiment",
                id=corpus_id, project=PROJECT).single()
            if state is None or state['frozen'] or (state['experiment'] and state['experiment'] != encoded):
                raise ValueError('MPNet target is frozen, unready or has a conflicting experiment')
            self._index_ready(session, corpus_id, allow_missing=True)
            rows = [{'id': chunk.chunk_id, 'source': chunk.model_dump_json(), 'vector': vector}
                    for chunk, vector in zip(chunks.values(), vectors)]
            for offset in range(0, len(rows), 64):
                batch = rows[offset:offset + 64]
                conflict = session.run(Query(
                    f'UNWIND $rows AS row OPTIONAL MATCH (n:Chunk:`{label}` {{id:row.id}}) '
                    'WHERE n.project=$project AND n.source_json=row.source '
                    'RETURN count(n) AS matched, sum(CASE WHEN n.embedding_768 IS NOT NULL AND '
                    "(n.embedding_768 <> row.vector OR coalesce(n.mpnet_encoder_revision,'') <> $revision) "
                    'THEN 1 ELSE 0 END) AS conflicts', timeout=30),
                    rows=batch, project=PROJECT, revision=manifest['encoder_revision']).single()
                if conflict['matched'] != len(batch) or conflict['conflicts']:
                    raise ValueError('MPNet source/vector conflicts with existing owned data')
                written = session.run(Query(
                    'MATCH (c:Corpus {id:$corpus,project:$project,ready:true}) WHERE NOT c.frozen '
                    f'UNWIND $rows AS row MATCH (n:Chunk:`{label}` {{id:row.id,project:$project}}) '
                    'SET n.embedding_768=row.vector,n.mpnet_encoder_revision=$revision RETURN count(n) AS count',
                    timeout=30), corpus=corpus_id, project=PROJECT, rows=batch,
                    revision=manifest['encoder_revision']).single()
                if written is None or written['count'] != len(batch):
                    raise ValueError('MPNet corpus became frozen or unavailable during setup')
            session.run(Query(
                f'CREATE VECTOR INDEX `{mpnet_index(corpus_id)}` IF NOT EXISTS FOR (n:`{label}`) '
                'ON (n.embedding_768) OPTIONS {indexConfig: {`vector.dimensions`:768, '
                "`vector.similarity_function`:'cosine'}}", timeout=30)).consume()
            session.run('CALL db.awaitIndex($name,120)', name=mpnet_index(corpus_id)).consume()
            self._index_ready(session, corpus_id)
            saved = session.run('MATCH (c:Corpus {id:$id,project:$project,ready:true}) WHERE NOT c.frozen '
                'SET c.mpnet_manifest_json=$manifest RETURN c.id AS id',
                id=corpus_id, project=PROJECT, manifest=encoded).single()
            if saved is None:
                raise ValueError('MPNet corpus became frozen before readiness publication')
        return self.experiment(corpus_id)

    def experiment(self, corpus_id: str) -> dict:
        """Verify source scope, dimensions/revision coverage and online index before every use."""
        self.snapshot(corpus_id)
        chunks = load_corpus_chunks(corpus_id)
        label, _ = corpus_names(corpus_id)
        with self.driver.session(database=self.database) as session:
            row = session.run("MATCH (c:Corpus {id:$id,project:$project,ready:true}) "
                "RETURN properties(c)['mpnet_manifest_json'] AS experiment",
                id=corpus_id, project=PROJECT).single()
            if row is None or not row['experiment']:
                raise ValueError('MPNet experiment is unready; run explicit embedding setup')
            manifest = json.loads(row['experiment'])
            if (manifest['source_chunks_sha256'] != source_identity(chunks)
                    or manifest['corpus_id'] != corpus_id or manifest['dimensions'] != 768):
                raise ValueError('MPNet source snapshot/dimensions changed')
            self._index_ready(session, corpus_id)
            count = session.run(f'MATCH (n:Chunk:`{label}` {{project:$project}}) '
                'WHERE size(n.embedding_768)=768 AND n.mpnet_encoder_revision=$revision RETURN count(n) AS count',
                project=PROJECT, revision=manifest['encoder_revision']).single()['count']
            if count != len(chunks) or manifest['chunk_count'] != len(chunks):
                raise ValueError('MPNet vector coverage differs from the fixed chunks')
            return manifest

    def vector_candidates(self, corpus_id: str, query: list[float]) -> list[tuple[Chunk, float]]:
        """Keep the same pool, actual-cosine reranking and deterministic ties as MiniLM."""
        manifest = self.experiment(corpus_id)
        return self._vector_candidates(corpus_id, query, mpnet_index(corpus_id), 768,
            'embedding_768', 'mpnet_encoder_revision', manifest['encoder_revision'])
