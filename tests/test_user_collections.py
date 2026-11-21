"""User registry isolation and durable failure boundaries; all source data are synthetic."""

from datetime import datetime, timezone
import json
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
from pydantic import ValidationError

from research_assistant.collections.contracts import (
    CorpusBinding, DocumentVersion, ImportJob, InputReference, LIMITS, UserCollection, supported_url,
)
from research_assistant.collections.scope import UserCollectionScope, load_user_scope
from research_assistant.collections.store import CollectionRegistry
from research_assistant.collections import scope as scope_module
from research_assistant.settings import Settings


def declared_scope(root: Path) -> UserCollectionScope:
    """Create only a synthetic declaration; never provision Docker or inspect real data."""
    project = 'dbu-m8-user-' + 'a' * 12
    scope = UserCollectionScope(scope_id='m8user-' + 'a' * 12, worktree_root=str(root.resolve()),
        storage_root=str(root.resolve() / 'data/user-collections'), target_project=project,
        target_uri='bolt://127.0.0.1:17687', container_id='c' * 64,
        volumes=(project + '_neo4j_data', project + '_neo4j_logs'))
    path = root / 'data/scopes/user-collections.json'
    path.parent.mkdir(parents=True)
    path.write_text(scope.model_dump_json(), encoding='utf-8')
    return scope


@pytest.fixture
def registry(tmp_path):
    """Use a new local-only scope per test, with a persistent owner binding."""
    declared_scope(tmp_path)
    store = CollectionRegistry(tmp_path)
    store.initialize()
    return store


def document(digest='1' * 64, pages=5, byte_count=100):
    """One bounded, content-addressed synthetic document."""
    return DocumentVersion(paper_id='pdf-' + digest, source_sha256=digest,
        source=InputReference(kind='upload', value='research.pdf'), byte_count=byte_count,
        pdf_pages=pages, indexed_pages=(1, 2))


def test_restart_revision_and_readiness(registry):
    first = registry.create('Biology')
    assert registry.describe(first)['available_modes'] == []
    second = registry.revise(first.collection_id, first.sha256, name='Biology notes', documents=(document(),))
    restarted = CollectionRegistry(registry.workspace)
    restarted.initialize()
    assert restarted.get(first.collection_id) == second
    assert second.previous_sha256 == first.sha256
    assert first.corpus_id != second.corpus_id
    assert restarted.describe(second)['readiness'] == 'not_verified'
    renamed = restarted.revise(second.collection_id, second.sha256, name='Renamed')
    assert renamed.documents == second.documents and renamed.binding is None
    with pytest.raises(ValueError, match='stale or foreign'):
        restarted.review_directory(first)
    assert restarted.review_directory(renamed).is_relative_to(registry.root)


def test_same_documents_do_not_share_corpus_or_review_bindings(registry):
    a, b = registry.create('A'), registry.create('B')
    a = registry.revise(a.collection_id, a.sha256, name=a.name, documents=(document(),))
    b = registry.revise(b.collection_id, b.sha256, name=b.name, documents=(document(),))
    assert a.corpus_id != b.corpus_id
    assert registry.review_directory(a) != registry.review_directory(b)
    binding = CorpusBinding(corpus_id=a.corpus_id, snapshot_sha256='a' * 64,
        chunks_sha256='b' * 64, chunk_count=1, encoder_revision='synthetic')
    with pytest.raises(ValidationError, match='another collection/revision'):
        UserCollection.model_validate({**b.model_dump(), 'binding': binding})


def test_concurrent_import_reservation_survives_restart(registry):
    a, b = registry.create('A'), registry.create('B')
    job = registry.queue(a.collection_id, a.sha256, (InputReference(kind='upload', value='paper.pdf'),))
    other = CollectionRegistry(registry.workspace)
    assert other.jobs() == [job]
    with pytest.raises(ValueError, match='Another import'):
        other.queue(b.collection_id, b.sha256, job.inputs)
    with pytest.raises(ValueError, match='active import'):
        other.revise(a.collection_id, a.sha256, name='Changed')
    closed = other.interrupt(job.job_id, job.sha256, 'Explicitly stopped; no worker executed')
    assert closed.previous_sha256 == job.sha256 and closed.state == 'interrupted'
    assert len(other._history('jobs', job.job_id, ImportJob)) == 2
    assert other.queue(b.collection_id, b.sha256, job.inputs).job_id != job.job_id
    with pytest.raises(ValueError, match='terminal'):
        other.interrupt(closed.job_id, closed.sha256, 'Cannot rewrite a terminal event')


def test_stale_head_and_lock_are_not_overwritten(registry):
    row = registry.create('A')
    before = registry.get(row.collection_id)
    with pytest.raises(ValueError, match='changed'):
        registry.revise(row.collection_id, '0' * 64, name='A')
    lock = registry.root / '.registry.lock'
    lock.write_text('stale owner', encoding='utf-8')
    with pytest.raises(FileExistsError):
        registry.create('B')
    assert lock.read_text() == 'stale owner' and registry.get(row.collection_id) == before


def test_history_tampering_is_not_repaired(registry):
    row = registry.create('A')
    path = registry.root / 'collections' / row.collection_id / 'history/000001.json'
    envelope = json.loads(path.read_bytes())
    envelope['record']['name'] = 'Changed'
    path.write_text(json.dumps(envelope), encoding='utf-8')
    with pytest.raises(ValueError, match='hash, chain or ownership'):
        registry.get(row.collection_id)


def test_ownership_change_and_foreign_scope_are_rejected(registry, tmp_path):
    foreign = tmp_path / 'foreign'
    foreign.mkdir()
    declared_scope(foreign)
    other = CollectionRegistry(foreign)
    other.initialize()
    with pytest.raises(ValueError, match='stale or foreign'):
        other.review_directory(registry.create('A'))
    path = registry.workspace / 'data/scopes/user-collections.json'
    value = json.loads(path.read_bytes())
    value['container_id'] = 'd' * 64
    path.write_text(json.dumps(value), encoding='utf-8')
    with pytest.raises(ValueError, match='owner'):
        CollectionRegistry(registry.workspace).initialize()


@pytest.mark.parametrize('identifier', ['pilot', 'expanded', '../x', 'uc-../../x', 'uc-' + 'A' * 32])
def test_preset_and_traversal_id_rejection(registry, identifier):
    with pytest.raises(ValueError, match='Invalid'):
        registry.get(identifier)


@pytest.mark.parametrize('value', [
    'http://example.com/a.pdf', 'https://127.0.0.1/a.pdf', 'https://[::1]/a.pdf',
    'https://user:password@example.com/a.pdf', 'https://example.com:444/a.pdf',
    'https://example.com/a.pdf#page=2', 'https://localhost/a.pdf', 'https://host.local/a.pdf',
    'https://example.com/a.html', 'https://example.com/a.pdf\n', 'https://2130706433/a.pdf',
    'https://arxiv.org/abs/2501.00309?download=yes',
])
def test_unsupported_url_inputs_do_not_reach_network(value):
    with pytest.raises(ValueError):
        InputReference(kind='url', value=value)


def test_supported_urls_and_document_boundaries():
    assert supported_url('https://arxiv.org/abs/2501.00309v2') == 'https://arxiv.org/pdf/2501.00309v2'
    assert supported_url('https://example.org/paper.pdf?download=1').endswith('?download=1')
    for name in ['../paper.pdf', 'C:\\paper.pdf', '/paper.pdf', 'notes.txt']:
        with pytest.raises(ValueError):
            InputReference(kind='upload', value=name)
    with pytest.raises(ValueError, match='content hash'):
        document().model_validate({**document().model_dump(), 'paper_id': 'arxiv:existing'})
    with pytest.raises(ValueError, match='unique, ordered'):
        DocumentVersion.model_validate({**document().model_dump(), 'indexed_pages': [2, 1]})
    with pytest.raises(ValueError):
        type(LIMITS)(max_documents=11)


def test_document_and_collection_resource_caps(registry):
    row = registry.create('A')
    with pytest.raises(ValueError, match='Duplicate'):
        registry.revise(row.collection_id, row.sha256, name='A', documents=(document(), document()))
    docs = tuple(document(str(i) * 64, pages=100) for i in range(1, 5))
    with pytest.raises(ValueError, match='page limit'):
        registry.revise(row.collection_id, row.sha256, name='A', documents=docs)
    with pytest.raises(ValueError):
        document(byte_count=LIMITS.max_pdf_bytes + 1)
    with pytest.raises(ValueError):
        registry.create('   ')
    with pytest.raises(ValidationError):
        UserCollection.model_validate({**row.model_dump(), 'ready': True, 'approved': True})


def test_scope_foreign_paths_and_legacy_target_rejected(tmp_path):
    scope = declared_scope(tmp_path)
    for changes in [
        {'storage_root': str(tmp_path / 'data/reviews/pilot')},
        {'target_uri': 'bolt://127.0.0.1:7687'},
        {'target_project': 'dbu-m4-recovery-m5dev-existing'},
        {'volumes': ['baseline_neo4j_data', 'baseline_neo4j_logs']},
    ]:
        with pytest.raises(ValidationError):
            UserCollectionScope.model_validate({**scope.model_dump(), **changes})


def target_container(scope):
    """Docker metadata fixture with only the fields used by the physical target guard."""
    return {'Id': scope.container_id, 'Image': scope.image_id, 'State': {'Running': True},
        'Config': {'Labels': {'com.docker.compose.project': scope.target_project}},
        'Mounts': [{'Name': name, 'Destination': dest, 'Type': 'volume', 'RW': True}
                   for name, dest in zip(scope.volumes, ['/data', '/logs'])],
        'NetworkSettings': {'Ports': {'7687/tcp': [{'HostIp': '127.0.0.1', 'HostPort': '17687'}]}}}


@pytest.mark.parametrize('change', ['container', 'image', 'volume', 'loopback', 'stopped'])
def test_physical_scope_substitution_rejected(tmp_path, monkeypatch, change):
    scope = declared_scope(tmp_path)
    container = target_container(scope)
    if change == 'container': container['Id'] = 'd' * 64
    elif change == 'image': container['Image'] = 'sha256:' + '0' * 64
    elif change == 'volume': container['Mounts'][0]['Name'] = 'foreign'
    elif change == 'loopback': container['NetworkSettings']['Ports']['7687/tcp'][0]['HostIp'] = '0.0.0.0'
    else: container['State']['Running'] = False
    monkeypatch.setattr(scope_module.subprocess, 'run', lambda *a, **k: SimpleNamespace(stdout=json.dumps([container])))
    with pytest.raises(ValueError, match='identity changed'):
        scope_module.inspect_target(scope)


def test_legacy_guard_delegates_only_with_explicit_user_scope(registry, monkeypatch):
    from research_assistant.graph.scope import guard_development_write
    monkeypatch.chdir(registry.workspace)
    calls = []
    monkeypatch.setattr(scope_module, 'guard_user_write', lambda settings: calls.append(settings.neo4j_uri))
    guard_development_write(Settings(neo4j_uri=registry.scope.target_uri))
    assert calls == [registry.scope.target_uri]


def test_user_guard_rejects_foreign_endpoint_before_docker(registry, monkeypatch):
    monkeypatch.chdir(registry.workspace)
    monkeypatch.setattr(scope_module, 'inspect_target', lambda *a: pytest.fail('No inspect on foreign endpoint'))
    with pytest.raises(ValueError, match='outside the declared'):
        scope_module.guard_user_write(Settings())


def test_registry_cli_uses_same_service(registry, monkeypatch, capsys):
    from research_assistant.collections.__main__ import main
    monkeypatch.chdir(registry.workspace)
    assert main(['create', '--name', 'Astronomy']) == 0
    created = json.loads(capsys.readouterr().out)
    assert created['available_modes'] == []
    assert main(['list']) == 0
    listed = json.loads(capsys.readouterr().out)
    assert listed['collections'][0]['collection_id'] == created['collection_id']
    assert main(['show', '--collection', 'expanded']) == 1
    assert json.loads(capsys.readouterr().out)['status'] == 'failed'


@pytest.mark.parametrize('access,frozen,wrong_owner', [
    ('read-only', 0, False), ('read-write', 1, False), ('read-write', 0, True),
])
def test_database_readonly_frozen_and_owner_guards(registry, monkeypatch, access, frozen, wrong_owner):
    monkeypatch.chdir(registry.workspace)
    monkeypatch.setattr(scope_module, 'inspect_target', lambda scope: {})
    owner = [{'id': registry.scope.scope_id, 'binding': '0' * 64 if wrong_owner else registry.scope.sha256}]
    class Session:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def run(self, query, **params):
            text = str(query)
            if 'UserCollectionWorkspace' in text:
                return SimpleNamespace(data=lambda: owner)
            if 'SHOW DATABASES' in text:
                return SimpleNamespace(single=lambda: {'access': access})
            return SimpleNamespace(single=lambda: {'n': frozen})
    closed = []
    driver = SimpleNamespace(session=lambda **k: Session(), close=lambda: closed.append(True))
    monkeypatch.setattr(scope_module.GraphDatabase, 'driver', lambda *a, **k: driver)
    with pytest.raises(ValueError, match='owner, writable state or frozen-data'):
        scope_module.guard_user_write(Settings(neo4j_uri=registry.scope.target_uri))
    assert closed == [True]


def test_redirected_registry_path_is_rejected(registry, tmp_path):
    row = registry.create('A')
    external = tmp_path / 'outside.txt'
    external.write_text('untouched')
    # File symlinks may need Windows developer mode; use resolve redirection as a portable fixture.
    original = Path.resolve
    target = registry.root / 'collections' / row.collection_id / 'history/000001.json'
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(Path, 'resolve', lambda p, *a, **k: external if p == target else original(p, *a, **k))
        with pytest.raises(ValueError, match='redirected'):
            registry.get(row.collection_id)
    assert external.read_text() == 'untouched'


def test_research_and_user_declarations_cannot_mix(registry, monkeypatch):
    from research_assistant.graph.scope import guard_development_write
    monkeypatch.chdir(registry.workspace)
    path = registry.workspace / 'data/scopes/retrieval-v2.json'
    path.write_text('{}')
    monkeypatch.setattr(scope_module, 'guard_user_write', lambda *a: pytest.fail('Do not select either target'))
    with pytest.raises(ValueError, match='must remain separate'):
        guard_development_write(Settings())


def test_registry_cli_does_not_echo_invalid_secret_url(registry, monkeypatch, capsys):
    from research_assistant.collections.__main__ import main
    monkeypatch.chdir(registry.workspace)
    monkeypatch.setenv('NEO4J_URI', 'bolt://user:do-not-print@127.0.0.1:7687')
    assert main(['list']) == 2
    output = capsys.readouterr().out
    assert 'do-not-print' not in output and json.loads(output)['error'] == 'invalid_settings'
