"""Provider-neutral Memo chunking contracts for an offline Phase 5 boundary."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Iterable, Mapping


CHUNK_INDEX_VERSION = "memo-chunk-v1"
CHUNK_INDEX_MODE = "chunk"
DEFAULT_MAX_CHARS = 1200


@dataclass(frozen=True)
class MemoChunk:
    """One deterministic chunk that can later be mapped to a vector record."""

    memo_id: str
    chunk_id: str
    content: str
    chunk_index: int
    chunk_count: int
    index_version: str
    index_mode: str
    metadata: Mapping[str, object]


def chunk_memo(
    memo_id: str,
    content: str,
    *,
    max_chars: int = DEFAULT_MAX_CHARS,
    index_version: str = CHUNK_INDEX_VERSION,
    metadata: Mapping[str, object] | None = None,
) -> tuple[MemoChunk, ...]:
    """Split Markdown without losing source characters or changing production indexing."""

    normalized_memo_id = str(memo_id).strip()
    if not normalized_memo_id:
        raise ValueError("memo_id must not be empty")
    if max_chars < 1:
        raise ValueError("max_chars must be positive")
    normalized_version = str(index_version).strip()
    if not normalized_version:
        raise ValueError("index_version must not be empty")
    if not content.strip():
        return ()

    pieces = _split_preserving_source(content, max_chars)
    chunk_count = len(pieces)
    chunks = tuple(
        MemoChunk(
            memo_id=normalized_memo_id,
            chunk_id=_stable_chunk_id(normalized_memo_id, normalized_version, index),
            content=piece,
            chunk_index=index,
            chunk_count=chunk_count,
            index_version=normalized_version,
            index_mode=CHUNK_INDEX_MODE,
            metadata=_chunk_metadata(
                normalized_memo_id,
                normalized_version,
                index,
                chunk_count,
                piece,
                metadata,
            ),
        )
        for index, piece in enumerate(pieces)
    )
    ensure_unique_chunk_ids(chunks)
    return chunks


def chunk_ids_for_memo(
    memo_id: str,
    chunk_count: int,
    index_version: str = CHUNK_INDEX_VERSION,
) -> list[str]:
    """Return the stable IDs needed to upsert or delete a Memo's chunk positions."""

    normalized_memo_id = str(memo_id).strip()
    if not normalized_memo_id:
        raise ValueError("memo_id must not be empty")
    if chunk_count < 0:
        raise ValueError("chunk_count must not be negative")
    normalized_version = str(index_version).strip()
    if not normalized_version:
        raise ValueError("index_version must not be empty")
    return [
        _stable_chunk_id(normalized_memo_id, normalized_version, index)
        for index in range(chunk_count)
    ]


def ensure_unique_chunk_ids(chunks: Iterable[MemoChunk]) -> None:
    """Reject duplicate IDs before a future vector-store lifecycle operation."""

    seen: set[str] = set()
    for chunk in chunks:
        if chunk.chunk_id in seen:
            raise ValueError(f"duplicate chunk_id: {chunk.chunk_id}")
        seen.add(chunk.chunk_id)


def _split_preserving_source(content: str, max_chars: int) -> list[str]:
    pieces: list[str] = []
    start = 0
    while start < len(content):
        hard_end = min(start + max_chars, len(content))
        end = hard_end
        if hard_end < len(content):
            last_newline = content.rfind("\n", start + 1, hard_end)
            if last_newline >= start + 1:
                end = last_newline + 1
        pieces.append(content[start:end])
        start = end
    return pieces


def _chunk_metadata(
    memo_id: str,
    index_version: str,
    chunk_index: int,
    chunk_count: int,
    content: str,
    source_metadata: Mapping[str, object] | None,
) -> dict[str, object]:
    normalized = dict(source_metadata or {})
    normalized.update(
        {
            "content": content,
            "memo_id": memo_id,
            "chunk_id": _stable_chunk_id(memo_id, index_version, chunk_index),
            "chunk_index": chunk_index,
            "chunk_count": chunk_count,
            "index_mode": CHUNK_INDEX_MODE,
            "index_version": index_version,
            "source_type": "memo_chunk",
        }
    )
    return normalized


def _stable_chunk_id(memo_id: str, index_version: str, chunk_index: int) -> str:
    memo_digest = hashlib.sha256(memo_id.encode("utf-8")).hexdigest()[:24]
    return f"{index_version}:{memo_digest}:{chunk_index:04d}"
