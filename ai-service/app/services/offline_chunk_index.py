"""Offline chunk indexing composition for Phase 5 retrieval evaluation."""

from __future__ import annotations

from collections.abc import Iterable

from app.adapters.embedding import DeterministicEmbeddingProvider
from app.adapters.vector_store import InMemoryVectorStore
from app.domain.embeddings import (
    EmbeddingProvider,
    VectorRecord,
    VectorStore,
    VectorStoreHealth,
)
from app.domain.memo_chunking import MemoChunk, ensure_unique_chunk_ids
from app.domain.retrieval import ChunkRetrievalResult, RetrievalResult
from app.services.chunk_retrieval import ChunkRetrievalService
from app.services.embedding_service import EmbeddingService
from app.services.retrieval_service import RetrievalService


class OfflineChunkIndex:
    """Index and retrieve Memo chunks without changing the production path."""

    def __init__(
        self,
        provider: EmbeddingProvider | None = None,
        store: VectorStore | None = None,
    ) -> None:
        self.provider = provider or DeterministicEmbeddingProvider()
        self.store = store or InMemoryVectorStore(self.provider.dimension)
        if self.provider.dimension != self.store.dimension:
            raise ValueError("embedding provider and vector store dimensions must match")
        self.retrieval_service = RetrievalService(
            EmbeddingService(self.provider, self.store)
        )
        self.chunk_retrieval_service = ChunkRetrievalService(self.retrieval_service)

    def upsert(self, chunks: Iterable[MemoChunk]) -> tuple[str, ...]:
        """Upsert chunks by stable chunk ID and return the IDs written."""

        chunk_list = tuple(chunks)
        ensure_unique_chunk_ids(chunk_list)
        for chunk in chunk_list:
            _validate_chunk(chunk)
        for chunk in chunk_list:
            embedding = self.provider.embed(chunk.content)
            self.store.upsert(
                VectorRecord(
                    embedding_id=chunk.chunk_id,
                    memo_id=chunk.memo_id,
                    vector=embedding.values,
                    metadata=_index_metadata(chunk),
                )
            )
        return tuple(chunk.chunk_id for chunk in chunk_list)

    def delete(self, chunks: Iterable[MemoChunk]) -> int:
        """Delete explicitly supplied chunk IDs and return the count removed."""

        chunk_list = tuple(chunks)
        ensure_unique_chunk_ids(chunk_list)
        for chunk in chunk_list:
            if not chunk.chunk_id:
                raise ValueError("chunk_id must not be empty")
        return sum(self.store.delete(chunk.chunk_id) for chunk in chunk_list)

    def retrieve(self, question: str, limit: int = 5) -> RetrievalResult:
        """Reuse the existing retrieval/context contract for offline comparisons."""

        return self.retrieval_service.retrieve(question, limit=limit)

    def retrieve_chunks(self, question: str, limit: int = 5) -> ChunkRetrievalResult:
        """Return the explicit internal chunk contract without changing public chat."""

        return self.chunk_retrieval_service.retrieve(question, limit=limit)

    def health(self) -> VectorStoreHealth:
        """Expose the provider-neutral store health for fixture assertions."""

        return self.store.health()


def _validate_chunk(chunk: MemoChunk) -> None:
    if not chunk.memo_id:
        raise ValueError("memo_id must not be empty")
    if not chunk.chunk_id:
        raise ValueError("chunk_id must not be empty")
    if not chunk.content.strip():
        raise ValueError("chunk content must not be empty")


def _index_metadata(chunk: MemoChunk) -> dict[str, object]:
    metadata = dict(chunk.metadata)
    metadata.update(
        {
            "content": chunk.content,
            "memo_id": chunk.memo_id,
            "chunk_id": chunk.chunk_id,
            "chunk_index": chunk.chunk_index,
            "chunk_count": chunk.chunk_count,
            "index_mode": chunk.index_mode,
            "index_version": chunk.index_version,
            "source_type": "memo_chunk",
        }
    )
    return metadata
