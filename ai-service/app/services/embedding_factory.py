"""Composition root for selecting the configured vector store."""

from __future__ import annotations

from app.adapters.embedding import DeterministicEmbeddingProvider
from app.adapters.fastembed_embedding import FastEmbedEmbeddingProvider
from app.adapters.qdrant_vector_store import QdrantVectorStore
from app.adapters.vector_store import InMemoryVectorStore
from app.domain.embeddings import EmbeddingProvider, VectorStore
from app.adapters.chunk_state import InMemoryChunkIndexStateStore
from app.services.embedding_service import EmbeddingService
from app.services.chunk_lifecycle import ChunkLifecycleCoordinator, ChunkIndexStateStore
from app.settings import AiSettings


def build_embedding_provider(configured: AiSettings) -> EmbeddingProvider:
    if configured.embedding_provider == "deterministic":
        return DeterministicEmbeddingProvider()
    return FastEmbedEmbeddingProvider.from_model_name(
        model_name=configured.fastembed_model,
        dimension=configured.fastembed_dimension,
        cache_dir=configured.fastembed_cache_dir,
    )


def build_vector_store(
    configured: AiSettings,
    provider: EmbeddingProvider,
    collection_name: str,
) -> VectorStore:
    if configured.vector_store == "memory":
        return InMemoryVectorStore(provider.dimension)
    store = QdrantVectorStore.from_url(
        url=configured.qdrant_url,
        dimension=provider.dimension,
        collection_name=collection_name,
        api_key=configured.qdrant_api_key,
    )
    return store


def build_embedding_service(settings: AiSettings | None = None) -> EmbeddingService:
    configured = settings or AiSettings.from_env()
    provider = build_embedding_provider(configured)
    store = build_vector_store(configured, provider, configured.qdrant_collection)
    return EmbeddingService(provider=provider, store=store)


def build_chunk_lifecycle_coordinator(
    settings: AiSettings | None = None,
    *,
    provider: EmbeddingProvider | None = None,
    state_store: ChunkIndexStateStore | None = None,
) -> ChunkLifecycleCoordinator:
    configured = settings or AiSettings.from_env()
    configured_provider = provider or build_embedding_provider(configured)
    if configured.index_mode == "chunk" and configured.vector_store == "qdrant":
        store = build_vector_store(
            configured,
            configured_provider,
            configured.qdrant_chunk_collection,
        )
    else:
        store = InMemoryVectorStore(configured_provider.dimension)
    return ChunkLifecycleCoordinator(
        provider=configured_provider,
        store=store,
        state_store=state_store or InMemoryChunkIndexStateStore(),
    )
