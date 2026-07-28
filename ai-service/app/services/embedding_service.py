"""Embedding orchestration independent from FastAPI and vector DB SDKs."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Mapping

from app.adapters.embedding import DeterministicEmbeddingProvider
from app.adapters.vector_store import InMemoryVectorStore
from app.domain.embeddings import EmbeddingProvider, VectorRecord, VectorStore


@dataclass(frozen=True)
class EmbeddedMemo:
    """Stable API-facing result from embedding one Memo."""

    embedding_id: str
    memo_id: str
    dimension: int
    provider: str


class EmbeddingService:
    """Coordinate provider output and vector-store upsert."""

    def __init__(self, provider: EmbeddingProvider | None = None, store: VectorStore | None = None) -> None:
        self.provider = provider or DeterministicEmbeddingProvider()
        self.store = store or InMemoryVectorStore(self.provider.dimension)
        if self.provider.dimension != self.store.dimension:
            raise ValueError("embedding provider and vector store dimensions must match")

    def embed_memo(
        self,
        memo_id: str,
        content: str,
        metadata: Mapping[str, object] | None = None,
    ) -> EmbeddedMemo:
        stored_memo_id = str(memo_id).strip()
        if not stored_memo_id:
            raise ValueError("memo_id must not be empty")
        if not content.strip():
            raise ValueError("embedding content must not be empty")

        embedding = self.provider.embed(content)
        embedding_id = _embedding_id(stored_memo_id)
        self.store.upsert(
            VectorRecord(
                embedding_id=embedding_id,
                memo_id=stored_memo_id,
                vector=embedding.values,
                metadata=dict(metadata or {}),
            )
        )
        return EmbeddedMemo(
            embedding_id=embedding_id,
            memo_id=stored_memo_id,
            dimension=embedding.dimension,
            provider=embedding.provider,
        )

    def delete_memo(self, memo_id: str | int) -> bool:
        """Delete the stable vector associated with one Memo."""

        stored_memo_id = str(memo_id).strip()
        if not stored_memo_id:
            raise ValueError("memo_id must not be empty")
        return self.store.delete(_embedding_id(stored_memo_id))


def _embedding_id(memo_id: str) -> str:
    digest = hashlib.sha256(memo_id.encode("utf-8")).hexdigest()[:24]
    return f"memo-{digest}"
