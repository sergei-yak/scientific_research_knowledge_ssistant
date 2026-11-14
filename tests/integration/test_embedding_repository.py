"""UUID-owned 384/768-D separation proof; no real corpus mutation or model/provider calls."""

import os
import uuid

import pytest

from research_assistant.contracts import Chunk, PaperManifestEntry, fingerprint, text_sha
from research_assistant.graph.mpnet import MPNetRepository, mpnet_index
from research_assistant.graph.repository import GraphRepository, PROJECT, corpus_names
from research_assistant.ingestion import sources
from research_assistant.settings import Settings


@pytest.mark.integration
@pytest.mark.skipif(os.getenv('RUN_EMBEDDING_SMOKE') != '1', reason='Set RUN_EMBEDDING_SMOKE=1 for UUID-owned embedding proof')
def test_native_encoder_separation_frozen_guard_and_source_preservation(monkeypatch):
    token = uuid.uuid4().hex
    corpus = fingerprint(['synthetic-embedding-fixture', token])
    text = 'Synthetic embedding fixture only.'
    chunk = Chunk(chunk_id='fixture-chunk-' + token, paper_id='fixture-paper-' + token,
        source_sha256='a' * 64, source_url='https://example.invalid/synthetic', page=1, section='Synthetic',
        page_start=0, page_end=len(text), text=text, text_sha256=text_sha(text), parser_version='fixture',
        chunker_version='fixture', mini_tokens=8, mpnet_tokens=8)
    paper = PaperManifestEntry(paper_id=chunk.paper_id, title='SYNTHETIC ONLY', source_url=chunk.source_url,
        source_sha256=chunk.source_sha256, local_path='unused.pdf', rights='Synthetic', rights_url=chunk.source_url,
        selected_pages=[1], selection_reason='UUID-owned native fixture')
    chunks = {chunk.chunk_id: chunk}
    original_loader = sources.load_corpus_chunks
    loader = lambda key: chunks if key == corpus else original_loader(key)
    monkeypatch.setattr(sources, 'load_corpus_chunks', loader)
    monkeypatch.setattr('research_assistant.graph.mpnet.load_corpus_chunks', loader)
    mini, mpnet = [1.0] + [0.0] * 383, [1.0] + [0.0] * 767
    base = GraphRepository(Settings.from_env())
    repo = MPNetRepository(Settings.from_env())
    try:
        base.ingest({'corpus_id': corpus, 'encoder_revision': 'fixture-mini'}, paper, [chunk], [mini])
        manifest = {'corpus_id': corpus, 'encoder_revision': 'fixture-mpnet', 'dimensions': 768,
                    'chunk_count': 1, 'source_chunks_sha256': sources.source_identity(chunks),
                    'vectors_sha256': fingerprint([mpnet])}
        assert repo.setup(corpus, chunks, [mpnet], manifest) == manifest
        assert base.vector_candidates(corpus, mini)[0][0] == chunk
        assert repo.vector_candidates(corpus, mpnet)[0][0] == chunk
        with repo.driver.session(database=repo.database) as session:
            session.run('MATCH (n:Chunk {id:$id,project:$project}) REMOVE n.mpnet_encoder_revision',
                        id=chunk.chunk_id, project=PROJECT).consume()
        with pytest.raises(ValueError, match='conflict'):
            repo.setup(corpus, chunks, [mpnet], manifest)
        with repo.driver.session(database=repo.database) as session:
            session.run('MATCH (n:Chunk {id:$id,project:$project}) SET n.mpnet_encoder_revision=$revision',
                        id=chunk.chunk_id, project=PROJECT, revision='fixture-mpnet').consume()
            actual = session.run('MATCH (n:Chunk {id:$id,project:$project}) '
                'RETURN n.embedding_384 AS mini,n.encoder_revision AS revision,n.source_json AS source',
                id=chunk.chunk_id, project=PROJECT).single()
            assert actual['mini'] == mini and actual['revision'] == 'fixture-mini'
            assert actual['source'] == chunk.model_dump_json()
            session.run('MATCH (c:Corpus {id:$id,project:$project}) SET c.frozen=true',
                        id=corpus, project=PROJECT).consume()
        assert repo.vector_candidates(corpus, mpnet)[0][0] == chunk
        with pytest.raises(ValueError, match='frozen'):
            repo.setup(corpus, chunks, [mpnet], manifest)
        with pytest.raises(ValueError, match='Query vector'):
            repo.vector_candidates(corpus, mini)
    finally:
        with repo.driver.session(database=repo.database) as session:
            for index in (corpus_names(corpus)[1], mpnet_index(corpus)):
                session.run(f'DROP INDEX `{index}` IF EXISTS').consume()
            session.run('MATCH (n {project:$project}) WHERE n.id IN $ids DETACH DELETE n',
                        project=PROJECT, ids=[corpus, chunk.chunk_id, paper.paper_id]).consume()
        repo.close()
        base.close()
