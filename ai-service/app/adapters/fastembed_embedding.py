"""Optional FastEmbed adapter behind the provider-neutral contract."""

from __future__ import annotations

from typing import Any

from app.domain.embeddings import EmbeddingVector, VectorDimensionError


class FastEmbedUnavailableError(RuntimeError):
    """Raised when the optional fastembed package is not installed."""


class FastEmbedInitializationError(RuntimeError):
    """Raised when FastEmbed cannot initialize the configured model."""


class FastEmbedEmbeddingProvider:
    """Adapt ``fastembed.TextEmbedding`` without leaking SDK types."""

    name = "fastembed"

    def __init__(self, model: Any, model_name: str, dimension: int) -> None:
        if dimension <= 0:
            raise ValueError("embedding dimension must be positive")
        if not model_name.strip():
            raise ValueError("FastEmbed model name must not be empty")
        self._model = model
        self.model_name = model_name
        self.dimension = dimension

    @classmethod
    def from_model_name(
        cls,
        model_name: str,
        dimension: int,
        cache_dir: str | None = None,
    ) -> FastEmbedEmbeddingProvider:
        try:
            from fastembed import TextEmbedding
        except ImportError as error:
            raise FastEmbedUnavailableError(
                "fastembed is not installed; install requirements-fastembed.txt "
                "before selecting AI_EMBEDDING_PROVIDER=fastembed"
            ) from error

        try:
            if cache_dir:
                model = TextEmbedding(model_name=model_name, cache_dir=cache_dir)
            else:
                model = TextEmbedding(model_name=model_name)
        except Exception as error:
            cache_hint = f"; cache_dir={cache_dir}" if cache_dir else ""
            raise FastEmbedInitializationError(
                f"failed to initialize FastEmbed model {model_name}{cache_hint}; "
                "verify the model cache or remove corrupted cache files"
            ) from error
        return cls(model=model, model_name=model_name, dimension=dimension)

    def embed(self, text: str) -> EmbeddingVector:
        if not text.strip():
            raise ValueError("embedding input must not be empty")
        try:
            vectors = list(self._model.embed([text]))
        except Exception as error:
            raise FastEmbedInitializationError(
                f"FastEmbed model {self.model_name} failed to embed input"
            ) from error
        if len(vectors) != 1:
            raise ValueError("FastEmbed must return exactly one vector for one input")

        try:
            values = tuple(float(value) for value in vectors[0])
        except (TypeError, ValueError) as error:
            raise ValueError("FastEmbed returned a non-numeric vector") from error
        if len(values) != self.dimension:
            raise VectorDimensionError(
                f"expected vector dimension {self.dimension}, got {len(values)}"
            )
        return EmbeddingVector(values=values, provider=self.name)
