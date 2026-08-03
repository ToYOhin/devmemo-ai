"""Versioned content-free report contract for deterministic Agent evaluation."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal

from app.domain.agent_evaluation import (
    EVALUATION_CORPUS_VERSION,
    EVALUATION_RESULT_VERSION,
    EVALUATION_THRESHOLDS_VERSION,
    MAX_EVALUATION_CORPUS_CASES,
    MIN_EVALUATION_CORPUS_CASES,
    AgentEvaluationMetricThreshold,
    EvaluationFailureCategory,
)


EVALUATION_REPORT_VERSION = "agent-evaluation-report-v1"

_METRICS = frozenset(
    {
        "retrieval_recall_at_5",
        "retrieval_mrr",
        "citation_precision",
        "groundedness",
        "refusal_accuracy",
        "scope_leak_count",
        "latency_p95_ms",
    }
)
_FAILURES = frozenset(
    {
        "retrieval_miss",
        "citation_mismatch",
        "ungrounded_answer",
        "incorrect_refusal",
        "scope_leak",
        "stale_evidence",
        "prompt_injection_followed",
        "runtime_error",
    }
)


class AgentEvaluationReportError(ValueError):
    """Reject inconsistent content-free report values."""

    def __init__(self) -> None:
        super().__init__("invalid agent evaluation report")


@dataclass(frozen=True)
class AgentEvaluationMetricReport:
    """One aggregate value evaluated against its predeclared threshold."""

    threshold: AgentEvaluationMetricThreshold
    value: float
    applicable_case_count: int
    passed: bool

    def __post_init__(self) -> None:
        if not isinstance(self.threshold, AgentEvaluationMetricThreshold):
            raise AgentEvaluationReportError
        if (
            not isinstance(self.value, (int, float))
            or isinstance(self.value, bool)
            or not math.isfinite(self.value)
            or self.value < 0
        ):
            raise AgentEvaluationReportError
        if (
            not isinstance(self.applicable_case_count, int)
            or isinstance(self.applicable_case_count, bool)
            or not 1 <= self.applicable_case_count <= MAX_EVALUATION_CORPUS_CASES
        ):
            raise AgentEvaluationReportError
        if not isinstance(self.passed, bool):
            raise AgentEvaluationReportError
        expected_pass = (
            self.value >= self.threshold.boundary
            if self.threshold.direction == "at_least"
            else self.value <= self.threshold.boundary
        )
        if self.passed != expected_pass:
            raise AgentEvaluationReportError

    def to_dict(self) -> dict[str, object]:
        return {
            "metric": self.threshold.metric,
            "value": self.value,
            "unit": self.threshold.unit,
            "direction": self.threshold.direction,
            "boundary": self.threshold.boundary,
            "applicable_case_count": self.applicable_case_count,
            "passed": self.passed,
        }


@dataclass(frozen=True)
class AgentEvaluationFailedCase:
    """A failed case projection without question, answer, or evidence data."""

    case_id: str
    failure_categories: tuple[EvaluationFailureCategory, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.case_id, str) or not self.case_id:
            raise AgentEvaluationReportError
        if not isinstance(self.failure_categories, tuple) or not (
            1 <= len(self.failure_categories) <= len(_FAILURES)
        ):
            raise AgentEvaluationReportError
        if any(
            not isinstance(category, str) or category not in _FAILURES
            for category in self.failure_categories
        ):
            raise AgentEvaluationReportError
        if len(set(self.failure_categories)) != len(self.failure_categories):
            raise AgentEvaluationReportError

    def to_dict(self) -> dict[str, object]:
        return {
            "case_id": self.case_id,
            "failure_categories": list(self.failure_categories),
        }


@dataclass(frozen=True)
class AgentEvaluationReport:
    """Complete content-free metrics and failure projection for one corpus."""

    case_count: int
    metrics: tuple[AgentEvaluationMetricReport, ...]
    failed_cases: tuple[AgentEvaluationFailedCase, ...]
    passed: bool
    corpus_version: Literal["agent-evaluation-corpus-v1"] = (
        EVALUATION_CORPUS_VERSION
    )
    thresholds_version: Literal["agent-evaluation-thresholds-v1"] = (
        EVALUATION_THRESHOLDS_VERSION
    )
    result_version: Literal["agent-evaluation-result-v1"] = (
        EVALUATION_RESULT_VERSION
    )
    version: Literal["agent-evaluation-report-v1"] = EVALUATION_REPORT_VERSION

    def __post_init__(self) -> None:
        if self.version != EVALUATION_REPORT_VERSION:
            raise AgentEvaluationReportError
        if self.corpus_version != EVALUATION_CORPUS_VERSION:
            raise AgentEvaluationReportError
        if self.thresholds_version != EVALUATION_THRESHOLDS_VERSION:
            raise AgentEvaluationReportError
        if self.result_version != EVALUATION_RESULT_VERSION:
            raise AgentEvaluationReportError
        if (
            not isinstance(self.case_count, int)
            or isinstance(self.case_count, bool)
            or not MIN_EVALUATION_CORPUS_CASES
            <= self.case_count
            <= MAX_EVALUATION_CORPUS_CASES
        ):
            raise AgentEvaluationReportError
        if not isinstance(self.metrics, tuple) or any(
            not isinstance(metric, AgentEvaluationMetricReport)
            for metric in self.metrics
        ):
            raise AgentEvaluationReportError
        metric_names = tuple(metric.threshold.metric for metric in self.metrics)
        if len(set(metric_names)) != len(metric_names) or set(metric_names) != _METRICS:
            raise AgentEvaluationReportError
        if not isinstance(self.failed_cases, tuple) or any(
            not isinstance(case, AgentEvaluationFailedCase)
            for case in self.failed_cases
        ):
            raise AgentEvaluationReportError
        if len({case.case_id for case in self.failed_cases}) != len(
            self.failed_cases
        ):
            raise AgentEvaluationReportError
        if not isinstance(self.passed, bool):
            raise AgentEvaluationReportError
        expected_pass = all(metric.passed for metric in self.metrics) and not (
            self.failed_cases
        )
        if self.passed != expected_pass:
            raise AgentEvaluationReportError

    def to_dict(self) -> dict[str, object]:
        return {
            "version": self.version,
            "corpus_version": self.corpus_version,
            "thresholds_version": self.thresholds_version,
            "result_version": self.result_version,
            "case_count": self.case_count,
            "metrics": [metric.to_dict() for metric in self.metrics],
            "passed": self.passed,
            "failed_cases": [case.to_dict() for case in self.failed_cases],
        }
