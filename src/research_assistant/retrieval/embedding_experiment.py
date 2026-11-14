"""Separate retrieval-only encoder comparison; no gold, prompts or provider calls."""

import json
from pathlib import Path
from typing import Literal

from research_assistant.contracts import QueryRequest, fingerprint
from research_assistant.embeddings import MPNetEncoder, TextEncoder
from research_assistant.graph.mpnet import MPNetRepository, mpnet_index
from research_assistant.ingestion.sources import load_corpus_chunks, source_identity
from research_assistant.pipeline import code_identity, retrieve_vector, write_immutable
from research_assistant.retrieval.service import retrieve_request
from research_assistant.settings import Settings


def setup_mpnet(corpus_id: str, settings: Settings) -> dict:
    """Cache one fixed-source encoding and explicitly publish its separate native index."""
    index = mpnet_index(corpus_id)
    chunks = load_corpus_chunks(corpus_id)
    encoder = MPNetEncoder()
    identity = {'format': 'embedding-experiment-v1', 'corpus_id': corpus_id,
        'source_chunks_sha256': source_identity(chunks), 'encoder': 'all-mpnet-base-v2',
        'encoder_revision': encoder.revision, 'dimensions': 768, 'chunk_count': len(chunks),
        'normalized': True, 'device': 'cpu', 'batch_size': 32, 'max_tokens': 384, 'index': index}
    cache = Path('data/embeddings') / corpus_id / fingerprint(identity)
    if cache.exists():
        manifest = json.loads((cache / 'manifest.json').read_text(encoding='utf-8'))
        vectors = json.loads((cache / 'vectors.json').read_text(encoding='utf-8'))
        if (any(manifest.get(key) != value for key, value in identity.items())
                or manifest['vectors_sha256'] != fingerprint(vectors)):
            raise ValueError('MPNet cache identity/content changed; never overwrite it')
    else:
        vectors = encoder.encode([chunk.text for chunk in chunks.values()])
        manifest = {**identity, 'vectors_sha256': fingerprint(vectors)}
        write_immutable(cache / 'vectors.json', json.dumps(vectors) + '\n')
        write_immutable(cache / 'manifest.json', json.dumps(manifest, sort_keys=True, indent=2) + '\n')
    repo = MPNetRepository(settings)
    try:
        return {'task_id': 'M4.2.1', 'experiment': repo.setup(corpus_id, chunks, vectors, manifest),
                'cache': str(cache), 'provider_calls': 0}
    finally:
        repo.close()


def retrieve_embedding(corpus_id: str, question: str, encoder_name: Literal['minilm', 'mpnet'],
                       settings: Settings, *, encoder: TextEncoder | None = None) -> dict:
    """Apply the preserved vector ranking/threshold/packing contract to one chosen encoder."""
    request = QueryRequest(corpus_id=corpus_id, question=question, mode='vector')
    if encoder_name == 'minilm':
        source, result = retrieve_request(request, settings, encoder=encoder)
        experiment = {'encoder': 'all-MiniLM-L6-v2', 'encoder_revision': source['encoder_revision'],
                      'dimensions': 384, 'device': 'cpu', 'normalized': True}
    elif encoder_name == 'mpnet':
        encoder = encoder if encoder is not None else MPNetEncoder()
        repo = MPNetRepository(settings)
        try:
            source, experiment = repo.snapshot(corpus_id), repo.experiment(corpus_id)
            if encoder.revision != experiment['encoder_revision']:
                raise ValueError('MPNet query encoder differs from the indexed experiment')
            result = retrieve_vector(request, repo, encoder)
        finally:
            repo.close()
    else:
        raise ValueError('Unknown encoder; no automatic substitution')
    return {'task_id': 'M4.2.1', 'request': request.model_dump(), 'corpus': source,
            'embedding_experiment': experiment, 'code': code_identity(),
            'retrieval': result.model_dump(mode='json'), 'generation': None, 'provider_calls': 0}
