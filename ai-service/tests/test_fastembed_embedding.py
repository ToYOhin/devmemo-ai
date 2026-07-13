import sys
import types

import pytest

from app.adapters.fastembed_embedding import (
    FastEmbedEmbeddingProvider,
    FastEmbedInitializationError,
    FastEmbedUnavailableError,
)
from app.domain.embeddings import VectorDimensionError


class FakeTextEmbedding:
    def __init__(self, model_name="BAAI/bge-small-en-v1.5"):
        self.model_name = model_name

    def embed(self, documents):
        return ([0.1, 0.2, 0.3, 0.4] for _ in documents)


def test_fastembed_adapter_maps_one_model_vector_to_domain_result():
    provider = FastEmbedEmbeddingProvider(FakeTextEmbedding(), "fake-model", dimension=4)

    result = provider.embed("Docker port mapping")

    assert result.provider == "fastembed"
    assert result.values == (0.1, 0.2, 0.3, 0.4)
    assert result.dimension == 4


def test_fastembed_adapter_rejects_empty_input():
    provider = FastEmbedEmbeddingProvider(FakeTextEmbedding(), "fake-model", dimension=4)

    with pytest.raises(ValueError, match="embedding input must not be empty"):
        provider.embed("  ")


def test_fastembed_adapter_checks_model_dimension():
    provider = FastEmbedEmbeddingProvider(FakeTextEmbedding(), "fake-model", dimension=8)

    with pytest.raises(VectorDimensionError, match="expected vector dimension 8, got 4"):
        provider.embed("content")


def test_fastembed_adapter_rejects_multiple_vectors_for_one_input():
    class BrokenModel:
        def embed(self, documents):
            return iter([[0.1, 0.2], [0.3, 0.4]])

    provider = FastEmbedEmbeddingProvider(BrokenModel(), "fake-model", dimension=2)

    with pytest.raises(ValueError, match="exactly one vector"):
        provider.embed("content")


def test_fastembed_adapter_reports_missing_optional_dependency(monkeypatch):
    monkeypatch.setitem(sys.modules, "fastembed", None)

    with pytest.raises(FastEmbedUnavailableError, match="requirements-fastembed.txt"):
        FastEmbedEmbeddingProvider.from_model_name("fake-model", dimension=4)


def test_fastembed_adapter_reports_model_initialization_failure(monkeypatch):
    class BrokenTextEmbedding:
        def __init__(self, **kwargs):
            raise RuntimeError("model download failed")

    monkeypatch.setitem(sys.modules, "fastembed", types.SimpleNamespace(TextEmbedding=BrokenTextEmbedding))

    with pytest.raises(FastEmbedInitializationError, match="verify the model cache"):
        FastEmbedEmbeddingProvider.from_model_name(
            "fake-model",
            dimension=4,
            cache_dir="H:/cache",
        )


def test_fastembed_adapter_forwards_explicit_cache_dir(monkeypatch):
    captured: dict[str, object] = {}

    class CapturingTextEmbedding:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setitem(
        sys.modules,
        "fastembed",
        types.SimpleNamespace(TextEmbedding=CapturingTextEmbedding),
    )

    FastEmbedEmbeddingProvider.from_model_name(
        "fake-model",
        dimension=4,
        cache_dir="H:/DevMemoAI/ai-service/model-cache",
    )

    assert captured == {
        "model_name": "fake-model",
        "cache_dir": "H:/DevMemoAI/ai-service/model-cache",
    }
