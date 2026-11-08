"""Synthetic human-decision records test rules; these are never production approvals."""

import csv
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest
from pydantic import ValidationError

from research_assistant.contracts import Chunk, PaperManifestEntry, SourceSpanRef, fingerprint, text_sha
from research_assistant.extraction.contracts import ProposedClaim
from research_assistant.review.contracts import EntityDefinition, HumanDecision, ReviewRevision
from research_assistant.review.facts import alias_targets, projection
from research_assistant.review.store import (
    append_event, entities_for, import_decisions, propose_revision, read_events,
    export_decisions, import_csv, review_lock, state, validate_revision,
)


def fixture(tmp_path, name="p1", claim_id="claim1", text="This method improves retrieval in the reported setting."):
    source = Chunk(chunk_id="chunk_" + name, paper_id=name, source_sha256="a" * 64,
        source_url="https://example.invalid", page=1, section="Methods", page_start=0, page_end=len(text),
        text=text, text_sha256=text_sha(text), parser_version="fixture", chunker_version="fixture", mini_tokens=10, mpnet_tokens=10)
    paper = PaperManifestEntry(paper_id=name, title="Synthetic fixture " + name, source_url=source.source_url,
        source_sha256=source.source_sha256, local_path="unused.pdf", document_type="primary_study",
        rights="Synthetic test fixture", rights_url="https://example.invalid", selected_pages=[1], selection_reason="Test only")
    draft = ProposedClaim(kind="finding", statement=text, method="Method A", method_aliases=["MA"],
        dataset=None, dataset_aliases=[], conditions={"metric": None}, quotes=[text])
    mapping = fingerprint({"method": draft.method, "method_aliases": draft.method_aliases, "dataset": None, "dataset_aliases": []})
    revision = ReviewRevision(claim_id=claim_id, revision=1, paper=paper, draft=draft,
        support=[SourceSpanRef(paper_id=name, source_sha256=source.source_sha256, chunk_id=source.chunk_id,
            start=0, end=len(text), quote_sha256=text_sha(text))], validation_errors=[], entity_revision=mapping,
        entities=entities_for(name, draft, mapping), change_reason="Synthetic fixture only")
    tmp_path.mkdir(exist_ok=True)
    config = tmp_path / "config.json"
    if not config.exists():
        config.write_text(json.dumps({"corpus_id": "a" * 64}), encoding="utf-8")
    with review_lock(tmp_path):
        append_event(tmp_path, "revision", revision.model_dump(mode="json"))
    return revision, {source.chunk_id: source}


def human(revision, choice="approved", second=0):
    return HumanDecision(claim_id=revision.claim_id, claim_revision=revision.revision,
        revision_sha256=revision.sha256, source_sha256=revision.paper.source_sha256,
        entity_revision=revision.entity_revision, decision=choice, reviewer="SYNTHETIC TEST FIXTURE",
        reviewed_at=datetime(2026, 11, 8, 0, 0, second, tzinfo=timezone.utc), review_seconds=None,
        review_time_note="Synthetic test; not measured", reason="Synthetic rule verification",
        origin="human_csv", provenance_sha256="b" * 64)


def test_pending_is_not_approval_and_explicit_decisions_round_trip_idempotently(tmp_path):
    revision, chunks = fixture(tmp_path)
    assert projection(tmp_path, chunks)["facts"] == []
    import_decisions(tmp_path, [human(revision)], chunks)
    first = projection(tmp_path, chunks)
    assert len(first["facts"]) == 1
    assert first["facts"][0]["evidence"]["conditions"]["metric"] is None
    assert first["facts"][0]["evidence"]["conditions"]["method"] == "Method A"
    assert first["facts"][0]["evidence"]["conditions"]["dataset"] is None
    before = [p.read_bytes() for p in sorted((tmp_path / "events").glob("*.json"))]
    assert import_decisions(tmp_path, [human(revision)], chunks)["new_decisions"] == 0
    assert [p.read_bytes() for p in sorted((tmp_path / "events").glob("*.json"))] == before


def test_revocation_and_replaying_an_old_approval_never_resurrect_facts(tmp_path):
    revision, chunks = fixture(tmp_path)
    import_decisions(tmp_path, [human(revision)], chunks)
    import_decisions(tmp_path, [human(revision, "rejected", 1)], chunks)
    import_decisions(tmp_path, [human(revision)], chunks)
    assert projection(tmp_path, chunks)["facts"] == []
    assert projection(tmp_path, chunks)["statuses"][0]["status"] == "rejected"


@pytest.mark.parametrize("change", ["text", "support", "source", "alias"])
def test_changes_invalidate_old_approval_and_need_a_new_human_decision(tmp_path, change):
    revision, chunks = fixture(tmp_path)
    import_decisions(tmp_path, [human(revision)], chunks)
    revised = revision.model_copy(deep=True, update={"revision": 2, "predecessor_sha256": revision.sha256,
                                                    "change_reason": "Synthetic proposed edit"})
    if change == "text":
        revised.draft.statement = "A changed assertion needs a new human review."
    elif change == "support":
        revised.support[0].quote_sha256 = "f" * 64
    elif change == "source":
        revised.paper.source_sha256 = "f" * 64
    else:
        revised.entities[0].aliases.append("new alias")
    propose_revision(tmp_path, revised, chunks)
    assert projection(tmp_path, chunks)["facts"] == []
    with pytest.raises(ValueError, match="current displayed"):
        import_decisions(tmp_path, [human(revision, second=2)], chunks)


def test_alias_update_invalidates_every_claim_sharing_that_reviewed_entity(tmp_path):
    a, chunks = fixture(tmp_path)
    b, other = fixture(tmp_path, "p2", "claim2")
    b.entities = [a.entities[0]]
    # Use an explicit shared-entity revision, not an alias-name auto-merge.
    b2 = b.model_copy(deep=True, update={"revision": 2, "predecessor_sha256": state(tmp_path)["current"]["claim2"].sha256})
    propose_revision(tmp_path, b2, {**chunks, **other})
    import_decisions(tmp_path, [human(a), human(b2)], {**chunks, **other})
    assert len(projection(tmp_path, {**chunks, **other})["facts"]) == 2
    updated = a.entities[0].model_copy(deep=True)
    updated.aliases.append("ambiguous")
    with review_lock(tmp_path):
        append_event(tmp_path, "entity", updated.model_dump(mode="json"))
    assert projection(tmp_path, {**chunks, **other})["facts"] == []


def test_exact_quote_and_paper_ownership_are_enforced_even_after_schema_validation(tmp_path):
    revision, chunks = fixture(tmp_path)
    revision.draft.quotes = ["A different quotation with no exact source support."]
    assert validate_revision(revision, chunks, state(tmp_path)["entities"])
    revision, chunks = fixture(tmp_path / "other")
    wrong = next(iter(chunks.values())).model_copy(update={"paper_id": "foreign-paper"})
    assert validate_revision(revision, {wrong.chunk_id: wrong}, state(tmp_path / "other")["entities"])


def test_wrong_revision_and_invalid_candidate_approvals_leave_no_partial_decisions(tmp_path):
    a, chunks = fixture(tmp_path)
    b, other = fixture(tmp_path, "p2", "claim2")
    decision = human(b).model_copy(update={"revision_sha256": "wrong"})
    with pytest.raises(ValueError, match="current displayed"):
        import_decisions(tmp_path, [human(a), decision], {**chunks, **other})
    assert not state(tmp_path)["decisions"]


def test_named_entities_cannot_be_silently_omitted_or_mapped_to_an_unrelated_entity(tmp_path):
    revision, chunks = fixture(tmp_path)
    absent = revision.model_copy(deep=True, update={"entities": []})
    assert any("entity binding" in error for error in validate_revision(absent, chunks, {}))
    other = EntityDefinition(id="unrelated", kind="method", name="Different method", aliases=[])
    unrelated = revision.model_copy(deep=True, update={"entities": [other]})
    assert any("entity binding" in error for error in validate_revision(unrelated, chunks, {other.id: other}))


def test_ambiguous_aliases_and_conflicting_reported_findings_stay_separate(tmp_path):
    a, chunks = fixture(tmp_path)
    b, other = fixture(tmp_path, "p2", "claim2", "This method does not improve retrieval in the reported setting.")
    definitions = state(tmp_path)["entities"]
    assert len(alias_targets("ＭＡ", definitions)) == 2
    import_decisions(tmp_path, [human(a), human(b)], {**chunks, **other})
    facts = projection(tmp_path, {**chunks, **other})["facts"]
    assert len(facts) == 2 and len({f["paper_id"] for f in facts}) == 2
    assert len({f["id"] for f in facts}) == 2


def test_journal_tampering_and_missing_reviewer_are_rejected(tmp_path):
    revision, chunks = fixture(tmp_path)
    with pytest.raises(ValidationError):
        HumanDecision.model_validate({**human(revision).model_dump(), "reviewer": ""})
    file = next((tmp_path / "events").glob("*.json"))
    record = json.loads(file.read_text(encoding="utf-8"))
    record["payload"]["draft"]["statement"] = "tampered"
    file.write_text(json.dumps(record), encoding="utf-8")
    with pytest.raises(ValueError, match="journal"):
        read_events(tmp_path)


def test_csv_round_trip_imports_explicit_rows_only_and_checks_source_binding(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    root = tmp_path / "review"
    revision, chunks = fixture(root)
    source = next(iter(chunks.values()))
    member = tmp_path / "member"
    member.mkdir()
    (member / "chunks.jsonl").write_text(source.model_dump_json() + "\n", encoding="utf-8")
    (member / "snapshot.json").write_text(json.dumps({"chunks_sha256": fingerprint([source.model_dump()])}), encoding="utf-8")
    corpus = tmp_path / "data/processed" / ("a" * 64)
    corpus.mkdir(parents=True)
    (corpus / "members.json").write_text(json.dumps([{"chunk_path": str(member / "chunks.jsonl"),
                                                     "snapshot_path": str(member / "snapshot.json")}]), encoding="utf-8")
    template = export_decisions(root)["decision_template"]
    assert import_csv(root, Path(template))["new_decisions"] == 0
    with open(template, encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        rows, fields = list(reader), reader.fieldnames
    rows[0].update(reviewer="SYNTHETIC TEST FIXTURE", reviewed_at="2026-11-08T00:00:00+00:00",
                   review_seconds="3", review_time_note="Synthetic measured duration", decision="approved", reason="Test only")
    decision_file = tmp_path / "human-fixture.csv"
    def save():
        with decision_file.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)
    save()
    assert import_csv(root, decision_file)["new_decisions"] == 1
    assert len(projection(root, chunks)["facts"]) == 1
    rows[0]["source_sha256"] = "f" * 64
    save()
    before = state(root)["head"]
    with pytest.raises(ValueError, match="current displayed"):
        import_csv(root, decision_file)
    assert state(root)["head"] == before


def test_quote_backed_corrections_do_not_relax_source_validation_or_inherit_approval(monkeypatch, tmp_path):
    from research_assistant.review import revisions as corrections

    monkeypatch.chdir(tmp_path)
    root = tmp_path / "review"
    revision, chunks = fixture(root)
    import_decisions(root, [human(revision)], chunks)
    monkeypatch.setattr(corrections, "load_chunks", lambda directory: chunks)
    member = tmp_path / "member"
    member.mkdir()
    text = next(iter(chunks.values())).text
    (member / "pages.jsonl").write_text(json.dumps({"page": 1, "text": text}) + "\n", encoding="utf-8")
    corpus = tmp_path / "data/processed" / ("a" * 64)
    corpus.mkdir(parents=True)
    (corpus / "members.json").write_text(json.dumps([{"paper_id": revision.paper.paper_id,
        "snapshot_path": str(member / "snapshot.json")}]), encoding="utf-8")
    before = state(root)["head"]
    with pytest.raises(ValueError, match="exact substring"):
        corrections.revise_from_quotes(root, revision.claim_id, revision.draft, [(1, "A fabricated quote that is not present.")], revision.entities, "Test")
    assert state(root)["head"] == before
    corrections.revise_from_quotes(root, revision.claim_id, revision.draft, [(1, "method improves retrieval")], revision.entities, "Source-backed proposed correction")
    assert state(root)["current"][revision.claim_id].revision == 2
    assert projection(root, chunks)["facts"] == []


def test_chat_batch_records_actual_batch_time_once_and_never_approves_unseen_labels(monkeypatch, tmp_path):
    from research_assistant.review import batches

    revision, chunks = fixture(tmp_path)
    monkeypatch.setattr(batches, "load_chunks", lambda directory: chunks)
    batches.export_batch(tmp_path, [revision.claim_id], tmp_path / "batch")
    path = tmp_path / "batch/batch.json"
    choices = {"R1": {"decision": "needs_review", "reason": "Check the source context"}}
    before = state(tmp_path)["head"]
    with pytest.raises(ValueError, match="outside"):
        batches.record_chat_decisions(tmp_path, path, "bad.json", "SYNTHETIC TEST FIXTURE",
            "R2 approve", {"R2": {"decision": "approved", "reason": "Test"}}, None, "not measured")
    assert state(tmp_path)["head"] == before
    with pytest.raises(ValueError, match="finite"):
        batches.record_chat_decisions(tmp_path, path, "bad-time.json", "SYNTHETIC TEST FIXTURE",
            "R1 needs_review", choices, float("nan"), "invalid")
    result = batches.record_chat_decisions(tmp_path, path, "chat.json", "SYNTHETIC TEST FIXTURE",
        "R1 needs_review — check the source context", choices, 120, "2 minutes")
    assert result["new_decisions"] == 1
    decision = state(tmp_path)["decisions"][(revision.claim_id, 1)][0]
    assert decision.review_seconds is None and decision.origin == "human_chat"
    receipt = json.loads((tmp_path / "human-inputs/chat.json").read_text(encoding="utf-8"))
    assert receipt["actual_batch_review_seconds_approx"] == 120
    assert batches.record_chat_decisions(tmp_path, path, "chat.json", "SYNTHETIC TEST FIXTURE",
        "R1 needs_review — check the source context", choices, 120, "2 minutes")["new_decisions"] == 0
    assert projection(tmp_path, chunks)["facts"] == []
