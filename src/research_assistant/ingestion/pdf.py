"""Page-aware normalized text and tokenizer-safe deterministic windows."""

from __future__ import annotations

import hashlib
from bisect import bisect_left
import re
import unicodedata
from pathlib import Path

import pymupdf

from research_assistant.contracts import Chunk, PaperManifestEntry, fingerprint, text_sha

PARSER_VERSION = "pymupdf-1.25.5-sorted-blocks-nfkc-v1"
CHUNKER_VERSION = "dual-tokenizer-soft-sections-200-overlap40-v2"


def normalize_block(text: str) -> str:
    """Freeze Unicode/control/whitespace normalization for exact future source offsets."""
    text = unicodedata.normalize("NFKC", text).replace("\u00ad", "")
    text = "".join(c for c in text if not unicodedata.category(c).startswith("C") or c.isspace())
    return re.sub(r"\s+", " ", text).strip()


def parse_pages(manifest: PaperManifestEntry, *, skip_empty: bool = False,
                max_page_characters: int | None = None,
                max_total_characters: int | None = None) -> list[dict]:
    """Parse only declared pages, preserving normalized paragraph/section locations."""
    path = Path(manifest.local_path)
    if hashlib.sha256(path.read_bytes()).hexdigest() != manifest.source_sha256:
        raise ValueError("PDF SHA-256 differs from the manifest")
    pages, section, characters = [], "Front matter", 0
    with pymupdf.open(path) as document:
        if manifest.selected_pages != sorted(set(manifest.selected_pages)):
            raise ValueError("Selected pages must be sorted and unique")
        for number in manifest.selected_pages:
            if not 1 <= number <= len(document):
                raise ValueError("Selected page is outside the PDF")
            page = document[number - 1]
            blocks = []
            for block in page.get_text("blocks", sort=True):
                if block[6] != 0:
                    continue
                text = normalize_block(block[4])
                if not text or (text.isdigit() and block[1] > page.rect.height * 0.9):
                    continue
                if re.fullmatch(r"\d+(?:\.\d+)*\s+[A-Z][^.!?]{1,100}", text):
                    section = text
                blocks.append({"text": text, "section": section,
                               "bbox": [round(v, 3) for v in block[:4]]})
            if not blocks:
                if skip_empty:
                    continue
                raise ValueError(f"No readable text on selected page {number}")
            page_characters = sum(len(b['text']) for b in blocks)
            characters += page_characters
            if ((max_page_characters is not None and page_characters > max_page_characters)
                    or (max_total_characters is not None and characters > max_total_characters)):
                raise ValueError('Extracted text exceeds the import text limit')
            pages.append({"page": number, "blocks": blocks,
                          "text": "\n\n".join(b["text"] for b in blocks),
                          "replacement_characters": sum(b["text"].count("\ufffd") for b in blocks)})
    return pages


def make_chunks(manifest: PaperManifestEntry, pages: list[dict], encoder,
                *, max_chunks: int | None = None) -> list[Chunk]:
    """Create page-local windows with soft section boundaries and no encoder truncation."""
    chunks = []
    config = {"parser": PARSER_VERSION, "chunker": CHUNKER_VERSION,
              "mini_revision": encoder.revision, "mpnet_revision": encoder.mpnet_revision}
    version = fingerprint(config)
    for page in pages:
        position, groups = 0, []
        for block in page["blocks"]:
            if groups and groups[-1]["section"] == block["section"]:
                groups[-1]["end"] = position + len(block["text"])
            else:
                groups.append({"start": position, "end": position + len(block["text"]), "section": block["section"]})
            position += len(block["text"]) + 2
        text = page["text"]
        mapping = encoder.mini_tokenizer(text, add_special_tokens=False, return_offsets_mapping=True,
                                         truncation=False, verbose=False)["offset_mapping"]
        starts = [interval[0] for interval in mapping]
        boundaries = [bisect_left(starts, group["start"]) for group in groups[1:]]
        offset = 0
        while offset < len(mapping):
            end = min(len(mapping), offset + 198)
            # Honor a nearby section boundary only after useful context exists;
            # isolated captions/headings must not consume entire evidence units.
            useful_boundaries = [b for b in boundaries if offset + 160 <= b <= end]
            if useful_boundaries:
                end = max(useful_boundaries)
            while end > offset:
                start_char, end_char = mapping[offset][0], mapping[end - 1][1]
                piece = text[start_char:end_char]
                mini = len(encoder.mini_tokenizer.encode(piece, add_special_tokens=True))
                mpnet = len(encoder.mpnet_tokenizer.encode(piece, add_special_tokens=True))
                if mini <= 200 and mpnet <= 384:
                    break
                end -= 1
            if end <= offset:
                raise ValueError("Cannot fit a source token in both encoders")
            sections = list(dict.fromkeys(g["section"] for g in groups
                                         if g["start"] < end_char and g["end"] > start_char))
            identity = fingerprint([manifest.source_sha256, version, page["page"], start_char, end_char])
            chunks.append(Chunk(
                chunk_id="chunk_" + identity, paper_id=manifest.paper_id,
                source_sha256=manifest.source_sha256, source_url=manifest.source_url,
                page=page["page"], section=" / ".join(sections), page_start=start_char, page_end=end_char,
                text=piece, text_sha256=text_sha(piece), parser_version=PARSER_VERSION,
                chunker_version=version, mini_tokens=mini, mpnet_tokens=mpnet,
            ))
            if max_chunks is not None and len(chunks) > max_chunks:
                raise ValueError('Collection chunk limit exceeded')
            if end == len(mapping):
                break
            offset = max(offset + 1, end - 40)
    return chunks
