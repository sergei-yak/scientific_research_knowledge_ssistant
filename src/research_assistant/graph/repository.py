"""Idempotent source ingestion and snapshot-scoped MiniLM vector retrieval."""

from __future__ import annotations

import json
import re

import numpy as np
from neo4j import GraphDatabase, Query

from research_assistant.contracts import Chunk, PaperManifestEntry
from research_assistant.settings import Settings

PROJECT = "dbu-research-assistant"


def corpus_names(corpus_id: str) -> tuple[str, str]:
    """Only content hashes can form owned schema identifiers; never user/LLM Cypher."""
    if not re.fullmatch(r"[a-f0-9]{64}", corpus_id):
        raise ValueError("Invalid corpus identity")
    return "RACorpus_" + corpus_id[:16], "ra_mini_" + corpus_id[:16]


class GraphRepository:
    """Use project-owned records and preserve unrelated data/schema."""

    def __init__(self, settings: Settings) -> None:
        self.driver = GraphDatabase.driver(
            settings.neo4j_uri,
            auth=(settings.neo4j_user, settings.neo4j_password.get_secret_value()),
            connection_timeout=10, max_transaction_retry_time=0,
        )
        self.database = settings.neo4j_database

    def close(self) -> None:
        """Release connections deterministically."""
        self.driver.close()

    def ingest(self, snapshot: dict, manifest: PaperManifestEntry,
               chunks: list[Chunk], vectors: list[list[float]]) -> dict:
        """MERGE immutable source records; mark a snapshot ready only after indexing."""
        label, index = corpus_names(snapshot["corpus_id"])
        array = np.asarray(vectors)
        if (array.shape != (len(chunks), 384) or not np.isfinite(array).all()
                or not np.allclose(np.linalg.norm(array, axis=1), 1, atol=1e-5)):
            raise ValueError("Invalid ingestion vector dimensions/values")
        if any(chunk.paper_id != manifest.paper_id or chunk.source_sha256 != manifest.source_sha256 for chunk in chunks):
            raise ValueError("Chunk belongs to a different paper/source")
        with self.driver.session(database=self.database) as session:
            for kind in ("Paper", "Chunk", "Corpus"):
                session.run(f"CREATE CONSTRAINT ra_{kind.lower()}_id IF NOT EXISTS FOR (n:{kind}) REQUIRE n.id IS UNIQUE").consume()
            existing_corpus = session.run("MATCH (c:Corpus {id:$id}) RETURN c.project AS project,properties(c)['frozen'] AS frozen",
                                          id=snapshot["corpus_id"]).single()
            if existing_corpus and (existing_corpus["project"] != PROJECT or existing_corpus["frozen"]):
                raise ValueError("Corpus is frozen or belongs to another owner")
            existing = session.run(
                "MATCH (p:Paper {id:$id}) RETURN p.source_sha256 AS sha, p.project AS project",
                id=manifest.paper_id,
            ).single()
            if existing and (existing["sha"] != manifest.source_sha256 or existing["project"] != PROJECT):
                raise ValueError("Existing paper identity belongs to a different source/owner")
            session.run(
                "MERGE (c:Corpus {id:$id}) ON CREATE SET c.frozen=false "
                "SET c.project=$project, c.ready=false, c.snapshot_json=$snapshot "
                "MERGE (p:Paper {id:$paper}) SET p.project=$project, p.source_sha256=$sha, p.title=$title, "
                "p.source_url=$url, p.document_type=$kind MERGE (c)-[:HAS_PAPER]->(p)",
                id=snapshot["corpus_id"], project=PROJECT, snapshot=json.dumps(snapshot),
                paper=manifest.paper_id, sha=manifest.source_sha256, title=manifest.title,
                url=manifest.source_url, kind=manifest.document_type,
            ).consume()
            for offset in range(0, len(chunks), 64):
                rows = [{"id": chunk.chunk_id, "text": chunk.text,
                         "source_json": chunk.model_dump_json(), "embedding": vector}
                        for chunk, vector in zip(chunks[offset:offset + 64], vectors[offset:offset + 64])]
                conflict = session.run(
                    "UNWIND $rows AS row MATCH (n:Chunk {id:row.id}) "
                    "WHERE coalesce(n.project,'') <> $project OR coalesce(n.source_json,'') <> row.source_json "
                    "OR coalesce(n.encoder_revision,'') <> $revision RETURN n.id AS id LIMIT 1",
                    rows=rows, project=PROJECT, revision=snapshot["encoder_revision"],
                ).single()
                if conflict:
                    raise ValueError("Existing chunk identity conflicts with immutable source/model")
                session.run(Query(
                    f"UNWIND $rows AS row MATCH (p:Paper {{id:$paper}}) "
                    f"MERGE (n:Chunk {{id:row.id}}) SET n:`{label}`, n.project=$project, "
                    "n.text=row.text, n.source_json=row.source_json, n.embedding_384=row.embedding, "
                    "n.encoder_revision=$revision MERGE (p)-[:HAS_CHUNK]->(n)", timeout=30),
                    rows=rows, paper=manifest.paper_id, project=PROJECT,
                    revision=snapshot["encoder_revision"],
                ).consume()
            session.run(Query(
                f"CREATE VECTOR INDEX `{index}` IF NOT EXISTS FOR (n:`{label}`) ON (n.embedding_384) "
                "OPTIONS {indexConfig: {`vector.dimensions`:384, `vector.similarity_function`:'cosine'}}",
                timeout=30,
            )).consume()
            session.run("CALL db.awaitIndex($name,120)", name=index).consume()
            count = session.run(f"MATCH (n:`{label}`) RETURN count(n) AS count").single()["count"]
            if count != len(chunks):
                raise ValueError("Snapshot chunk count mismatch; snapshot remains unready")
            session.run("MATCH (c:Corpus {id:$id,project:$project}) SET c.ready=true",
                        id=snapshot["corpus_id"], project=PROJECT).consume()
        return {"corpus_id": snapshot["corpus_id"], "chunks": count, "index": index, "ready": True}

    def combine(self, snapshot: dict, chunk_ids: list[str]) -> dict:
        """Index an explicit union of owned chunks; preserve member snapshots and metadata."""
        label, index = corpus_names(snapshot["corpus_id"])
        paper_ids = [p["paper_id"] for p in snapshot["papers"]]
        if len(set(chunk_ids)) != len(chunk_ids) or len(chunk_ids) != snapshot["chunk_count"]:
            raise ValueError("Combined chunk identities/count mismatch")
        if any(edge["citing"] not in paper_ids or edge["cited"] not in paper_ids
               for edge in snapshot["metadata"]["citation_edges"]):
            raise ValueError("Citation endpoint outside selected corpus")
        with self.driver.session(database=self.database) as session:
            existing = session.run(
                "MATCH (c:Corpus {id:$id}) RETURN c.project AS project,c.snapshot_json AS snapshot,properties(c)['frozen'] AS frozen",
                id=snapshot["corpus_id"]).single()
            encoded = json.dumps(snapshot)
            if existing and (existing["project"] != PROJECT or existing["frozen"] or existing["snapshot"] != encoded):
                raise ValueError("Combined snapshot conflicts with an existing/frozen corpus")
            valid = session.run(Query(
                "UNWIND $ids AS id MATCH (n:Chunk {id:id,project:$project}) "
                "WHERE n.encoder_revision=$revision RETURN count(n) AS count", timeout=30),
                ids=chunk_ids, project=PROJECT, revision=snapshot["encoder_revision"]).single()["count"]
            if valid != len(chunk_ids):
                raise ValueError("Combined snapshot references missing/incompatible chunks")
            session.run(
                "MERGE (c:Corpus {id:$id}) ON CREATE SET c.frozen=false "
                "SET c.project=$project,c.ready=false,c.snapshot_json=$snapshot",
                id=snapshot["corpus_id"], project=PROJECT, snapshot=encoded).consume()
            for offset in range(0, len(chunk_ids), 128):
                session.run(Query(f"UNWIND $ids AS id MATCH (n:Chunk {{id:id,project:$project}}) SET n:`{label}`",
                                  timeout=30), ids=chunk_ids[offset:offset+128], project=PROJECT).consume()
            for paper in snapshot["metadata"]["papers"]:
                session.run(
                    "MATCH (c:Corpus {id:$id,project:$project}),(p:Paper {id:$paper,project:$project}) "
                    "MERGE (c)-[r:HAS_PAPER]->(p) SET r.metadata_json=$metadata",
                    id=snapshot["corpus_id"], project=PROJECT, paper=paper["paper_id"], metadata=json.dumps(paper)).consume()
            for edge in snapshot["metadata"]["citation_edges"]:
                session.run(
                    "MATCH (a:Paper {id:$a,project:$project}),(b:Paper {id:$b,project:$project}) "
                    "MERGE (a)-[r:CITES {corpus_id:$corpus}]->(b) "
                    "SET r.source='openalex',r.version_scope='work_level_not_pdf_version'",
                    a=edge["citing"], b=edge["cited"], project=PROJECT, corpus=snapshot["corpus_id"]).consume()
            session.run(Query(
                f"CREATE VECTOR INDEX `{index}` IF NOT EXISTS FOR (n:`{label}`) ON (n.embedding_384) "
                "OPTIONS {indexConfig: {`vector.dimensions`:384, `vector.similarity_function`:'cosine'}}",
                timeout=30)).consume()
            session.run("CALL db.awaitIndex($name,120)", name=index).consume()
            count = session.run(f"MATCH (n:`{label}`) RETURN count(n) AS count").single()["count"]
            if count != len(chunk_ids):
                raise ValueError("Combined chunk count mismatch; snapshot remains unready")
            session.run("MATCH (c:Corpus {id:$id,project:$project}) SET c.ready=true",
                        id=snapshot["corpus_id"], project=PROJECT).consume()
        return {"corpus_id": snapshot["corpus_id"], "chunks": count, "index": index, "ready": True}

    def snapshot(self, corpus_id: str) -> dict:
        """Read an explicitly chosen ready corpus without searching local files."""
        corpus_names(corpus_id)
        with self.driver.session(database=self.database) as session:
            row = session.run("MATCH (c:Corpus {id:$id,project:$project,ready:true}) RETURN c.snapshot_json AS snapshot",
                              id=corpus_id, project=PROJECT).single()
            if row is None:
                raise ValueError("Corpus does not exist or ingestion is not ready")
            return json.loads(row["snapshot"])

    def vector_candidates(self, corpus_id: str, query: list[float]) -> list[tuple[Chunk, float]]:
        """Retrieve a bounded ANN pool, then order by actual cosine and stable ID."""
        _, index = corpus_names(corpus_id)
        snapshot = self.snapshot(corpus_id)
        q = np.asarray(query, dtype=float)
        if q.shape != (384,) or not np.isfinite(q).all() or np.linalg.norm(q) == 0:
            raise ValueError("Query vector is invalid")
        with self.driver.session(database=self.database) as session:
            records = session.run(Query(
                "CALL db.index.vector.queryNodes($index,24,$vector) YIELD node,score "
                "WHERE node.project=$project RETURN node.source_json AS source,node.embedding_384 AS embedding, "
                "node.encoder_revision AS revision",
                timeout=30), index=index, vector=query, project=PROJECT).data()
        candidates = []
        for row in records:
            vector = np.asarray(row["embedding"], dtype=float)
            if (vector.shape != (384,) or not np.isfinite(vector).all()
                    or np.linalg.norm(vector) == 0 or row["revision"] != snapshot["encoder_revision"]):
                raise ValueError("Indexed vector is invalid or uses a different encoder")
            score = float(np.dot(q, vector) / (np.linalg.norm(q) * np.linalg.norm(vector)))
            candidates.append((Chunk.model_validate_json(row["source"]), max(-1.0, min(1.0, score))))
        return sorted(candidates, key=lambda pair: (-pair[1], pair[0].chunk_id))[:12]
