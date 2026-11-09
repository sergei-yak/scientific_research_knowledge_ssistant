"""Freeze two source-only paragraph selectors per addition before local extraction."""

import json
import re
from pathlib import Path

from research_assistant.extraction.contracts import ExtractionPlan, PassageSelector
from research_assistant.extraction.pilot import make_passage
from research_assistant.pipeline import write_immutable


def main() -> None:
    """Choose method prose and a limitation/conclusion without questions or retrieval scores."""
    report = json.loads(Path('runs/m4-1/ingestion.json').read_text(encoding='utf-8'))
    pilot = json.loads(Path('manifests/pilot-five-papers.json').read_text(encoding='utf-8'))
    old_ids = {paper['paper_id'] for paper in pilot['papers']}
    selections, witnesses = {}, []
    for member in report['papers']:
        if member['paper_id'] in old_ids:
            continue
        pages = [json.loads(line) for line in Path(member['snapshot_path']).with_name('pages.jsonl').read_text(encoding='utf-8').splitlines()]
        choices = [(page, block) for page in pages for block in page['blocks']
                   if len(block['text']) >= 180 and not re.match(r'^(?:Table|Figure|Fig\.|\[\d+\])', block['text'])
                   and not block['section'].casefold().startswith(('references', 'appendix', 'bibliography'))]
        if not choices:
            raise ValueError('No usable source prose')
        method = max(choices, key=lambda pair: (
            bool(re.search(r'method|framework|approach|retrieval|construction', pair[1]['section'], re.I)),
            bool(re.search(r'we (?:propose|introduce|present)|our (?:method|framework|approach)', pair[1]['text'], re.I)),
            -pair[0]['page']))
        conclusions = [pair for pair in choices if pair != method and re.search(r'limitation|conclusion|discussion', pair[1]['section'], re.I)]
        other = conclusions[-1] if conclusions else next((pair for pair in reversed(choices) if pair != method), method)
        selectors = []
        for purpose, (page, block) in [('method_design', method), ('qualified_discussion_or_limitation', other)]:
            if any(s.page == page['page'] and s.anchor == block['text'][:90] for s in selectors):
                continue
            selector = PassageSelector(page=page['page'], anchor=block['text'][:90], max_blocks=1, purpose=purpose)
            selectors.append(selector)
            witnesses.append(make_passage(member['paper_id'], pages, selector, 600))
        selections[member['paper_id']] = selectors
    plan = ExtractionPlan(version='expansion-claims-v1', max_requests_per_paper=2,
                          max_candidates_per_paper=4, selections=selections)
    write_immutable(Path('manifests/expansion-extraction.json'), plan.model_dump_json(indent=2) + '\n')
    write_immutable(Path('runs/m4-1/selected-passages.json'), json.dumps(witnesses, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({'corpus_id': report['corpus_id'], 'papers': len(selections), 'passages': len(witnesses),
                      'maximum_requests': len(witnesses), 'maximum_candidates': 4 * len(selections), 'approved': 0}))


if __name__ == '__main__':
    main()
