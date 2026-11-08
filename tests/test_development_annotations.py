"""Synthetic development annotations test source integrity and human-validation boundaries."""

import json
from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from research_assistant.contracts import (
    Chunk, EvaluationQuestion, EvidenceItem, GoldFact, SourceSpanRef, fingerprint, text_sha,
)
from research_assistant.evaluation import development as dev
from research_assistant.evaluation.scoring import score_evidence


@pytest.fixture
def dataset(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    chunks = {}
    for key, paper, page in [('a', 'paper-a', 1), ('b', 'paper-a', 2), ('c', 'paper-b', 1)]:
        text = 'SYNTHETIC source statement ' + key + '.'
        chunks[key] = Chunk(chunk_id=key, paper_id=paper, source_sha256=('a' if paper=='paper-a' else 'b')*64,
            source_url='https://example.invalid/test', page=page, section='Synthetic', page_start=0,
            page_end=len(text), text=text, text_sha256=text_sha(text), parser_version='test',
            chunker_version='test', mini_tokens=10, mpnet_tokens=10)

    def span(key):
        c = chunks[key]
        return SourceSpanRef(paper_id=c.paper_id, source_sha256=c.source_sha256,
            chunk_id=key, start=0, end=len(c.text), quote_sha256=c.text_sha256)

    first = GoldFact(fact_id='independent-gold-a', statement='Two synthetic premises are required.',
                     support_sets=[[span('a'), span('b')]])
    second = GoldFact(fact_id='independent-gold-b', statement='Synthetic other paper.', support_sets=[[span('c')]])
    entries = []
    for category, prefix in [('direct','D'),('cross_paper','C'),('multi_hop','M'),('unanswerable','U')]:
        for number in (1,2):
            facts = [] if category=='unanswerable' else [first] if category=='direct' else [first,second]
            q = EvaluationQuestion(question_id=f'DEV-{prefix}{number}', question='Synthetic test question.',
                category=category, split='development', reference_answer='Synthetic answer.', facts=facts,
                sufficient_fact_sets=[[f.fact_id for f in facts]] if facts else [])
            chain = [{'source':'A','relation':'links','target':'B'},
                     {'source':'B','relation':'links','target':'C'}] if category=='multi_hop' else []
            entries.append(dev.DevelopmentAnnotation(gold=q, category_rationale='Synthetic test category.',
                reasoning_chain=chain, unanswerable_rationale='No synthetic measurement.' if category=='unanswerable' else None,
                context_spans=[span('a')] if category=='unanswerable' else []))
    root = tmp_path / 'data/evaluation/development/test-v1'
    monkeypatch.setattr(dev, 'load_corpus_chunks', lambda corpus: chunks)
    audit = {'questions': {'DEV-U1': {'status':'Synthetic triage only'}, 'DEV-U2': {'status':'Synthetic triage only'}}}
    dev.create_dataset(root, 'a'*64, entries, chunks, audit)
    return root, entries, chunks


def test_eight_stratified_drafts_are_feasible_but_not_human_validated(dataset):
    root, entries, chunks = dataset
    report = dev.check_dataset(root)
    assert report['review']['human_validated'] == 0 and report['review']['ready'] is False
    assert len(report['checks']) == 8
    assert all(row['witnesses'][0]['recall']==1 for row in report['checks'] if row['witnesses'])
    requests = [json.loads(line) for line in (root/'questions.jsonl').read_text(encoding='utf-8').splitlines()]
    assert len(requests)==8 and all(set(q)=={'question_id','question','split','category','secondary_tags'} for q in requests)
    assert all('facts' not in q and 'reference_answer' not in q for q in requests)


def test_real_multi_passage_and_truncation_boundaries_use_shared_scorer(dataset):
    root, entries, chunks = dataset
    q = entries[0].gold
    spans = q.facts[0].support_sets[0]
    items = [EvidenceItem(id=s.chunk_id, excerpts=[dev.source_excerpt(s,chunks)]) for s in spans]
    assert score_evidence(q,dev.assembled_result(items[:1]),chunks)['evidence_fact_recall_at_6']==0
    assert score_evidence(q,dev.assembled_result(items),chunks)['evidence_fact_recall_at_6']==1
    truncated = spans[1].model_copy(update={'end':spans[1].end-1})
    clipped = EvidenceItem(id=truncated.chunk_id,excerpts=[dev.source_excerpt(truncated,chunks)])
    assert score_evidence(q,dev.assembled_result([items[0],clipped]),chunks)['evidence_fact_recall_at_6']==0
    # Renaming independent gold keys cannot change credit; graph claim keys are never consulted.
    renamed = q.model_copy(deep=True)
    renamed.facts[0].fact_id='another-independent-gold-key'
    renamed.sufficient_fact_sets=[['another-independent-gold-key']]
    assert score_evidence(renamed,dev.assembled_result(items),chunks)['evidence_fact_recall_at_6']==1
    assert score_evidence(entries[-1].gold,dev.assembled_result(items),chunks)['evidence_fact_recall_at_6'] is None


def test_hash_edits_and_changed_sources_fail_closed(dataset):
    root, _, chunks = dataset
    path = root/'annotations.jsonl'
    original = path.read_text(encoding='utf-8')
    path.write_text(original.replace('Synthetic answer.','Changed answer.'),encoding='utf-8')
    with pytest.raises(ValueError,match='hash changed'):
        dev.load_dataset(root)
    path.write_text(original,encoding='utf-8')
    c=chunks['a']
    chunks['a']=c.model_copy(update={'section':'Changed source metadata'})
    with pytest.raises(ValueError,match='source snapshot changed'):
        dev.load_dataset(root)


def test_external_and_held_out_inputs_are_rejected_before_dataset_read(dataset,monkeypatch,tmp_path):
    root, entries, _ = dataset
    def forbidden_read(*args,**kwargs):
        raise AssertionError('No file read should occur outside the development directory')
    with monkeypatch.context() as guard:
        guard.setattr(type(root),'read_text',forbidden_read)
        with pytest.raises(ValueError,match='inside data/evaluation/development'):
            dev.load_dataset(tmp_path/'external-inputs')
    payload=entries[0].model_dump(mode='json')
    payload['gold']['split']='held_out'
    with pytest.raises(ValidationError,match='development annotations only'):
        dev.DevelopmentAnnotation.model_validate(payload)


def test_category_precedence_and_allocation_are_enforced(dataset):
    _, entries, chunks=dataset
    payload=entries[4].model_dump(mode='json')
    payload['gold']['category']='cross_paper'
    with pytest.raises(ValidationError,match='takes category precedence'):
        dev.DevelopmentAnnotation.model_validate(payload)
    payload['gold']['category']='multi_hop'
    payload['reasoning_chain'][1]['source']='Disconnected'
    with pytest.raises(ValidationError,match='connected chain'):
        dev.DevelopmentAnnotation.model_validate(payload)
    with pytest.raises(ValueError,match='eight unique'):
        dev.validate_annotations(entries[:7],chunks)


def test_only_exact_displayed_human_decisions_validate_gold_and_replay_is_idempotent(dataset):
    root, _, _ = dataset
    dev.export_review_batch(root,['DEV-D1','DEV-D2'],'batch-01')
    choices={'DEV-D1':{'decision':'approved','reason':'Synthetic test only'}}
    args=(root,'batch-01','test-human.json','SYNTHETIC TEST FIXTURE','DEV-D1 approve; synthetic only',choices)
    result=dev.record_gold_decisions(*args,batch_seconds=120,verbatim_time_response='Synthetic two minutes')
    assert result['human_validated']==1 and result['ready'] is False
    assert result['questions']['DEV-D2']=='pending'
    checked = dev.check_dataset(root)
    assert checked['checks'][0]['semantic_validation']=='approved'
    assert checked['checks'][1]['semantic_validation']=='pending'
    receipt=root/'human-inputs/test-human.json'
    before=receipt.read_bytes()
    assert dev.record_gold_decisions(*args,batch_seconds=120,verbatim_time_response='Synthetic two minutes')==result
    assert receipt.read_bytes()==before
    record=json.loads(before)
    assert record['per_question_seconds'] is None and record['actual_batch_review_seconds_approx']==120
    with pytest.raises(ValueError,match='displayed development batch'):
        dev.record_gold_decisions(root,'batch-01','unseen.json','SYNTHETIC TEST FIXTURE','Unseen test',
            {'DEV-C1':{'decision':'approved','reason':'Synthetic'}})
    with pytest.raises(ValueError,match='finite'):
        dev.record_gold_decisions(*args,batch_seconds=float('nan'))
    with pytest.raises(ValueError,match='Preserve the existing receipt'):
        dev.record_gold_decisions(*args,batch_seconds=121)


def test_later_revocation_is_preserved_and_old_receipt_replay_cannot_resurrect_gold(dataset):
    root, _, _ = dataset
    dev.export_review_batch(root,['DEV-D1'],'batch-01')
    args=(root,'batch-01','approved.json','SYNTHETIC TEST FIXTURE','Approve test',
          {'DEV-D1':{'decision':'approved','reason':'Synthetic'}})
    dev.record_gold_decisions(*args)
    dev.record_gold_decisions(root,'batch-01','revoked.json','SYNTHETIC TEST FIXTURE','Needs review test',
        {'DEV-D1':{'decision':'needs_review','reason':'Synthetic revocation'}})
    # Fix distinct synthetic timestamps rather than depending on machine timer precision.
    for name,at in [('approved.json',datetime(2026,1,1,tzinfo=timezone.utc)),
                    ('revoked.json',datetime(2026,1,1,tzinfo=timezone.utc)+timedelta(seconds=1))]:
        path=root/'human-inputs'/name
        receipt=json.loads(path.read_text(encoding='utf-8'))
        receipt.pop('receipt_sha256')
        receipt['received_at']=at.isoformat()
        path.write_text(json.dumps({**receipt,'receipt_sha256':fingerprint(receipt)},indent=2)+'\n',encoding='utf-8')
    assert dev.record_gold_decisions(*args)['questions']['DEV-D1']=='needs_review'


def test_stale_batch_and_tampered_receipt_do_not_validate(dataset):
    root, _, _ = dataset
    path=dev.export_review_batch(root,['DEV-D1'],'batch-01')
    original=path.read_text(encoding='utf-8')
    batch=json.loads(original)
    batch['items'][0]['entry_sha256']='f'*64
    path.write_text(json.dumps(batch),encoding='utf-8')
    args=(root,'batch-01','human.json','SYNTHETIC TEST FIXTURE','Synthetic approve',
          {'DEV-D1':{'decision':'approved','reason':'Synthetic'}})
    with pytest.raises(ValueError,match='Stale annotation'):
        dev.record_gold_decisions(*args)
    path.write_text(original,encoding='utf-8')
    dev.record_gold_decisions(*args)
    receipt=root/'human-inputs/human.json'
    receipt.write_text(receipt.read_text(encoding='utf-8').replace('SYNTHETIC TEST FIXTURE','Edited'),encoding='utf-8')
    with pytest.raises(ValueError,match='receipt hash changed'):
        dev.review_status(root)
