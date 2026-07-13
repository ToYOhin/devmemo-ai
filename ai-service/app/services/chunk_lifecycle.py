"""Explicit opt-in lifecycle orchestration for Memo chunk vectors."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Protocol

from app.domain.embeddings import EmbeddingProvider, VectorStore
from app.domain.memo_chunking import CHUNK_INDEX_MODE, CHUNK_INDEX_VERSION, chunk_memo
from app.services.offline_chunk_index import OfflineChunkIndex


@dataclass(frozen=True)
class ChunkIndexState:
    memo_id: str
    index_version: str
    chunk_ids: tuple[str, ...]


@dataclass(frozen=True)
class ChunkIndexStateStats:
    tracked_memos: int
    tracked_chunks: int
    status: str
    detail: str | None = None


class ChunkIndexStateStore(Protocol):
    """Persist only lifecycle bookkeeping, never the original Markdown."""

    def get(self, memo_id: str) -> ChunkIndexState | None:
        ...

    def save(self, memo_id: str, index_version: str, chunk_ids: tuple[str, ...]) -> None:
        ...

    def delete(self, memo_id: str) -> bool:
        ...

    @property
    def backend_name(self) -> str:
        ...

    def stats(self) -> ChunkIndexStateStats:
        ...


@dataclass(frozen=True)
class ChunkLifecycleResult:
    memo_id: str
    index_version: str
    index_mode: str
    chunk_count: int
    upserted_count: int
    deleted_count: int
    provider: str


@dataclass(frozen=True)
class ChunkIndexHealth:
    index_mode: str
    index_version: str
    provider: str
    available: bool
    status: str
    dimension: int
    point_count: int | None
    tracked_memos: int
    tracked_chunks: int
    state_backend: str
    detail: str | None = None


class ChunkLifecycleCoordinator:
    """Upsert current chunks before deleting stale IDs from the same version."""

    def __init__(
        self,
        provider: EmbeddingProvider,
        store: VectorStore,
        state_store: ChunkIndexStateStore | None = None,
    ) -> None:
        self.provider = provider
        self.store = store
        if provider.dimension != self.store.dimension:
            raise ValueError("embedding provider and vector store dimensions must match")
        if state_store is None:
            raise ValueError("chunk state store must be configured explicitly")
        self.state_store = state_store
        self.index = OfflineChunkIndex(provider=provider, store=self.store)

    def upsert_memo(
        self,
        memo_id: str,
        content: str,
        metadata: Mapping[str, object] | None = None,
        *,
        max_chars: int = 1200,
    ) -> ChunkLifecycleResult:
        chunks = chunk_memo(memo_id, content, max_chars=max_chars, metadata=metadata)
        current_ids = tuple(chunk.chunk_id for chunk in chunks)
        previous = self.state_store.get(str(memo_id))
        previous_ids = (
            previous.chunk_ids
            if previous is not None and previous.index_version == CHUNK_INDEX_VERSION
            else ()
        )

        self.index.upsert(chunks)
        stale_ids = tuple(chunk_id for chunk_id in previous_ids if chunk_id not in current_ids)
        deleted_count = sum(self.store.delete(chunk_id) for chunk_id in stale_ids)
        if current_ids:
            self.state_store.save(str(memo_id), CHUNK_INDEX_VERSION, current_ids)
        else:
            self.state_store.delete(str(memo_id))
        return ChunkLifecycleResult(
            memo_id=str(memo_id),
            index_version=CHUNK_INDEX_VERSION,
            index_mode=CHUNK_INDEX_MODE,
            chunk_count=len(chunks),
            upserted_count=len(chunks),
            deleted_count=deleted_count,
            provider=self.provider.name,
        )

    def delete_memo(self, memo_id: str) -> ChunkLifecycleResult:
        state = self.state_store.get(str(memo_id))
        chunk_ids = (
            state.chunk_ids
            if state is not None and state.index_version == CHUNK_INDEX_VERSION
            else ()
        )
        deleted_count = sum(self.store.delete(chunk_id) for chunk_id in chunk_ids)
        self.state_store.delete(str(memo_id))
        return ChunkLifecycleResult(
            memo_id=str(memo_id),
            index_version=CHUNK_INDEX_VERSION,
            index_mode=CHUNK_INDEX_MODE,
            chunk_count=0,
            upserted_count=0,
            deleted_count=deleted_count,
            provider=self.provider.name,
        )

    def health(self) -> ChunkIndexHealth:
        """Report vector points and lifecycle state without mutating either store."""

        store_health = self.store.health()
        state_stats = self.state_store.stats()
        available = store_health.available and state_stats.status == "ready"
        detail = state_stats.detail or store_health.detail
        return ChunkIndexHealth(
            index_mode=CHUNK_INDEX_MODE,
            index_version=CHUNK_INDEX_VERSION,
            provider=store_health.provider,
            available=available,
            status="ready" if available else "degraded",
            dimension=store_health.dimension,
            point_count=store_health.point_count,
            tracked_memos=state_stats.tracked_memos,
            tracked_chunks=state_stats.tracked_chunks,
            state_backend=self.state_store.backend_name,
            detail=detail,
        )
