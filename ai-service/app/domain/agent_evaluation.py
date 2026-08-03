"""Strict, provider-neutral contracts for sanitized Agent evaluation."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Literal, Mapping, cast


EVALUATION_CASE_VERSION = "agent-evaluation-case-v1"
EVALUATION_RESULT_VERSION = "agent-evaluation-result-v1"
MAX_EVALUATION_PAYLOAD_BYTES = 16_384
MAX_EVALUATION_QUESTION_CHARS = 500
MAX_EVALUATION_EVIDENCE_IDS = 20

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


def _parse_json_object(body: bytes) -> Mapping[str, object]:
    try:
        if (
            not isinstance(body, bytes)
            or not 0 < len(body) <= MAX_EVALUATION_PAYLOAD_BYTES
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
