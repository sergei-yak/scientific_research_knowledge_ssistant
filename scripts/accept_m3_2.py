"""Bounded development product scenarios; no gold inputs, graph writes or paid-provider calls."""

import argparse
import json
import time
from pathlib import Path

from research_assistant.contracts import QueryRequest
from research_assistant.embeddings import Encoder
from research_assistant.pipeline import QueryExecutionError, code_identity, run_query, write_immutable
from research_assistant.product import PILOT_CORPUS, WORKFLOWS, prepare_output
from research_assistant.settings import Settings, configure_caches


def main() -> int:
    """Save one immutable run/view/CSV per scenario, with at most four explicit local calls."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path, required=True)
    parser.add_argument('--generate', action='store_true', help='Permit one local Qwen call per scenario, no retries')
    parser.add_argument('--scenario', nargs='+', choices=['discovery', 'comparison', 'limitations', 'abstention'],
                        help='Run only these scenarios; omitted means all four')
    args = parser.parse_args()
    if args.output_dir.exists():
        parser.error('Choose a new output directory')
    configure_caches()
    settings = Settings.from_env()
    if args.generate and settings.generation_provider != 'ollama':
        parser.error('This acceptance runner permits only the explicitly selected local provider')
    started = time.perf_counter()
    encoder = Encoder()
    load_seconds = time.perf_counter() - started
    scenarios = [(key, key, WORKFLOWS[key]) for key in ('discovery', 'comparison', 'limitations')]
    scenarios.append(('abstention', 'ask', 'What measured QA improvement does the original HippoRAG paper report from directly fine-tuning its NER and OpenIE components?'))
    if args.scenario:
        scenarios = [scenario for scenario in scenarios if scenario[0] in args.scenario]
    results = []
    for name, workflow, question in scenarios:
        print(f'Starting {name}; generate={args.generate}', flush=True)
        try:
            run = run_query(QueryRequest(corpus_id=PILOT_CORPUS, mode='graph', question=question),
                            settings, generate=args.generate, workflow=workflow, encoder=encoder)
        except QueryExecutionError as exc:
            write_immutable(args.output_dir / name / 'failed-run.json', exc.artifact.model_dump_json(indent=2) + '\n')
            results.append({'scenario': name, 'contract_pass': False, 'error': str(exc),
                            'generation_ms': exc.artifact.generation.elapsed_ms if exc.artifact.generation else None})
            print(json.dumps(results[-1]), flush=True)
            continue
        directory = args.output_dir / name
        write_immutable(directory / 'run.json', run.model_dump_json(indent=2) + '\n')
        view, csv_text = prepare_output(run, settings)
        write_immutable(directory / 'view.json', view.model_dump_json(indent=2) + '\n')
        write_immutable(directory / 'evidence.csv', csv_text)
        row = {'scenario': name, 'view_status': view.status, 'papers': view.paper_count,
               'methods': view.method_count, 'approved_rows': len(view.rows),
               'units': len(run.retrieval.evidence), 'estimated_tokens': run.retrieval.estimated_tokens,
               'requested_mode': run.retrieval.requested_mode, 'effective_mode': run.retrieval.effective_mode,
               'fallback_reason': run.retrieval.fallback_reason,
               'graph_rows_inspected': run.retrieval.audit.get('graph_rows'),
               'selected_graph_paths': sum(len(item.graph_paths) for item in run.retrieval.evidence),
               'generation_ms': run.generation.elapsed_ms if run.generation else None,
               'insufficient_evidence': run.result.insufficient_evidence if run.result else None,
               'context_sha256': run.retrieval.context_sha256}
        row['contract_pass'] = (bool(run.result and run.result.insufficient_evidence and not run.result.citations)
                                if name == 'abstention' and args.generate else view.status == 'evidence available')
        results.append(row)
        print(json.dumps(row), flush=True)
    summary = {'task_id': 'M3.2', **code_identity(), 'encoder_load_seconds': load_seconds,
               'scenarios': results, 'new_local_calls': sum(row['generation_ms'] is not None for row in results),
               'paid_calls': 0, 'gold_inputs': 0, 'held_out_accesses': 0,
               'note': 'Development product checks, not blinded semantic answer scoring or a Graph advantage.'}
    write_immutable(args.output_dir / 'summary.json', json.dumps(summary, indent=2) + '\n')
    return 0 if all(row['contract_pass'] for row in results) else 1


if __name__ == '__main__':
    raise SystemExit(main())
