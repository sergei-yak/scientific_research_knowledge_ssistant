"""Propose four source-backed corrections; raw extraction and human eligibility remain separate."""

import json
from pathlib import Path

from research_assistant.extraction.contracts import ProposedClaim
from research_assistant.extraction.pilot import validate_candidate
from research_assistant.pipeline import write_immutable
from research_assistant.review.contracts import ReviewRevision
from research_assistant.review.store import entities_for, load_chunks, propose_revision, state

TARGETS = {
    '2404.09296': 'claim_3fe286316b13067c88c11190d3a6dd0ebdfda780b2e47d4776ed4230ede75189',
    '2406.11460': 'claim_7e7c6826689b932fada70204ba66fcd450d4e01bd51abefe66f95736b56e360c',
    '2407.21276': 'claim_7f29925590463e08e3c4f0a082061ca15be70a2e9a11861bc3db880a368eaf04',
    '2409.12177': 'claim_0c8367e0ee159cd5959161885b46fb76770ded5aea1b1aa0433400b36b888f89',
}


def main() -> None:
    """Use exact selected prose and explicit unknowns; never request new inference or approve."""
    directory = Path('data/reviews/expansion-v1')
    chunks = load_chunks(directory)
    results = []
    for base, claim_id in TARGETS.items():
        original = state(directory)['current'][claim_id]
        if original.revision != 1:
            raise ValueError('Expected the original unreviewed draft; preserve and inspect later revisions')
        bundle = json.loads(Path(f'runs/m4-1/claim-packets/arxiv-{base}v1/bundle.json').read_text(encoding='utf-8'))
        candidate = next(c for c in bundle['candidates'] if c['claim_id'] == claim_id)
        passage = next(p for p in bundle['passages'] if p['id'] == candidate['passage_id'])
        text, draft = passage['text'], original.draft.model_dump()
        if base == '2404.09296':
            draft.update(method='E-OED Framework', method_aliases=['Educational Open Entity Discovery'],
                quotes=[text[text.index('We then introduce'):text.index(' Lastly,')]])
        elif base == '2406.11460':
            first, second = text[text.index('These examples'):].split('More- over, ', 1)
            draft.update(method='TRACE', method_aliases=[], dataset=None, dataset_aliases=[], quotes=[first.strip(), second.strip()],
                statement='In their case study, the authors report that TRACE constructs reasoning chains for multi-hop questions and describe the chains as an interpretable account of how answers are generated.')
        elif base == '2407.21276':
            draft.update(kind='finding', dataset=None, dataset_aliases=[],
                conditions={key: None for key in ('split', 'dataset_version', 'metric', 'protocol', 'limitations')},
                statement='The authors report that PolyRAG surpassed the compared methods across the examined groups, model backbones and two benchmarks, and describe a balance between precision and recall. This is their qualified report about those configurations.')
        else:
            draft.update(method='LitFM', method_aliases=[],
                quotes=[text[text.index('Extensive experi- mental results'):]],
                statement='The authors report that LitFM showed versatility and superior performance across six benchmark tasks in their experiments.')
        draft = ProposedClaim.model_validate(draft)
        mapped = validate_candidate(draft, bundle['paper'], passage, list(chunks.values()))
        if mapped['validation_errors']:
            raise ValueError(mapped['validation_errors'])
        entity_revision = mapped['entity_revision']
        revision = ReviewRevision.model_validate({**original.model_dump(), 'revision': 2,
            'draft': draft, 'support': mapped['claim']['support'], 'validation_errors': [],
            'entities': entities_for(original.paper.paper_id, draft, entity_revision), 'entity_revision': entity_revision,
            'predecessor_sha256': original.sha256,
            'change_reason': 'M4.1 source-prose correction: retain exact normalized quotation spelling/line-break hyphens; make proposed method explicit when named; remove footnote/multi-dataset identity errors; keep qualitative reports attributed. Raw revision 1 preserved; fresh human review required.'})
        result = propose_revision(directory, revision, chunks)
        if result['source_errors']:
            raise ValueError(result['source_errors'])
        results.append(result)
    write_immutable(Path('runs/m4-1/draft-corrections.json'), json.dumps({'task_id': 'M4.1', 'new_approvals': 0, 'corrections': results}, indent=2) + '\n')
    print(json.dumps({'corrected_drafts': len(results), 'new_approvals': 0}))


if __name__ == '__main__':
    main()
