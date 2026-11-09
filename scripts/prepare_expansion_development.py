"""Prepare explicitly unvalidated expanded-scope development drafts, never held-out data."""

import json
import re
from pathlib import Path

from research_assistant.evaluation.development import (
    DevelopmentAnnotation, create_dataset, export_review_batch, load_dataset, review_status,
)
from research_assistant.ingestion.sources import load_corpus_chunks
from research_assistant.pipeline import write_immutable


def main() -> None:
    """Keep pilot annotations/receipts untouched and require fresh decisions for the new scope."""
    original, entries, _ = load_dataset(Path('data/evaluation/development/pilot-v1'))
    corpus_id = json.loads(Path('runs/m4-1/ingestion.json').read_text(encoding='utf-8'))['corpus_id']
    chunks = load_corpus_chunks(corpus_id)
    snapshot = json.loads((Path('data/processed') / corpus_id / 'snapshot.json').read_text(encoding='utf-8'))
    patterns = {
        'DEV-U1': r'(?i)\b(?:carbon|emissions?|CO2e|kilowatt|kWh|energy)\b',
        'DEV-U2': r'(?i)\b(?:fine[-\s]*tun\w*|NER|OpenIE|named[-\s]*entity|open[-\s]*information[-\s]*extraction)\b',
    }
    questions = {}
    for key, pattern in patterns.items():
        matches = []
        for chunk in chunks.values():
            for match in re.finditer(pattern, chunk.text):
                matches.append({'paper_id': chunk.paper_id, 'chunk_id': chunk.chunk_id, 'page': chunk.page,
                    'start': match.start(), 'end': match.end(),
                    'context': chunk.text[max(0, match.start() - 160):match.end() + 240]})
        questions[key] = {'pattern': pattern, 'match_count': len(matches), 'matches': matches,
            'status': 'lexical_triage_only_semantic_judgment_pending'}
    audit = {'corpus_id': corpus_id, 'chunks_scanned': len(chunks),
        'coverage': {p['paper_id']: p['selected_pages'] for p in snapshot['papers']},
        'questions': questions, 'caveat': 'Complete keyword matches within indexed chunks; neither absence nor presence proves answerability. Overlapping chunks can repeat matches; omitted pages/later versions are outside scope.'}
    drafts = []
    for entry in entries:
        raw = entry.model_dump(mode='json')
        raw['revision'] += 1
        if entry.gold.category == 'unanswerable':
            raw['gold']['question'] = raw['gold']['question'].replace('indexed pilot', 'indexed 20-paper corpus')
            raw['gold']['reference_answer'] = raw['gold']['reference_answer'].replace('indexed pilot', 'indexed corpus')
            raw['unanswerable_rationale'] = ('Expanded-scope revalidation PENDING. The prior pilot rationale is historical: '
                + entry.unanswerable_rationale + ' Reassess against all 1,427 indexed chunks and the new absence audit; no validation carries over automatically.')
        drafts.append(DevelopmentAnnotation.model_validate(raw))
    directory = Path('data/evaluation/development/expansion-v1-draft')
    created = create_dataset(directory, corpus_id, drafts, chunks, audit,
        selection_note='Retained pilot development topics with explicitly new 20-paper scope; source-span facts preserved, no retrieval-gain selection, no held-out inputs. New human validation required.')
    for index, ids in enumerate([['DEV-D1', 'DEV-D2'], ['DEV-C1', 'DEV-C2'], ['DEV-M1', 'DEV-M2'], ['DEV-U1', 'DEV-U2']], 1):
        export_review_batch(directory, ids, 'batch-' + f'{index:02d}')
    status = review_status(directory)
    report = {'task_id': 'M4.1', 'created': created, 'status': status,
        'prior_corpus_id': original['corpus_id'], 'pilot_receipts_copied': False, 'heldout_accesses': 0,
        'triage_matches': {key: value['match_count'] for key, value in questions.items()}}
    write_immutable(Path('runs/m4-1/development-drafts.json'), json.dumps(report, indent=2) + '\n')
    print(json.dumps({'ready': status['ready'], 'triage_matches': report['triage_matches'], 'dataset': str(directory)}))


if __name__ == '__main__':
    main()
