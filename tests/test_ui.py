"""Offline Streamlit interaction tests; no service, model or private evaluation reads."""

from pathlib import Path

from streamlit.testing.v1 import AppTest

from research_assistant import pipeline, product
from test_product import fixture_run

APP = Path('src/research_assistant/ui/app.py')


def prepare_app(monkeypatch):
    run, catalog, _ = fixture_run('discovery')
    calls = []
    def query(request, settings, **kwargs):
        calls.append((request, kwargs))
        return run.model_copy(update={'request': request, 'workflow': kwargs['workflow']})
    monkeypatch.setattr(pipeline, 'run_query', query)
    monkeypatch.setattr(pipeline, 'write_immutable', lambda *args: None)
    monkeypatch.setattr('research_assistant.embeddings.Encoder', lambda: object())
    monkeypatch.setattr(product, 'prepare_output', lambda saved, settings, **kwargs: (product.build_view(saved, catalog), product.evidence_csv(saved)))
    return AppTest.from_file(str(APP), default_timeout=20), calls


def test_submit_and_widget_reruns_do_not_repeat_queries_or_relabel_saved_mode(monkeypatch):
    app, calls = prepare_app(monkeypatch)
    app.run()
    assert not app.exception and not calls
    app.button[0].click().run()
    assert not app.exception and len(calls) == 1
    assert calls[0][1]['generate'] is False
    assert any('Requested: graph' in caption.value and 'Effective: hybrid_facts' in caption.value for caption in app.caption)
    assert any('not generated' in info.value for info in app.info)
    assert len(app.get('download_button')) == 2
    next(widget for widget in app.selectbox if widget.label=='Retrieval mode').set_value('vector').run()
    assert len(calls) == 1
    assert any('Requested: graph' in caption.value for caption in app.caption)


def test_v2_is_explicit_preserves_pilot_default_and_disables_synthesis(monkeypatch):
    app,calls=prepare_app(monkeypatch)
    app.run()
    next(w for w in app.selectbox if w.label=='Retrieval profile').set_value('retrieval-v2').run()
    assert not app.exception and not calls
    assert app.checkbox[0].disabled and not app.checkbox[0].value
    assert next(w for w in app.text_input if w.label=='Corpus ID').value==product.PILOT_CORPUS
    assert next(w for w in app.text_input if w.label=='V2 scope file').value=='data/scopes/retrieval-v2.json'
    app.button[0].click().run()
    assert not app.exception and len(calls)==1
    assert calls[0][0].profile_id=='retrieval-v2' and calls[0][1]['generate'] is False
    assert calls[0][1]['review_directory']==Path('data/reviews/expansion-v1')
    assert any('returns evidence only' in message.value for message in app.info)


def test_shared_reranker_selection_is_explicit_and_widget_changes_do_not_query(monkeypatch):
    app,calls=prepare_app(monkeypatch);app.run()
    next(w for w in app.selectbox if w.label=='Retrieval profile').set_value('retrieval-v2').run()
    next(w for w in app.selectbox if w.label=='Evidence ordering').set_value('cross_encoder').run()
    assert not app.exception and not calls
    app.button[0].click().run()
    assert not app.exception and calls[0][0].selector_id=='cross_encoder'
    assert calls[0][1]['generate'] is False
    next(w for w in app.selectbox if w.label=='Retrieval mode').set_value('vector').run()
    assert len(calls)==1


def test_stale_result_disables_exports_and_failed_new_submit_clears_old_answer(monkeypatch):
    app, calls = prepare_app(monkeypatch)
    app.run().button[0].click().run()
    def stale(*args): raise ValueError('Review head changed')
    monkeypatch.setattr(product, 'prepare_output', stale)
    app.run()
    assert not app.exception and len(app.get('download_button')) == 0
    assert any('export is disabled' in error.value for error in app.error)
    monkeypatch.setattr(pipeline, 'run_query', stale)
    app.button[0].click().run()
    assert 'run' not in app.session_state
    assert len(app.get('download_button')) == 0


def test_completed_run_is_preserved_before_current_display_validation(monkeypatch):
    app, calls = prepare_app(monkeypatch)
    saved = []
    monkeypatch.setattr(pipeline, 'write_immutable', lambda path, text: saved.append((path, text)))
    def stale(*args): raise ValueError('Review changed after query')
    monkeypatch.setattr(product, 'prepare_output', stale)
    app.run().button[0].click().run()
    assert len(calls) == 1 and len(saved) == 1
    assert 'run' not in app.session_state and not app.get('download_button')
