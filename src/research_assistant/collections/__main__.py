"""Thin collection/import CLI; the upload interface follows in M8.3."""

import argparse
from contextlib import ExitStack
from datetime import datetime, timezone
import json
from pathlib import Path

from pydantic import ValidationError

from research_assistant.collections.scope import guard_user_write
from research_assistant.collections.store import CollectionRegistry
from research_assistant.settings import Settings


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
    importing = commands.add_parser('import', help='Import explicitly supplied PDFs/links once, without generation')
    importing.add_argument('--collection', required=True)
    importing.add_argument('--expected-head', required=True)
    importing.add_argument('--pdf', action='append', type=Path, default=[])
    importing.add_argument('--url', action='append', default=[])
    args = parser.parse_args(argv)
    try:
        settings = Settings.from_env()
    except ValueError:
        print(json.dumps({'status': 'failed', 'error': 'invalid_settings',
                          'message': 'Invalid local settings; check configuration without sharing credentials'}))
        return 2
    try:
        registry = CollectionRegistry()
        if args.command == 'scope-check':
            guard_user_write(settings)
            result = {'status': 'passed', 'scope_id': registry.scope.scope_id,
                      'target_uri': registry.scope.target_uri}
        elif args.command == 'list':
            result = {'collections': [registry.describe(row) for row in registry.list()]}
        elif args.command == 'jobs':
            result = {'jobs': [job.model_dump(mode='json') for job in registry.jobs()]}
        elif args.command == 'job':
            result = registry.get_job(args.job).model_dump(mode='json')
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
        return 0
    except Exception as exc:
        message = (exc.errors(include_input=False, include_url=False)[0]['msg']
                   if isinstance(exc, ValidationError) else str(exc))
        print(json.dumps({'status': 'failed', 'created_at': datetime.now(timezone.utc).isoformat(),
            'error': type(exc).__name__, 'message': settings.redact(message)}))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
