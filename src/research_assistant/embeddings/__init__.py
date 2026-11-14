"""CPU encoders using completed, pinned M0 model artifacts only."""

from __future__ import annotations

import numpy as np
from typing import Protocol

from research_assistant.smoke import encoder_artifact


class TextEncoder(Protocol):
    """Only a pinned revision and checked text encoding cross the retrieval boundary."""

    revision: str

    def encode(self, texts: list[str]) -> list[list[float]]:
        """Return finite, normalized embeddings without truncation."""
        ...


def encode_checked(model, texts: list[str], dimension: int, token_limit: int) -> list[list[float]]:
    """Apply the same no-truncation, finite/unit-vector contract to either frozen encoder."""
    for text in texts:
        if len(model.tokenizer.encode(text, add_special_tokens=True)) > token_limit:
            raise ValueError('Encoder input would be truncated')
    vectors = model.encode(texts, normalize_embeddings=True, batch_size=32)
    if (vectors.shape != (len(texts), dimension) or not np.isfinite(vectors).all()
            or not np.allclose(np.linalg.norm(vectors, axis=1), 1, atol=1e-5)):
        raise ValueError('Invalid encoder output')
    return vectors.tolist()


class Encoder:
    """Own the two fixed tokenizers and the baseline MiniLM model."""

    def __init__(self) -> None:
        from sentence_transformers import SentenceTransformer
        from transformers import AutoTokenizer

        mini_path, self.revision = encoder_artifact("all-MiniLM-L6-v2")
        mpnet_path, self.mpnet_revision = encoder_artifact("all-mpnet-base-v2")
        self.model = SentenceTransformer(str(mini_path), device="cpu", local_files_only=True)
        self.mini_tokenizer = self.model.tokenizer
        self.mpnet_tokenizer = AutoTokenizer.from_pretrained(str(mpnet_path), local_files_only=True)

    def encode(self, texts: list[str]) -> list[list[float]]:
        """Reject truncation and return finite normalized vectors with known dimensions."""
        return encode_checked(self.model, texts, 384, 256)


class MPNetEncoder:
    """Pinned CPU MPNet for the separate vector-only retrieval experiment."""

    def __init__(self) -> None:
        from sentence_transformers import SentenceTransformer

        path, self.revision = encoder_artifact('all-mpnet-base-v2')
        self.model = SentenceTransformer(str(path), device='cpu', local_files_only=True)
        if self.model.max_seq_length != 384:
            raise ValueError('MPNet tokenizer limit differs from the pinned experiment')

    def encode(self, texts: list[str]) -> list[list[float]]:
        """Encode the unchanged query/chunk text without silently truncating it."""
        return encode_checked(self.model, texts, 768, 384)
