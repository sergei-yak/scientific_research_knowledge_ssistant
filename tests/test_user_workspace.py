"""Checked collection QA/export and UI state using synthetic indexed sources only."""

from contextlib import contextmanager
from datetime import datetime, timezone
import csv
import hashlib
import io
import json
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest

from research_assistant.collections import workspace
from research_assistant.collections.contracts import InputReference
from research_assistant.collections.store import CollectionRegistry
from research_assistant.contracts import DraftAnswer, RetrievalResult, RunArtifact, text_sha
from research_assistant.generation import validate_answer
from research_assistant.ingestion import user_import
from research_assistant.ingestion.sources import load_corpus_chunks
from research_assistant.retrieval.catalog import chunk_evidence
from research_assistant.retrieval.evidence import assemble_evidence
from research_assistant.settings import Settings
from test_ingestion import FakeEncoder
from test_user_collections import declared_scope
from test_user_imports import inline_inspector, pdf_bytes, upload

APP = Path('src/research_assistant/ui/collections_app.py').resolve()


@pytest.fixture
def scene(tmp_path, monkeypatch):
    """Exercise real immutable files/index adapters; replace only external DB/model boundaries."""
    from research_assistant import pipeline
    declared_scope(tmp_path)
    monkeypatch.chdir(tmp_path)
    registry = CollectionRegistry(tmp_path)
    registry.initialize()
    snapshots, calls = {}, []
    state = {'online': True}
    class Repo:
        def __init__(self, *args): pass
        def ingest(self, snapshot, manifest, chunks, vectors):
            snapshots[snapshot['corpus_id']] = snapshot
            return {'ready': True, 'corpus_id': snapshot['corpus_id']}
        def combine(self, snapshot, ids):
            snapshots[snapshot['corpus_id']] = snapshot
            return {'ready': True}
        def snapshot(self, corpus): return snapshots[corpus]
        def prepare_indexes(self, corpus): return {'indexes': [{'state': 'ONLINE'}]}
        @contextmanager
        def reading(self, *args): yield self
        def check_indexes(self, *args):
            if not state['online']: raise ValueError('Required indexes unavailable')
        def close(self): pass
    class Encoder(FakeEncoder):
        def encode(self, texts): return [[1.0] + [0.0] * 383 for text in texts]
    monkeypatch.setattr(pipeline, 'GraphRepository', Repo)
    monkeypatch.setattr(user_import, 'GraphRepository', Repo)
    monkeypatch.setattr(user_import, 'SearchRepository', Repo)
    monkeypatch.setattr(workspace, 'SearchRepository', Repo)
    monkeypatch.setattr(workspace, 'guard_user_write', lambda settings: None)
    def indexed(name='First collection', filename='paper.pdf', text='A source-backed synthetic research excerpt.'):
        row = registry.create(name)
        data = pdf_bytes(text)
        entry = upload(data, filename)
        job = registry.queue(row.collection_id, row.sha256, (entry.reference,))
        result = user_import.run_import(registry, job.job_id, [entry], Settings(),
            encoder_factory=Encoder, inspector=inline_inspector, write_guard=lambda settings: None)
        assert result['status'] == 'ready', result
        return registry.get(row.collection_id)
    def query(request, settings, **kwargs):
        calls.append((request, kwargs))
        chunks = load_corpus_chunks(request.corpus_id)
        evidence, context, aliases, tokens, decisions = assemble_evidence([chunk_evidence(next(iter(chunks.values())))])
        retrieval = RetrievalResult(requested_mode=request.mode, effective_mode=request.mode,
            evidence=evidence, context=context, context_sha256=text_sha(context), aliases=aliases,
            estimated_tokens=tokens, candidates=decisions, retrieval_ms=1)
        answer = validate_answer(DraftAnswer(answer='Supported fixture answer.', citations=['E1'],
            insufficient_evidence=False), retrieval) if kwargs['generate'] else None
        return RunArtifact(run_id=uuid4().hex, created_at=datetime.now(timezone.utc).isoformat(),
            request=request, corpus_manifest=snapshots[request.corpus_id], code_revision='synthetic',
            code_dirty=False, configuration={}, retrieval=retrieval, generation=None, result=answer,
            generation_requested=kwargs['generate'])
    monkeypatch.setattr(workspace, 'run_query', query)
    settings = Settings(neo4j_uri=registry.scope.target_uri)
    row = indexed()
    return SimpleNamespace(registry=registry, row=row, indexed=indexed, calls=calls,
                          state=state, settings=settings, encoder=Encoder())


def ask(scene, **kwargs):
    return workspace.query_collection(scene.registry, scene.row.collection_id, scene.row.sha256,
        'What does the paper describe?', kwargs.pop('mode', 'hybrid'), scene.settings,
        encoder=scene.encoder, **kwargs)


def test_checked_query_pdf_and_csv_exports_do_not_repeat_inference(scene):
    run = ask(scene, generate=True)
    for _ in range(3):
        view, csv_text, ready = workspace.checked_output(scene.registry, scene.row.collection_id,
            run, scene.settings, scene.row.sha256)
        assert ready.marker == run.configuration['user_collection']
        source = next(iter(ready.sources.values()))
        assert source.web_url is None and source.filename == source.reference == 'paper.pdf'
        assert hashlib.sha256(source.data).hexdigest() == scene.row.documents[0].source_sha256
        rows = list(csv.DictReader(io.StringIO(csv_text)))
        assert rows[0]['source_reference'] == 'paper.pdf'
        assert rows[0]['quotation'] == run.retrieval.evidence[0].excerpts[0].text
    assert len(scene.calls) == 1
    assert (Path('runs/user-collections/queries') / run.run_id / 'run.json').exists()


def test_cross_collection_and_stale_revision_cannot_display_or_export(scene):
    run = ask(scene)
    other = scene.indexed(name='Other', text='An unrelated synthetic source.')
    with pytest.raises(ValueError, match='different or changed'):
        workspace.checked_output(scene.registry, other.collection_id, run, scene.settings)
    newer = scene.registry.revise(scene.row.collection_id, scene.row.sha256, name='Renamed')
    with pytest.raises(ValueError, match='changed'):
        workspace.checked_output(scene.registry, newer.collection_id, run, scene.settings, scene.row.sha256)
    assert len(scene.calls) == 1


@pytest.mark.parametrize('mode', ['graph', 'hybrid_facts', 'unknown'])
def test_unreviewed_modes_rejected_before_query_or_source_access(scene, monkeypatch, mode):
    monkeypatch.setattr(workspace, 'verify_collection', lambda *a, **k: pytest.fail('No ready/source check'))
    with pytest.raises(ValueError, match='human review'):
        ask(scene, mode=mode)
    assert not scene.calls


def test_source_corruption_and_index_failure_disable_output(scene):
    run = ask(scene)
    scene.state['online'] = False
    with pytest.raises(ValueError, match='indexes unavailable'):
        workspace.checked_output(scene.registry, scene.row.collection_id, run, scene.settings)
    scene.state['online'] = True
    document = scene.row.documents[0]
    scene.registry._path('sources', document.source_sha256 + '.pdf').write_bytes(b'corrupted fixture')
    with pytest.raises(ValueError, match='Source PDF changed'):
        workspace.checked_output(scene.registry, scene.row.collection_id, run, scene.settings)


def test_member_path_escape_is_refused_before_reading_foreign_file(scene, tmp_path):
    directory = Path('data/processed') / scene.row.corpus_id
    members = json.loads((directory / 'members.json').read_bytes())
    members[0]['chunk_path'] = str(tmp_path / 'do-not-read-private.json')
    (directory / 'members.json').write_text(json.dumps(members))
    with pytest.raises(ValueError, match='foreign or redirected'):
        workspace.verify_collection(scene.registry, scene.row.collection_id, scene.settings)


def test_csv_source_fields_share_formula_escaping(scene):
    scene.row = scene.indexed(name='Spreadsheet input', filename='=SUM(1).pdf')
    run = ask(scene)
    _, csv_text, _ = workspace.checked_output(scene.registry, scene.row.collection_id, run, scene.settings)
    row = next(csv.DictReader(io.StringIO(csv_text)))
    assert row['source_reference'].startswith("'=") and row['source_filename'].startswith("'=")
    assert {'source_reference', 'source_filename'} <= set(json.loads(row['escaped_fields']))


def test_query_import_and_revision_locks_are_shared(scene):
    registry, row = scene.registry, scene.row
    with registry.query_lock():
        with pytest.raises(FileExistsError):
            with registry.query_lock(): pytest.fail('No second query')
        with pytest.raises(ValueError, match='question is running'):
            registry.queue(row.collection_id, row.sha256, (InputReference(kind='upload', value='x.pdf'),))
        with pytest.raises(ValueError, match='question is running'):
            registry.revise(row.collection_id, row.sha256, name='Race')
    job = registry.queue(row.collection_id, row.sha256, (InputReference(kind='upload', value='x.pdf'),))
    with pytest.raises(ValueError, match='import is active or reserved'):
        with registry.query_lock(): pytest.fail('No query during reserved import')
    registry.interrupt(job.job_id, job.sha256, 'Fixture reservation resolved')
    with registry.query_lock(): pass


def test_cli_query_and_saved_export_call_same_services(scene, monkeypatch, capsys, tmp_path):
    from research_assistant.collections.__main__ import main
    monkeypatch.setattr(Settings, 'from_env', classmethod(lambda cls: scene.settings))
    output, csv_path = tmp_path / 'answer.json', tmp_path / 'evidence.csv'
    assert main(['query', '--collection', scene.row.collection_id, '--expected-head', scene.row.sha256,
                 '--question', 'What is described?', '--output', str(output)]) == 0
    capsys.readouterr()
    assert main(['export', '--collection', scene.row.collection_id, '--run', str(output), '--output', str(csv_path)]) == 0
    assert csv_path.read_bytes().startswith(b'\xef\xbb\xbf') and len(scene.calls) == 1
    assert main(['query', '--collection', scene.row.collection_id, '--expected-head', scene.row.sha256,
                 '--question', 'Do not run again', '--output', str(output)]) == 1
    assert len(scene.calls) == 1


def prepare_ui(scene, monkeypatch):
    """Actual Streamlit execution, with only external model/database calls replaced."""
    from streamlit.testing.v1 import AppTest
    monkeypatch.setattr(Settings, 'from_env', classmethod(lambda cls: scene.settings))
    monkeypatch.setattr('research_assistant.ui.app.cached_encoder', lambda: scene.encoder)
    return AppTest.from_file(str(APP), default_timeout=20)


def button(app, label):
    return next(item for item in app.button if item.label == label)


def test_ui_only_offers_vector_hybrid_and_requires_explicit_submit(scene, monkeypatch):
    app = prepare_ui(scene, monkeypatch).run()
    assert not app.exception and not scene.calls
    modes = next(item for item in app.selectbox if item.label == 'Retrieval mode')
    assert modes.options == ['Vector', 'Hybrid']
    next(item for item in app.text_area if item.label == 'Research question').set_value('What is described?')
    button(app, 'Ask question').click().run()
    assert not app.exception and len(scene.calls) == 1 and not scene.calls[0][1]['generate']
    assert len(app.get('download_button')) == 3  # source PDF, shared CSV, shared JSON
    app.run()
    next(item for item in app.selectbox if item.label == 'Retrieval mode').set_value('vector').run()
    assert len(scene.calls) == 1 and any('Requested: hybrid' in c.value for c in app.caption)
    assert all('userpdf://' not in link.url for link in app.get('link_button'))


def test_ui_selection_change_clears_previous_answer_and_exports(scene, monkeypatch):
    other = scene.indexed(name='Second collection', text='Different evidence.')
    app = prepare_ui(scene, monkeypatch).run()
    next(item for item in app.text_area if item.label == 'Research question').set_value('A question')
    button(app, 'Ask question').click().run()
    next(item for item in app.selectbox if item.label == 'Paper collection').set_value(other.collection_id).run()
    assert not app.exception and len(scene.calls) == 1
    assert 'user_run' not in app.session_state and not app.get('download_button')


def test_ui_empty_collection_import_and_generation_controls(scene, monkeypatch):
    empty = scene.registry.create('Empty')
    app = prepare_ui(scene, monkeypatch).run()
    next(item for item in app.selectbox if item.label == 'Paper collection').set_value(empty.collection_id).run()
    assert button(app, 'Ask question').disabled
    assert any(item.label == 'Import documents' for item in app.button)
    assert any('Import documents before' in i.value for i in app.info)
    next(item for item in app.selectbox if item.label == 'Paper collection').set_value(scene.row.collection_id).run()
    next(item for item in app.text_area if item.label == 'Research question').set_value('A question')
    next(item for item in app.checkbox if item.label == 'Generate an answer').check()
    button(app, 'Ask question').click().run()
    assert not app.exception and scene.calls[0][1]['generate']
    assert any('Supported fixture answer.' == text.value for text in app.text)
    scene.state['online'] = False
    app.run()
    assert 'user_run' not in app.session_state and not app.get('download_button')


def test_ui_file_import_form_really_runs_and_clears_previous_output(scene, monkeypatch):
    import streamlit as st
    file = io.BytesIO(pdf_bytes('A second synthetic source uploaded through the form.'))
    file.name = 'new-source.pdf'
    monkeypatch.setattr(st, 'file_uploader', lambda *a, **k: [file])
    monkeypatch.setitem(user_import.run_import.__kwdefaults__, 'inspector', inline_inspector)
    monkeypatch.setitem(user_import.run_import.__kwdefaults__, 'write_guard', lambda settings: None)
    app = prepare_ui(scene, monkeypatch).run()
    next(item for item in app.text_area if item.label == 'Research question').set_value('Question before import')
    button(app, 'Ask question').click().run()
    assert 'user_run' in app.session_state
    button(app, 'Import documents').click().run()
    assert not app.exception
    assert app.session_state['last_import']['status'] == 'ready'
    assert len(scene.registry.get(scene.row.collection_id).documents) == 2
    assert 'user_run' not in app.session_state and not app.get('download_button')
    assert len(scene.calls) == 1


def test_ui_import_keeps_selection_when_empty_collection_becomes_ready(scene, monkeypatch):
    import streamlit as st
    scene.registry.create('Another empty collection')
    target = scene.registry.create('Z target collection')
    file = io.BytesIO(pdf_bytes('First upload into the selected empty collection.'))
    file.name = 'first-upload.pdf'
    monkeypatch.setattr(st, 'file_uploader', lambda *a, **k: [file])
    monkeypatch.setitem(user_import.run_import.__kwdefaults__, 'inspector', inline_inspector)
    monkeypatch.setitem(user_import.run_import.__kwdefaults__, 'write_guard', lambda settings: None)
    app = prepare_ui(scene, monkeypatch).run()
    next(item for item in app.selectbox if item.label == 'Paper collection').set_value(target.collection_id).run()
    button(app, 'Import documents').click().run()
    assert not app.exception and app.session_state['last_import']['status'] == 'ready'
    assert next(item for item in app.selectbox if item.label == 'Paper collection').value == target.collection_id
    assert any(h.value == target.name for h in app.subheader)


def test_query_generation_failure_is_saved_with_collection_binding(scene, monkeypatch):
    from research_assistant.pipeline import QueryExecutionError
    prior = ask(scene)
    failed = prior.model_copy(update={'run_id': uuid4().hex, 'result': None, 'generation_requested': True})
    def unavailable(*args, **kwargs):
        raise QueryExecutionError('Synthetic provider unavailable', failed)
    monkeypatch.setattr(workspace, 'run_query', unavailable)
    with pytest.raises(QueryExecutionError) as raised:
        ask(scene, generate=True)
    assert raised.value.artifact.configuration['user_collection']['collection_id'] == scene.row.collection_id
    assert (Path('runs/user-collections/queries') / failed.run_id / 'failed-run.json').exists()
    assert not (scene.registry.root / '.query.lock').exists()


def test_source_progress_callback_cannot_fail_valid_processing(scene, monkeypatch):
    row = scene.registry.create('Progress display failure')
    file = io.BytesIO(pdf_bytes('A source whose progress callback fails.'))
    monkeypatch.setitem(user_import.run_import.__kwdefaults__, 'inspector', inline_inspector)
    monkeypatch.setitem(user_import.run_import.__kwdefaults__, 'write_guard', lambda settings: None)
    def bad_view(job): raise RuntimeError('Synthetic disconnected progress view')
    result = workspace.import_collection(scene.registry, row.collection_id, row.sha256,
        [('source.pdf', file)], [], scene.settings, encoder_factory=lambda: scene.encoder, on_progress=bad_view)
    assert result['status'] == 'ready' and scene.registry.get(row.collection_id).binding
