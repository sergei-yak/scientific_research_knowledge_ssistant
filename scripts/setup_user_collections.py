"""Provision one NEW empty M8 target; never restore, reset or reuse an existing scope/volume."""

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import secrets
import socket
import subprocess
import time
from uuid import uuid4

from neo4j import GraphDatabase

from research_assistant.collections.scope import IMAGE_ID, SCOPE_FILE, UserCollectionScope, inspect_target
from research_assistant.collections.store import CollectionRegistry
from research_assistant.pipeline import write_immutable


def main() -> None:
    """Check fresh paths and resources, then bind an empty database and local registry once."""
    root = Path.cwd().resolve()
    if not (root / '.git').exists() or any((root / p).exists() for p in
            ('.env', str(SCOPE_FILE), 'data/user-collections')):
        raise ValueError('Use a fresh project checkout with no environment, user scope or registry')
    subprocess.run(['docker', 'image', 'inspect', IMAGE_ID], capture_output=True, check=True, timeout=20)
    ident = uuid4().hex[:12]
    project = 'dbu-m8-user-' + ident
    for name in (project + '_neo4j_data', project + '_neo4j_logs'):
        if subprocess.run(['docker', 'volume', 'inspect', name], capture_output=True, timeout=20).returncode == 0:
            raise ValueError('Fresh UUID target volume already exists')
    sockets = [socket.socket(), socket.socket()]
    try:
        for probe in sockets:
            probe.bind(('127.0.0.1', 0))
        bolt, http = [probe.getsockname()[1] for probe in sockets]
    finally:
        for probe in sockets:
            probe.close()
    password = secrets.token_hex(24)
    env = '\n'.join(['COMPOSE_PROJECT_NAME=' + project, 'NEO4J_IMAGE=' + IMAGE_ID,
        'NEO4J_USER=neo4j', 'NEO4J_PASSWORD=' + password, 'NEO4J_READ_ONLY=false',
        f'NEO4J_URI=bolt://127.0.0.1:{bolt}', f'NEO4J_BOLT_PORT={bolt}', f'NEO4J_HTTP_PORT={http}',
        'GENERATION_PROVIDER=ollama', 'GENERATION_MODEL=qwen3.8:latest',
        'EXTRACTION_PROVIDER=ollama', 'EXTRACTION_MODEL=qwen3.8:latest',
        'API_BUDGET_APPROVED=false', 'API_BUDGET_USD=0', 'MAX_RETRIES=0',
        'MAX_CONCURRENCY=1', 'OLLAMA_CONTEXT_TOKENS=4096', 'MAX_OUTPUT_TOKENS=512']) + '\n'
    write_immutable(root / '.env', env)
    run = root / 'runs/m8/m8-1'
    write_immutable(run / 'target-plan.json', json.dumps({'task_id': 'M8.1', 'project': project,
        'image_id': IMAGE_ID, 'bolt_port': bolt, 'http_port': http,
        'created_at': datetime.now(timezone.utc).isoformat(), 'purpose': 'new empty user collections only',
        'model_requests': 0, 'paid_spend': 0}, indent=2) + '\n')
    command = ['docker', 'compose', '--env-file', str(root / '.env'), '-p', project,
               '-f', str(root / 'compose.yaml')]
    # Do not inherit another checkout's Compose project, ports, image or paid settings.
    process_env = {k: v for k, v in os.environ.items() if not k.startswith(('NEO4J_', 'COMPOSE_'))}
    result = subprocess.run(command + ['up', '-d', '--pull', 'never', 'neo4j'], env=process_env,
        capture_output=True, text=True, timeout=120)
    write_immutable(run / 'target-startup.log', result.stdout + result.stderr)
    result.check_returncode()
    container = json.loads(subprocess.check_output(['docker', 'inspect', project + '-neo4j-1']))[0]
    scope = UserCollectionScope(scope_id='m8user-' + ident, worktree_root=str(root),
        storage_root=str(root / 'data/user-collections'), target_project=project,
        target_uri=f'bolt://127.0.0.1:{bolt}', container_id=container['Id'],
        volumes=(project + '_neo4j_data', project + '_neo4j_logs'))
    inspect_target(scope)
    driver = GraphDatabase.driver(scope.target_uri, auth=('neo4j', password),
        connection_timeout=2, max_transaction_retry_time=0)
    try:
        for attempt in range(30):
            try:
                driver.verify_connectivity()
                break
            except Exception:
                if attempt == 29:
                    raise
                time.sleep(1)
        with driver.session(database='neo4j') as session:
            if session.run('MATCH (n) RETURN count(n) AS n').single()['n']:
                raise ValueError('New target unexpectedly contains data; refusing setup')
            write_immutable(root / SCOPE_FILE, scope.model_dump_json(indent=2) + '\n')
            session.run('CREATE (o:UserCollectionWorkspace {id:$id,scope_sha256:$sha})',
                id=scope.scope_id, sha=scope.sha256).consume()
    finally:
        driver.close()
    registry = CollectionRegistry(root)
    registry.initialize()
    output = {'status': 'passed', 'scope': scope.model_dump(mode='json'),
              'scope_sha256': scope.sha256, 'registry_collections': len(registry.list()),
              'model_requests': 0, 'paid_spend': 0, 'private_access': False}
    write_immutable(run / 'target-setup.json', json.dumps(output, indent=2) + '\n')
    print(json.dumps({'status': 'passed', 'project': project, 'target_uri': scope.target_uri,
                      'scope_id': scope.scope_id, 'collections': 0}))


if __name__ == '__main__':
    main()
