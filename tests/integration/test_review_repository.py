"""Opt-in UUID-owned synthetic fixture; never records production human approvals."""

import json
import os
import uuid
from datetime import datetime, timezone

import pytest

from research_assistant.contracts import Chunk, PaperManifestEntry, SourceSpanRef, fingerprint, text_sha
from research_assistant.extraction.contracts import ProposedClaim
from research_assistant.graph.repository import PROJECT, corpus_names
from research_assistant.graph.reviews import ReviewRepository, fact_names
from research_assistant.review.contracts import EntityDefinition, HumanDecision, ReviewRevision
from research_assistant.review.facts import projection
from research_assistant.review.store import append_event, import_decisions, review_lock
from research_assistant.settings import Settings


@pytest.mark.integration
@pytest.mark.skipif(os.getenv("RUN_REVIEW_SMOKE") != "1", reason="Set RUN_REVIEW_SMOKE=1 for isolated Neo4j review checks")
def test_live_review_projection_revocation_and_search_indexes(tmp_path):
    token = uuid.uuid4().hex
    project = PROJECT + "-fixture-" + token
    corpus = fingerprint(["review-fixture", token])
    label, _ = corpus_names(corpus)
    active_label, vector_index, text_index = fact_names(corpus)
    repo = ReviewRepository(Settings.from_env(), project=project)
    (tmp_path / "config.json").write_text(json.dumps({"corpus_id": corpus}), encoding="utf-8")
    entity = EntityDefinition(id="method-fixture-" + token, kind="method", name="Synthetic method", aliases=["SM"])
    dataset = EntityDefinition(id="dataset-fixture-" + token, kind="dataset", name="Synthetic dataset", aliases=[])
    chunks, revisions = {}, []
    try:
        with repo.driver.session(database=repo.database) as session:
            session.run("CREATE (c:Corpus {id:$id,project:$project,ready:true,frozen:false})",
                        id=corpus, project=project).consume()
            for number, assertion in enumerate(("This synthetic method improves retrieval in setting A.",
                                                 "This synthetic method does not improve retrieval in setting B.")):
                paper_id, chunk_id = f"fixture-paper-{token}-{number}", f"fixture-chunk-{token}-{number}"
                source = Chunk(chunk_id=chunk_id, paper_id=paper_id, source_sha256="a" * 64,
                    source_url="https://example.invalid/synthetic", page=1, section="Synthetic test",
                    page_start=0, page_end=len(assertion), text=assertion, text_sha256=text_sha(assertion),
                    parser_version="fixture", chunker_version="fixture", mini_tokens=20, mpnet_tokens=20)
                chunks[chunk_id] = source
                paper = PaperManifestEntry(paper_id=paper_id, title="SYNTHETIC FIXTURE ONLY", source_url=source.source_url,
                    source_sha256=source.source_sha256, local_path="unused.pdf", rights="Synthetic",
                    rights_url=source.source_url, document_type="primary_study", selected_pages=[1], selection_reason="Fixture")
                draft = ProposedClaim(kind="evaluation", statement=assertion, method=entity.name,
                    method_aliases=entity.aliases, dataset=dataset.name, dataset_aliases=[], conditions={"protocol": f"setting {number}"}, quotes=[assertion])
                revision = ReviewRevision(claim_id=f"fixture-claim-{token}-{number}", revision=1, paper=paper,
                    draft=draft, support=[SourceSpanRef(paper_id=paper_id, source_sha256=source.source_sha256,
                        chunk_id=chunk_id, start=0, end=len(assertion), quote_sha256=text_sha(assertion))],
                    validation_errors=[], entity_revision=fingerprint([entity.revision, dataset.revision]), entities=[entity, dataset], change_reason="Synthetic fixture, no human")
                revisions.append(revision)
                with review_lock(tmp_path):
                    append_event(tmp_path, "revision", revision.model_dump(mode="json"))
                session.run(f"MATCH (c:Corpus {{id:$corpus,project:$project}}) CREATE (p:Paper {{id:$paper,project:$project,source_sha256:$sha}}),"
                            f"(n:Chunk:`{label}` {{id:$chunk,project:$project,source_json:$source}}),"
                            "(c)-[:HAS_PAPER]->(p),(p)-[:HAS_CHUNK]->(n)",
                            corpus=corpus, project=project, paper=paper_id, sha=source.source_sha256,
                            chunk=chunk_id, source=source.model_dump_json()).consume()
        decisions = [HumanDecision(claim_id=r.claim_id, claim_revision=1, revision_sha256=r.sha256,
            source_sha256=r.paper.source_sha256, entity_revision=r.entity_revision, reviewer="SYNTHETIC TEST FIXTURE",
            reviewed_at=datetime(2026, 11, 8, tzinfo=timezone.utc), review_seconds=None,
            review_time_note="Synthetic; not measured", reason="Synthetic test only", decision="approved",
            origin="human_csv", provenance_sha256="b" * 64) for r in revisions]
        import_decisions(tmp_path, decisions, chunks)
        first = projection(tmp_path, chunks)
        vectors = [[1.0] + [0.0] * 383 for _ in first["facts"]]
        repo.publish(corpus, first, vectors, "fixture-encoder")
        repo.publish(corpus, first, vectors, "fixture-encoder")
        assert len(repo.active_facts(corpus, first["review_head"])) == 2
        revoked = decisions[0].model_copy(update={"decision": "needs_review", "reviewed_at": datetime(2026, 11, 8, 0, 1, tzinfo=timezone.utc)})
        import_decisions(tmp_path, [revoked], chunks)
        second = projection(tmp_path, chunks)
        with pytest.raises(ValueError, match="stale"):
            repo.active_facts(corpus, second["review_head"])
        repo.publish(corpus, second, [[1.0] + [0.0] * 383], "fixture-encoder")
        assert len(repo.active_facts(corpus, second["review_head"])) == 1
        with pytest.raises(ValueError, match="preserved database head"):
            repo.publish(corpus, first, vectors, "fixture-encoder")
        with repo.driver.session(database=repo.database) as session:
            history = session.run("MATCH (f:FactText {project:$project}) RETURN count(f) AS count", project=project).single()["count"]
            assert history == 2
            vector_count = session.run("CALL db.index.vector.queryNodes($index,12,$vector) YIELD node RETURN count(node) AS count",
                                      index=vector_index, vector=vectors[0]).single()["count"]
            text_count = session.run("CALL db.index.fulltext.queryNodes($index,'retrieval') YIELD node RETURN count(node) AS count",
                                    index=text_index).single()["count"]
            assert vector_count == text_count == 1
            wrong_owner = session.run("MATCH (p:Paper {project:$project})-[:REPORTS_EVALUATION]->(n) "
                                      "WHERE p.id<>n.reporting_paper_id RETURN count(n) AS count", project=project).single()["count"]
            assert wrong_owner == 0
            rows = session.run("MATCH (n:Evaluation {project:$project})-[:OF_METHOD]->(m:Method),"
                               "(n)-[:ON_DATASET]->(d:Dataset) RETURN n.method_id=m.id AS method_ok,"
                               "n.dataset_id=d.id AS dataset_ok,n.protocol AS protocol,n.value AS value",project=project).data()
            assert len(rows) == 2 and all(row["method_ok"] and row["dataset_ok"] and row["value"] is None for row in rows)
            assert {row["protocol"] for row in rows} == {"setting 0", "setting 1"}
        changed = entity.model_copy(deep=True)
        changed.aliases.append("changed alias")
        with review_lock(tmp_path):
            append_event(tmp_path, "entity", changed.model_dump(mode="json"))
        after_alias = projection(tmp_path, chunks)
        assert not after_alias["facts"]
        repo.publish(corpus, after_alias, [], "fixture-encoder")
        assert repo.active_facts(corpus, after_alias["review_head"]) == []
        with repo.driver.session(database=repo.database) as session:
            assert session.run(f"MATCH (n:`{active_label}`) RETURN count(n) AS count").single()["count"] == 0
            session.run("MATCH (c:Corpus {id:$id,project:$project}) SET c.frozen=true", id=corpus, project=project).consume()
            with pytest.raises(ValueError, match="frozen"):
                repo.publish(corpus, after_alias, [], "fixture-encoder")
    finally:
        # Only resources created by this exact UUID-owned fixture are cleaned up.
        assert project == PROJECT + "-fixture-" + token and len(token) == 32
        with repo.driver.session(database=repo.database) as session:
            count = session.run("MATCH (n {project:$project}) RETURN count(n) AS count", project=project).single()["count"]
            assert count < 40
            for index in (vector_index, text_index):
                session.run(f"DROP INDEX `{index}` IF EXISTS").consume()
            session.run("MATCH (n {project:$project}) DETACH DELETE n", project=project).consume()
        repo.close()
