"""Opt-in ownership proof on the explicitly declared M8 target; never legacy databases."""

import json
import os
from pathlib import Path
from uuid import uuid4

import pytest
from neo4j import GraphDatabase

from research_assistant.collections.contracts import InputReference
from research_assistant.collections.scope import guard_user_write, inspect_target, load_user_scope
from research_assistant.collections.store import CollectionRegistry
from research_assistant.graph.scope import guard_development_write
from research_assistant.settings import Settings

pytestmark = [pytest.mark.integration,
              pytest.mark.skipif(os.getenv('RUN_USER_COLLECTION_SMOKE') != '1', reason='Explicit M8-only smoke opt-in required')]


def test_native_m8_target_registry_restart_and_frozen_refusal():
    """Check native guard/rollback and retain an empty example; clean only our new UUID probe."""
    scope, settings = load_user_scope(), Settings.from_env()
    assert settings.neo4j_uri == scope.target_uri
    physical = inspect_target(scope)
    guard_development_write(settings)
    registry = CollectionRegistry()
    row = registry.create('M8.1 empty setup example ' + uuid4().hex[:6])
    assert CollectionRegistry().get(row.collection_id) == row
    job = registry.queue(row.collection_id, row.sha256,
        (InputReference(kind='upload', value='not-imported.pdf'),))
    assert job in CollectionRegistry().jobs()
    registry.interrupt(job.job_id, job.sha256, 'Native metadata smoke only; no PDF import or request executed')
    assert registry.describe(row)['available_modes'] == []
    driver = GraphDatabase.driver(settings.neo4j_uri,
        auth=(settings.neo4j_user, settings.neo4j_password.get_secret_value()), max_transaction_retry_time=0)
    probe_id = 'm8-smoke-' + uuid4().hex
    try:
        with driver.session(database=scope.database) as session:
            before = session.run('MATCH (n) RETURN count(n) AS n').single()['n']
            with session.begin_transaction() as tx:
                tx.run('CREATE (:M8WriteProbe {id:$id})', id=probe_id).consume()
                tx.rollback()
            session.run('CREATE (:Corpus {id:$id,project:$project,frozen:true})',
                id=probe_id, project=scope.scope_id).consume()
            try:
                with pytest.raises(ValueError, match='frozen-data'):
                    guard_user_write(settings)
            finally:
                session.run('MATCH (c:Corpus {id:$id,project:$project}) DELETE c',
                    id=probe_id, project=scope.scope_id).consume()
            after = session.run('MATCH (n) RETURN count(n) AS n').single()['n']
        assert before == after == 1
        guard_user_write(settings)
    finally:
        driver.close()
    report = {'status': 'passed', 'physical_target': physical, 'registry_restart': True,
        'queued_job_preserved_then_explicitly_interrupted': True, 'available_modes': [],
        'write_probe_rolled_back': True, 'frozen_write_guard_refused': True,
        'graph_nodes_before': before, 'graph_nodes_after': after,
        'retained_empty_example': row.collection_id, 'new_model_calls': 0, 'private_access': False}
    path = Path('runs/m8/m8-1/native-proof.json')
    with path.open('x', encoding='utf-8') as handle:
        handle.write(json.dumps(report, indent=2) + '\n')
