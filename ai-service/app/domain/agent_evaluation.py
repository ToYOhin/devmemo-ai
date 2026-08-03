"""Strict, provider-neutral contracts for sanitized Agent evaluation."""

from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass
from typing import Literal, Mapping, cast


EVALUATION_CASE_VERSION = "agent-evaluation-case-v1"
EVALUATION_CORPUS_VERSION = "agent-evaluation-corpus-v1"
EVALUATION_RESULT_VERSION = "agent-evaluation-result-v1"
EVALUATION_THRESHOLDS_VERSION = "agent-evaluation-thresholds-v1"
MAX_EVALUATION_PAYLOAD_BYTES = 16_384
MAX_EVALUATION_CORPUS_BYTES = 131_072
MAX_EVALUATION_QUESTION_CHARS = 500
MAX_EVALUATION_EVIDENCE_IDS = 20
MIN_EVALUATION_CORPUS_CASES = 50
MAX_EVALUATION_CORPUS_CASES = 100
MIN_EVALUATION_CASES_PER_CATEGORY = 2

EvaluationCategory = Literal[
    "lookup",
    "synthesis",
    "no_answer",
    "conflicting_evidence",
    "visibility_boundary",
    "deletion",
    "stale_state",
    "prompt_injection",
]
EvaluationAnswerState = Literal["answer", "no_answer", "refusal"]
ObservedAnswerState = Literal["answer", "no_answer", "refusal", "error"]
EvaluationFailureCategory = Literal[
    "retrieval_miss",
    "citation_mismatch",
    "ungrounded_answer",
    "incorrect_refusal",
    "scope_leak",
    "stale_evidence",
    "prompt_injection_followed",
    "runtime_error",
]
EvaluationMetric = Literal[
    "retrieval_recall_at_5",
    "retrieval_mrr",
    "citation_precision",
    "groundedness",
    "refusal_accuracy",
    "scope_leak_count",
    "latency_p95_ms",
]
EvaluationMetricUnit = Literal["ratio", "count", "milliseconds"]
EvaluationMetricDirection = Literal["at_least", "at_most"]

_CASE_FIELDS = frozenset(
    {
        "version",
        "case_id",
        "category",
        "data_classification",
        "question",
        "visible_evidence_ids",
        "expected_evidence_ids",
        "forbidden_evidence_ids",
        "expected_answer_state",
    }
)
_CATEGORIES = frozenset(
    {
        "lookup",
        "synthesis",
        "no_answer",
        "conflicting_evidence",
        "visibility_boundary",
        "deletion",
        "stale_state",
        "prompt_injection",
    }
)
_CATEGORY_ORDER: tuple[EvaluationCategory, ...] = (
    "lookup",
    "synthesis",
    "no_answer",
    "conflicting_evidence",
    "visibility_boundary",
    "deletion",
    "stale_state",
    "prompt_injection",
)
_CORPUS_FIELDS = frozenset(
    {"version", "case_version", "category_counts", "cases"}
)
_ANSWER_STATES = frozenset({"answer", "no_answer", "refusal"})
_OBSERVED_ANSWER_STATES = frozenset({"answer", "no_answer", "refusal", "error"})
_FAILURE_CATEGORIES = frozenset(
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
_RESULT_FIELDS = frozenset(
    {
        "version",
        "case_id",
        "answer_state",
        "retrieved_evidence_ids",
        "citation_evidence_ids",
        "failure_categories",
        "latency_ms",
    }
)
_THRESHOLD_FIELDS = frozenset(
    {
        "metric",
        "unit",
        "direction",
        "boundary",
        "range_min",
        "range_max",
        "applicable_categories",
    }
)
_THRESHOLDS_FIELDS = frozenset(
    {"version", "corpus_version", "result_version", "thresholds"}
)
_METRIC_RULES: dict[
    EvaluationMetric, tuple[EvaluationMetricUnit, EvaluationMetricDirection, float, float]
] = {
    "retrieval_recall_at_5": ("ratio", "at_least", 0.0, 1.0),
    "retrieval_mrr": ("ratio", "at_least", 0.0, 1.0),
    "citation_precision": ("ratio", "at_least", 0.0, 1.0),
    "groundedness": ("ratio", "at_least", 0.0, 1.0),
    "refusal_accuracy": ("ratio", "at_least", 0.0, 1.0),
    "scope_leak_count": ("count", "at_most", 0.0, 100.0),
    "latency_p95_ms": ("milliseconds", "at_most", 0.0, 600_000.0),
}
_CASE_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")
_EVIDENCE_ID_PATTERN = re.compile(r"^evidence-[a-z0-9][a-z0-9_-]{0,63}$")


class AgentEvaluationContractError(ValueError):
    """Reject malformed evaluation data without retaining its contents."""

    def __init__(self) -> None:
        super().__init__("invalid agent evaluation contract")


@dataclass(frozen=True)
class AgentEvaluationCase:
    """One sanitized case with explicit authorized and forbidden evidence."""

    case_id: str
    category: EvaluationCategory
    question: str
    visible_evidence_ids: tuple[str, ...]
    expected_evidence_ids: tuple[str, ...]
    forbidden_evidence_ids: tuple[str, ...]
    expected_answer_state: EvaluationAnswerState
    data_classification: Literal["synthetic"] = "synthetic"
    version: Literal["agent-evaluation-case-v1"] = EVALUATION_CASE_VERSION

    def __post_init__(self) -> None:
        if self.version != EVALUATION_CASE_VERSION:
            raise AgentEvaluationContractError
        if self.data_classification != "synthetic":
            raise AgentEvaluationContractError
        if not isinstance(self.case_id, str) or not _CASE_ID_PATTERN.fullmatch(
            self.case_id
        ):
            raise AgentEvaluationContractError
        if not isinstance(self.category, str) or self.category not in _CATEGORIES:
            raise AgentEvaluationContractError
        if (
            not isinstance(self.expected_answer_state, str)
            or self.expected_answer_state not in _ANSWER_STATES
        ):
            raise AgentEvaluationContractError
        if not isinstance(self.question, str):
            raise AgentEvaluationContractError
        question = self.question.strip()
        if not question or len(question) > MAX_EVALUATION_QUESTION_CHARS:
            raise AgentEvaluationContractError

        visible = _validate_evidence_ids(self.visible_evidence_ids)
        expected = _validate_evidence_ids(self.expected_evidence_ids)
        forbidden = _validate_evidence_ids(self.forbidden_evidence_ids)
        if not set(expected).issubset(visible):
            raise AgentEvaluationContractError
        if set(visible).intersection(forbidden):
            raise AgentEvaluationContractError
        if self.expected_answer_state == "answer" and not expected:
            raise AgentEvaluationContractError
        if self.expected_answer_state != "answer" and expected:
            raise AgentEvaluationContractError

        object.__setattr__(self, "question", question)
        object.__setattr__(self, "visible_evidence_ids", visible)
        object.__setattr__(self, "expected_evidence_ids", expected)
        object.__setattr__(self, "forbidden_evidence_ids", forbidden)

    @classmethod
    def from_dict(cls, payload: Mapping[str, object]) -> AgentEvaluationCase:
        if set(payload) != _CASE_FIELDS:
            raise AgentEvaluationContractError
        return cls(
            version=cast(Literal["agent-evaluation-case-v1"], payload["version"]),
            case_id=cast(str, payload["case_id"]),
            category=cast(EvaluationCategory, payload["category"]),
            data_classification=cast(
                Literal["synthetic"], payload["data_classification"]
            ),
            question=cast(str, payload["question"]),
            visible_evidence_ids=_as_evidence_ids(payload["visible_evidence_ids"]),
            expected_evidence_ids=_as_evidence_ids(payload["expected_evidence_ids"]),
            forbidden_evidence_ids=_as_evidence_ids(payload["forbidden_evidence_ids"]),
            expected_answer_state=cast(
                EvaluationAnswerState, payload["expected_answer_state"]
            ),
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "version": self.version,
            "case_id": self.case_id,
            "category": self.category,
            "data_classification": self.data_classification,
            "question": self.question,
            "visible_evidence_ids": list(self.visible_evidence_ids),
            "expected_evidence_ids": list(self.expected_evidence_ids),
            "forbidden_evidence_ids": list(self.forbidden_evidence_ids),
            "expected_answer_state": self.expected_answer_state,
        }


def parse_evaluation_case(body: bytes) -> AgentEvaluationCase:
    """Parse one exact case object and reject duplicate or unknown fields."""

    payload = _parse_json_object(body)
    return AgentEvaluationCase.from_dict(payload)


@dataclass(frozen=True)
class AgentEvaluationResult:
    """One content-free observed result suitable for deterministic scoring."""

    case_id: str
    answer_state: ObservedAnswerState
    retrieved_evidence_ids: tuple[str, ...]
    citation_evidence_ids: tuple[str, ...]
    failure_categories: tuple[EvaluationFailureCategory, ...]
    latency_ms: int
    version: Literal["agent-evaluation-result-v1"] = EVALUATION_RESULT_VERSION

    def __post_init__(self) -> None:
        if self.version != EVALUATION_RESULT_VERSION:
            raise AgentEvaluationContractError
        if not isinstance(self.case_id, str) or not _CASE_ID_PATTERN.fullmatch(
            self.case_id
        ):
            raise AgentEvaluationContractError
        if (
            not isinstance(self.answer_state, str)
            or self.answer_state not in _OBSERVED_ANSWER_STATES
        ):
            raise AgentEvaluationContractError
        retrieved = _validate_evidence_ids(self.retrieved_evidence_ids)
        citations = _validate_evidence_ids(self.citation_evidence_ids)
        if not set(citations).issubset(retrieved):
            raise AgentEvaluationContractError
        if self.answer_state != "answer" and citations:
            raise AgentEvaluationContractError
        if (
            not isinstance(self.latency_ms, int)
            or isinstance(self.latency_ms, bool)
            or not 0 <= self.latency_ms <= 600_000
        ):
            raise AgentEvaluationContractError
        if not isinstance(self.failure_categories, tuple):
            raise AgentEvaluationContractError
        if len(self.failure_categories) > len(_FAILURE_CATEGORIES):
            raise AgentEvaluationContractError
        if any(
            not isinstance(value, str) or value not in _FAILURE_CATEGORIES
            for value in self.failure_categories
        ):
            raise AgentEvaluationContractError
        if len(set(self.failure_categories)) != len(self.failure_categories):
            raise AgentEvaluationContractError
        if self.answer_state == "error" and self.failure_categories != (
            "runtime_error",
        ):
            raise AgentEvaluationContractError

        object.__setattr__(self, "retrieved_evidence_ids", retrieved)
        object.__setattr__(self, "citation_evidence_ids", citations)

    @classmethod
    def from_dict(cls, payload: Mapping[str, object]) -> AgentEvaluationResult:
        if set(payload) != _RESULT_FIELDS:
            raise AgentEvaluationContractError
        failures = payload["failure_categories"]
        if not isinstance(failures, list):
            raise AgentEvaluationContractError
        return cls(
            version=cast(
                Literal["agent-evaluation-result-v1"], payload["version"]
            ),
            case_id=cast(str, payload["case_id"]),
            answer_state=cast(ObservedAnswerState, payload["answer_state"]),
            retrieved_evidence_ids=_as_evidence_ids(
                payload["retrieved_evidence_ids"]
            ),
            citation_evidence_ids=_as_evidence_ids(
                payload["citation_evidence_ids"]
            ),
            failure_categories=tuple(cast(list[EvaluationFailureCategory], failures)),
            latency_ms=cast(int, payload["latency_ms"]),
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "version": self.version,
            "case_id": self.case_id,
            "answer_state": self.answer_state,
            "retrieved_evidence_ids": list(self.retrieved_evidence_ids),
            "citation_evidence_ids": list(self.citation_evidence_ids),
            "failure_categories": list(self.failure_categories),
            "latency_ms": self.latency_ms,
        }


def parse_evaluation_result(body: bytes) -> AgentEvaluationResult:
    """Parse one exact content-free result object."""

    payload = _parse_json_object(body)
    return AgentEvaluationResult.from_dict(payload)


@dataclass(frozen=True)
class AgentEvaluationCorpus:
    """A reviewable synthetic corpus with exact stratification metadata."""

    cases: tuple[AgentEvaluationCase, ...]
    category_counts: tuple[tuple[EvaluationCategory, int], ...]
    case_version: Literal["agent-evaluation-case-v1"] = EVALUATION_CASE_VERSION
    version: Literal["agent-evaluation-corpus-v1"] = EVALUATION_CORPUS_VERSION

    def __post_init__(self) -> None:
        if self.version != EVALUATION_CORPUS_VERSION:
            raise AgentEvaluationContractError
        if self.case_version != EVALUATION_CASE_VERSION:
            raise AgentEvaluationContractError
        if not isinstance(self.cases, tuple) or not (
            MIN_EVALUATION_CORPUS_CASES
            <= len(self.cases)
            <= MAX_EVALUATION_CORPUS_CASES
        ):
            raise AgentEvaluationContractError
        if any(not isinstance(case, AgentEvaluationCase) for case in self.cases):
            raise AgentEvaluationContractError
        if len({case.case_id for case in self.cases}) != len(self.cases):
            raise AgentEvaluationContractError
        if len({case.question.casefold() for case in self.cases}) != len(self.cases):
            raise AgentEvaluationContractError
        if any("synthetic" not in case.question.casefold() for case in self.cases):
            raise AgentEvaluationContractError

        actual_counts = tuple(
            (category, sum(case.category == category for case in self.cases))
            for category in _CATEGORY_ORDER
        )
        if self.category_counts != actual_counts:
            raise AgentEvaluationContractError
        if any(
            count < MIN_EVALUATION_CASES_PER_CATEGORY
            for _, count in self.category_counts
        ):
            raise AgentEvaluationContractError

    @classmethod
    def from_dict(cls, payload: Mapping[str, object]) -> AgentEvaluationCorpus:
        if set(payload) != _CORPUS_FIELDS:
            raise AgentEvaluationContractError
        raw_cases = payload["cases"]
        raw_counts = payload["category_counts"]
        if not isinstance(raw_cases, list) or not isinstance(raw_counts, dict):
            raise AgentEvaluationContractError
        if set(raw_counts) != _CATEGORIES:
            raise AgentEvaluationContractError
        counts: list[tuple[EvaluationCategory, int]] = []
        for category in _CATEGORY_ORDER:
            count = raw_counts[category]
            if not isinstance(count, int) or isinstance(count, bool):
                raise AgentEvaluationContractError
            counts.append((category, count))
        try:
            cases = tuple(
                AgentEvaluationCase.from_dict(case)
                for case in cast(list[Mapping[str, object]], raw_cases)
            )
        except (AttributeError, TypeError) as error:
            raise AgentEvaluationContractError from error
        return cls(
            version=cast(
                Literal["agent-evaluation-corpus-v1"], payload["version"]
            ),
            case_version=cast(
                Literal["agent-evaluation-case-v1"], payload["case_version"]
            ),
            cases=cases,
            category_counts=tuple(counts),
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "version": self.version,
            "case_version": self.case_version,
            "category_counts": dict(self.category_counts),
            "cases": [case.to_dict() for case in self.cases],
        }


def parse_evaluation_corpus(body: bytes) -> AgentEvaluationCorpus:
    """Parse an exact bounded corpus without executing any case."""

    payload = _parse_json_object(body, max_bytes=MAX_EVALUATION_CORPUS_BYTES)
    return AgentEvaluationCorpus.from_dict(payload)


@dataclass(frozen=True)
class AgentEvaluationMetricThreshold:
    """One predeclared metric gate with no observed value."""

    metric: EvaluationMetric
    unit: EvaluationMetricUnit
    direction: EvaluationMetricDirection
    boundary: float
    range_min: float
    range_max: float
    applicable_categories: tuple[EvaluationCategory, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.metric, str) or self.metric not in _METRIC_RULES:
            raise AgentEvaluationContractError
        expected_unit, expected_direction, expected_min, expected_max = (
            _METRIC_RULES[self.metric]
        )
        if self.unit != expected_unit or self.direction != expected_direction:
            raise AgentEvaluationContractError
        for value in (self.boundary, self.range_min, self.range_max):
            if (
                not isinstance(value, (int, float))
                or isinstance(value, bool)
                or not math.isfinite(value)
            ):
                raise AgentEvaluationContractError
        if (self.range_min, self.range_max) != (expected_min, expected_max):
            raise AgentEvaluationContractError
        if not self.range_min <= self.boundary <= self.range_max:
            raise AgentEvaluationContractError
        if not isinstance(self.applicable_categories, tuple) or not (
            1 <= len(self.applicable_categories) <= len(_CATEGORY_ORDER)
        ):
            raise AgentEvaluationContractError
        if any(
            not isinstance(category, str) or category not in _CATEGORIES
            for category in self.applicable_categories
        ):
            raise AgentEvaluationContractError
        if len(set(self.applicable_categories)) != len(self.applicable_categories):
            raise AgentEvaluationContractError

    @classmethod
    def from_dict(
        cls, payload: Mapping[str, object]
    ) -> AgentEvaluationMetricThreshold:
        if set(payload) != _THRESHOLD_FIELDS:
            raise AgentEvaluationContractError
        categories = payload["applicable_categories"]
        if not isinstance(categories, list):
            raise AgentEvaluationContractError
        return cls(
            metric=cast(EvaluationMetric, payload["metric"]),
            unit=cast(EvaluationMetricUnit, payload["unit"]),
            direction=cast(EvaluationMetricDirection, payload["direction"]),
            boundary=cast(float, payload["boundary"]),
            range_min=cast(float, payload["range_min"]),
            range_max=cast(float, payload["range_max"]),
            applicable_categories=tuple(
                cast(list[EvaluationCategory], categories)
            ),
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "metric": self.metric,
            "unit": self.unit,
            "direction": self.direction,
            "boundary": self.boundary,
            "range_min": self.range_min,
            "range_max": self.range_max,
            "applicable_categories": list(self.applicable_categories),
        }


@dataclass(frozen=True)
class AgentEvaluationThresholds:
    """The complete versioned gate set declared before benchmark execution."""

    thresholds: tuple[AgentEvaluationMetricThreshold, ...]
    corpus_version: Literal["agent-evaluation-corpus-v1"] = (
        EVALUATION_CORPUS_VERSION
    )
    result_version: Literal["agent-evaluation-result-v1"] = (
        EVALUATION_RESULT_VERSION
    )
    version: Literal["agent-evaluation-thresholds-v1"] = (
        EVALUATION_THRESHOLDS_VERSION
    )

    def __post_init__(self) -> None:
        if self.version != EVALUATION_THRESHOLDS_VERSION:
            raise AgentEvaluationContractError
        if self.corpus_version != EVALUATION_CORPUS_VERSION:
            raise AgentEvaluationContractError
        if self.result_version != EVALUATION_RESULT_VERSION:
            raise AgentEvaluationContractError
        if not isinstance(self.thresholds, tuple) or any(
            not isinstance(threshold, AgentEvaluationMetricThreshold)
            for threshold in self.thresholds
        ):
            raise AgentEvaluationContractError
        metrics = tuple(threshold.metric for threshold in self.thresholds)
        if len(set(metrics)) != len(metrics) or set(metrics) != set(_METRIC_RULES):
            raise AgentEvaluationContractError

    @classmethod
    def from_dict(cls, payload: Mapping[str, object]) -> AgentEvaluationThresholds:
        if set(payload) != _THRESHOLDS_FIELDS:
            raise AgentEvaluationContractError
        raw_thresholds = payload["thresholds"]
        if not isinstance(raw_thresholds, list):
            raise AgentEvaluationContractError
        try:
            thresholds = tuple(
                AgentEvaluationMetricThreshold.from_dict(threshold)
                for threshold in cast(
                    list[Mapping[str, object]], raw_thresholds
                )
            )
        except (AttributeError, TypeError) as error:
            raise AgentEvaluationContractError from error
        return cls(
            version=cast(
                Literal["agent-evaluation-thresholds-v1"], payload["version"]
            ),
            corpus_version=cast(
                Literal["agent-evaluation-corpus-v1"], payload["corpus_version"]
            ),
            result_version=cast(
                Literal["agent-evaluation-result-v1"], payload["result_version"]
            ),
            thresholds=thresholds,
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "version": self.version,
            "corpus_version": self.corpus_version,
            "result_version": self.result_version,
            "thresholds": [threshold.to_dict() for threshold in self.thresholds],
        }


def parse_evaluation_thresholds(body: bytes) -> AgentEvaluationThresholds:
    """Parse predeclared metric gates without executing a benchmark."""

    payload = _parse_json_object(body)
    return AgentEvaluationThresholds.from_dict(payload)


def _as_evidence_ids(value: object) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise AgentEvaluationContractError
    return tuple(cast(list[str], value))  # validated without coercion below


def _validate_evidence_ids(values: tuple[str, ...]) -> tuple[str, ...]:
    if not isinstance(values, tuple) or len(values) > MAX_EVALUATION_EVIDENCE_IDS:
        raise AgentEvaluationContractError
    for value in values:
        if not isinstance(value, str) or not _EVIDENCE_ID_PATTERN.fullmatch(value):
            raise AgentEvaluationContractError
    if len(set(values)) != len(values):
        raise AgentEvaluationContractError
    return values


def _parse_json_object(
    body: bytes, *, max_bytes: int = MAX_EVALUATION_PAYLOAD_BYTES
) -> Mapping[str, object]:
    try:
        if (
            not isinstance(body, bytes)
            or not 0 < len(body) <= max_bytes
        ):
            raise AgentEvaluationContractError
        payload = json.loads(body, object_pairs_hook=_reject_duplicate_fields)
        if not isinstance(payload, dict):
            raise AgentEvaluationContractError
        return payload
    except AgentEvaluationContractError:
        raise
    except (TypeError, ValueError, UnicodeDecodeError) as error:
        raise AgentEvaluationContractError from error


def _reject_duplicate_fields(pairs: list[tuple[str, object]]) -> dict[str, object]:
    payload: dict[str, object] = {}
    for key, value in pairs:
        if key in payload:
            raise AgentEvaluationContractError
        payload[key] = value
    return payload
