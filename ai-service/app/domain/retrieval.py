"""Provider-neutral contracts for knowledge-base retrieval."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping


@dataclass(frozen=True)
class Citation:
    """A retrieved whole-Memo reference safe to return from the API."""

    memo_id: str
    embedding_id: str
    score: float
    metadata: Mapping[str, object]


@dataclass(frozen=True)
class RetrievalResult:
    """Retrieved citations plus the context assembled for an LLM."""

    context: str
    citations: tuple[Citation, ...]


@dataclass(frozen=True)
class ChunkCitation:
    """Internal chunk reference; original content stays server-side in context."""

    memo_id: str
    chunk_id: str
    chunk_index: int
    index_version: str
    score: float
    metadata: Mapping[str, object]


@dataclass(frozen=True)
class ChunkRetrievalResult:
    """Internal chunk retrieval result, deliberately separate from public chat."""

    context: str
    citations: tuple[ChunkCitation, ...]


class RetrievalInputError(ValueError):
    """Raised when a question or result limit is invalid."""


class RetrievalUnavailableError(RuntimeError):
    """Raised when the configured embedding or vector store cannot retrieve."""
