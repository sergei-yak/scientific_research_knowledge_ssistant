"""Offline Streamlit interaction tests; no service, model or private evaluation reads."""

from pathlib import Path

from streamlit.testing.v1 import AppTest

from research_assistant import pipeline, product, product_catalog
from research_assistant.settings import Settings
from test_product import fixture_run

APP = Path('src/research_assistant/ui/app.py')


def prepare_app(monkeypatch, with_answer=False, with_connection=False):
    run, catalog, _ = fixture_run('discovery')
    if with_answer:
        from research_assistant.contracts import DraftAnswer
        from research_assistant.generation import validate_answer
        answer = validate_answer(DraftAnswer(answer='A supported generated answer.', insufficient_evidence=False, citations=['E1']), run.retrieval)
        run = run.model_copy(update={'result':answer,'generation_requested':True})
    if with_connection:
        evidence = [item.model_copy(deep=True) for item in run.retrieval.evidence]
        evidence[0].graph_paths = [{'template':'shared_method','reporting_paper_id':evidence[0].paper_ids[0]}]
        run = run.model_copy(update={'retrieval':run.retrieval.model_copy(update={'evidence':evidence,'effective_mode':'graph','fallback_reason':None})})
    calls = []
    monkeypatch.setattr(Settings, 'from_env', classmethod(lambda cls: Settings()))
    def target(key, profile, settings):
        uri = 'bolt://127.0.0.1:60395' if profile == 'retrieval-v2' else settings.neo4j_uri
        return product_catalog.CORPORA[key], settings.model_copy(update={'neo4j_uri': uri}), ('data/scopes/retrieval-v2.json' if profile == 'retrieval-v2' else None)
    monkeypatch.setattr(product_catalog, 'product_target', target)
    monkeypatch.setattr(product_catalog, 'configured_profiles', lambda key: ['baseline','retrieval-v2'] if key == 'expanded' else ['baseline'])
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
    next(w for w in app.selectbox if w.label=='Paper collection').set_value('expanded').run()
    next(w for w in app.selectbox if w.label=='Retrieval profile').set_value('retrieval-v2').run()
    assert not app.exception and not calls
    assert app.checkbox[0].disabled and not app.checkbox[0].value
    assert not app.text_input
    assert calls == []
    app.button[0].click().run()
    assert not app.exception and len(calls)==1
    assert calls[0][0].profile_id=='retrieval-v2' and calls[0][1]['generate'] is False
    assert calls[0][1]['review_directory']==Path('data/reviews/expansion-v1')
    assert any('returns evidence only' in message.value for message in app.info)


def test_shared_reranker_selection_is_explicit_and_widget_changes_do_not_query(monkeypatch):
    app,calls=prepare_app(monkeypatch);app.run()
    next(w for w in app.selectbox if w.label=='Paper collection').set_value('expanded').run()
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


def test_named_expanded_corpus_binds_review_store_and_hides_previous_result(monkeypatch):
    app, calls = prepare_app(monkeypatch)
    display_reviews = []
    original = product.prepare_output
    def output(run, settings, **kwargs):
        display_reviews.append(kwargs['review_directory'])
        return original(run, settings, **kwargs)
    monkeypatch.setattr(product, 'prepare_output', output)
    app.run().button[0].click().run()
    assert calls[0][0].corpus_id == product.PILOT_CORPUS
    next(w for w in app.selectbox if w.label == 'Paper collection').set_value('expanded').run()
    assert len(calls) == 1 and not app.get('download_button') and 'run' not in app.session_state
    app.button[0].click().run()
    assert not app.exception and len(calls) == 2
    assert calls[1][0].corpus_id == product_catalog.CORPORA['expanded'].corpus_id
    assert calls[1][1]['review_directory'] == Path('data/reviews/expansion-v1')
    assert display_reviews[-2:] == [Path('data/reviews/expansion-v1')]*2
    assert any(w.value == 'Source evidence' for w in app.subheader)
    assert any(w.value == 'Graph connections used' for w in app.subheader)


def test_pilot_has_only_standard_profile_and_synthesis_is_explicit(monkeypatch):
    app, calls = prepare_app(monkeypatch)
    app.run()
    profile = next(w for w in app.selectbox if w.label == 'Retrieval profile')
    assert profile.options == ['Standard'] and profile.value == 'baseline'
    assert not app.checkbox[0].value
    app.checkbox[0].check().run()
    assert not calls
    app.button[0].click().run()
    assert not app.exception and calls[0][1]['generate'] is True


def test_unconfigured_experimental_scope_is_not_offered(monkeypatch):
    app, calls = prepare_app(monkeypatch)
    monkeypatch.setattr(product_catalog, 'configured_profiles', lambda key: ['baseline'])
    app.run()
    next(w for w in app.selectbox if w.label == 'Paper collection').set_value('expanded').run()
    assert not app.exception and not calls
    assert next(w for w in app.selectbox if w.label == 'Retrieval profile').options == ['Standard']
    assert any('separate research checkout' in w.value for w in app.caption)


def test_generated_citation_aliases_keep_sources_and_downloads_visible(monkeypatch):
    app, calls = prepare_app(monkeypatch, with_answer=True)
    app.run().button[0].click().run()
    assert not app.exception and not app.error and len(calls) == 1
    assert any(w.value == 'Cited source cards: E1' for w in app.caption)
    assert len(app.get('download_button')) == 2
    assert any(w.value == 'Source evidence' for w in app.subheader)
    app.run()
    assert len(calls) == 1 and not app.error


def test_selected_graph_connection_renders_inside_source_card(monkeypatch):
    app, calls = prepare_app(monkeypatch, with_connection=True)
    app.run().button[0].click().run()
    assert not app.exception and not app.error
    assert any('Route: shared method' in w.value for w in app.caption)
    assert len(app.get('download_button')) == 2
