"""Score sealed M5.4 public development artifacts offline; never run retrieval/inference."""

import json
from collections import Counter
from pathlib import Path
from statistics import mean, median

from research_assistant.contracts import EvidenceItem, RunArtifact, RetrievalResult, fingerprint, text_sha
from research_assistant.evaluation.development import load_dataset, review_status
from research_assistant.evaluation.freeze import file_sha
from research_assistant.evaluation.retrieval_diagnostics import incremental_graph_support, validate_candidates
from research_assistant.evaluation.scoring import score_candidates, score_evidence
from research_assistant.pipeline import write_immutable
from research_assistant.retrieval.catalog import load_catalog
from research_assistant.retrieval.evidence import assemble_evidence, estimate_tokens, render_context, validate_context
from research_assistant.review.store import review_lock
from research_assistant.settings import configure_caches

ROOT = Path('runs/retrieval-v2/m5-4/comparison-v1')
DATA = Path('data/evaluation/development/expansion-v1')
REVIEW = Path('data/reviews/expansion-v1')


def result_from_items(items):
    """Represent actual selected units only, preserving the normal <=6/1800 contract."""
    context, aliases = render_context(items)
    return RetrievalResult(requested_mode='graph', effective_mode='graph', evidence=items, context=context,
        context_sha256=text_sha(context), aliases=aliases, estimated_tokens=estimate_tokens(context), candidates=[], retrieval_ms=0)


def main():
    """Validate all saved pools, replay packing, report every arm and operational graph signal."""
    if (ROOT/'offline-results.json').exists():
        raise ValueError('Keep immutable offline results; disclose any later amendment')
    manifest = json.loads((ROOT/'execution-manifest.json').read_text(encoding='utf-8'))
    complete = json.loads((ROOT/'execution-complete.json').read_text(encoding='utf-8'))
    assert complete['attempts'] == 96 and complete['failures'] == 0
    for path, sha in manifest['file_sha256'].items():
        assert file_sha(Path(path)) == sha
    dataset, entries, chunks = load_dataset(DATA)
    status = review_status(DATA)
    assert status['ready']
    questions = {e.gold.question_id: e.gold for e in entries}
    assert list(questions) == manifest['policy']['development_ids']
    with review_lock(REVIEW):
        catalog = load_catalog(REVIEW, dataset['corpus_id'], chunks)
    assert fingerprint(catalog.facts) == manifest['readiness']['catalog_sha256']
    rows = []; runs = {}; pools = {}; checks = []; common = {}
    def check(name, condition):
        checks.append({'name': name, 'passed': bool(condition)})
        if not condition:
            raise ValueError(name)
    for outcome in complete['outcomes']:
        qid, arm, mode = outcome['question_id'], outcome['arm'], outcome['mode']
        path = ROOT/'runs'/(outcome['id']+'.json')
        check('saved_run_hash:'+outcome['id'], file_sha(path)==outcome['run_sha256'])
        run = RunArtifact.model_validate_json(path.read_bytes()); result = run.retrieval; audit = result.audit
        check('exact_question:'+outcome['id'], run.request.question==questions[qid].question)
        check('no_generation:'+outcome['id'], not run.generation_requested and run.generation is None and run.result is None)
        check('source_tree:'+outcome['id'], run.configuration['source_tree_sha256']==manifest['source_tree_sha256'])
        check('snapshot:'+outcome['id'], run.corpus_manifest==manifest['readiness']['snapshot'])
        if mode in {'hybrid_facts','graph'}:
            check('current_head:'+outcome['id'], audit['review_head']==catalog.head)
        validate_context(result, chunks)
        baseline = [EvidenceItem.model_validate(item) for item in audit['eligible_candidates']]
        candidates = [EvidenceItem.model_validate(item) for item in audit.get('graph_eligible_candidates', audit['eligible_candidates'])]
        validate_candidates(baseline, chunks, catalog); validate_candidates(candidates, chunks, catalog)
        chosen, context, aliases, tokens, decisions = assemble_evidence(baseline if result.fallback_reason else candidates)
        check('packer_replay:'+outcome['id'], chosen==result.evidence and context==result.context and aliases==result.aliases and tokens==result.estimated_tokens)
        pre_items = [EvidenceItem.model_validate(item) for item in audit.get('pre_fallback_evidence', [])]
        if mode=='graph':
            pre_chosen, pre_context, _, _, pre_decisions = assemble_evidence(candidates)
            check('prefallback_replay:'+outcome['id'], pre_chosen==pre_items and text_sha(pre_context)==audit['pre_fallback_context_sha256'] and pre_decisions==audit['pre_fallback_decisions'])
        final = score_evidence(questions[qid], result, chunks)
        candidate_score = score_candidates(questions[qid], candidates, chunks)
        baseline_score = score_candidates(questions[qid], baseline, chunks)
        row = {'id': outcome['id'], 'question_id': qid, 'arm': arm, 'mode': mode,
            'category': questions[qid].category, 'final': final, 'candidate': candidate_score, 'baseline_candidate': baseline_score,
            'candidate_ids': [i.id for i in candidates], 'baseline_candidate_ids': [i.id for i in baseline],
            'final_ids': [i.id for i in result.evidence],
            'raw_final_ids': [i.id for i in result.evidence if i.kind=='chunk'],
            'paper_ids': sorted({p for i in result.evidence for p in i.paper_ids}),
            'paper_count': len({p for i in result.evidence for p in i.paper_ids}),
            'estimated_tokens': result.estimated_tokens, 'effective_mode': result.effective_mode,
            'fallback_reason': result.fallback_reason, 'graph_rows': audit.get('graph_rows'),
            'graph_call_count': len(audit.get('graph_calls', [])),
            'graph_rows_by_family': dict(Counter(c['template'] for c in audit.get('graph_calls', []) for _ in c['rows'])),
            'graph_unique_targets': len({r['id'] for r in audit.get('graph_row_outcomes', [])}),
            'graph_duplicate_rows': sum(r['duplicate'] for r in audit.get('graph_row_outcomes', [])),
            'graph_rows_already_baseline': sum(r['baseline_member'] for r in audit.get('graph_row_outcomes', [])),
            'retained_graph_ids': audit.get('graph_candidates_retained'),
            'selected_paths': {i.id: i.graph_paths for i in result.evidence if i.graph_paths},
            'prefallback': score_evidence(questions[qid], result_from_items(pre_items), chunks) if mode=='graph' else None,
            'prefallback_exclusions': dict(Counter(d['reason'] or 'selected' for d in audit.get('pre_fallback_decisions', []))),
            'final_exclusions': dict(Counter(d.get('reason') or 'selected' for d in result.candidates)),
            'inner_retrieval_ms': result.retrieval_ms, 'scope_inclusive_ms': audit.get('request_elapsed_ms'),
            'run_query_wall_ms': outcome['run_query_wall_ms'], 'export_validation_ms': outcome['export_validation_ms'],
            'reranker_readiness': audit.get('reranker_readiness'), 'selection_pairs': audit.get('selection', {}).get('pairs_inferred'),
            'selection_cache_hits': sum(s['cache_hits'] for s in audit.get('selection', {}).get('stages', {}).values()) if arm=='A2' else None,
            'selection_stage_ms': {name: s['elapsed_ms'] for name, s in audit.get('selection', {}).get('stages', {}).items()},
            'resources': run.configuration['resources_after_generation']}
        if arm=='A2':
            selection = audit['selection']
            check('neural_budget:'+outcome['id'], selection['unique_candidates']<=88 and selection['pairs_inferred']<=88)
            for stage in selection['stages'].values():
                for item in stage['rows']:
                    key = qid, item['feature_sha256']
                    check('shared_score:'+outcome['id']+':'+item['id'], key not in common or common[key]==item['score'])
                    common[key] = item['score']
        rows.append(row); runs[qid, arm, mode] = run; pools[qid, arm, mode] = baseline
    contrasts = []
    for qid in questions:
        for arm, _, _ in manifest['arms']:
            graph = runs[qid, arm, 'graph'].retrieval; ablation = runs[qid, arm, 'hybrid_facts'].retrieval
            baseline_ids = {i.id for i in pools[qid, arm, 'hybrid_facts']}
            check('graph_baseline_pool:'+qid+arm, baseline_ids=={i.id for i in pools[qid, arm, 'graph']})
            if graph.fallback_reason:
                check('exact_fallback:'+qid+arm, all(getattr(graph,k)==getattr(ablation,k) for k in ('context','context_sha256','evidence','aliases','estimated_tokens','candidates')))
            row = {'question_id': qid, 'arm': arm, 'category': questions[qid].category,
                **incremental_graph_support(questions[qid], graph, ablation, baseline_ids, chunks),
                'same_context': graph.context_sha256==ablation.context_sha256,
                'raw_retained': sorted({i.id for i in graph.evidence if i.kind=='chunk'} & {i.id for i in ablation.evidence if i.kind=='chunk'}),
                'raw_displaced': sorted({i.id for i in ablation.evidence if i.kind=='chunk'} - {i.id for i in graph.evidence if i.kind=='chunk'}),
                'raw_added': sorted({i.id for i in graph.evidence if i.kind=='chunk'} - {i.id for i in ablation.evidence if i.kind=='chunk'})}
            contrasts.append(row)
        for mode in ('vector','hybrid','hybrid_facts'):
            check('reference_parity:'+qid+mode, runs[qid,'A0',mode].retrieval.context_sha256==runs[qid,'A1',mode].retrieval.context_sha256)
            check('fixed_non_graph_pool:'+qid+mode, {i.id for i in pools[qid,'A1',mode]}=={i.id for i in pools[qid,'A2',mode]})
    summary = []; signals = []
    for arm, _, _ in manifest['arms']:
        for mode in manifest['modes']:
            subset = [r for r in rows if r['arm']==arm and r['mode']==mode]
            answerable = [r for r in subset if r['category']!='unanswerable']
            summary.append({'arm': arm, 'mode': mode, 'answerable_n': len(answerable),
                'mean_candidate_support': mean(r['candidate']['candidate_support_recall'] for r in answerable),
                'mean_final_recall_at_6': mean(r['final']['evidence_fact_recall_at_6'] for r in answerable),
                'fallbacks_all_8': sum(bool(r['fallback_reason']) for r in subset),
                'selected_novel_all_8': sum(len(c['novel_selected_ids']) for c in contrasts if c['arm']==arm),
                'mean_run_query_wall_ms': mean(r['run_query_wall_ms'] for r in subset),
                'median_run_query_wall_ms': median(r['run_query_wall_ms'] for r in subset),
                'min_run_query_wall_ms': min(r['run_query_wall_ms'] for r in subset),
                'max_run_query_wall_ms': max(r['run_query_wall_ms'] for r in subset)})
        if arm!='A0':
            graph_mean = next(r['mean_final_recall_at_6'] for r in summary if r['arm']==arm and r['mode']=='graph')
            base_mean = next(r['mean_final_recall_at_6'] for r in summary if r['arm']==arm and r['mode']=='hybrid_facts')
            witnessed = [r['question_id'] for r in contrasts if r['arm']==arm and r['category']!='unanswerable' and r['has_incremental_support']]
            signals.append({'arm': arm, 'graph_mean': graph_mean, 'ablation_mean': base_mean,
                'paired_delta': graph_mean-base_mean, 'witnessed_question_ids': witnessed,
                'signal_passed': bool(witnessed) and graph_mean-base_mean>1e-12})
    interactions = []
    for qid in questions:
        left = runs[qid,'A1','graph'].retrieval.audit; right = runs[qid,'A2','graph'].retrieval.audit
        interactions.append({'question_id': qid, 'anchors_changed': left['anchors']!=right['anchors'],
            'retained_graph_pool_changed': set(left['graph_candidates_retained'])!=set(right['graph_candidates_retained']),
            'A1_anchors': left['anchors'], 'A2_anchors': right['anchors']})
    output = {'task_id': 'M5.4', 'execution_manifest_sha256': file_sha(ROOT/'execution-manifest.json'),
        'development_readiness': status, 'checks_passed': len(checks), 'checks': checks,
        'summary': summary, 'paired_graph_signal': signals, 'graph_signal_passed': any(s['signal_passed'] for s in signals),
        'operational_gate': 'Quality signal only here; final acceptance also requires test/plan/preservation integrity.',
        'rows': rows, 'contrasts': contrasts, 'selector_anchor_interactions': interactions,
        'actual_scored_feature_count': len(common), 'private_access': False,
        'generation': 0, 'paid': 0, 'metric_limits': manifest['scoring']}
    write_immutable(ROOT/'offline-results.json', json.dumps(output, indent=2, ensure_ascii=False)+'\n')
    print(json.dumps({k:output[k] for k in ('checks_passed','summary','paired_graph_signal','graph_signal_passed')}, indent=2))


if __name__ == '__main__':
    configure_caches(); main()
