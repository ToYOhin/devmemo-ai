"""Offline retrieval evaluation without coupling to a provider or vector SDK."""

from __future__ import annotations

from app.domain.retrieval_evaluation import (
    RetrievalEvaluationCase,
    RetrievalEvaluationResult,
)
from app.services.retrieval_service import RetrievalService


class RetrievalEvaluator:
    """Run bounded Recall@K checks against the existing retrieval service."""

    def __init__(self, retrieval_service: RetrievalService) -> None:
        self.retrieval_service = retrieval_service

    def evaluate_case(self, case: RetrievalEvaluationCase) -> RetrievalEvaluationResult:
        _validate_case(case)
        result = self.retrieval_service.retrieve(case.question, limit=case.limit)
        expected = set(case.expected_memo_ids)
        retrieved = tuple(citation.memo_id for citation in result.citations)
        relevant = tuple(memo_id for memo_id in retrieved if memo_id in expected)
        first_rank = next(
            (rank for rank, memo_id in enumerate(retrieved, start=1) if memo_id in expected),
            None,
        )
        recall = len(set(relevant)) / len(expected)
        return RetrievalEvaluationResult(
            case_id=case.case_id,
            retrieved_memo_ids=retrieved,
            relevant_memo_ids=relevant,
            recall_at_k=recall,
            first_relevant_rank=first_rank,
        )

    def evaluate(
        self, cases: list[RetrievalEvaluationCase]
    ) -> list[RetrievalEvaluationResult]:
        return [self.evaluate_case(case) for case in cases]


def _validate_case(case: RetrievalEvaluationCase) -> None:
    if not case.case_id.strip():
        raise ValueError("evaluation case_id must not be empty")
    if not case.question.strip():
        raise ValueError("evaluation question must not be empty")
    if not case.expected_memo_ids:
        raise ValueError("evaluation expected_memo_ids must not be empty")
    if len(set(case.expected_memo_ids)) != len(case.expected_memo_ids):
        raise ValueError("evaluation expected_memo_ids must be unique")
    if case.limit < 1 or case.limit > RetrievalService.MAX_LIMIT:
        raise ValueError(
            f"evaluation limit must be between 1 and {RetrievalService.MAX_LIMIT}"
        )
