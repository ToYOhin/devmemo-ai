"""Deterministic embedding adapter used by the local MVP and tests."""

from __future__ import annotations

import hashlib

from app.domain.embeddings import EmbeddingVector


class DeterministicEmbeddingProvider:
    """Generate a stable low-cost vector without downloading a model."""

    name = "deterministic"
    dimension = 8

    def embed(self, text: str) -> EmbeddingVector:
        if not text.strip():
            raise ValueError("embedding input must not be empty")
        digest = hashlib.sha256(text.encode("utf-8")).digest()
        values = tuple(round((byte / 255.0) * 2 - 1, 6) for byte in digest[: self.dimension])
        return EmbeddingVector(values=values, provider=self.name)
