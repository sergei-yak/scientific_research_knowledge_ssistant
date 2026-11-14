"""Write a head-addressed current review checkpoint; never edit immutable packets/receipts."""

import hashlib
import json
from collections import Counter
from pathlib import Path

from research_assistant.contracts import fingerprint
from research_assistant.evaluation.development import read_receipt, review_status
from research_assistant.evaluation.readiness import EvaluatorAttestation, check_attestation
from research_assistant.pipeline import write_immutable
from research_assistant.review.facts import projection
from research_assistant.review.store import load_chunks, state


def main() -> None:
    """Derive counts from shared eligibility and supplied human times, not queue labels."""
    directory = Path('data/reviews/expansion-v1')
    review = projection(directory, load_chunks(directory))
    registry = json.loads(Path('runs/m4-1/mapping-proposals.json').read_text(encoding='utf-8'))['batches']
    current = state(directory)['current']
    packet_root = Path('runs/m4-1/review-batches').resolve()
    for path in sorted(Path('runs/m4-1/packet-amendments').glob('*.json')):
        amendment = json.loads(path.read_text(encoding='utf-8'))
        packet = Path(amendment['packet']).resolve()
        if not packet.is_relative_to(packet_root):
            raise ValueError('Review packet amendment escaped the claim-review directory')
        presented = json.loads(packet.with_name('batch.json').read_text(encoding='utf-8'))
        if fingerprint(presented) != amendment['batch_sha256']:
            raise ValueError('Amended packet hash mismatch')
        row = next(row for row in registry if row['batch'] == amendment['batch'])
        expected = {key for key, value in current.items() if value.paper.paper_id == row['paper_id']}
        items = presented['items']
        if ({item['claim_id'] for item in items} == expected and len(items) == len(expected)
                and all(current[item['claim_id']].sha256 == item['revision_sha256'] for item in items)):
            row['packet'] = amendment['packet']
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
    gold = review_status(Path('data/evaluation/development/expansion-v1'))
    gold_receipts = [read_receipt(path) for path in sorted(
        Path('data/evaluation/development/expansion-v1/human-inputs').glob('m4-1-gold-batch-*-sergei.json'))]
    if any(receipt['dataset_sha256'] != gold['dataset_sha256'] for receipt in gold_receipts):
        raise ValueError('Gold-review time belongs to a different annotation version')
    known_gold_times = [receipt['actual_batch_review_seconds_approx'] for receipt in gold_receipts
                        if receipt['actual_batch_review_seconds_approx'] is not None]
    evaluator_status = 'pending'
    private_gold_seconds = None
    readiness_path = Path('runs/m4-1/evaluation-readiness-manifest.json')
    if readiness_path.exists():
        readiness = json.loads(readiness_path.read_text(encoding='utf-8'))
        reference = Path(readiness['attestation']['path'])
        if (reference.is_absolute() or '..' in reference.parts
                or reference.parts[:2] != ('runs', 'm4-1')):
            raise ValueError('Attestation must be a named public M4.1 artifact')
        public_path = reference.resolve()
        if not public_path.is_relative_to(Path('runs/m4-1').resolve()):
            raise ValueError('Attestation escaped the public report directory')
        raw = public_path.read_bytes()
        if hashlib.sha256(raw).hexdigest() != readiness['attestation']['file_sha256']:
            raise ValueError('Public attestation hash changed')
        attestation = EvaluatorAttestation.model_validate_json(raw)
        checked = check_attestation(attestation, readiness['corpus_id'], review['review_head'], gold['dataset_sha256'])
        if (not gold['ready'] or checked['exposure_requires_resolution_before_freeze']
                or readiness['heldout']['questions_sha256'] != attestation.heldout_questions_sha256
                or readiness['heldout']['annotations_sha256'] != attestation.heldout_annotations_sha256):
            raise ValueError('Current human readiness or private commitments need resolution')
        evaluator_status = checked['status']
        private_gold_seconds = readiness['human_review']['approx_private_total_seconds']
    complete = (evaluator_status == 'attested' and gold['ready'] and counts['approved'] == 28
                and len(review['facts']) == 51 and sum(counts.values()) == 28)
    report = {'task_id': 'M4.1', 'status': 'done' if complete else 'waiting_for_human', 'review_head': review['review_head'],
        'active_claims_total': len(review['facts']), 'expansion_claims': sum(counts.values()),
        'expansion_approved': counts['approved'], 'expansion_rejected': counts['rejected'],
        'expansion_pending': sum(v for k, v in counts.items() if k not in {'approved', 'rejected'}),
        'approx_known_human_review_seconds': sum(known_times), 'batches_with_unknown_time': len(receipts) - len(known_times),
        'per_claim_review_time': None, 'batches': batches,
        'development_annotations_validated': gold['human_validated'], 'development_ready': gold['ready'],
        'development_dataset_directory': 'data/evaluation/development/expansion-v1',
        'approx_known_gold_review_seconds': sum(known_gold_times),
        'gold_batches_with_unknown_time': len(gold_receipts) - len(known_gold_times),
        'per_question_review_time': None,
        'evaluator_final_24_question_attestation': evaluator_status,
        'heldout_annotations_human_validated_attested': 16 if evaluator_status == 'attested' else 0,
        'approx_private_gold_review_seconds': private_gold_seconds,
        'heldout_content_accesses': 0, 'heldout_access_count_scope': 'development agent only',
        'final_run_authorized': False}
    path = Path('runs/m4-1/review-progress') / (review['review_head'] + '-' + fingerprint(report)[:12] + '.json')
    write_immutable(path, json.dumps(report, indent=2) + '\n')
    print(json.dumps({key: value for key, value in report.items() if key != 'batches'} | {'artifact': str(path)}))


if __name__ == '__main__':
    main()
