"""Export the first completed paper for human review while independent extraction continues."""

import json
import shutil
from pathlib import Path

from research_assistant.extraction.contracts import ProposedClaim
from research_assistant.extraction.pilot import validate_candidate
from research_assistant.pipeline import write_immutable
from research_assistant.review.batches import export_batch
from research_assistant.review.contracts import ReviewRevision
from research_assistant.review.store import load_chunks, prepare_review, propose_revision, state


def main() -> None:
    """Preserve raw drafts; correct an exact-quotation failure only as a new unapproved revision."""
    name = 'arxiv-2402.12352v1'
    source = Path('runs/m4-1/claim-packets') / name
    partial = Path('runs/m4-1/review-imports/first-paper')
    if not partial.exists():
        shutil.copytree(source, partial / name)
    bundle = json.loads((source / 'bundle.json').read_text(encoding='utf-8'))
    write_immutable(partial / 'summary.json', json.dumps({'task_id': 'M4.1', 'corpus_id': bundle['corpus_id'],
        'scope': 'Mechanical subset export of a completed paper, not the ongoing extraction summary',
        'papers': [{'paper_id': bundle['paper']['paper_id']}]}, indent=2) + '\n')
    directory = Path('data/reviews/expansion-v1')
    report = prepare_review(partial, directory)
    chunks = load_chunks(directory)
    original = state(directory)['current'][bundle['candidates'][1]['claim_id']]
    statement = "The authors hypothesize that ES IR's difficulty accessing long-tail knowledge is related to a lack of data balancing, which can concentrate retrieval in the closest high-density region."
    quote = 'We hypothesized that the cause is rather the lack of data balancing that makes ES IR retrieve text chunks predomi- nantly from the closest high-density region.'
    draft = ProposedClaim.model_validate({**original.draft.model_dump(), 'statement': statement, 'quotes': [quote]})
    passage = next(p for p in bundle['passages'] if p['id'] == bundle['candidates'][1]['passage_id'])
    mapped = validate_candidate(draft, bundle['paper'], passage, list(chunks.values()))
    if mapped['validation_errors']:
        raise ValueError(mapped['validation_errors'])
    revised = ReviewRevision.model_validate({**original.model_dump(), 'revision': 2, 'draft': draft,
        'support': mapped['claim']['support'], 'validation_errors': [], 'predecessor_sha256': original.sha256,
        'change_reason': 'Narrow to the explicitly attributed hypothesis; preserve the exact normalized line-break hyphen in the quotation. Raw revision 1 remains historical; fresh human approval required.'})
    correction = propose_revision(directory, revised, chunks)
    batch = export_batch(directory, [c['claim_id'] for c in bundle['candidates']], Path('runs/m4-1/review-batches/batch-01'), prefix='E')
    write_immutable(Path('runs/m4-1/first-review-preparation.json'), json.dumps({'import': report, 'correction': correction, 'batch': batch}, indent=2) + '\n')
    print(json.dumps(batch))


if __name__ == '__main__':
    main()
