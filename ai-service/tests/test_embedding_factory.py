import sys

import pytest

from app.adapters.qdrant_vector_store import QdrantUnavailableError
from app.adapters.vector_store import InMemoryVectorStore
from app.services.embedding_factory import build_embedding_service
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


def test_webhook_indexing_is_disabled_by_default(monkeypatch):
    monkeypatch.delenv("AI_INDEX_ON_WEBHOOK", raising=False)

    assert AiSettings.from_env().index_on_webhook is False


def test_webhook_indexing_boolean_is_strict(monkeypatch):
    monkeypatch.setenv("AI_INDEX_ON_WEBHOOK", "yes")

    with pytest.raises(ValueError, match="true or false"):
        parse_env_bool("AI_INDEX_ON_WEBHOOK")


def test_fastembed_cache_dir_is_optional_and_configurable(monkeypatch):
    monkeypatch.setenv("AI_FASTEMBED_CACHE_DIR", "H:/DevMemoAI/ai-service/model-cache")

    assert AiSettings.from_env().fastembed_cache_dir == (
        "H:/DevMemoAI/ai-service/model-cache"
    )

    monkeypatch.setenv("AI_FASTEMBED_CACHE_DIR", "  ")
    assert AiSettings.from_env().fastembed_cache_dir is None
