"""Source-preservation and retrieval/export checks; never load held-out or changed gold."""

import json
from pathlib import Path

from research_assistant.contracts import QueryRequest, fingerprint
from research_assistant.embeddings import Encoder
from research_assistant.graph.recovery import capture
from research_assistant.graph.reviews import synchronize_review
from research_assistant.pipeline import run_query, write_immutable
from research_assistant.product import WORKFLOWS, prepare_output
from research_assistant.review.facts import projection
from research_assistant.review.store import load_chunks
from research_assistant.settings import Settings, configure_caches


def main() -> None:
    """Exercise shared services without generation, score tuning, private inputs or data resets."""
    configure_caches()
    settings = Settings.from_env()
    root = Path('runs/m4-1')
    ingestion = json.loads((root / 'ingestion.json').read_text(encoding='utf-8'))
    directory = Path('data/reviews/expansion-v1')
    sync = synchronize_review(directory, settings)
    encoder = Encoder()
    checks = []
    for workflow, question in WORKFLOWS.items():
        if not question:
            continue  # The free-form Ask workflow intentionally has no preset question.
        for mode in ('vector', 'hybrid', 'hybrid_facts', 'graph'):
            run = run_query(QueryRequest(question=question, mode=mode, corpus_id=ingestion['corpus_id']),
                settings, review_directory=directory, generate=False, workflow=workflow, encoder=encoder)
            view, csv_text = prepare_output(run, settings, directory)
            prefix = root / 'retrieval-checks-final' / (workflow + '-' + mode)
            write_immutable(prefix.with_suffix('.json'), run.model_dump_json(indent=2) + '\n')
            write_immutable(prefix.with_suffix('.csv'), csv_text)
            checks.append({'workflow': workflow, 'requested_mode': mode, 'effective_mode': run.retrieval.effective_mode,
                'fallback_reason': run.retrieval.fallback_reason, 'units': len(run.retrieval.evidence),
                'tokens': run.retrieval.estimated_tokens, 'papers_in_view': view.paper_count,
                'status': 'passed_source_context_export_contracts', 'run': str(prefix.with_suffix('.json'))})
    before = json.loads((root / 'preservation-before.json').read_text(encoding='utf-8'))
    after = capture(settings)
    current = {n['key']: n for n in after['nodes']}
    changed = [n['key'] for n in before['nodes'] if n['key'] not in current
               or n['properties'] != current[n['key']]['properties']
               or not set(n['labels']) <= set(current[n['key']]['labels'])]
    after_edges = {fingerprint(edge) for edge in after['relationships']}
    missing_edges = [edge for edge in before['relationships'] if fingerprint(edge) not in after_edges]
    pilot = projection(Path('data/reviews/pilot'), load_chunks(Path('data/reviews/pilot')))
    if changed or missing_edges or len(pilot['facts']) != 23:
        raise ValueError('Original data preservation failed: ' + str(changed))
    report = {'task_id': 'M4.1', 'status': 'passed_engineering_checks_human_readiness_pending',
        'corpus_id': ingestion['corpus_id'], 'papers': 20, 'chunks': ingestion['chunks'],
        'review_sync': sync, 'retrieval_checks': checks, 'generation_calls': 0, 'paid_calls': 0,
        'heldout_accesses': 0, 'gold_scoring_on_expansion': 'pending_new_human_validated_annotation_version',
        'preservation': {'original_nodes': len(before['nodes']), 'original_relationships': len(before['relationships']),
            'changed_original_properties': changed, 'missing_original_relationships': len(missing_edges),
            'original_labels_preserved': True, 'old_schema_preserved': all(x in after['indexes'] for x in before['indexes'])
                and all(x in after['constraints'] for x in before['constraints']),
            'current_nodes': len(after['nodes']), 'current_relationships': len(after['relationships']),
            'pilot_approved_claims': len(pilot['facts']), 'pilot_review_head': pilot['review_head']},
        'caveat': 'Expanded raw sources plus carried pilot approvals; new extraction candidates remain ineligible until human decisions.'}
    write_immutable(root / 'engineering-checks.json', json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(report, ensure_ascii=False))


if __name__ == '__main__':
    main()
