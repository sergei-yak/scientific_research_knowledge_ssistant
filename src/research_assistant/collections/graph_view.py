"""Read-only logical collection graph using the existing source and approval boundaries."""

from __future__ import annotations

from typing import Literal
from urllib.parse import urlsplit

from research_assistant.collections.contracts import ImmutableContract
from research_assistant.collections.reviews import review_directory
from research_assistant.collections.workspace import ReadyCollection, verify_collection
from research_assistant.contracts import fingerprint
from research_assistant.graph.search import SearchRepository
from research_assistant.ingestion.sources import load_corpus_chunks
from research_assistant.retrieval.catalog import ReviewCatalog
from research_assistant.review.facts import projection
from research_assistant.review.store import review_lock


class GraphNode(ImmutableContract):
    """A current source/review object, never an inferred entity or historical proposal."""

    id: str
    kind: Literal['Collection', 'Paper', 'Passage', 'Finding', 'Evaluation', 'Method', 'Dataset', 'Search record']
    label: str
    details: dict


class GraphEdge(ImmutableContract):
    """A directed source-ownership or explicitly reviewed relationship."""

    id: str
    source: str
    target: str
    relation: str
    label: str
    details: dict


class CollectionGraph(ImmutableContract):
    """Complete current logical graph; viewer filters do not change this snapshot."""

    format: Literal['collection-graph-v1'] = 'collection-graph-v1'
    collection_marker: dict
    review_head: str
    review_notice: str
    nodes: list[GraphNode]
    edges: list[GraphEdge]

    @property
    def sha256(self) -> str:
        """Bind the complete map, its source membership and exact review revision."""
        return fingerprint(self.model_dump(mode='json'))


RELATIONS = {
    'HAS_PAPER': 'contains paper', 'HAS_CHUNK': 'contains passage',
    'REPORTS_FINDING': 'reports finding', 'REPORTS_EVALUATION': 'reports evaluation',
    'SUPPORTED_BY': 'supported by', 'REPRESENTS': 'search record for',
    'OF_METHOD': 'evaluates method', 'ON_DATASET': 'evaluated on dataset',
    'ABOUT_METHOD': 'about method', 'ABOUT_DATASET': 'about dataset',
    'MENTIONS': 'mentions (discovery only)',
}


def build_graph(ready: ReadyCollection, chunks: dict, reviewed: dict) -> CollectionGraph:
    """Map verified source/review contracts without creating claims or merging names."""
    nodes, edges = {}, {}

    def node(kind, identity, label, details):
        key = kind + ':' + identity
        value = GraphNode(id=key, kind=kind, label=label, details=details)
        if key in nodes and nodes[key] != value:
            raise ValueError('Conflicting graph node identity')
        nodes[key] = value
        return key

    def edge(source, target, relation, details=None):
        if relation not in RELATIONS or source not in nodes or target not in nodes:
            raise ValueError('Graph relationship has an unknown role or endpoint')
        details = details or {}
        key = fingerprint([source, target, relation, details])
        edges[key] = GraphEdge(id=key, source=source, target=target, relation=relation,
                               label=RELATIONS[relation], details=details)

    collection = ready.collection
    center = node('Collection', collection.corpus_id, collection.name,
                  {'collection_id': collection.collection_id, 'revision': collection.revision,
                   'description': 'Current collection, not a scientific entity'})
    papers, passages = {}, {}
    for document in collection.documents:
        source = ready.sources[document.paper_id]
        label = urlsplit(source.web_url).path.rsplit('/', 1)[-1] if source.web_url else source.filename
        papers[document.paper_id] = node('Paper', document.paper_id, label,
            {'paper_id': document.paper_id, 'source': source.reference, 'url': source.web_url,
             'source_sha256': document.source_sha256, 'indexed_pages': list(document.indexed_pages)})
        edge(center, papers[document.paper_id], 'HAS_PAPER')
    for chunk in sorted(chunks.values(), key=lambda c: (c.paper_id, c.page, c.page_start, c.chunk_id)):
        if chunk.paper_id not in papers:
            raise ValueError('Passage is outside this collection')
        passages[chunk.chunk_id] = node('Passage', chunk.chunk_id, f'PDF p. {chunk.page}: {chunk.text[:65]}',
            {'paper_id': chunk.paper_id, 'page': chunk.page, 'text': chunk.text,
             'source': ready.sources[chunk.paper_id].reference, 'source_sha256': chunk.source_sha256,
             'url': ready.sources[chunk.paper_id].web_url})
        edge(papers[chunk.paper_id], passages[chunk.chunk_id], 'HAS_CHUNK')
    for fact in reviewed['facts']:
        if fact['paper_id'] not in papers:
            raise ValueError('Reviewed claim belongs to another collection')
        sources = []
        for excerpt in fact['evidence']['excerpts']:
            if excerpt['chunk_id'] not in passages or excerpt['paper_id'] != fact['paper_id']:
                raise ValueError('Reviewed graph support is outside its reporting paper')
            sources.append({'paper_id': excerpt['paper_id'], 'page': excerpt['page'],
                'quotation': excerpt['text'], 'source': ready.sources[excerpt['paper_id']].reference,
                'url': ready.sources[excerpt['paper_id']].web_url,
                'start': excerpt['start'], 'end': excerpt['end']})
        kind = 'Evaluation' if fact['kind'] == 'evaluation' else 'Finding'
        claim = node(kind, fingerprint([collection.corpus_id, fact['claim_id'], fact['claim_revision']]),
            fact['claim_text'], {'claim_id': fact['claim_id'], 'revision': fact['claim_revision'],
                'text': fact['claim_text'], 'status': 'Current source-reviewed approval',
                'conditions': fact['evidence']['conditions'], 'sources': sources})
        edge(papers[fact['paper_id']], claim,
             'REPORTS_EVALUATION' if kind == 'Evaluation' else 'REPORTS_FINDING', {'sources': sources})
        search = node('Search record', fact['id'], 'Search representation of ' + fact['claim_id'],
                     {'claim_id': fact['claim_id'], 'description': 'Derived search record, not a separate finding'})
        edge(search, claim, 'REPRESENTS')
        for excerpt in fact['evidence']['excerpts']:
            edge(claim, passages[excerpt['chunk_id']], 'SUPPORTED_BY',
                 {'page': excerpt['page'], 'quotation': excerpt['text'],
                  'start': excerpt['start'], 'end': excerpt['end']})
        for definition in fact['entities']:
            entity = node('Method' if definition['kind'] == 'method' else 'Dataset',
                fingerprint(definition), definition['name'],
                {'entity_id': definition['id'], 'aliases': definition['aliases'],
                 'description': 'Exact reviewed identity. Matching names are not automatically merged.'})
            role = (('OF_METHOD' if definition['kind'] == 'method' else 'ON_DATASET') if kind == 'Evaluation'
                    else ('ABOUT_METHOD' if definition['kind'] == 'method' else 'MENTIONS'))
            role = fact.get('relation_roles', {}).get(definition['id'], role)
            edge(claim, entity, role, {'sources': sources,
                 'interpretation': 'Discovery mention only' if role == 'MENTIONS' else 'Source-reviewed mapping'})
    return CollectionGraph(collection_marker=ready.marker, review_head=reviewed['review_head'],
        review_notice=('Current source-reviewed claims and exact published mappings.' if reviewed['facts'] else
            'Document structure only. No current approved claims or scientific entity connections.'),
        nodes=sorted(nodes.values(), key=lambda n: n.id), edges=sorted(edges.values(), key=lambda e: e.id))


def load_collection_graph(registry, collection_id: str, expected_head: str, settings) -> tuple[CollectionGraph, ReadyCollection]:
    """Revalidate every display/export, holding existing collection/review locks; no inference."""
    with registry.query_lock():
        ready = verify_collection(registry, collection_id, settings, expected_head)
        chunks = load_corpus_chunks(ready.collection.corpus_id)
        directory = review_directory(registry, ready)
        empty = {'review_head': '0' * 64, 'facts': []}
        if not (directory / 'config.json').exists():
            return build_graph(ready, chunks, empty), ready
        with review_lock(directory):
            reviewed = projection(directory, chunks)
            if reviewed['facts']:
                catalog = ReviewCatalog.from_review(ready.collection.corpus_id, reviewed)
                repo = SearchRepository(settings)
                try:
                    with repo.reading(catalog.corpus_id, catalog.head, settings.graph_query_timeout_seconds):
                        repo.check_indexes(catalog.corpus_id, True)
                        repo.fact_vectors(catalog, chunks, ready.snapshot['encoder_revision'], strict_roles=True)
                finally:
                    repo.close()
            graph = build_graph(ready, chunks, reviewed)
            if registry.get(collection_id) != ready.collection:
                raise ValueError('Collection changed during graph validation')
            return graph, ready
