"""Memo-to-vector indexing boundary.

Phase 3c indexes one complete Memo as one document. Chunking is deliberately
deferred so provider and vector-store selection can evolve independently.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from app.services.embedding_service import EmbeddedMemo, EmbeddingService


@dataclass(frozen=True)
class MemoIndexDocument:
    """Normalized input for the current one-Memo/one-vector index path."""

    memo_id: str
    content: str
    metadata: Mapping[str, object]

    @classmethod
    def from_memo(
        cls,
        memo_id: str,
        content: str,
        metadata: Mapping[str, object] | None = None,
    ) -> MemoIndexDocument:
        normalized = dict(metadata or {})
        # Keep the complete Memo as derived index context for the Phase 4 RAG path.
        # Retrieval removes this internal field from public citation metadata.
        normalized["content"] = content
        normalized.setdefault("source_type", "memo")
        normalized.setdefault("index_version", "memo-v1")
        return cls(memo_id=memo_id, content=content, metadata=normalized)


def index_memo(service: EmbeddingService, document: MemoIndexDocument) -> EmbeddedMemo:
    """Index one complete Memo through the configured provider and store."""

    return service.embed_memo(document.memo_id, document.content, document.metadata)
