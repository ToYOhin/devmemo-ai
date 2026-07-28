import sys

import pytest

from app.adapters.qdrant_vector_store import QdrantUnavailableError
from app.adapters.vector_store import InMemoryVectorStore
from app.adapters.chunk_state import InMemoryChunkIndexStateStore
from app.adapters.embedding import DeterministicEmbeddingProvider
from app.domain.embeddings import VectorStoreHealth
from app.services.embedding_factory import (
    build_chunk_lifecycle_coordinator,
    build_embedding_service,
)
from app.settings import AiSettings, parse_env_bool


def test_memory_is_the_safe_default(monkeypatch):
    monkeypatch.delenv("AI_VECTOR_STORE", raising=False)

    service = build_embedding_service()

    assert isinstance(service.store, InMemoryVectorStore)


def test_invalid_vector_store_mode_is_rejected(monkeypatch):
    monkeypatch.setenv("AI_VECTOR_STORE", "redis")

    with pytest.raises(ValueError, match="memory or qdrant"):
        build_embedding_service()


def test_qdrant_mode_is_explicit_and_lazy_dependency_is_clear(monkeypatch):
    monkeypatch.setitem(sys.modules, "qdrant_client", None)

    with pytest.raises(QdrantUnavailableError, match="qdrant-client"):
        build_embedding_service(
            AiSettings(
                vector_store="qdrant",
                qdrant_url="http://localhost:6333",
                qdrant_collection="devmemo_test",
            )
        )


def test_qdrant_chunk_collection_is_distinct_by_default(monkeypatch):
    monkeypatch.delenv("QDRANT_COLLECTION", raising=False)
    monkeypatch.delenv("QDRANT_CHUNK_COLLECTION", raising=False)

    settings = AiSettings.from_env()

    assert settings.qdrant_collection == "devmemo_memos"
    assert settings.qdrant_chunk_collection == "devmemo_memo_chunks"
    assert settings.qdrant_chunk_collection != settings.qdrant_collection


def test_qdrant_chunk_collection_is_configurable_but_cannot_reuse_memo_collection(
    monkeypatch,
):
    monkeypatch.setenv("QDRANT_COLLECTION", "memos-v1")
    monkeypatch.setenv("QDRANT_CHUNK_COLLECTION", "chunks-v1")

    settings = AiSettings.from_env()

    assert settings.qdrant_collection == "memos-v1"
    assert settings.qdrant_chunk_collection == "chunks-v1"

    monkeypatch.setenv("QDRANT_CHUNK_COLLECTION", "memos-v1")
    with pytest.raises(ValueError, match="must differ"):
        AiSettings.from_env()


def test_qdrant_collection_names_cannot_be_empty(monkeypatch):
    monkeypatch.setenv("QDRANT_CHUNK_COLLECTION", " ")

    with pytest.raises(ValueError, match="QDRANT_CHUNK_COLLECTION"):
        AiSettings.from_env()


def test_chunk_qdrant_composition_uses_the_isolated_collection(monkeypatch):
    calls = []

    class FakeQdrantStore(InMemoryVectorStore):
        def health(self):
            return VectorStoreHealth(
                provider="qdrant",
                available=True,
                dimension=self.dimension,
                status="green",
                collection="devmemo_memo_chunks",
                point_count=0,
            )

    def fake_qdrant_store(cls, url, dimension, collection_name, api_key=None):
        calls.append((url, dimension, collection_name, api_key))
        return FakeQdrantStore(dimension)

    monkeypatch.setattr(
        "app.services.embedding_factory.QdrantVectorStore.from_url",
        classmethod(fake_qdrant_store),
    )
    settings = AiSettings(
        index_mode="chunk",
        vector_store="qdrant",
        qdrant_url="http://qdrant.test:6333",
        qdrant_collection="devmemo_memos",
        qdrant_chunk_collection="devmemo_memo_chunks",
        qdrant_api_key="secret",
    )

    coordinator = build_chunk_lifecycle_coordinator(
        settings,
        provider=DeterministicEmbeddingProvider(),
        state_store=InMemoryChunkIndexStateStore(),
    )

    assert calls == [
        ("http://qdrant.test:6333", 8, "devmemo_memo_chunks", "secret")
    ]
    assert coordinator.health().provider == "qdrant"
    assert coordinator.health().status == "ready"


def test_chunk_composition_stays_memory_when_qdrant_is_not_explicit(monkeypatch):
    def fail_if_called(*args, **kwargs):
        raise AssertionError("Qdrant must not be selected for the default chunk path")

    monkeypatch.setattr(
        "app.services.embedding_factory.QdrantVectorStore.from_url", fail_if_called
    )

    coordinator = build_chunk_lifecycle_coordinator(
        AiSettings(index_mode="chunk", vector_store="memory"),
        provider=DeterministicEmbeddingProvider(),
        state_store=InMemoryChunkIndexStateStore(),
    )

    assert coordinator.store.health().provider == "memory"


def test_webhook_indexing_is_disabled_by_default(monkeypatch):
    monkeypatch.delenv("AI_INDEX_ON_WEBHOOK", raising=False)

    assert AiSettings.from_env().index_on_webhook is False


def test_webhook_indexing_boolean_is_strict(monkeypatch):
    monkeypatch.setenv("AI_INDEX_ON_WEBHOOK", "yes")

    with pytest.raises(ValueError, match="true or false"):
        parse_env_bool("AI_INDEX_ON_WEBHOOK")


def test_chunk_index_mode_is_opt_in(monkeypatch):
    monkeypatch.delenv("AI_INDEX_MODE", raising=False)
    assert AiSettings.from_env().index_mode == "memo"

    monkeypatch.setenv("AI_INDEX_MODE", "chunk")
    assert AiSettings.from_env().index_mode == "chunk"


def test_invalid_chunk_index_mode_is_rejected(monkeypatch):
    monkeypatch.setenv("AI_INDEX_MODE", "hybrid")

    with pytest.raises(ValueError, match="memo or chunk"):
        AiSettings.from_env()


def test_fastembed_cache_dir_is_optional_and_configurable(monkeypatch):
    monkeypatch.setenv("AI_FASTEMBED_CACHE_DIR", "H:/DevMemoAI/ai-service/model-cache")

    assert AiSettings.from_env().fastembed_cache_dir == (
        "H:/DevMemoAI/ai-service/model-cache"
    )

    monkeypatch.setenv("AI_FASTEMBED_CACHE_DIR", "  ")
    assert AiSettings.from_env().fastembed_cache_dir is None
