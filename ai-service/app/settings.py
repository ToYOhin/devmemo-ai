"""Environment-only settings for AI Service composition."""

from __future__ import annotations

import base64
import binascii
import os
import re
from dataclasses import dataclass
from urllib.parse import urlsplit


_REHYDRATION_SECRET_PATTERN = re.compile(r"^[A-Za-z0-9_-]{43}$")


@dataclass(frozen=True)
class AiSettings:
    embedding_provider: str = "deterministic"
    fastembed_model: str = "BAAI/bge-small-en-v1.5"
    fastembed_dimension: int = 384
    fastembed_cache_dir: str | None = None
    index_on_webhook: bool = False
    agent_enabled: bool = False
    agent_internal_secret: str | None = None
    agent_rehydration_enabled: bool = False
    agent_rehydration_secret_current: str | None = None
    agent_rehydration_secret_previous: str | None = None
    agent_rehydration_memos_url: str | None = None
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
        agent_enabled = parse_env_bool("AI_AGENT_ENABLED", default=False)
        agent_internal_secret = os.getenv("AI_AGENT_INTERNAL_SECRET", "").strip() or None
        if agent_enabled and agent_internal_secret is None:
            raise ValueError("AI_AGENT_INTERNAL_SECRET is required when AI_AGENT_ENABLED=true")
        agent_rehydration_enabled = parse_env_bool(
            "AI_AGENT_REHYDRATION_ENABLED", default=False
        )
        agent_rehydration_secret_current: str | None = None
        agent_rehydration_secret_previous: str | None = None
        agent_rehydration_memos_url: str | None = None
        if agent_rehydration_enabled:
            if not agent_enabled:
                raise ValueError(
                    "AI_AGENT_REHYDRATION_ENABLED requires AI_AGENT_ENABLED=true"
                )
            agent_rehydration_secret_current = _parse_rehydration_secret(
                "AI_AGENT_REHYDRATION_SECRET_CURRENT"
            )
            previous_value = os.getenv(
                "AI_AGENT_REHYDRATION_SECRET_PREVIOUS", ""
            ).strip()
            if previous_value:
                agent_rehydration_secret_previous = _parse_rehydration_secret(
                    "AI_AGENT_REHYDRATION_SECRET_PREVIOUS"
                )
            if agent_rehydration_secret_previous == agent_rehydration_secret_current:
                raise ValueError("rehydration current and previous secrets must differ")
            if agent_internal_secret in {
                agent_rehydration_secret_current,
                agent_rehydration_secret_previous,
            }:
                raise ValueError("rehydration secrets must differ from delegation secret")
            agent_rehydration_memos_url = _parse_rehydration_memos_url()
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
            agent_enabled=agent_enabled,
            agent_internal_secret=agent_internal_secret,
            agent_rehydration_enabled=agent_rehydration_enabled,
            agent_rehydration_secret_current=agent_rehydration_secret_current,
            agent_rehydration_secret_previous=agent_rehydration_secret_previous,
            agent_rehydration_memos_url=agent_rehydration_memos_url,
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


def _parse_rehydration_secret(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not _REHYDRATION_SECRET_PATTERN.fullmatch(value):
        raise ValueError(f"{name} must be an unpadded base64url 32-byte secret")
    try:
        decoded = base64.urlsafe_b64decode(value + "=")
    except (binascii.Error, ValueError) as error:
        raise ValueError(
            f"{name} must be an unpadded base64url 32-byte secret"
        ) from error
    if len(decoded) != 32 or base64.urlsafe_b64encode(decoded).decode().rstrip("=") != value:
        raise ValueError(f"{name} must be an unpadded base64url 32-byte secret")
    return value


def _parse_rehydration_memos_url() -> str:
    value = os.getenv("AI_AGENT_REHYDRATION_MEMOS_URL", "").strip()
    parsed = urlsplit(value)
    try:
        parsed.port
    except ValueError as error:
        raise ValueError(
            "AI_AGENT_REHYDRATION_MEMOS_URL must be one HTTP(S) origin"
        ) from error
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("AI_AGENT_REHYDRATION_MEMOS_URL must be one HTTP(S) origin")
    return value.rstrip("/")
