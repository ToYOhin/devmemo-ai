"""Versioned, redacted public projection of the internal chunk contract."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping

from app.domain.memo_chunking import CHUNK_INDEX_VERSION
from app.domain.retrieval import ChunkCitation


PUBLIC_CHUNK_API_VERSION = "public-chunk-v1"
_MAX_LIMIT = 10


@dataclass(frozen=True)
class PublicChunkCitation:
    memo_id: str
    chunk_id: str
    chunk_index: int
    score: float
    metadata: Mapping[str, object]

    def to_dict(self) -> dict[str, object]:
        return {
            "memo_id": self.memo_id,
            "chunk_id": self.chunk_id,
            "chunk_index": self.chunk_index,
            "score": self.score,
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class PublicChunkSearchResponse:
    provider: str
    chunks: tuple[PublicChunkCitation, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "api_version": PUBLIC_CHUNK_API_VERSION,
            "index_version": CHUNK_INDEX_VERSION,
            "provider": self.provider,
            "chunks": [chunk.to_dict() for chunk in self.chunks],
            "retrieved_count": len(self.chunks),
        }


def build_public_chunk_response(
    *,
    citations: Iterable[ChunkCitation],
    provider: str,
    visible_memo_ids: frozenset[str],
    limit: int,
) -> PublicChunkSearchResponse:
    """Authorize, deduplicate, sort, and redact internal chunk citations."""

    if not visible_memo_ids:
        raise ValueError("visible_memo_ids must not be empty")
    if limit < 1 or limit > _MAX_LIMIT:
        raise ValueError(f"public chunk limit must be between 1 and {_MAX_LIMIT}")

    candidates = sorted(
        (citation for citation in citations if citation.memo_id in visible_memo_ids),
        key=lambda citation: (-citation.score, citation.memo_id, citation.chunk_index, citation.chunk_id),
    )
    selected: list[PublicChunkCitation] = []
    seen_memos: set[str] = set()
    for citation in candidates:
        if citation.memo_id in seen_memos:
            continue
        seen_memos.add(citation.memo_id)
        selected.append(_redact(citation))
        if len(selected) == limit:
            break
    return PublicChunkSearchResponse(provider=provider, chunks=tuple(selected))


def _redact(citation: ChunkCitation) -> PublicChunkCitation:
    """Expose only the explicitly approved citation metadata allowlist."""

    metadata: dict[str, object] = {"source_type": "memo_chunk"}
    title = citation.metadata.get("title")
    if isinstance(title, str) and title.strip():
        metadata["title"] = title.strip()[:160]
    return PublicChunkCitation(
        memo_id=citation.memo_id,
        chunk_id=citation.chunk_id,
        chunk_index=citation.chunk_index,
        score=citation.score,
        metadata=metadata,
    )
