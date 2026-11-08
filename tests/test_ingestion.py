"""Synthetic PDF and deterministic tokenizer-window coverage tests."""

import hashlib
import re

import pymupdf

from research_assistant.contracts import PaperManifestEntry
from research_assistant.ingestion.pdf import make_chunks, normalize_block, parse_pages


def manifest(path, pages):
    return PaperManifestEntry(paper_id="synthetic", title="Synthetic test PDF",
        source_url="https://example.invalid/paper", source_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        local_path=str(path), rights="Synthetic fixture authored by tests", rights_url="https://example.invalid",
        selected_pages=pages, selection_reason="Offline test")


class Tokenizer:
    def __init__(self, factor=1):
        self.factor = factor

    def encode(self, text, add_special_tokens=True):
        return [0] * (len(text.split()) * self.factor + (2 if add_special_tokens else 0))

    def __call__(self, text, **kwargs):
        return {"offset_mapping": [(m.start(), m.end()) for m in re.finditer(r"\S+", text)]}


class FakeEncoder:
    revision, mpnet_revision = "mini-fixture", "mpnet-fixture"
    mini_tokenizer, mpnet_tokenizer = Tokenizer(), Tokenizer(2)


def test_pdf_declared_pages_and_source_hash(tmp_path):
    path = tmp_path / "synthetic.pdf"
    doc = pymupdf.open()
    for text in ("1 Methods\nMethod X uses Dataset Y.", "2 Results\nDifferent page."):
        doc.new_page().insert_text((60, 70), text)
    doc.save(path)
    doc.close()
    entry = manifest(path, [1])
    pages = parse_pages(entry)
    assert len(pages) == 1 and "Dataset Y" in pages[0]["text"]
    assert "Different page" not in pages[0]["text"]
    path.write_bytes(path.read_bytes() + b"changed")
    import pytest
    with pytest.raises(ValueError, match="SHA-256"):
        parse_pages(entry)


def test_windows_are_stable_cover_source_and_fit_both_tokenizers(tmp_path):
    path = tmp_path / "placeholder"
    path.write_bytes(b"synthetic")
    entry = manifest(path, [1])
    text = " ".join(f"word{i}" for i in range(450))
    pages = [{"page": 1, "text": text, "blocks": [{"text": text, "section": "Methods"}]}]
    a = make_chunks(entry, pages, FakeEncoder())
    b = make_chunks(entry, pages, FakeEncoder())
    assert [c.model_dump() for c in a] == [c.model_dump() for c in b]
    assert all(c.mini_tokens <= 200 and c.mpnet_tokens <= 384 for c in a)
    assert set(text.split()) == set(" ".join(c.text for c in a).split())
    assert all(c.text == text[c.page_start:c.page_end] for c in a)
    encoder = FakeEncoder()
    encoder.mpnet_revision = "different-tokenizer-version"
    assert make_chunks(entry, pages, encoder)[0].chunk_id != a[0].chunk_id


def test_normalization_is_explicit_and_idempotent():
    normalized = normalize_block("ﬁnding\x02\n  on  page\t1")
    assert normalized == "finding on page 1"
    assert normalize_block(normalized) == normalized


def test_short_captions_and_headings_share_useful_neighboring_context(tmp_path):
    path = tmp_path / "placeholder"
    path.write_bytes(b"synthetic")
    entry = manifest(path, [1])
    blocks = [{"text": "Figure 1: A useful framework.", "section": "Previous section"},
              {"text": "2 Framework", "section": "2 Framework"},
              {"text": " ".join(f"detail{i}" for i in range(350)), "section": "2.1 Components"}]
    text = "\n\n".join(b["text"] for b in blocks)
    chunks = make_chunks(entry, [{"page": 1, "text": text, "blocks": blocks}], FakeEncoder())
    assert chunks[0].mini_tokens >= 160
    assert "Figure 1" in chunks[0].text and "detail0" in chunks[0].text
    assert "2.1 Components" in chunks[0].section
