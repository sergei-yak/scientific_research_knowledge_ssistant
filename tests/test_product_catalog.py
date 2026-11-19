"""Product collection bindings preserve scoped retrieval and immutable settings."""
from pathlib import Path
from types import SimpleNamespace
import pytest
from research_assistant import product_catalog as catalog
from research_assistant.settings import Settings


def test_named_corpora_bind_current_review_stores():
    assert catalog.CORPORA['pilot'].review_directory == Path('data/reviews/pilot')
    assert catalog.CORPORA['expanded'].review_directory == Path('data/reviews/expansion-v1')
    assert catalog.CORPORA['pilot'].corpus_id != catalog.CORPORA['expanded'].corpus_id


def test_standard_target_preserves_explicit_settings():
    settings = Settings()
    corpus, bound, scope = catalog.product_target('expanded', 'baseline', settings)
    assert bound is settings and scope is None and corpus.papers == 20


def test_v2_rejects_pilot_before_scope_io(monkeypatch):
    monkeypatch.setattr(catalog, 'load_scope', lambda *args: pytest.fail('No scope read for pilot'))
    with pytest.raises(ValueError, match='twenty-paper'):
        catalog.product_target('pilot', 'retrieval-v2', Settings())


def test_v2_uses_declared_target_without_mutating_settings(monkeypatch):
    captured = []
    def scope(request):
        captured.append(request)
        return SimpleNamespace(target_uri='bolt://127.0.0.1:60395',review_directory='data/reviews/expansion-v1')
    monkeypatch.setattr(catalog, 'load_scope', scope)
    original = Settings()
    corpus, bound, path = catalog.product_target('expanded', 'retrieval-v2', original)
    assert original.neo4j_uri == 'bolt://127.0.0.1:7687'
    assert bound.neo4j_uri == 'bolt://127.0.0.1:60395'
    assert captured[0].corpus_id == corpus.corpus_id
    assert path == 'data/scopes/retrieval-v2.json'


def test_foreign_scope_is_not_offered_and_cannot_select_target(monkeypatch,tmp_path):
    monkeypatch.setattr(catalog,'load_scope',lambda request: SimpleNamespace(target_uri='bolt://127.0.0.1:60395',review_directory=str(tmp_path/'foreign')))
    assert catalog.configured_profiles('expanded') == ['baseline']
    with pytest.raises(ValueError,match='another checkout'):
        catalog.product_target('expanded','retrieval-v2',Settings())


def test_configured_scope_is_explicit_and_pilot_remains_standard(monkeypatch):
    monkeypatch.setattr(catalog,'load_scope',lambda request: SimpleNamespace(review_directory='data/reviews/expansion-v1'))
    assert catalog.configured_profiles('expanded') == ['baseline','retrieval-v2']
    assert catalog.configured_profiles('pilot') == ['baseline']
