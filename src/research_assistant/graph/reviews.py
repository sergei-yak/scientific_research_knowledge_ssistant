"""Atomic current-review projections, active-only indexes and fail-closed review-head reads."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from neo4j import Query

from research_assistant.contracts import EvidenceItem, fingerprint
from research_assistant.embeddings import Encoder
from research_assistant.graph.repository import GraphRepository, PROJECT, corpus_names
from research_assistant.pipeline import write_immutable
from research_assistant.review.contracts import EntityDefinition
from research_assistant.review.facts import projection
from research_assistant.review.store import load_chunks, review_lock, state
from research_assistant.settings import Settings


def fact_names(corpus_id: str) -> tuple[str, str, str]:
    """Trusted content hashes are the only dynamic schema identifiers."""
    corpus_names(corpus_id)
    suffix = corpus_id[:16]
    return "RAApproved_" + suffix, "ra_facts_vector_" + suffix, "ra_facts_text_" + suffix


class ReviewRepository(GraphRepository):
    """Preserve history while atomically replacing derived eligibility for one corpus."""

    def __init__(self, settings: Settings, project: str = PROJECT) -> None:
        super().__init__(settings)
        self.project = project

    def publish(self, corpus_id: str, review: dict, vectors: list[list[float]], encoder_revision: str) -> dict:
        """Validate first, then update claims, facts and review head in one transaction."""
        active_label, vector_index, text_index = fact_names(corpus_id)
        source_label, _ = corpus_names(corpus_id)
        facts = review["facts"]
        array = np.asarray(vectors)
        if facts and (array.shape != (len(facts), 384) or not np.isfinite(array).all()
                      or not np.allclose(np.linalg.norm(array, axis=1), 1, atol=1e-5)):
            raise ValueError("Invalid approved-fact vectors")
        if len(vectors) != len(facts):
            raise ValueError("Fact/vector count mismatch")
        for fact in facts:
            EvidenceItem.model_validate(fact["evidence"])
        with self.driver.session(database=self.database) as session:
            target = session.run("MATCH (c:Corpus {id:$id,project:$project,ready:true}) RETURN properties(c)['frozen'] AS frozen",
                                 id=corpus_id, project=self.project).single()
            if not target or target["frozen"]:
                raise ValueError("Review target is missing, unready or frozen")
            for label in ("ReviewedClaim", "FactText", "ReviewState", "Method", "Dataset"):
                session.run(f"CREATE CONSTRAINT ra_review_{label.lower()}_id IF NOT EXISTS FOR (n:{label}) REQUIRE n.id IS UNIQUE").consume()
            session.run(f"CREATE VECTOR INDEX `{vector_index}` IF NOT EXISTS FOR (f:`{active_label}`) ON (f.embedding_384) OPTIONS {{indexConfig: {{`vector.dimensions`:384, `vector.similarity_function`:'cosine'}}}}").consume()
            session.run(f"CREATE FULLTEXT INDEX `{text_index}` IF NOT EXISTS FOR (f:`{active_label}`) ON EACH [f.search_text]").consume()
            with session.begin_transaction(timeout=30) as tx:
                corpus = tx.run("MATCH (c:Corpus {id:$id,project:$project,ready:true}) RETURN properties(c)['frozen'] AS frozen",
                                id=corpus_id, project=self.project).single()
                if not corpus or corpus["frozen"]:
                    raise ValueError("Review target is missing, unready or frozen")
                previous = tx.run("MATCH (r:ReviewState {id:$id}) RETURN r.project AS project,r.head_sha256 AS head",
                                  id=corpus_id).single()
                if previous and (previous["project"] != self.project or previous["head"] not in review["ancestor_heads"]):
                    raise ValueError("Review history does not extend the preserved database head")
                # Every actual support node must remain in this corpus and its reporting paper.
                for fact in facts:
                    source = tx.run(
                        "MATCH (c:Corpus {id:$corpus,project:$project})-[:HAS_PAPER]->(p:Paper {id:$paper,project:$project}) "
                        "RETURN p.source_sha256 AS sha", corpus=corpus_id, project=self.project,
                        paper=fact["paper_id"]).single()
                    if not source or source["sha"] != fact["source_sha256"]:
                        raise ValueError("Approved fact's reporting paper/source is not current")
                    count = tx.run(f"MATCH (n:`{source_label}`) WHERE n.project=$project AND n.id IN $ids RETURN count(n) AS count",
                                   project=self.project, ids=fact["evidence"]["source_chunk_ids"]).single()["count"]
                    if count != len(fact["evidence"]["source_chunk_ids"]):
                        raise ValueError("Approved fact support is outside the selected corpus")
                tx.run(f"MATCH (f:FactText {{project:$project,corpus_id:$corpus}}) SET f.active=false REMOVE f:`{active_label}`",
                       project=self.project, corpus=corpus_id).consume()
                tx.run("MATCH (n:ReviewedClaim {project:$project,corpus_id:$corpus}) SET n.current=false,n.status='needs_review'",
                       project=self.project, corpus=corpus_id).consume()
                for status in review["statuses"]:
                    node_id = fingerprint([corpus_id, status["claim_id"], status["revision"]])
                    tx.run("MATCH (n:ReviewedClaim {id:$id,project:$project}) SET n.status=$status,n.current=true",
                           id=node_id, project=self.project, status=status["status"]).consume()
                for fact, vector in zip(facts, vectors):
                    node_id = fingerprint([corpus_id, fact["claim_id"], fact["claim_revision"]])
                    old = tx.run("MATCH (f:FactText {id:$id}) RETURN f.project AS project,f.corpus_id AS corpus,f.revision_sha256 AS revision",
                                 id=fact["id"]).single()
                    if old and (old["project"] != self.project or old["corpus"] != corpus_id or old["revision"] != fact["revision_sha256"]):
                        raise ValueError("Fact identity conflicts with preserved data")
                    old_claim = tx.run("MATCH (n:ReviewedClaim {id:$id}) RETURN n.project AS project",
                                       id=node_id).single()
                    if old_claim and old_claim["project"] != self.project:
                        raise ValueError("Claim identity belongs to another project")
                    label = "Evaluation" if fact["kind"] == "evaluation" else "Finding"
                    relationship = "REPORTS_EVALUATION" if fact["kind"] == "evaluation" else "REPORTS_FINDING"
                    tx.run(
                        f"MATCH (p:Paper {{id:$paper,project:$project}}) MERGE (n:ReviewedClaim {{id:$node}}) "
                        f"SET n:{label},n.project=$project,n.corpus_id=$corpus,n.claim_id=$claim,n.revision=$revision,"
                        "n.reporting_paper_id=$paper,n.source_sha256=$source,n.text=$text,n.entity_revision=$entity,"
                        "n.conditions_json=$conditions,n.metric=$metric,n.value=$value,n.unit=$unit,"
                        "n.dataset_version=$dataset_version,n.split=$split,n.protocol=$protocol,"
                        "n.status='approved',n.current=true "
                        f"MERGE (p)-[:{relationship}]->(n) "
                        "MERGE (f:FactText {id:$fact}) "
                        f"SET f:`{active_label}`,f.project=$project,f.corpus_id=$corpus,f.active=true,"
                        "f.claim_id=$claim,f.claim_revision=$revision,f.revision_sha256=$revision_sha,"
                        "f.approval_revision=$decision,f.rendered_text=$rendered,f.search_text=$rendered,"
                        "f.embedding_text=$embedding_text,f.embedding_384=$vector,f.encoder_revision=$encoder,"
                        "f.representation_version=$format,"
                        "f.evidence_json=$evidence MERGE (f)-[:REPRESENTS]->(n)",
                        paper=fact["paper_id"], project=self.project, node=node_id, corpus=corpus_id,
                        claim=fact["claim_id"], revision=fact["claim_revision"], source=fact["source_sha256"],
                        text=fact["claim_text"], entity=fact["entity_revision"], fact=fact["id"],
                        conditions=json.dumps(fact["evidence"]["conditions"], ensure_ascii=False),
                        metric=fact["evidence"]["conditions"].get("metric"), value=fact["evidence"]["conditions"].get("value"),
                        unit=fact["evidence"]["conditions"].get("unit"), dataset_version=fact["evidence"]["conditions"].get("dataset_version"),
                        split=fact["evidence"]["conditions"].get("split"), protocol=fact["evidence"]["conditions"].get("protocol"),
                        revision_sha=fact["revision_sha256"], decision=fact["decision_id"], rendered=fact["rendered_text"],
                        embedding_text=fact["embedding_text"], vector=vector, encoder=encoder_revision,
                        format=fact["representation_version"], evidence=json.dumps(fact["evidence"], ensure_ascii=False)).consume()
                    for excerpt in fact["evidence"]["excerpts"]:
                        tx.run("MATCH (n:ReviewedClaim {id:$node,project:$project}),(s:Chunk {id:$chunk,project:$project}) "
                               "MERGE (n)-[r:SUPPORTED_BY {start:$start,end:$end}]->(s) SET r.source_sha256=$sha",
                               node=node_id, project=self.project, chunk=excerpt["chunk_id"], start=excerpt["start"],
                               end=excerpt["end"], sha=excerpt["source_sha256"]).consume()
                    for raw in fact["entities"]:
                        entity = EntityDefinition.model_validate(raw)
                        entity_id = fingerprint(entity.model_dump())
                        entity_label = "Method" if entity.kind == "method" else "Dataset"
                        edge = ("OF_METHOD" if entity.kind == "method" else "ON_DATASET") if fact["kind"] == "evaluation" else ("ABOUT_METHOD" if entity.kind == "method" else "MENTIONS")
                        old_entity = tx.run(f"MATCH (e:{entity_label} {{id:$id}}) RETURN e.project AS project",
                                            id=entity_id).single()
                        if old_entity and old_entity["project"] != self.project:
                            raise ValueError("Entity identity belongs to another project")
                        tx.run(f"MATCH (n:ReviewedClaim {{id:$node,project:$project}}) MERGE (e:{entity_label} {{id:$id}}) "
                               "SET e.project=$project,e.entity_id=$logical,e.canonical_name=$name,e.aliases=$aliases,"
                               f"e.alias_revision=$alias_revision,n.{entity.kind}_id=$id MERGE (n)-[:{edge}]->(e)",
                               node=node_id, project=self.project, id=entity_id, logical=entity.id,
                               name=entity.name, aliases=entity.aliases, alias_revision=entity.revision).consume()
                tx.run("MERGE (r:ReviewState {id:$corpus}) SET r.project=$project,r.head_sha256=$head",
                       corpus=corpus_id, project=self.project, head=review["review_head"]).consume()
                tx.commit()
            for index in (vector_index, text_index):
                session.run("CALL db.awaitIndex($name,120)", name=index).consume()
        return {"corpus_id": corpus_id, "review_head": review["review_head"], "active_facts": len(facts),
                "vector_index": vector_index, "fulltext_index": text_index}

    def active_facts(self, corpus_id: str, expected_head: str) -> list[dict]:
        """All fact consumers must present the current journal head; stale projections fail."""
        label, _, _ = fact_names(corpus_id)
        with self.driver.session(database=self.database) as session:
            row = session.run("MATCH (r:ReviewState {id:$corpus,project:$project}) RETURN r.head_sha256 AS head",
                              corpus=corpus_id, project=self.project).single()
            if not row or row["head"] != expected_head:
                raise ValueError("Review projection is stale; synchronize before retrieving approved facts")
            records = session.run(Query(
                f"MATCH (f:`{label}` {{project:$project,corpus_id:$corpus,active:true}})-[:REPRESENTS]->"
                "(n:ReviewedClaim {project:$project,current:true,status:'approved'}) "
                "RETURN f.id AS id,f.evidence_json AS evidence ORDER BY f.id", timeout=30),
                project=self.project, corpus=corpus_id).data()
        return [{"id": row["id"], "evidence": EvidenceItem.model_validate_json(row["evidence"]).model_dump()} for row in records]


def synchronize_review(directory: Path, settings: Settings) -> dict:
    """Rebuild only current human-approved facts; no LLM calls, approvals or silent truncation."""
    with review_lock(directory):
        chunks = load_chunks(directory)
        review = projection(directory, chunks)
        config = json.loads((directory / "config.json").read_text(encoding="utf-8"))
        encoder = Encoder() if review["facts"] else None
        snapshot = json.loads((Path("data/processed") / config["corpus_id"] / "snapshot.json").read_text(encoding="utf-8"))
        if encoder and encoder.revision != snapshot["encoder_revision"]:
            raise ValueError("Fact encoder revision differs from the corpus encoder")
        vectors = encoder.encode([f["embedding_text"] for f in review["facts"]]) if encoder else []
        encoder_revision = encoder.revision if encoder else "none-no-facts"
        repository = ReviewRepository(settings)
        try:
            result = repository.publish(config["corpus_id"], review, vectors, encoder_revision)
            result["verified_active_facts"] = len(repository.active_facts(config["corpus_id"], review["review_head"]))
        finally:
            repository.close()
        write_immutable(directory / "projections" / (review["review_head"] + "-" + review["representation_version"] + ".json"),
                        json.dumps(review, ensure_ascii=False, indent=2) + "\n")
    return result
