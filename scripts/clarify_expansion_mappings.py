"""Propose explicit paper-owned method identities before remaining human review batches."""

import json
import re
from pathlib import Path

from research_assistant.contracts import fingerprint
from research_assistant.review.batches import export_batch
from research_assistant.review.contracts import EntityDefinition, ReviewRevision
from research_assistant.review.store import load_chunks, propose_revision, state
from research_assistant.pipeline import write_immutable

METHODS = {
    '2405.12035': ('KG-RAG', []), '2405.16933': ('PG-RAG', []),
    '2406.11460': ('TRACE', []), '2407.10805': ('Think-on-Graph 2.0 (ToG2.0)', ['ToG2.0']),
    '2407.13909': ('PRAGyan', []), '2407.21276': ('PolyRAG', []),
    '2408.04187': ('MedGraphRAG', []), '2408.04948': ('HybridRAG', []),
    '2408.08535': ('CommunityKG-RAG', []), '2409.09046': ('HyPA-RAG', []),
    '2409.12177': ('LitFM', []),
}


def normalized(value: str) -> str:
    """Use source presence only as a guard, never as approval or cross-paper entity merging."""
    return re.sub(r'[^a-z0-9]', '', value.casefold())


def main() -> None:
    """Retain all approved revisions; present every changed mapping for fresh human decisions."""
    directory = Path('data/reviews/expansion-v1')
    chunks = load_chunks(directory)
    current = state(directory)
    changes = []
    for old in current['current'].values():
        base = (old.paper.arxiv_id or '').split('v')[0]
        if base not in METHODS:
            continue
        if (old.claim_id, old.revision) in current['decisions']:
            raise ValueError('Do not alter a human-reviewed revision in this proposal-only operation')
        name, aliases = METHODS[base]
        source = ' '.join(c.text for c in chunks.values() if c.paper_id == old.paper.paper_id)
        # ToG's long name has punctuation/parentheses; the short exact source spelling is sufficient.
        if normalized(aliases[0] if aliases else name) not in normalized(source + ' ' + old.paper.title):
            raise ValueError('Proposed method name is absent from this pinned paper')
        draft = old.draft.model_copy(deep=True)
        draft.method, draft.method_aliases = name, aliases
        if base == '2408.08535':
            draft.statement = ('In the examined configurations, the authors report that increasing the number of top communities '
                'improves accuracy while holding community-to-sentence selection constant. No exact threshold or numerical gain is asserted.')
            draft.conditions['protocol'] = 'Increase the number of top communities while holding community-to-sentence selection constant; exact thresholds unknown for this claim'
        method = EntityDefinition(id='method:arxiv-' + base + ':' + normalized(name), kind='method', name=name, aliases=aliases)
        # Keep any separately proposed dataset unchanged; never merge it across papers here.
        entities = [method] + [entity for entity in old.entities if entity.kind != 'method']
        revision = ReviewRevision.model_validate({**old.model_dump(), 'revision': old.revision + 1,
            'draft': draft, 'entities': entities,
            'entity_revision': fingerprint([entity.model_dump() for entity in entities]),
            'predecessor_sha256': old.sha256,
            'change_reason': 'M4.1 proposed mapping clarification before human review: bind the method to its own pinned paper and use one explicit identity within that paper. Configuration names are not method aliases; CommunityKG claim is narrowed to its exact qualitative quotation. No cross-paper entity merge or approval.'})
        result = propose_revision(directory, revision, chunks)
        if result['source_errors']:
            raise ValueError(result['source_errors'])
        changes.append(result)
    queue = json.loads(Path('runs/m4-1/review-batches/queue.json').read_text(encoding='utf-8'))
    registry = []
    prefixes = ['E', 'ED', 'CS', 'KG', 'AC', 'PG', 'TR', 'TG', 'PR', 'PY', 'MG', 'HY', 'CO', 'PA', 'LF']
    latest = state(directory)
    for row, prefix in zip(queue['batches'], prefixes):
        number = row['batch']
        if number <= 3:
            packet = Path(row['packet']).parent if number != 3 else Path('runs/m4-1/review-batches/batch-03-r2')
        else:
            packet = Path('runs/m4-1/review-batches') / f'batch-{number:02d}-mapped'
            ids = [key for key, value in latest['current'].items() if value.paper.paper_id == row['paper_id']]
            export_batch(directory, ids, packet, prefix)
        registry.append({**row, 'packet': str(packet / 'REVIEW.md')})
    write_immutable(Path('runs/m4-1/mapping-proposals.json'), json.dumps({'new_approvals': 0, 'changes': changes, 'batches': registry}, indent=2) + '\n')
    print(json.dumps({'mapping_revisions_proposed': len(changes), 'new_approvals': 0}))


if __name__ == '__main__':
    main()
