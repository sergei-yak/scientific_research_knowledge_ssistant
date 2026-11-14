"""Encoder/index guards preserve source scope and reject incompatible experiment data."""

from types import SimpleNamespace

import numpy as np
import pytest

from research_assistant.embeddings import encode_checked
from research_assistant.graph.mpnet import MPNetRepository
from research_assistant.graph.repository import corpus_names
from research_assistant.retrieval.embedding_experiment import retrieve_embedding


def test_overlong_input_is_rejected_before_model_inference():
    model = SimpleNamespace(tokenizer=SimpleNamespace(encode=lambda *a, **k: [1] * 385))
    with pytest.raises(ValueError, match='truncated'):
        encode_checked(model, ['Synthetic text'], 768, 384)


@pytest.mark.parametrize('vector', [np.zeros((1, 768)), np.full((1, 768), np.nan), np.ones((1, 384))])
def test_encoder_rejects_wrong_dimension_nonfinite_and_nonunit_outputs(vector):
    model = SimpleNamespace(tokenizer=SimpleNamespace(encode=lambda *a, **k: [1]),
                            encode=lambda *a, **k: vector)
    with pytest.raises(ValueError, match='encoder output'):
        encode_checked(model, ['Synthetic text'], 768, 384)


@pytest.mark.parametrize('vectors', [[[0.0] * 384], [[0.0] * 768], [[float('nan')] * 768]])
def test_invalid_index_vectors_fail_before_any_database_access(vectors):
    repository = object.__new__(MPNetRepository)
    with pytest.raises(ValueError, match='vectors'):
        repository.setup('a' * 64, {'synthetic': object()}, vectors, {})


def test_unknown_encoder_does_not_construct_a_model_or_substitute_a_condition():
    with pytest.raises(ValueError, match='Unknown encoder'):
        retrieve_embedding('a' * 64, 'Synthetic question?', 'other', None)


@pytest.mark.parametrize('change', ['dimension', 'property', 'label', 'offline', 'missing'])
def test_native_index_collision_or_unavailability_is_an_error(change):
    label, _ = corpus_names('a' * 64)
    row = {'labelsOrTypes': [label], 'properties': ['embedding_768'], 'state': 'ONLINE',
           'options': {'indexConfig': {'vector.dimensions': 768, 'vector.similarity_function': 'cosine'}}}
    if change == 'dimension': row['options']['indexConfig']['vector.dimensions'] = 384
    if change == 'property': row['properties'] = ['embedding_384']
    if change == 'label': row['labelsOrTypes'] = ['AnotherCorpus']
    if change == 'offline': row['state'] = 'POPULATING'
    if change == 'missing': row = None
    session = SimpleNamespace(run=lambda *a, **k: SimpleNamespace(single=lambda: row))
    with pytest.raises(ValueError, match='index'):
        MPNetRepository._index_ready(None, session, 'a' * 64)
