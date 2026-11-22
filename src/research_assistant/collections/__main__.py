"""Thin collection/import/QA/review CLI calling the same services as Streamlit."""

import argparse
from contextlib import ExitStack
from datetime import datetime, timezone
import json
from pathlib import Path

from pydantic import ValidationError

from research_assistant.collections.scope import guard_user_write
from research_assistant.collections.store import CollectionRegistry
from research_assistant.settings import Settings, configure_caches


def main(argv: list[str] | None = None) -> int:
    """Call the same registry services intended for Streamlit, without hidden network work."""
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    commands.add_parser('list')
    commands.add_parser('jobs')
    job = commands.add_parser('job')
    job.add_argument('--job', required=True)
    create = commands.add_parser('create')
    create.add_argument('--name', required=True)
    show = commands.add_parser('show')
    show.add_argument('--collection', required=True)
    rename = commands.add_parser('rename')
    rename.add_argument('--collection', required=True)
    rename.add_argument('--expected-head', required=True)
    rename.add_argument('--name', required=True)
    commands.add_parser('scope-check')
    commands.add_parser('start', help='Start only the exact retained M8 container, without recreation')
    importing = commands.add_parser('import', help='Import explicitly supplied PDFs/links once, without generation')
    importing.add_argument('--collection', required=True)
    importing.add_argument('--expected-head', required=True)
    importing.add_argument('--pdf', action='append', type=Path, default=[])
    importing.add_argument('--url', action='append', default=[])
    query = commands.add_parser('query', help='Ask only the selected committed collection using shared services')
    query.add_argument('--collection', required=True)
    query.add_argument('--expected-head', required=True)
    query.add_argument('--question', required=True)
    query.add_argument('--mode', choices=['vector', 'hybrid', 'hybrid_facts', 'graph'], default='hybrid')
    query.add_argument('--generate', action='store_true')
    query.add_argument('--output', type=Path, required=True)
    export = commands.add_parser('export', help='Validate saved collection evidence without new inference')
    export.add_argument('--collection', required=True)
    export.add_argument('--run', type=Path, required=True)
    export.add_argument('--format', choices=['csv', 'json'], default='csv')
    export.add_argument('--output', type=Path, required=True)
    review_commands = {}
    for name in ['review-status','review-propose','review-extract','review-present','review-decide','review-publish']:
        sub = commands.add_parser(name)
        sub.add_argument('--collection',required=True)
        sub.add_argument('--expected-head',required=True)
        review_commands[name] = sub
    for name in ['review-propose','review-extract']:
        review_commands[name].add_argument('--chunk-id',required=True)
    review_commands['review-propose'].add_argument('--draft',type=Path,required=True)
    review_commands['review-propose'].add_argument('--entities',type=Path)
    review_commands['review-propose'].add_argument('--supersedes')
    review_commands['review-propose'].add_argument('--expected-revision')
    review_commands['review-present'].add_argument('--claim',required=True)
    review_commands['review-present'].add_argument('--output',type=Path,required=True)
    review_commands['review-decide'].add_argument('--presentation',type=Path,required=True)
    review_commands['review-decide'].add_argument('--response',type=Path,required=True)
    review_commands['review-publish'].add_argument('--review-head',required=True)
    args = parser.parse_args(argv)
    try:
        settings = Settings.from_env()
    except ValueError:
        print(json.dumps({'status': 'failed', 'error': 'invalid_settings',
                          'message': 'Invalid local settings; check configuration without sharing credentials'}))
        return 2
    try:
        registry = CollectionRegistry()
        configure_caches()
        if args.command in {'query', 'export', 'review-present'} and args.output.exists():
            raise ValueError('Output file exists; choose a new path before executing')
        if args.command == 'scope-check':
            guard_user_write(settings)
            result = {'status': 'passed', 'scope_id': registry.scope.scope_id,
                      'target_uri': registry.scope.target_uri}
        elif args.command == 'start':
            from research_assistant.collections.scope import start_user_target
            result = start_user_target(settings)
        elif args.command == 'list':
            result = {'collections': [registry.describe(row) for row in registry.list()]}
        elif args.command == 'jobs':
            result = {'jobs': [job.model_dump(mode='json') for job in registry.jobs()]}
        elif args.command == 'job':
            result = registry.get_job(args.job).model_dump(mode='json')
        elif args.command.startswith('review-'):
            from research_assistant.collections import reviews
            from research_assistant.collections.workspace import verify_collection
            from research_assistant.collections.proposals import extract_proposals
            from research_assistant.extraction.contracts import ProposedClaim
            from research_assistant.pipeline import write_immutable
            if args.command == 'review-status':
                ready = verify_collection(registry,args.collection,settings,args.expected_head)
                result = reviews.review_status(registry,ready,settings)
            elif args.command == 'review-propose':
                draft = ProposedClaim.model_validate_json(args.draft.read_bytes())
                result = reviews.propose_claim(registry,args.collection,args.expected_head,draft,args.chunk_id,settings,
                    entity_ids=json.loads(args.entities.read_bytes()) if args.entities else None,
                    supersedes=args.supersedes,expected_revision=args.expected_revision).model_dump(mode='json')
            elif args.command == 'review-extract':
                result = extract_proposals(registry,args.collection,args.expected_head,args.chunk_id,settings)
            elif args.command == 'review-present':
                shown = reviews.present_claim(registry,args.collection,args.expected_head,args.claim,settings)
                write_immutable(args.output,shown.model_dump_json(indent=2)+'\n')
                result = {'presentation_sha256':shown.sha256,'output':str(args.output)}
            elif args.command == 'review-decide':
                shown = reviews.ReviewPresentation.model_validate_json(args.presentation.read_bytes())
                response = reviews.UIResponse.model_validate_json(args.response.read_bytes())
                result = reviews.record_decision(registry,args.collection,args.expected_head,shown,response,settings)
            else:
                result = reviews.publish_review(registry,args.collection,args.expected_head,args.review_head,settings)
        elif args.command == 'query':
            from research_assistant.collections.workspace import query_collection
            from research_assistant.pipeline import write_immutable
            run = query_collection(registry, args.collection, args.expected_head,
                args.question, args.mode, settings, generate=args.generate)
            write_immutable(args.output, run.model_dump_json(indent=2) + '\n')
            result = {'status': 'passed', 'run_id': run.run_id, 'output': str(args.output),
                      'evidence_units': len(run.retrieval.evidence), 'generation_requested': run.generation_requested}
        elif args.command == 'export':
            from research_assistant.collections.workspace import checked_output
            from research_assistant.contracts import RunArtifact
            from research_assistant.pipeline import write_immutable
            run = RunArtifact.model_validate_json(args.run.read_bytes())
            _, csv_text, _ = checked_output(registry, args.collection, run, settings)
            write_immutable(args.output, '\ufeff' + csv_text if args.format == 'csv' else run.model_dump_json(indent=2) + '\n')
            result = {'status': 'passed', 'output': str(args.output), 'new_generation_requests': 0}
        elif args.command == 'import':
            from research_assistant.collections.contracts import InputReference
            from research_assistant.ingestion.user_import import ImportInput, run_import
            with ExitStack() as stack:
                entries = [ImportInput(InputReference(kind='upload', value=path.name),
                    stack.enter_context(path.open('rb'))) for path in args.pdf]
                entries.extend(ImportInput(InputReference(kind='url', value=url)) for url in args.url)
                job = registry.queue(args.collection, args.expected_head, tuple(e.reference for e in entries))
                result = run_import(registry, job.job_id, entries, settings)
            print(json.dumps(result, indent=2))
            return 0 if result['status'] in {'ready', 'duplicate'} else 1
        elif args.command == 'create':
            result = registry.describe(registry.create(args.name))
        elif args.command == 'rename':
            result = registry.describe(registry.revise(args.collection, args.expected_head, name=args.name))
        else:
            result = registry.describe(registry.get(args.collection))
        print(json.dumps(result, indent=2))
        return 1 if result.get('status') == 'failed' else 0
    except Exception as exc:
        message = (exc.errors(include_input=False, include_url=False)[0]['msg']
                   if isinstance(exc, ValidationError) else str(exc))
        print(json.dumps({'status': 'failed', 'created_at': datetime.now(timezone.utc).isoformat(),
            'error': type(exc).__name__, 'message': settings.redact(message)}))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
