import pytest

from app.adapters.embedding import DeterministicEmbeddingProvider
from app.adapters.vector_store import InMemoryVectorStore
from app.services.embedding_service import EmbeddingService


def test_embedding_service_upserts_a_stable_memo_record():
    store = InMemoryVectorStore(dimension=8)
    service = EmbeddingService(DeterministicEmbeddingProvider(), store)

    first = service.embed_memo("memo-1", "Docker port mapping", {"title": "Docker"})
    second = service.embed_memo("memo-1", "FastAPI port mapping", {"title": "Updated"})

    assert first.embedding_id == second.embedding_id
    assert second.dimension == 8
    assert second.provider == "deterministic"
    assert len(store.search(DeterministicEmbeddingProvider().embed("FastAPI port mapping").values)) == 1
    assert store.search(DeterministicEmbeddingProvider().embed("FastAPI port mapping").values)[0].metadata == {
        "title": "Updated"
    }


def test_embedding_service_rejects_empty_memo_id_or_content():
    service = EmbeddingService()

    with pytest.raises(ValueError, match="memo_id must not be empty"):
        service.embed_memo("  ", "content")
    with pytest.raises(ValueError, match="content must not be empty"):
        service.embed_memo("memo-1", "  ")


def test_embedding_service_rejects_provider_store_dimension_mismatch():
    class TwoDimensionalProvider:
        dimension = 2
        name = "test"

        def embed(self, text):
            raise AssertionError("provider should not be called")

    with pytest.raises(ValueError, match="dimensions must match"):
        EmbeddingService(TwoDimensionalProvider(), InMemoryVectorStore(dimension=8))


def test_embedding_service_deletes_vector_by_stable_memo_id():
    store = InMemoryVectorStore(dimension=8)
    service = EmbeddingService(DeterministicEmbeddingProvider(), store)
    indexed = service.embed_memo("memo-delete", "content")

    assert service.delete_memo("memo-delete") is True
    assert service.delete_memo("memo-delete") is False
    assert store.delete(indexed.embedding_id) is False
