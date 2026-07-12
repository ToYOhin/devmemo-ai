"""Embedding boundary reserved for the RAG phase."""

from __future__ import annotations

import hashlib


class DeterministicEmbedder:
    """Stable test vector; replace with a model-backed adapter in Phase 3."""

    dimensions = 8

    def embed(self, text: str) -> list[float]:
        digest = hashlib.sha256(text.encode("utf-8")).digest()
        return [round((byte / 255.0) * 2 - 1, 6) for byte in digest[: self.dimensions]]
