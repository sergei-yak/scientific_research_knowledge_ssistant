"""Explicit local storage and physical database ownership for user collections."""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
from typing import Literal
from urllib.parse import urlsplit

from neo4j import GraphDatabase, Query
from pydantic import Field, model_validator

from research_assistant.collections.contracts import CollectionLimits, ImmutableContract, LIMITS
from research_assistant.contracts import fingerprint
from research_assistant.settings import Settings

SCOPE_FILE = Path('data/scopes/user-collections.json')
IMAGE_ID = 'sha256:42ef3ebfd671ebd01fdebb6dcbe80cf7b45eef2aa3d346ef4132f7ef31e67d2f'


class UserCollectionScope(ImmutableContract):
    """A new M8-only target, never a reused baseline or evaluation authority."""

    format: Literal['user-collections-scope-v1'] = 'user-collections-scope-v1'
    scope_id: str = Field(pattern=r'^m8user-[a-f0-9]{12}$')
    worktree_root: str
    storage_root: str
    target_project: str
    target_uri: str
    database: Literal['neo4j'] = 'neo4j'
    container_id: str = Field(pattern=r'^[a-f0-9]{64}$')
    image_id: Literal[IMAGE_ID] = IMAGE_ID
    volumes: tuple[str, str]
    limits: CollectionLimits = LIMITS

    @model_validator(mode='after')
    def isolated_locations(self) -> UserCollectionScope:
        """Require M8-specific names, nondefault loopback ports and checkout-local storage."""
        root = Path(self.worktree_root)
        expected_storage = root / 'data/user-collections'
        uri = urlsplit(self.target_uri)
        expected_project = 'dbu-m8-user-' + self.scope_id.removeprefix('m8user-')
        if (not root.is_absolute() or root.resolve() != root
                or Path(self.storage_root) != expected_storage or expected_storage.resolve() != expected_storage):
            raise ValueError('User collection storage must be inside its declared checkout')
        if (uri.scheme != 'bolt' or uri.hostname != '127.0.0.1' or uri.port in {None, 7687}
                or uri.username or uri.password or uri.path or uri.query or uri.fragment):
            raise ValueError('User target requires a separate explicit loopback Bolt port')
        if self.target_project != expected_project or sorted(self.volumes) != [
                expected_project + '_neo4j_data', expected_project + '_neo4j_logs']:
            raise ValueError('User target project/volumes are not its own M8 namespace')
        return self

    @property
    def sha256(self) -> str:
        """Bind storage, target identity and the fixed resource policy together."""
        return fingerprint(self.model_dump(mode='json'))


def load_user_scope(workspace: Path | None = None) -> UserCollectionScope:
    """Read one explicit declaration; never search other worktrees or evaluator directories."""
    root = (workspace or Path.cwd()).resolve()
    path = root / SCOPE_FILE
    if path.resolve() != path:
        raise ValueError('Scope declaration cannot use a redirected path')
    scope = UserCollectionScope.model_validate_json(path.read_bytes())
    if Path(scope.worktree_root) != root:
        raise ValueError('User collection scope belongs to another checkout')
    return scope


def inspect_target(scope: UserCollectionScope) -> dict:
    """Attest only the exact named M8 container; never expose container environment secrets."""
    result = subprocess.run(['docker', 'inspect', scope.target_project + '-neo4j-1'],
        capture_output=True, text=True, check=True, timeout=20)
    container = json.loads(result.stdout)[0]
    mounts = container.get('Mounts', [])
    volumes = {m.get('Name') for m in mounts if m.get('Destination') in {'/data', '/logs'}}
    bindings = container.get('NetworkSettings', {}).get('Ports', {}).get('7687/tcp') or []
    port = urlsplit(scope.target_uri).port
    if (container['Id'] != scope.container_id or container['Image'] != scope.image_id
            or container['Config'].get('Labels', {}).get('com.docker.compose.project') != scope.target_project
            or volumes != set(scope.volumes) or not container['State']['Running']
            or not bindings or any(b['HostIp'] != '127.0.0.1' or int(b['HostPort']) != port for b in bindings)
            or any(m.get('Type') != 'volume' or not m.get('RW') for m in mounts
                   if m.get('Destination') in {'/data', '/logs'})):
        raise ValueError('M8 container, image, port or writable volume identity changed')
    return {'container_id': container['Id'], 'project': scope.target_project,
            'image_id': container['Image'], 'volumes': sorted(volumes), 'target_uri': scope.target_uri}


def guard_user_write(settings: Settings) -> None:
    """Fail before graph writes on foreign, frozen, read-only or rebound physical targets."""
    scope = load_user_scope()
    if settings.neo4j_uri != scope.target_uri or settings.neo4j_database != scope.database:
        raise ValueError('Refusing graph write outside the declared user target')
    inspect_target(scope)
    driver = GraphDatabase.driver(settings.neo4j_uri,
        auth=(settings.neo4j_user, settings.neo4j_password.get_secret_value()),
        connection_timeout=10, max_transaction_retry_time=0)
    try:
        with driver.session(database=scope.database) as session:
            owners = session.run(Query('MATCH (o:UserCollectionWorkspace) '
                'RETURN o.id AS id,o.scope_sha256 AS binding', timeout=10)).data()
            access = session.run('SHOW DATABASES YIELD name, access WHERE name=$name RETURN access',
                name=scope.database).single()
            frozen = session.run(Query('MATCH (c:Corpus) WHERE c.frozen=true RETURN count(c) AS n',
                timeout=10)).single()['n']
            if (owners != [{'id': scope.scope_id, 'binding': scope.sha256}]
                    or not access or access['access'] != 'read-write' or frozen):
                raise ValueError('M8 workspace owner, writable state or frozen-data guard failed')
    finally:
        driver.close()
