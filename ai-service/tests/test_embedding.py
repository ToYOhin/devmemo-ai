import pytest

from app.adapters.embedding import DeterministicEmbeddingProvider
from app.adapters.vector_store import InMemoryVectorStore
from app.domain.embeddings import EmbeddingVector, EmbeddingProvider, VectorDimensionError, VectorRecord
from embedding import DeterministicEmbedder


def test_deterministic_provider_is_repeatable_and_fixed_dimension():
    provider: EmbeddingProvider = DeterministicEmbeddingProvider()

    first = provider.embed("Docker port mapping")
    second = provider.embed("Docker port mapping")

    assert isinstance(first, EmbeddingVector)
    assert first == second
    assert first.provider == "deterministic"
    assert first.dimension == 8


def test_deterministic_provider_rejects_empty_input():
    with pytest.raises(ValueError, match="must not be empty"):
        DeterministicEmbeddingProvider().embed("  ")


def test_legacy_embedder_keeps_list_based_compatibility():
    vector = DeterministicEmbedder().embed("legacy caller")

    assert isinstance(vector, list)
    assert len(vector) == DeterministicEmbedder.dimensions
    assert len(DeterministicEmbedder().embed("")) == DeterministicEmbedder.dimensions


def test_vector_store_upserts_searches_and_returns_metadata():
    store = InMemoryVectorStore(dimension=2)
    store.upsert(VectorRecord("embedding-a", "memo-a", (1.0, 0.0), {"title": "Docker"}))
    store.upsert(VectorRecord("embedding-b", "memo-b", (0.0, 1.0), {"title": "FastAPI"}))

    results = store.search((1.0, 0.0), limit=1)

    assert len(results) == 1
    assert results[0].embedding_id == "embedding-a"
    assert results[0].memo_id == "memo-a"
    assert results[0].score == 1.0
    assert results[0].metadata == {"title": "Docker"}


def test_vector_store_upsert_replaces_and_delete_is_idempotent():
    store = InMemoryVectorStore(dimension=2)
    record = VectorRecord("embedding-a", "memo-a", (1.0, 0.0), {"version": 1})
    store.upsert(record)
    store.upsert(VectorRecord("embedding-a", "memo-a", (0.0, 1.0), {"version": 2}))

    assert store.search((0.0, 1.0))[0].metadata == {"version": 2}
    assert store.delete("embedding-a") is True
    assert store.delete("embedding-a") is False
    assert store.search((0.0, 1.0)) == []


def test_vector_store_rejects_dimension_mismatch_and_invalid_limit():
    store = InMemoryVectorStore(dimension=2)

    with pytest.raises(VectorDimensionError, match="expected vector dimension 2"):
        store.upsert(VectorRecord("bad", "memo", (1.0,), {}))
    with pytest.raises(VectorDimensionError):
        store.search((1.0,))
    with pytest.raises(ValueError, match="limit must be positive"):
        store.search((1.0, 0.0), limit=0)
