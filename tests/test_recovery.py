"""Snapshot corruption/ownership/schema/target guards; synthetic files only."""

import hashlib
import json

import pytest

from research_assistant.contracts import fingerprint
from research_assistant.graph import recovery
from research_assistant.graph.repository import PROJECT
from research_assistant.settings import Settings


def graph():
    return {'version': {'versions': ['5.26.32'], 'edition': 'community'},
            'nodes': [{'key': 'Paper:shared', 'labels': ['Paper'], 'properties': {'id': 'shared', 'project': PROJECT}},
                      {'key': 'Dataset:shared', 'labels': ['Dataset'], 'properties': {'id': 'shared', 'project': PROJECT}}],
            'relationships': [], 'constraints': [{'name': 'ra_paper_id', 'type': 'UNIQUENESS', 'entityType': 'NODE',
                                                   'labelsOrTypes': ['Paper'], 'properties': ['id']}], 'indexes': []}


def bundle(tmp_path):
    value = graph()
    raw = json.dumps(value).encode()
    (tmp_path / 'graph.json').write_bytes(raw)
    (tmp_path / 'files/data').mkdir(parents=True)
    (tmp_path / 'files/data/fixture.txt').write_bytes(b'original')
    manifest = {'format': 'logical-recovery-v1', 'project': PROJECT, 'source_uri': 'bolt://127.0.0.1:7687',
                'graph_file_sha256': hashlib.sha256(raw).hexdigest(), 'graph_sha256': fingerprint(value),
                'assets': {'data/fixture.txt': hashlib.sha256(b'original').hexdigest()}}
    (tmp_path / 'manifest.json').write_text(json.dumps(manifest), encoding='utf-8')
    return manifest, value


def test_stable_ids_are_scoped_by_base_label_not_global():
    recovery.validate_graph(graph())
    assert recovery.node_key(['Paper'], 'shared') != recovery.node_key(['Dataset'], 'shared')


@pytest.mark.parametrize('change', ['owner', 'label', 'duplicate', 'endpoint', 'schema'])
def test_invalid_snapshot_cannot_construct_writes(change):
    value = graph()
    if change == 'owner': value['nodes'][0]['properties']['project'] = 'another-project'
    if change == 'label': value['nodes'][0]['labels'] = ['Paper', 'Injected` DELETE n']
    if change == 'duplicate': value['nodes'].append(value['nodes'][0])
    if change == 'endpoint': value['relationships'] = [{'start': 'Paper:absent', 'end': 'Dataset:shared', 'type': 'CITES', 'properties': {}}]
    if change == 'schema': value['constraints'][0]['name'] = 'ra_bad` DELETE n'
    with pytest.raises(ValueError):
        recovery.validate_graph(value)


@pytest.mark.parametrize('target', ['graph', 'asset'])
def test_byte_checksums_reject_changed_snapshot_files(tmp_path, target):
    bundle(tmp_path)
    recovery.verify_snapshot(tmp_path)
    file = tmp_path / ('graph.json' if target == 'graph' else 'files/data/fixture.txt')
    file.write_bytes(file.read_bytes() + b'changed')
    with pytest.raises((ValueError, json.JSONDecodeError)):
        recovery.verify_snapshot(tmp_path)


@pytest.mark.parametrize('path', ['../outside', 'data/../../outside'])
def test_asset_paths_cannot_escape_snapshot(tmp_path, path):
    with pytest.raises(ValueError, match='escapes'):
        recovery.safe_asset(tmp_path, path)


@pytest.mark.parametrize('uri,project', [('bolt://localhost:7687', 'dbu-m3-recovery-fixture'),
                                       ('bolt://localhost:8765', 'production')])
def test_restore_refuses_source_endpoint_or_non_disposable_project(monkeypatch, uri, project):
    def forbidden(*args, **kwargs): pytest.fail('Target rejected before docker/database operations')
    monkeypatch.setattr(recovery.subprocess, 'run', forbidden)
    with pytest.raises(ValueError):
        recovery.attest_target(Settings(neo4j_uri=uri), {'source_uri': 'bolt://127.0.0.1:7687'}, project)


def test_nonempty_target_never_receives_create_delete_or_schema_operations(monkeypatch, tmp_path):
    manifest, value = bundle(tmp_path)
    monkeypatch.setattr(recovery, 'attest_target', lambda *args: {})
    statements = []
    class Result:
        def single(self): return {'n': 1}
    class Session:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def run(self, statement, **kwargs):
            statements.append(statement)
            return Result()
    class Repo:
        database = 'neo4j'
        driver = type('Driver', (), {'session': lambda *args, **kwargs: Session()})()
        def __init__(self, settings): pass
        def close(self): pass
    monkeypatch.setattr(recovery, 'GraphRepository', Repo)
    with pytest.raises(ValueError, match='must be empty'):
        recovery.restore_snapshot(tmp_path, Settings(neo4j_uri='bolt://localhost:8765'), 'dbu-m3-recovery-fixture')
    assert statements == ['MATCH (n) RETURN count(n) AS n']
