"""Current human-review catalog and shared deterministic retrieval primitives."""

import json
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from research_assistant.contracts import Chunk, EvidenceItem, SourceExcerpt
from research_assistant.review.contracts import EntityDefinition
from research_assistant.review.facts import projection


@dataclass
class ReviewCatalog:
    """One source-validated review projection, never evaluation gold or model output."""

    corpus_id: str
    head: str
    facts: dict[str, dict]
    entities: dict[str, EntityDefinition]

    @classmethod
    def from_review(cls, corpus_id: str, review: dict) -> 'ReviewCatalog':
        """Consume the shared eligibility projection instead of reimplementing approval rules."""
        entities = {e['id']: EntityDefinition.model_validate(e) for f in review['facts'] for e in f['entities']}
        return cls(corpus_id, review['review_head'], {f['id']: f for f in review['facts']}, entities)


def checked_fact(item: EvidenceItem, catalog: ReviewCatalog | None) -> dict:
    """Bind scoring/display content to the same current source-approved representation."""
    fact = catalog.facts.get(item.id) if catalog else None
    if fact is None:
        raise ValueError('Evidence is no longer in the current approved projection; rerun the query')
    expected = EvidenceItem.model_validate(fact['evidence'])
    for field in ('kind', 'paper_ids', 'source_chunk_ids', 'excerpts', 'approved_claim_ids',
                  'claim_revision', 'claim_text', 'conditions'):
        if getattr(item, field) != getattr(expected, field):
            raise ValueError('Displayed fact differs from the current approved revision')
    return fact


def load_catalog(directory: Path, corpus_id: str, chunks: dict[str, Chunk]) -> ReviewCatalog:
    """Require the explicitly selected review store to belong to the requested corpus."""
    config = json.loads((directory / 'config.json').read_text(encoding='utf-8'))
    if config['corpus_id'] != corpus_id:
        raise ValueError('Review directory belongs to a different corpus')
    return ReviewCatalog.from_review(corpus_id, projection(directory, chunks))


def cosine(query: list[float], vector: list[float]) -> float:
    """Reject incompatible or invalid vectors; compare actual cosine, never native lexical scores."""
    q, v = np.asarray(query, dtype=float), np.asarray(vector, dtype=float)
    if any(x.shape != (384,) or not np.isfinite(x).all() or np.linalg.norm(x) == 0 for x in (q, v)):
        raise ValueError('Invalid retrieval vector dimensions/values')
    return max(-1.0, min(1.0, float(np.dot(q, v) / (np.linalg.norm(q) * np.linalg.norm(v)))))


def alias_matches(text: str, entities: dict[str, EntityDefinition]) -> set[str]:
    """Match all reviewed canonical names/aliases with NFKC word boundaries; retain ambiguity."""
    text = unicodedata.normalize('NFKC', text).casefold()
    return {key for key, entity in entities.items() for alias in [entity.name, *entity.aliases]
            if alias.strip() and re.search(r'(?<!\w)' + re.escape(unicodedata.normalize('NFKC', alias).casefold().strip()) + r'(?!\w)', text)}


def lexical_query(text: str) -> str:
    """Treat question text as literal terms, never Lucene operators, fields or query syntax."""
    terms = list(dict.fromkeys(re.findall(r'\w+', unicodedata.normalize('NFKC', text).casefold())))
    return ' OR '.join('"' + term + '"' for term in terms[:128])


def chunk_evidence(chunk: Chunk, origin: str = 'hybrid') -> EvidenceItem:
    """Use the same exact raw-source unit in every mode."""
    return EvidenceItem(id=chunk.chunk_id, retrieval_origin=origin, excerpts=[SourceExcerpt(
        chunk_id=chunk.chunk_id, paper_id=chunk.paper_id, source_sha256=chunk.source_sha256,
        source_url=chunk.source_url, page=chunk.page, section=chunk.section,
        chunk_page_start=chunk.page_start, start=0, end=len(chunk.text), text=chunk.text)])


def evidence_text(item: EvidenceItem) -> str:
    """Only actually available source/claim/condition text contributes alias matches."""
    return '\n'.join([item.claim_text or '', json.dumps(item.conditions, ensure_ascii=False),
                      *(excerpt.text for excerpt in item.excerpts)])
