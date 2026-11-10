"""Finalize proposed development annotation scope before fresh human validation; no held-out IO."""

import json
from pathlib import Path

from research_assistant.evaluation.development import (
    DevelopmentAnnotation, create_dataset, export_review_batch, load_dataset, review_status,
)
from research_assistant.pipeline import write_immutable


def main() -> None:
    """Preserve the initial draft, remove historical-scope placeholders and grant no validation."""
    source = Path('data/evaluation/development/expansion-v1-draft')
    manifest, entries, chunks = load_dataset(source)
    audit = json.loads((source / 'absence-audit.json').read_text(encoding='utf-8'))
    rationales = {
        'DEV-U1': (
            'Scoped to the 1,427 indexed chunks and declared pages of the pinned 20-paper corpus. '
            'The 13 carbon/energy keyword matches are retained in the audit; overlap can repeat matches. '
            'They concern unrelated molecule/energy discussion, a county-emissions benchmark question in KG-RAG, '
            'financial-sector labels in HybridRAG, and general environmental discussion in HyPA-RAG. '
            'These do not establish kilograms of CO2e for Edge et al.’s Behind the Tech evaluation. '
            'Its indexed evaluation/cost prose does not provide that measurement. The numeric county-emissions '
            'example must not be reassigned to the Graph RAG study. Keyword absence alone is not proof; '
            'human validation covers this source-attributed absence judgment. Omitted pages, appendices, '
            'other versions and the wider literature are outside scope.'),
        'DEV-U2': (
            'Scoped to the pinned 20-paper indexed corpus, including original HippoRAG pages 1–10. '
            'The full 171 fine-tuning/NER/OpenIE lexical matches are retained, including overlapping and '
            'unrelated mentions. Original HippoRAG describes off-the-shelf components without extra training '
            'on page 9 and suggests potential direct NER/OpenIE fine-tuning benefit on page 10. '
            'Its tested OpenIE replacement models and off-the-shelf fine-tuned retrieval encoders do not '
            'establish a measured before/after QA gain from directly fine-tuning those two components. '
            'Other papers’ training results must retain their own reporting paper/intervention. No source '
            'support for the requested measured intervention gain is proposed. Lexical triage is not '
            'semantic proof; human validation covers the scoped unanswerability judgment. Omitted original '
            'appendices and other versions have not been certified absent.'),
    }
    proposed = []
    for entry in entries:
        value = entry.model_dump(mode='json')
        if entry.gold.question_id in rationales:
            value['revision'] = 3
            value['unanswerable_rationale'] = rationales[entry.gold.question_id]
        proposed.append(DevelopmentAnnotation.model_validate(value))
    directory = Path('data/evaluation/development/expansion-v1')
    created = create_dataset(directory, manifest['corpus_id'], proposed, chunks, audit,
        selection_note='Retained pilot development topics with explicit 20-paper scope; complete candidate annotations prepared before fresh human validation or expanded performance scoring. Original pilot and initial expansion drafts preserved; no held-out inputs or gain-based selection.')
    for number, ids in enumerate([['DEV-D1', 'DEV-D2'], ['DEV-C1', 'DEV-C2'], ['DEV-M1', 'DEV-M2'], ['DEV-U1', 'DEV-U2']], 1):
        export_review_batch(directory, ids, f'batch-{number:02d}')
    status = review_status(directory)
    report = {'task_id': 'M4.1', 'created': created, 'human_review': status,
        'prior_draft_unchanged': True, 'prior_receipts_copied': False, 'heldout_accesses': 0,
        'note': 'Six answerable annotations retain revision 2/source supports; the two scoped absence rationales are proposed revision 3. No validation is granted.'}
    write_immutable(Path('runs/m4-1/development-final-candidates.json'), json.dumps(report, indent=2) + '\n')
    print(json.dumps({'dataset': str(directory), 'dataset_sha256': created['dataset_sha256'], 'ready': status['ready']}))


if __name__ == '__main__':
    main()
