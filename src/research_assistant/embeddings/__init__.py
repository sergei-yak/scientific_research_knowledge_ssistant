"""CPU encoders using completed, pinned M0 model artifacts only."""

from __future__ import annotations

import numpy as np

from research_assistant.smoke import encoder_artifact


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
        for text in texts:
            if len(self.mini_tokenizer.encode(text, add_special_tokens=True)) > 256:
                raise ValueError("MiniLM input would be truncated")
        vectors = self.model.encode(texts, normalize_embeddings=True, batch_size=32)
        if vectors.shape != (len(texts), 384) or not np.isfinite(vectors).all():
            raise ValueError("Invalid encoder output")
        return vectors.tolist()
