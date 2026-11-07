"""HW9 Part 2: sentence embeddings (SentenceTransformers all-MiniLM-L6-v2, 384 dimensions, unit length).

Unit-length vectors make Redis's COSINE distance equal to 1 - cosine similarity."""
from __future__ import annotations

import numpy as np

from cache_layer.config import EMBED_DIM, EMBED_MODEL


class Embedder:
    def __init__(self, model_name: str = EMBED_MODEL) -> None:
        self.model_name = model_name
        self._model = None

    def _load(self):
        if self._model is None:
            from sentence_transformers import SentenceTransformer  # heavy import, only when first needed
            self._model = SentenceTransformer(self.model_name)
        return self._model

    def encode(self, text: str) -> np.ndarray:
        vec = self._load().encode(text, normalize_embeddings=True)
        vec = np.asarray(vec, dtype=np.float32)
        if vec.shape != (EMBED_DIM,):
            raise ValueError(f"expected {EMBED_DIM} dimensions, got {vec.shape}")
        return vec

    def encode_bytes(self, text: str) -> bytes:
        return self.encode(text).tobytes()


def cosine(a: np.ndarray, b: np.ndarray) -> float:
    na, nb = float(np.linalg.norm(a)), float(np.linalg.norm(b))
    return float(np.dot(a, b) / (na * nb)) if na and nb else 0.0
