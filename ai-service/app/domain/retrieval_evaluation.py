"""Provider-neutral contracts for offline retrieval quality checks."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RetrievalEvaluationCase:
    """One deterministic question and the Memo IDs expected in its result."""

    case_id: str
    question: str
    expected_memo_ids: tuple[str, ...]
    limit: int = 5


@dataclass(frozen=True)
class RetrievalEvaluationResult:
    """Bounded metrics for one retrieval evaluation case."""

    case_id: str
    retrieved_memo_ids: tuple[str, ...]
    relevant_memo_ids: tuple[str, ...]
    recall_at_k: float
    first_relevant_rank: int | None
