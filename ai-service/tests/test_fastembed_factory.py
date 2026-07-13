import pytest

from app.adapters.embedding import DeterministicEmbeddingProvider
from app.adapters.fastembed_embedding import FastEmbedEmbeddingProvider
from app.adapters.vector_store import InMemoryVectorStore
from app.services.embedding_factory import build_embedding_service
from app.settings import AiSettings


def test_fastembed_configuration_builds_matching_memory_store(monkeypatch):
    fake_provider = FastEmbedEmbeddingProvider(
        model=object(),
        model_name="fake-model",
        dimension=4,
    )
    monkeypatch.setattr(
        FastEmbedEmbeddingProvider,
        "from_model_name",
        classmethod(lambda cls, model_name, dimension, cache_dir=None: fake_provider),
    )

    service = build_embedding_service(
        AiSettings(
            embedding_provider="fastembed",
            fastembed_model="fake-model",
            fastembed_dimension=4,
        )
    )

    assert service.provider is fake_provider
    assert isinstance(service.store, InMemoryVectorStore)
    assert service.store.dimension == 4


def test_deterministic_provider_remains_the_default(monkeypatch):
    monkeypatch.delenv("AI_EMBEDDING_PROVIDER", raising=False)

    service = build_embedding_service()

    assert isinstance(service.provider, DeterministicEmbeddingProvider)
    assert service.provider.dimension == 8


def test_invalid_embedding_provider_mode_is_rejected(monkeypatch):
    monkeypatch.setenv("AI_EMBEDDING_PROVIDER", "openai")

    with pytest.raises(ValueError, match="deterministic or fastembed"):
        build_embedding_service()


def test_fastembed_dimension_must_be_positive(monkeypatch):
    monkeypatch.setenv("AI_FASTEMBED_DIMENSION", "0")

    with pytest.raises(ValueError, match="positive integer"):
        build_embedding_service()
