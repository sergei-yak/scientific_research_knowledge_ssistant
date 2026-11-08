"""Adversarial source/review/budget fixtures; no model or service calls."""

import csv
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from research_assistant.contracts import Chunk, fingerprint, text_sha
from research_assistant.extraction import pilot
from research_assistant.extraction.contracts import ExtractionPlan, ExtractionResponse, PassageSelector, ProposedClaim
from research_assistant.ingestion.metadata import select_match
from research_assistant.graph.repository import GraphRepository
from research_assistant.review.audit import audit_packets


def chunk(text, identity, base=0, paper="p1"):
    return Chunk(chunk_id=identity, paper_id=paper, source_sha256="a" * 64,
                 source_url="https://example.invalid/paper", page=1, section="Methods",
                 page_start=base, page_end=base + len(text), text=text, text_sha256=text_sha(text),
                 parser_version="fixture", chunker_version="fixture", mini_tokens=10, mpnet_tokens=10)


def draft(kind="finding", quote="Our method uses a graph index."):
    return ProposedClaim(kind=kind, statement="The authors describe graph-based retrieval.",
                         method="Method A", method_aliases=["MA"], dataset="Dataset X",
                         dataset_aliases=[], conditions={"split": None}, quotes=[quote])


def test_exact_quotes_can_span_overlapping_windows_but_not_gaps_or_other_papers():
    text = "Our method uses a graph index."
    passage = {"paper_id": "p1", "page": 1, "start": 0, "text": text}
    sources = [chunk(text[:18], "c1"), chunk(text[12:], "c2", 12)]
    spans = pilot.map_quote(text, passage, sources)
    assert len(spans) == 2
    assert sum(span.end - span.start for span in spans) == len(text)
    with pytest.raises(ValueError, match="exact substring"):
        pilot.map_quote("Our method uses an invented index.", passage, sources)
    with pytest.raises(ValueError, match="gap"):
        pilot.map_quote(text, passage, [chunk(text, "wrong-owner", paper="p2")])
    with pytest.raises(ValueError, match="gap"):
        pilot.map_quote(text, passage, [sources[0]])


def test_survey_evaluation_ownership_is_rejected_and_validation_never_approves():
    text = "Our method uses a graph index."
    paper = {"paper_id": "p1", "source_sha256": "a" * 64, "document_type": "survey"}
    passage = {"id": "passage", "paper_id": "p1", "page": 1, "start": 0, "text": text}
    row = pilot.validate_candidate(draft("evaluation"), paper, passage, [chunk(text, "c1")])
    assert row["validation_errors"] and row["claim"]["status"] == "candidate"
    finding = pilot.validate_candidate(draft(), paper, passage, [chunk(text, "c1")])
    assert finding["claim"]["status"] == "validated"
    assert finding["human_review_status"] == "pending"
    assert finding["entity_mapping_status"] == "proposed_unreviewed"
    assert finding["draft"]["method_aliases"] == ["MA"]
    contaminated = pilot.validate_candidate(draft(), {**paper, "paper_id": "other-paper"}, passage, [chunk(text, "c1")])
    assert contaminated["validation_status"] == "candidate"
    assert any("different" in error for error in contaminated["validation_errors"])


def test_passage_selection_is_exact_and_limits_are_validated_before_calls():
    text = "A method description with adequate context. " * 8
    pages = [{"page": 1, "text": text, "blocks": [{"text": text, "section": "Methods"}]}]
    selector = PassageSelector(page=1, anchor="method description", max_blocks=1, purpose="Method")
    passage = pilot.make_passage("p1", pages, selector, 120, counter=len)
    assert passage["text"] == text[passage["start"]:passage["end"]]
    assert len(passage["text"]) <= 120
    with pytest.raises(ValueError, match="outside"):
        pilot.make_passage("p1", pages, selector.model_copy(update={"page": 2}), 120, counter=len)
    with pytest.raises(ValidationError):
        ExtractionPlan(max_candidates_per_paper=13, selections={"p1": [selector]})
    with pytest.raises(ValidationError):
        ExtractionPlan(selections={"p1": [selector] * 9})


def test_interrupted_requests_reserve_unknown_candidates_across_amendments():
    plan = ExtractionPlan(max_requests_per_paper=8, selections={})
    previous = [{"generated": 2, "unknown_candidate_upper_bound": 0} for _ in range(5)]
    previous.append({"generated": 0, "unknown_candidate_upper_bound": 2})
    assert pilot.remaining_budget(previous, plan) == (2, 0)


def test_unknown_started_request_is_never_treated_as_unused_budget(tmp_path):
    path = tmp_path / "request-01.started.json"
    path.write_text(json.dumps({"allowance": 2, "messages": [{"content": json.dumps({"passage": {"id": "p"}})}]}), encoding="utf-8")
    attempts = pilot.read_attempts(tmp_path)
    assert attempts[0]["status"] == "pending_unknown_outcome"
    assert attempts[0]["unknown_candidate_upper_bound"] == 2


def test_openalex_does_not_accept_first_unrelated_or_ambiguous_search_hit():
    paper = SimpleNamespace(arxiv_id="1234.56789v1", title="A Specific Paper")
    wrong = {"id": "W1", "title": "A Different Paper", "doi": None}
    right = {"id": "W2", "title": "A Specific Paper", "doi": None}
    assert select_match(paper, {"results": [wrong, right]}) == right
    assert select_match(paper, {"results": [right, {**right, "id": "W3"}]}) is None
    assert select_match(paper, {"results": [wrong]}) is None


def test_ingestion_rejects_wrong_paper_sources_before_database_access():
    repository = object.__new__(GraphRepository)
    paper = SimpleNamespace(paper_id="owner", source_sha256="a" * 64)
    source = SimpleNamespace(paper_id="other-paper", source_sha256="a" * 64)
    with pytest.raises(ValueError, match="different paper/source"):
        repository.ingest({"corpus_id": "a" * 64}, paper, [source], [[1.0] + [0.0] * 383])


@pytest.mark.parametrize("duplicate", [False, True])
def test_combined_corpus_rejects_invalid_membership_before_database_access(duplicate):
    repository = object.__new__(GraphRepository)
    ids = ["c1", "c1"] if duplicate else ["c1"]
    edges = [] if duplicate else [{"citing": "outsider", "cited": "owner"}]
    snapshot = {"corpus_id": "a" * 64, "papers": [{"paper_id": "owner"}],
                "chunk_count": len(ids), "metadata": {"citation_edges": edges}}
    with pytest.raises(ValueError, match="mismatch|outside"):
        repository.combine(snapshot, ids)


def test_export_resume_reuses_all_calls_and_leaves_decisions_blank(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(pilot, "estimate_tokens", len)
    identity = "a" * 64
    root = Path("data/processed") / identity
    root.mkdir(parents=True)
    papers, members, selections = [], [], {}
    for i in range(5):
        paper_id = f"p{i}"
        text = "Our method uses a graph index. " + "A longer description gives useful source context. " * 3
        source = chunk(text, "chunk" + str(i), paper=paper_id)
        directory = tmp_path / ("member" + str(i))
        directory.mkdir()
        (directory / "snapshot.json").write_text(json.dumps({"chunks_sha256": fingerprint([source.model_dump()])}), encoding="utf-8")
        (directory / "chunks.jsonl").write_text(source.model_dump_json() + "\n", encoding="utf-8")
        (directory / "pages.jsonl").write_text(json.dumps({"page": 1, "text": text,
            "blocks": [{"text": text, "section": "Methods"}]}) + "\n", encoding="utf-8")
        papers.append({"paper_id": paper_id, "title": paper_id, "document_type": "primary_study",
                       "source_sha256": "a" * 64, "source_url": "https://example.invalid", "selected_pages": [1]})
        members.append({"paper_id": paper_id, "chunk_path": str(directory / "chunks.jsonl"), "snapshot_path": str(directory / "snapshot.json")})
        selections[paper_id] = [PassageSelector(page=1, anchor="Our method", purpose="Method")]
    (root / "snapshot.json").write_text(json.dumps({"papers": papers}), encoding="utf-8")
    (root / "members.json").write_text(json.dumps(members), encoding="utf-8")
    plan = ExtractionPlan(max_requests_per_paper=1, selections=selections)
    plan_path = tmp_path / "plan.json"
    plan_path.write_text(plan.model_dump_json(), encoding="utf-8")

    class FakeClient:
        calls = 0
        model, digest, last_result = "local-fixture", "fixed", None

        def __init__(self, *args, **kwargs):
            assert kwargs["purpose"] == "extraction"

        def generate_structured(self, schema, messages):
            FakeClient.calls += 1
            return ExtractionResponse(candidates=[draft()]), SimpleNamespace(model_dump=lambda **kwargs: {"fixture": True})

    monkeypatch.setattr(pilot, "OllamaClient", FakeClient)
    first = pilot.extract_pilot(identity, plan_path, tmp_path / "first", SimpleNamespace())
    assert FakeClient.calls == 5 and first["approved"] == 0
    journals = {p: p.read_bytes() for p in Path("data/extraction").rglob("*.json")}
    second = pilot.extract_pilot(identity, plan_path, tmp_path / "second", SimpleNamespace())
    assert FakeClient.calls == 5 and len(second["papers"]) == 5
    assert all(p.read_bytes() == content for p, content in journals.items())
    rows = list(csv.DictReader((tmp_path / "second/p0/decisions.csv").open(encoding="utf-8")))
    assert len(rows) == 1 and rows[0]["decision"] == "" and rows[0]["reviewer"] == ""
    assert second["papers"][0]["approved"] == second["papers"][0]["human_review_seconds"] == 0
    assert audit_packets(tmp_path / "second")["status"] == "passed"
    # A metadata-only corpus revision does not buy a fresh extraction allowance.
    revised = Path("data/processed") / ("b" * 64)
    revised.mkdir()
    for name in ("snapshot.json", "members.json"):
        (revised / name).write_bytes((root / name).read_bytes())
    plan.amendment_decision = "D-fixture"
    plan_path.write_text(plan.model_dump_json(), encoding="utf-8")
    pilot.extract_pilot("b" * 64, plan_path, tmp_path / "revised", SimpleNamespace())
    assert FakeClient.calls == 5
    path = tmp_path / "second/p0/bundle.json"
    corrupt = json.loads(path.read_text(encoding="utf-8"))
    original = path.read_bytes()
    corrupt["stats"]["requests_reserved"] = 0
    path.write_text(json.dumps(corrupt), encoding="utf-8")
    with pytest.raises(ValueError, match="accounting mismatch"):
        audit_packets(tmp_path / "second")
    path.write_bytes(original)
    corrupt = json.loads(path.read_text(encoding="utf-8"))
    corrupt["candidates"][0]["draft"]["quotes"] = ["This quote was never in the source."]
    path.write_text(json.dumps(corrupt), encoding="utf-8")
    with pytest.raises(ValueError, match="mismatch"):
        audit_packets(tmp_path / "second")
