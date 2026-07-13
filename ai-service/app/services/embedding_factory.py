"""Composition root for selecting the configured vector store."""

from __future__ import annotations

from app.adapters.embedding import DeterministicEmbeddingProvider
from app.adapters.fastembed_embedding import FastEmbedEmbeddingProvider
from app.adapters.qdrant_vector_store import QdrantVectorStore
from app.adapters.vector_store import InMemoryVectorStore
from app.services.embedding_service import EmbeddingService
from app.settings import AiSettings


def build_embedding_service(settings: AiSettings | None = None) -> EmbeddingService:
    configured = settings or AiSettings.from_env()
    if configured.embedding_provider == "deterministic":
        provider = DeterministicEmbeddingProvider()
    else:
        provider = FastEmbedEmbeddingProvider.from_model_name(
            model_name=configured.fastembed_model,
            dimension=configured.fastembed_dimension,
            cache_dir=configured.fastembed_cache_dir,
        )
    if configured.vector_store == "memory":
        return EmbeddingService(provider=provider, store=InMemoryVectorStore(provider.dimension))
    store = QdrantVectorStore.from_url(
        url=configured.qdrant_url,
        dimension=provider.dimension,
        collection_name=configured.qdrant_collection,
        api_key=configured.qdrant_api_key,
    )
    return EmbeddingService(provider=provider, store=store)
