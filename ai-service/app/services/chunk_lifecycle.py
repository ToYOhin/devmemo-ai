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


class ChunkIndexStateStore(Protocol):
    """Persist only lifecycle bookkeeping, never the original Markdown."""

    def get(self, memo_id: str) -> ChunkIndexState | None:
        ...

    def save(self, memo_id: str, index_version: str, chunk_ids: tuple[str, ...]) -> None:
        ...

    def delete(self, memo_id: str) -> bool:
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
