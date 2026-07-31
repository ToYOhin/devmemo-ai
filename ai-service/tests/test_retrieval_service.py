import pytest

from app.adapters.embedding import DeterministicEmbeddingProvider
from app.adapters.vector_store import InMemoryVectorStore
from app.domain.retrieval import RetrievalInputError, RetrievalUnavailableError
from app.services.embedding_service import EmbeddingService
from app.services.memo_indexing import MemoIndexDocument, index_memo
from app.services.retrieval_service import RetrievalService


def _service_with_memos() -> EmbeddingService:
    service = EmbeddingService(DeterministicEmbeddingProvider(), InMemoryVectorStore(8))
    index_memo(
        service,
        MemoIndexDocument.from_memo(
            "memo-docker",
            "Docker port mapping fixed by changing docker-compose ports.",
            {"title": "Docker ports", "tags": ["docker", "network"]},
        ),
    )
    index_memo(
        service,
        MemoIndexDocument.from_memo(
            "memo-fastapi",
            "FastAPI dependency installation on Ubuntu.",
            {"title": "FastAPI setup", "tags": ["fastapi"]},
        ),
    )
    return service


def test_retrieval_returns_ranked_citations_and_context_without_internal_content_metadata():
    result = RetrievalService(_service_with_memos()).retrieve("Docker port problem", limit=2)

    assert len(result.citations) == 2
    assert result.citations[0].memo_id == "memo-docker"
    assert "content" not in result.citations[0].metadata
    assert "docker-compose ports" in result.context
    assert "memo_id=memo-docker" in result.context


def test_retrieval_returns_empty_result_for_empty_index():
    service = EmbeddingService(DeterministicEmbeddingProvider(), InMemoryVectorStore(8))

    result = RetrievalService(service).retrieve("unknown topic")

    assert result.citations == ()
    assert result.context == ""


def test_authorized_retrieval_filters_before_context_assembly_and_rejects_chunk_indexes():
    service = _service_with_memos()
    index_memo(
        service,
        MemoIndexDocument.from_memo(
            "memo-chunk",
            "TOP SECRET chunk content",
            {"title": "chunk", "index_version": "memo-chunk-v1"},
        ),
    )

    result = RetrievalService(service).retrieve_authorized(
        "Docker secret",
        limit=3,
        visible_memo_ids=frozenset({"memo-docker", "memo-chunk"}),
    )

    assert [citation.memo_id for citation in result.citations] == ["memo-docker"]
    assert "TOP SECRET" not in result.context


@pytest.mark.parametrize("question", ["", "  "])
def test_retrieval_rejects_empty_question(question):
    with pytest.raises(RetrievalInputError, match="question must not be empty"):
        RetrievalService(_service_with_memos()).retrieve(question)


@pytest.mark.parametrize("limit", [0, 11])
def test_retrieval_rejects_invalid_limit(limit):
    with pytest.raises(RetrievalInputError, match="between 1 and 10"):
        RetrievalService(_service_with_memos()).retrieve("Docker", limit=limit)


def test_retrieval_reports_store_failure_as_provider_neutral_error():
    class BrokenStore(InMemoryVectorStore):
        def search(self, query, limit=5):
            raise OSError("offline")

    service = EmbeddingService(DeterministicEmbeddingProvider(), BrokenStore(8))

    with pytest.raises(RetrievalUnavailableError, match="knowledge-base retrieval unavailable"):
        RetrievalService(service).retrieve("Docker")
