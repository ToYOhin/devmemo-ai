"""Provider-neutral contracts for memo embeddings and vector indexing."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Protocol, Sequence


class VectorDimensionError(ValueError):
    """Raised when a vector does not match the configured dimension."""


@dataclass(frozen=True)
class EmbeddingVector:
    """A model-independent vector returned by an embedding provider."""

    values: tuple[float, ...]
    provider: str

    @property
    def dimension(self) -> int:
        return len(self.values)


@dataclass(frozen=True)
class VectorRecord:
    """A memo vector and the metadata needed to cite it later."""

    embedding_id: str
    memo_id: str
    vector: tuple[float, ...]
    metadata: Mapping[str, object]


@dataclass(frozen=True)
class VectorSearchResult:
    """A provider-neutral vector search result."""

    embedding_id: str
    memo_id: str
    score: float
    metadata: Mapping[str, object]


@dataclass(frozen=True)
class VectorStoreHealth:
    """Provider-neutral read-only status for an index store."""

    provider: str
    available: bool
    dimension: int
    status: str
    collection: str | None = None
    point_count: int | None = None
    detail: str | None = None


class EmbeddingProvider(Protocol):
    """Generate vectors without exposing a model SDK to the domain."""

    name: str
    dimension: int

    def embed(self, text: str) -> EmbeddingVector:
        ...


class VectorStore(Protocol):
    """Store and search vectors without exposing a vector DB SDK."""

    dimension: int

    def health(self) -> VectorStoreHealth:
        ...

    def upsert(self, record: VectorRecord) -> None:
        ...

    def search(self, query: Sequence[float], limit: int = 5) -> list[VectorSearchResult]:
        ...

    def search_visible_memos(
        self,
        query: Sequence[float],
        visible_memo_ids: frozenset[str],
        limit: int = 5,
    ) -> list[VectorSearchResult]:
        ...

    def delete(self, embedding_id: str) -> bool:
        ...
