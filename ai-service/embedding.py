"""Compatibility exports for the Phase 3 embedding boundary."""

from __future__ import annotations

import hashlib

from app.adapters.embedding import DeterministicEmbeddingProvider


class DeterministicEmbedder:
    """Keep the original list-based helper for existing callers."""

    dimensions = DeterministicEmbeddingProvider.dimension

    def embed(self, text: str) -> list[float]:
        if not text.strip():
            digest = hashlib.sha256(text.encode("utf-8")).digest()
            return [round((byte / 255.0) * 2 - 1, 6) for byte in digest[: self.dimensions]]
        vector = DeterministicEmbeddingProvider().embed(text)
        return list(vector.values)
