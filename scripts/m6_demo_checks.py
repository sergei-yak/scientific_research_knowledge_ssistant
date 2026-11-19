"""Bounded public product checks; never reads evaluation inputs or changes source data."""
import argparse
import csv
import io
import json
from datetime import datetime, timezone
from pathlib import Path

from research_assistant.contracts import QueryRequest
from research_assistant.embeddings import Encoder
from research_assistant.pipeline import QueryExecutionError, run_query, write_immutable
from research_assistant.product import WORKFLOWS, prepare_output
from research_assistant.product_catalog import product_target
from research_assistant.settings import Settings, configure_caches

ROOT = Path('runs/m6')


def event(value):
    """Append attempts rather than resetting a demo allowance after a failure."""
    value['recorded_at_utc'] = datetime.now(timezone.utc).isoformat()
    with (ROOT/'activity.jsonl').open('a', encoding='utf-8') as out:
        out.write(json.dumps(value)+'\n')


def reserve(label, generate):
    """Bound local product probes independently of all consumed research ledgers."""
    scope = json.loads((ROOT/'scope-v1.json').read_text(encoding='utf-8'))
    ledger = ROOT/'activity.jsonl'
    entries = [json.loads(line) for line in ledger.read_text(encoding='utf-8').splitlines()] if ledger.exists() else []
    attempts = [row for row in entries if row['event'] == 'reservation']
    if any(row['label'] == label for row in attempts):
        raise ValueError('This demo check was already attempted; preserve its outcome')
    if len(attempts) >= scope['max_logical_retrieval_checks'] or (generate and sum(row['generate'] for row in attempts) >= scope['max_local_generation_attempts']):
        raise ValueError('Recorded demo allowance is exhausted')
    event({'event':'reservation','label':label,'generate':generate})


def main():
    """Check all modes/corpus bindings, then optional explicit local Qwen answers."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--generate', action='store_true')
    args = parser.parse_args()
    configure_caches()
    settings = Settings.from_env()
    if settings.generation_provider != 'ollama':
        raise ValueError('This demonstration authorizes local Ollama only')
    encoder, results, summaries = Encoder(), {}, []
    cases = []
    for key in ['pilot','expanded']:
        for mode in ['vector','hybrid','hybrid_facts','graph']:
            cases.append((key+'-'+mode,key,'baseline','reference',mode,'comparison',WORKFLOWS['comparison'],False))
    for selector in ['reference','cross_encoder']:
        cases.append(('v2-'+selector,'expanded','retrieval-v2',selector,'graph','comparison',WORKFLOWS['comparison'],False))
    cases.append(('v2-public-connection','expanded','retrieval-v2','reference','graph','ask',
        'What scaling caveat does the GraphRAG survey describe, and what remains unvalidated in original HippoRAG?',False))
    if args.generate:
        cases += [
            ('answer-pilot-discovery','pilot','baseline','reference','graph','discovery',WORKFLOWS['discovery'],True),
            ('answer-expanded-lightrag','expanded','baseline','reference','hybrid','ask',
                'What do LightRAG low-level and high-level retrieval strategies retrieve?',True),
            ('answer-expanded-limitations','expanded','baseline','reference','graph','limitations',WORKFLOWS['limitations'],True),
            ('answer-expanded-unknown','expanded','baseline','reference','hybrid','ask',
                'What exact carbon emissions in kilograms of CO2e are reported for Graph RAG Behind the Tech evaluation?',True)]
    for label,key,profile,selector,mode,workflow,question,generate in cases:
        reserve(label,generate)
        collection,target,scope_file = product_target(key,profile,settings)
        request = QueryRequest(question=question,corpus_id=collection.corpus_id,mode=mode,
            profile_id=profile,selector_id=selector,scope_file=scope_file)
        try:
            run = run_query(request,target,review_directory=collection.review_directory,
                generate=generate,workflow=workflow,encoder=encoder)
            write_immutable(ROOT/'checks'/label/'run.json',run.model_dump_json(indent=2)+'\n')
            view, export = prepare_output(run,target,collection.review_directory)
            write_immutable(ROOT/'checks'/label/'evidence.csv',export)
            rows = list(csv.DictReader(io.StringIO(export)))
            assert len(rows) == sum(len(item.excerpts) for item in run.retrieval.evidence)
            assert run.retrieval.estimated_tokens <= 1800 and len(run.retrieval.evidence) <= 6
            assert run.result is not None if generate else run.result is None
            results[label] = run
            summary = {'label':label,'status':'passed','run_id':run.run_id,'requested':mode,
                'effective':run.retrieval.effective_mode,'fallback':run.retrieval.fallback_reason,
                'evidence_units':len(run.retrieval.evidence),'export_rows':len(rows),
                'graph_connections':sum(len(item.graph_paths) for item in run.retrieval.evidence),
                'workflow_status':view.status,'approved_rows':len(view.rows),
                'generation_requested':generate,'provider_called':run.generation is not None,
                'insufficient_evidence':run.result.insufficient_evidence if run.result else None,
                'citation_count':len(run.result.citations) if run.result else None,
                'retrieval_ms':run.retrieval.retrieval_ms,
                'generation_ms':run.generation.elapsed_ms if run.generation else None}
            event({'event':'completed',**summary})
        except Exception as exc:
            if isinstance(exc, QueryExecutionError):
                write_immutable(ROOT/'checks'/label/'failed-run.json',exc.artifact.model_dump_json(indent=2)+'\n')
            summary = {'label':label,'status':'failed','error_type':type(exc).__name__,'message':settings.redact(str(exc))}
            event({'event':'failed',**summary})
        summaries.append(summary)
        print(json.dumps(summary),flush=True)
    parity = {}
    for key in ['pilot','expanded']:
        graph,facts = results.get(key+'-graph'),results.get(key+'-hybrid_facts')
        parity[key] = bool(graph and facts and (not graph.retrieval.fallback_reason or graph.retrieval.context_sha256 == facts.retrieval.context_sha256))
    report = {'checks':summaries,'fallback_context_parity':parity,'all_passed':all(s['status']=='passed' for s in summaries) and all(parity.values()),
        'private_inputs_read':0,'database_mutations':0,'paid_calls':0,'automatic_retries':0}
    write_immutable(ROOT/'live-checks.json',json.dumps(report,indent=2)+'\n')
    return 0 if report['all_passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
