"""Current collection graph integrity and UI tests, using explicitly synthetic review input."""

import json

import pytest

from research_assistant.collections import graph_view, reviews
from research_assistant.ingestion.sources import load_corpus_chunks
from research_assistant.ui.collection_graph import graph_html
from test_user_workspace import scene, prepare_ui
from test_user_review import review_scene, proposal, present, decide, publish


@pytest.fixture
def graph_scene(review_scene, monkeypatch):
    """Keep actual journals/sources; replace only the external, already-tested graph boundary."""
    parent = reviews.SearchRepository
    class Repository(parent):
        def fact_vectors(self, catalog, *args, strict_roles=False):
            assert strict_roles is True
            if review_scene.native_failure:
                raise ValueError(review_scene.native_failure)
            return super().fact_vectors(catalog, *args)
    monkeypatch.setattr(graph_view, 'SearchRepository', Repository)
    review_scene.native_failure = None
    return review_scene


def load(s, row=None):
    row = row or s.row
    return graph_view.load_collection_graph(s.registry, row.collection_id, row.sha256, s.settings)[0]


def test_source_only_graph_is_complete_scoped_and_has_no_scientific_links(scene):
    graph = load(scene)
    chunks = load_corpus_chunks(scene.row.corpus_id)
    assert len(graph.nodes) == 2 + len(chunks)
    assert len(graph.edges) == 1 + len(chunks)
    assert {n.kind for n in graph.nodes} == {'Collection', 'Paper', 'Passage'}
    assert {e.relation for e in graph.edges} == {'HAS_PAPER', 'HAS_CHUNK'}
    assert graph.collection_marker['collection_sha256'] == scene.row.sha256
    assert graph.review_head == '0' * 64 and not scene.calls


def test_approved_graph_preserves_entities_roles_quotes_and_representation(graph_scene):
    s = graph_scene
    revision = proposal(s, dataset='Fixture data')
    decide(s, present(s, revision)); publish(s)
    graph = load(s)
    assert {n.kind for n in graph.nodes} == {'Collection', 'Paper', 'Passage', 'Finding', 'Method', 'Dataset', 'Search record'}
    assert {'ABOUT_METHOD', 'MENTIONS', 'SUPPORTED_BY', 'REPRESENTS', 'REPORTS_FINDING'} <= {e.relation for e in graph.edges}
    assert 'ABOUT_DATASET' not in {e.relation for e in graph.edges}
    mention = next(e for e in graph.edges if e.relation == 'MENTIONS')
    assert mention.details['interpretation'] == 'Discovery mention only'
    claim = next(n for n in graph.nodes if n.kind == 'Finding')
    assert claim.details['sources'][0]['quotation'] == revision.draft.quotes[0]
    assert graph.sha256 == load(s).sha256 and not s.calls


@pytest.mark.parametrize('decision', [None, 'rejected', 'needs_review'])
def test_unapproved_claims_never_become_graph_nodes(graph_scene, decision):
    s = graph_scene; revision = proposal(s)
    if decision: decide(s, present(s, revision), decision)
    assert not any(n.kind in {'Finding', 'Method'} for n in load(s).nodes)


@pytest.mark.parametrize('failure', ['Graph relationship role differs from its exact approved mapping',
    'Graph fact support relationships changed', 'Graph alias/entity identity changed', 'Required indexes unavailable'])
def test_native_integrity_failure_cannot_render_approved_looking_partial_graph(graph_scene, failure):
    s = graph_scene; revision = proposal(s); decide(s, present(s, revision)); publish(s)
    s.native_failure = failure
    with pytest.raises(ValueError, match=failure): load(s)


def test_stale_publication_blocks_graph_and_revocation_removes_nodes(graph_scene):
    s = graph_scene; revision = proposal(s); decide(s, present(s, revision))
    with pytest.raises(ValueError): load(s)
    publish(s); assert any(n.kind == 'Finding' for n in load(s).nodes)
    decide(s, present(s, revision), 'rejected')
    assert not any(n.kind == 'Finding' for n in load(s).nodes)


def test_other_collection_and_changed_head_do_not_inherit_claims(graph_scene):
    s = graph_scene; revision = proposal(s); decide(s, present(s, revision)); publish(s)
    other = s.indexed('Separate topic', 'different.pdf', 'An unrelated source in another collection.')
    assert not any(n.kind in {'Finding', 'Method'} for n in load(s, other).nodes)
    with pytest.raises(ValueError):
        graph_view.load_collection_graph(s.registry, other.collection_id, s.row.sha256, s.settings)


def test_changed_pdf_blocks_graph_source_display(scene):
    document = scene.row.documents[0]
    # Resolve only the owned source path declared by the genuine synthetic import.
    from research_assistant.collections.workspace import verify_collection
    ready = verify_collection(scene.registry, scene.row.collection_id, scene.settings, scene.row.sha256)
    assert ready.sources[document.paper_id].data
    path = scene.registry._path('sources', document.source_sha256 + '.pdf')
    path.write_bytes(b'corrupt changed PDF')
    with pytest.raises(ValueError): load(scene)


def test_map_does_not_merge_same_names_with_distinct_reviewed_identities(graph_scene):
    s = graph_scene
    revision = proposal(s); decide(s, present(s, revision)); publish(s)
    ready = graph_view.verify_collection(s.registry, s.row.collection_id, s.settings, s.row.sha256)
    directory = s.registry.review_directory(s.row)
    from research_assistant.review.facts import projection
    chunks = load_corpus_chunks(s.row.corpus_id); reviewed = projection(directory, chunks)
    second = json.loads(json.dumps(reviewed['facts'][0]))
    second['claim_id'] += '-different'; second['id'] += '-different'
    second['entities'][0]['id'] += '-different'
    reviewed['facts'].append(second)
    graph = graph_view.build_graph(ready, chunks, reviewed)
    methods = [n for n in graph.nodes if n.kind == 'Method']
    assert len(methods) == 2 and methods[0].label == methods[1].label


def test_html_treats_document_text_as_data_and_retains_every_node(scene):
    graph = load(scene)
    malicious = '</script><script>alert("paper")</script>&<b>'
    graph = graph.model_copy(update={'nodes': [n.model_copy(update={'label': malicious}) for n in graph.nodes]})
    html = graph_html(graph)
    assert malicious not in html and '\\u003c/script\\u003e' in html
    assert 'textContent' in html and 'innerHTML' not in html
    assert 'src="https://' not in html and 'src="http://' not in html
    assert 'Full graph' in html and 'Showing ${visible.length} of ${data.nodes.length}' in html
    assert html.count('id="graph-data"') == 1


def test_complete_map_has_no_hidden_passage_limit_at_collection_capacity(scene):
    ready = graph_view.verify_collection(scene.registry, scene.row.collection_id, scene.settings, scene.row.sha256)
    original = next(iter(load_corpus_chunks(scene.row.corpus_id).values()))
    chunks = {f'synthetic-{i}': original.model_copy(update={'chunk_id': f'synthetic-{i}'}) for i in range(3000)}
    graph = graph_view.build_graph(ready, chunks, {'review_head': '0' * 64, 'facts': []})
    assert len(graph.nodes) == 3002 and len(graph.edges) == 3001
    assert len([n for n in graph.nodes if n.kind == 'Passage']) == 3000
    assert len(json.loads(graph.model_dump_json())['nodes']) == 3002


def test_graph_toggle_displays_component_without_running_a_question(scene, monkeypatch):
    app = prepare_ui(scene, monkeypatch).run()
    assert not app.exception and not scene.calls
    next(c for c in app.checkbox if c.label == 'Show collection graph').check().run()
    assert not app.exception and not scene.calls
    assert any(s.value == 'Collection graph explorer' for s in app.subheader)
    assert not any('Graph view is unavailable' in e.value for e in app.error)
