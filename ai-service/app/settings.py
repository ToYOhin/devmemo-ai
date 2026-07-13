"""Environment-only settings for AI Service composition."""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class AiSettings:
    embedding_provider: str = "deterministic"
    fastembed_model: str = "BAAI/bge-small-en-v1.5"
    fastembed_dimension: int = 384
    fastembed_cache_dir: str | None = None
    index_on_webhook: bool = False
    index_mode: str = "memo"
    vector_store: str = "memory"
    qdrant_url: str = "http://localhost:6333"
    qdrant_collection: str = "devmemo_memos"
    qdrant_chunk_collection: str = "devmemo_memo_chunks"
    qdrant_api_key: str | None = None

    def __post_init__(self) -> None:
        if not self.qdrant_collection.strip():
            raise ValueError("QDRANT_COLLECTION must not be empty")
        if not self.qdrant_chunk_collection.strip():
            raise ValueError("QDRANT_CHUNK_COLLECTION must not be empty")
        if self.qdrant_collection.strip() == self.qdrant_chunk_collection.strip():
            raise ValueError(
                "QDRANT_CHUNK_COLLECTION must differ from QDRANT_COLLECTION"
            )

    @classmethod
    def from_env(cls) -> AiSettings:
        embedding_provider = os.getenv("AI_EMBEDDING_PROVIDER", "deterministic").strip().lower()
        if embedding_provider not in {"deterministic", "fastembed"}:
            raise ValueError("AI_EMBEDDING_PROVIDER must be deterministic or fastembed")

        fastembed_model = os.getenv("AI_FASTEMBED_MODEL", "BAAI/bge-small-en-v1.5").strip()
        if not fastembed_model:
            raise ValueError("AI_FASTEMBED_MODEL must not be empty")
        try:
            fastembed_dimension = int(os.getenv("AI_FASTEMBED_DIMENSION", "384"))
        except ValueError as error:
            raise ValueError("AI_FASTEMBED_DIMENSION must be a positive integer") from error
        if fastembed_dimension <= 0:
            raise ValueError("AI_FASTEMBED_DIMENSION must be a positive integer")
        fastembed_cache_dir = os.getenv("AI_FASTEMBED_CACHE_DIR", "").strip() or None

        index_on_webhook = parse_env_bool("AI_INDEX_ON_WEBHOOK", default=False)
        index_mode = os.getenv("AI_INDEX_MODE", "memo").strip().lower()
        if index_mode not in {"memo", "chunk"}:
            raise ValueError("AI_INDEX_MODE must be memo or chunk")

        vector_store = os.getenv("AI_VECTOR_STORE", "memory").strip().lower()
        if vector_store not in {"memory", "qdrant"}:
            raise ValueError("AI_VECTOR_STORE must be memory or qdrant")
        return cls(
            embedding_provider=embedding_provider,
            fastembed_model=fastembed_model,
            fastembed_dimension=fastembed_dimension,
            fastembed_cache_dir=fastembed_cache_dir,
            index_on_webhook=index_on_webhook,
            index_mode=index_mode,
            vector_store=vector_store,
            qdrant_url=os.getenv("QDRANT_URL", "http://localhost:6333").strip(),
            qdrant_collection=os.getenv("QDRANT_COLLECTION", "devmemo_memos").strip(),
            qdrant_chunk_collection=os.getenv(
                "QDRANT_CHUNK_COLLECTION", "devmemo_memo_chunks"
            ).strip(),
            qdrant_api_key=os.getenv("QDRANT_API_KEY") or None,
        )


def parse_env_bool(name: str, default: bool = False) -> bool:
    """Parse a strict composition-boundary boolean environment variable."""

    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    normalized = raw_value.strip().lower()
    if normalized not in {"true", "false"}:
        raise ValueError(f"{name} must be true or false")
    return normalized == "true"
