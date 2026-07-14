from dataclasses import replace

import pytest

from app.adapters.embedding import DeterministicEmbeddingProvider
from app.adapters.vector_store import InMemoryVectorStore
from app.domain.embeddings import VectorRecord
from app.domain.memo_chunking import chunk_memo
from app.domain.retrieval import RetrievalUnavailableError
from app.services.chunk_retrieval import ChunkRetrievalService
from app.services.embedding_service import EmbeddingService
from app.services.offline_chunk_index import OfflineChunkIndex
from app.services.retrieval_service import RetrievalService


def test_chunk_retrieval_returns_explicit_metadata_and_server_context():
    index = OfflineChunkIndex()
    chunks = chunk_memo("memo-chunk", "Docker port mapping", max_chars=32)
    index.upsert(chunks)

    result = index.retrieve_chunks("Docker port mapping")

    assert result.citations
    citation = result.citations[0]
    assert citation.memo_id == "memo-chunk"
    assert citation.chunk_id == chunks[0].chunk_id
    assert citation.chunk_index == 0
    assert citation.index_version == "memo-chunk-v1"
    assert citation.metadata["source_type"] == "memo_chunk"
    assert "content" not in citation.metadata
    assert "Docker port mapping" in result.context


def test_chunk_retrieval_reuses_shared_input_validation():
    index = OfflineChunkIndex()

    with pytest.raises(ValueError, match="question must not be empty"):
        index.retrieve_chunks(" ")
    with pytest.raises(ValueError, match="between 1 and 10"):
        index.retrieve_chunks("Docker", limit=11)


def test_chunk_retrieval_rejects_non_chunk_metadata():
    provider = DeterministicEmbeddingProvider()
    store = InMemoryVectorStore(provider.dimension)
    service = EmbeddingService(provider, store)
    chunks = chunk_memo("memo-invalid", "content", max_chars=32)
    chunk = replace(
        chunks[0],
        metadata={"content": chunks[0].content, "memo_id": chunks[0].memo_id},
    )
    vector = provider.embed(chunk.content)
    store.upsert(
        VectorRecord(
            chunk.chunk_id,
            chunk.memo_id,
            vector.values,
            dict(chunk.metadata),
        )
    )

    with pytest.raises(RetrievalUnavailableError, match="source_type"):
        ChunkRetrievalService(RetrievalService(service)).retrieve("content")
