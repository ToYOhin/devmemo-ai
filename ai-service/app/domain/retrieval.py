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


class RetrievalInputError(ValueError):
    """Raised when a question or result limit is invalid."""


class RetrievalUnavailableError(RuntimeError):
    """Raised when the configured embedding or vector store cannot retrieve."""
