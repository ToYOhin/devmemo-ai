from dataclasses import replace

import pytest

from app.adapters.embedding import DeterministicEmbeddingProvider
from app.adapters.vector_store import InMemoryVectorStore
from app.domain.memo_chunking import chunk_memo
from app.domain.retrieval_evaluation import RetrievalEvaluationCase
from app.services.embedding_service import EmbeddingService
from app.services.memo_indexing import MemoIndexDocument, index_memo
from app.services.offline_chunk_index import OfflineChunkIndex
from app.services.retrieval_evaluator import RetrievalEvaluator
from app.services.retrieval_service import RetrievalService


def test_offline_chunk_index_returns_chunk_citation_and_context():
    index = OfflineChunkIndex()
    chunks = chunk_memo(
        "memo-docker",
        "Docker port mapping\ncompose exposes the service port.",
        max_chars=24,
    )

    assert index.upsert(chunks) == tuple(chunk.chunk_id for chunk in chunks)

    result = index.retrieve(chunks[0].content.strip(), limit=5)
    citation = next(item for item in result.citations if item.embedding_id == chunks[0].chunk_id)

    assert citation.memo_id == "memo-docker"
    assert citation.metadata["chunk_id"] == chunks[0].chunk_id
    assert citation.metadata["chunk_index"] == chunks[0].chunk_index
    assert citation.metadata["index_version"] == "memo-chunk-v1"
    assert chunks[0].content.strip() in result.context
    assert "content" not in citation.metadata


def test_shorter_update_requires_explicit_stale_chunk_delete():
    index = OfflineChunkIndex()
    old_chunks = chunk_memo("memo-1", "alpha beta gamma", max_chars=6)
    new_chunks = chunk_memo("memo-1", "alpha", max_chars=6)

    index.upsert(old_chunks)
    index.upsert(new_chunks)
    assert index.health().point_count == len(old_chunks)

    deleted = index.delete(old_chunks[len(new_chunks) :])

    assert deleted == len(old_chunks) - len(new_chunks)
    assert index.health().point_count == len(new_chunks)


def test_offline_chunk_index_rejects_duplicates_and_empty_content():
    index = OfflineChunkIndex()
    chunks = chunk_memo("memo-1", "abcdefgh", max_chars=4)

    with pytest.raises(ValueError, match="duplicate chunk_id"):
        index.upsert((chunks[0], replace(chunks[1], chunk_id=chunks[0].chunk_id)))

    with pytest.raises(ValueError, match="content"):
        index.upsert((replace(chunks[0], content=" "),))

    assert index.health().point_count == 0
    assert index.upsert(()) == ()


def test_chunk_trial_can_be_compared_with_complete_memo_baseline():
    target_content = "Docker port mapping uses compose."
    noise_content = "Python typing belongs in the backend notes."
    target_chunks = chunk_memo("memo-target", target_content, max_chars=12)
    noise_chunks = chunk_memo("memo-noise", noise_content, max_chars=12)

    chunk_index = OfflineChunkIndex(
        DeterministicEmbeddingProvider(), InMemoryVectorStore(8)
    )
    chunk_index.upsert((*target_chunks, *noise_chunks))

    full_embedding = EmbeddingService(
        DeterministicEmbeddingProvider(), InMemoryVectorStore(8)
    )
    index_memo(
        full_embedding,
        MemoIndexDocument.from_memo("memo-target", target_content, {"title": "Docker"}),
    )
    index_memo(
        full_embedding,
        MemoIndexDocument.from_memo("memo-noise", noise_content, {"title": "Python"}),
    )
    case = RetrievalEvaluationCase(
        case_id="docker-chunk-baseline",
        question=target_content,
        expected_memo_ids=("memo-target",),
        limit=2,
    )

    full_result = RetrievalEvaluator(RetrievalService(full_embedding)).evaluate_case(case)
    chunk_result = RetrievalEvaluator(chunk_index.retrieval_service).evaluate_case(case)

    assert full_result.recall_at_k == 1.0
    assert chunk_result.recall_at_k == 1.0
    assert chunk_result.first_relevant_rank is not None
    assert any(
        citation.metadata["index_version"] == "memo-chunk-v1"
        for citation in chunk_index.retrieve(target_content, limit=2).citations
    )
