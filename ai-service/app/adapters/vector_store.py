"""Low-cost in-memory vector store for Phase 3 boundary tests."""

from __future__ import annotations

import math
from collections.abc import Sequence

from app.domain.embeddings import (
    VectorDimensionError,
    VectorRecord,
    VectorSearchResult,
    VectorStoreHealth,
)


class InMemoryVectorStore:
    """Deterministic vector store that can later be replaced by Qdrant."""

    def __init__(self, dimension: int) -> None:
        if dimension <= 0:
            raise ValueError("vector dimension must be positive")
        self.dimension = dimension
        self._records: dict[str, VectorRecord] = {}

    def upsert(self, record: VectorRecord) -> None:
        self._validate_vector(record.vector)
        if not record.embedding_id:
            raise ValueError("embedding_id must not be empty")
        if not record.memo_id:
            raise ValueError("memo_id must not be empty")
        self._records[record.embedding_id] = VectorRecord(
            embedding_id=record.embedding_id,
            memo_id=record.memo_id,
            vector=tuple(record.vector),
            metadata=dict(record.metadata),
        )

    def search(self, query: Sequence[float], limit: int = 5) -> list[VectorSearchResult]:
        self._validate_vector(query)
        if limit <= 0:
            raise ValueError("search limit must be positive")

        scored = [
            VectorSearchResult(
                embedding_id=record.embedding_id,
                memo_id=record.memo_id,
                score=_cosine_similarity(query, record.vector),
                metadata=dict(record.metadata),
            )
            for record in self._records.values()
        ]
        scored.sort(key=lambda result: (-result.score, result.embedding_id))
        return scored[:limit]

    def search_visible_memos(
        self,
        query: Sequence[float],
        visible_memo_ids: frozenset[str],
        limit: int = 5,
    ) -> list[VectorSearchResult]:
        """Search only the Memos authorized by the Memos service boundary."""

        self._validate_vector(query)
        if limit <= 0:
            raise ValueError("search limit must be positive")

        scored = [
            VectorSearchResult(
                embedding_id=record.embedding_id,
                memo_id=record.memo_id,
                score=_cosine_similarity(query, record.vector),
                metadata=dict(record.metadata),
            )
            for record in self._records.values()
            if record.memo_id in visible_memo_ids
        ]
        scored.sort(key=lambda result: (-result.score, result.embedding_id))
        return scored[:limit]

    def delete(self, embedding_id: str) -> bool:
        return self._records.pop(embedding_id, None) is not None

    def health(self) -> VectorStoreHealth:
        return VectorStoreHealth(
            provider="memory",
            available=True,
            dimension=self.dimension,
            status="ready",
            point_count=len(self._records),
        )

    def _validate_vector(self, vector: Sequence[float]) -> None:
        if len(vector) != self.dimension:
            raise VectorDimensionError(
                f"expected vector dimension {self.dimension}, got {len(vector)}"
            )


def _cosine_similarity(left: Sequence[float], right: Sequence[float]) -> float:
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return round(sum(a * b for a, b in zip(left, right, strict=True)) / (left_norm * right_norm), 6)
