"""Write a head-addressed current review checkpoint; never edit immutable packets/receipts."""

import json
from collections import Counter
from pathlib import Path

from research_assistant.contracts import fingerprint
from research_assistant.evaluation.development import review_status
from research_assistant.pipeline import write_immutable
from research_assistant.review.facts import projection
from research_assistant.review.store import load_chunks


def main() -> None:
    """Derive counts from shared eligibility and supplied human times, not queue labels."""
    directory = Path('data/reviews/expansion-v1')
    review = projection(directory, load_chunks(directory))
    registry = json.loads(Path('runs/m4-1/mapping-proposals.json').read_text(encoding='utf-8'))['batches']
    papers = {row['paper_id'] for row in registry}
    counts = Counter(row['status'] for row in review['statuses'] if row['paper_id'] in papers)
    batches = []
    for row in registry:
        states = [value for value in review['statuses'] if value['paper_id'] == row['paper_id']]
        batches.append({**row, 'approved': sum(value['status'] == 'approved' for value in states),
            'pending': sum(value['status'] not in {'approved', 'rejected'} for value in states),
            'rejected': sum(value['status'] == 'rejected' for value in states),
            'status': 'decisions_complete' if all(value['status'] in {'approved', 'rejected'} for value in states) else 'awaiting_human_decisions'})
    receipts = [json.loads(path.read_text(encoding='utf-8')) for path in
                sorted((directory / 'human-inputs').glob('m4-1-batch-*-sergei.json'))]
    known_times = [row['actual_batch_review_seconds_approx'] for row in receipts if row['actual_batch_review_seconds_approx'] is not None]
    gold = review_status(Path('data/evaluation/development/expansion-v1-draft'))
    report = {'task_id': 'M4.1', 'status': 'waiting_for_human', 'review_head': review['review_head'],
        'active_claims_total': len(review['facts']), 'expansion_claims': sum(counts.values()),
        'expansion_approved': counts['approved'], 'expansion_rejected': counts['rejected'],
        'expansion_pending': sum(v for k, v in counts.items() if k not in {'approved', 'rejected'}),
        'approx_known_human_review_seconds': sum(known_times), 'batches_with_unknown_time': len(receipts) - len(known_times),
        'per_claim_review_time': None, 'batches': batches,
        'development_annotations_validated': gold['human_validated'], 'development_ready': gold['ready'],
        'evaluator_final_24_question_attestation': 'pending', 'heldout_content_accesses': 0,
        'final_run_authorized': False}
    path = Path('runs/m4-1/review-progress') / (review['review_head'] + '-' + fingerprint(report)[:12] + '.json')
    write_immutable(path, json.dumps(report, indent=2) + '\n')
    print(json.dumps({key: value for key, value in report.items() if key != 'batches'} | {'artifact': str(path)}))


if __name__ == '__main__':
    main()
