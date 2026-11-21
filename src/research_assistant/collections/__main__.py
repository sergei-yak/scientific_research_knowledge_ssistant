"""Thin registry CLI; import execution and the upload UI follow in M8.2/M8.3."""

import argparse
from datetime import datetime, timezone
import json

from research_assistant.collections.scope import guard_user_write
from research_assistant.collections.store import CollectionRegistry
from research_assistant.settings import Settings


def main(argv: list[str] | None = None) -> int:
    """Call the same registry services intended for Streamlit, without hidden network work."""
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    commands.add_parser('list')
    create = commands.add_parser('create')
    create.add_argument('--name', required=True)
    show = commands.add_parser('show')
    show.add_argument('--collection', required=True)
    rename = commands.add_parser('rename')
    rename.add_argument('--collection', required=True)
    rename.add_argument('--expected-head', required=True)
    rename.add_argument('--name', required=True)
    commands.add_parser('scope-check')
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
        elif args.command == 'create':
            result = registry.describe(registry.create(args.name))
        elif args.command == 'rename':
            result = registry.describe(registry.revise(args.collection, args.expected_head, name=args.name))
        else:
            result = registry.describe(registry.get(args.collection))
        print(json.dumps(result, indent=2))
        return 0
    except Exception as exc:
        print(json.dumps({'status': 'failed', 'created_at': datetime.now(timezone.utc).isoformat(),
            'error': type(exc).__name__, 'message': settings.redact(str(exc))}))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
