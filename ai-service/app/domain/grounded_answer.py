"""Strict provider-neutral contract for a future grounded Agent answer.

The current EvidenceAnswerAgent does not call this module. It defines the
untrusted Provider result that a later runtime slice may validate before any
Provider text is allowed to cross the existing safe response boundary.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Iterable, Literal, Mapping, cast

from app.domain.agent import AgentCitation


GROUNDED_ANSWER_VERSION = "grounded-answer-result-v1"
MAX_GROUNDED_ANSWER_CHARS = 4_000
MAX_GROUNDED_CITATIONS = 10
MAX_PROVIDER_RESULT_BYTES = 16_384

GroundedAnswerFailureCode = Literal[
    "invalid_grounded_answer",
    "provider_timeout",
    "provider_unavailable",
]

_REFERENCE_PATTERN = re.compile(r"^evidence-[A-Za-z0-9_-]{1,48}$")
_EXPECTED_FIELDS = frozenset({"version", "answer", "citation_refs"})
_FAILURE_CODES = frozenset(
    {"invalid_grounded_answer", "provider_timeout", "provider_unavailable"}
)


class GroundedAnswerContractError(ValueError):
    """Fail closed without retaining Provider text or parsing details."""

    def __init__(self) -> None:
        super().__init__("invalid grounded answer")


@dataclass(frozen=True)
class ProviderGroundedAnswer:
    """Exact untrusted result accepted from a future configured Provider."""

    answer: str
    citation_refs: tuple[str, ...]
    version: Literal["grounded-answer-result-v1"] = GROUNDED_ANSWER_VERSION

    def __post_init__(self) -> None:
        if self.version != GROUNDED_ANSWER_VERSION:
            raise GroundedAnswerContractError
        if not isinstance(self.answer, str):
            raise GroundedAnswerContractError
        normalized_answer = self.answer.strip()
        if not normalized_answer or len(normalized_answer) > MAX_GROUNDED_ANSWER_CHARS:
            raise GroundedAnswerContractError
        if not isinstance(self.citation_refs, tuple):
            raise GroundedAnswerContractError
        if not 1 <= len(self.citation_refs) <= MAX_GROUNDED_CITATIONS:
            raise GroundedAnswerContractError

        normalized_refs: list[str] = []
        for reference in self.citation_refs:
            if not isinstance(reference, str):
                raise GroundedAnswerContractError
            normalized = reference.strip()
            if not _REFERENCE_PATTERN.fullmatch(normalized):
                raise GroundedAnswerContractError
            normalized_refs.append(normalized)
        if len(set(normalized_refs)) != len(normalized_refs):
            raise GroundedAnswerContractError

        object.__setattr__(self, "answer", normalized_answer)
        object.__setattr__(self, "citation_refs", tuple(normalized_refs))

    @classmethod
    def from_dict(cls, payload: Mapping[str, object]) -> ProviderGroundedAnswer:
        if set(payload) != _EXPECTED_FIELDS:
            raise GroundedAnswerContractError
        citation_refs = payload["citation_refs"]
        if not isinstance(citation_refs, list):
            raise GroundedAnswerContractError
        return cls(
            version=cast(Literal["grounded-answer-result-v1"], payload["version"]),
            answer=cast(str, payload["answer"]),
            citation_refs=tuple(citation_refs),
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "version": self.version,
            "answer": self.answer,
            "citation_refs": list(self.citation_refs),
        }


@dataclass(frozen=True)
class ValidatedGroundedAnswer:
    """Server-owned projection after every reference has been authorized."""

    answer: str
    citations: tuple[AgentCitation, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "answer": self.answer,
            "citations": [citation.to_dict() for citation in self.citations],
        }


@dataclass(frozen=True)
class GroundedAnswerFailure:
    """Bounded content-free failure suitable for a later internal mapping."""

    error_code: GroundedAnswerFailureCode

    def __post_init__(self) -> None:
        if self.error_code not in _FAILURE_CODES:
            raise ValueError("unsupported grounded answer failure code")

    def to_dict(self) -> dict[str, str]:
        return {"error_code": self.error_code}


def parse_provider_grounded_answer(body: bytes) -> ProviderGroundedAnswer:
    """Parse one exact JSON object and reject duplicate or unknown fields."""

    try:
        if not isinstance(body, bytes) or not 0 < len(body) <= MAX_PROVIDER_RESULT_BYTES:
            raise GroundedAnswerContractError
        payload = json.loads(body, object_pairs_hook=_reject_duplicate_fields)
        if not isinstance(payload, dict):
            raise GroundedAnswerContractError
        return ProviderGroundedAnswer.from_dict(payload)
    except GroundedAnswerContractError:
        raise
    except (TypeError, ValueError, UnicodeDecodeError) as error:
        raise GroundedAnswerContractError from error


def validate_grounded_answer(
    result: ProviderGroundedAnswer,
    evidence_by_reference: Mapping[str, AgentCitation],
    *,
    protected_context_fragments: Iterable[str] = (),
) -> ValidatedGroundedAnswer:
    """Map opaque references to server-owned citations and reject context echoes."""

    if not evidence_by_reference:
        raise GroundedAnswerContractError
    for reference, citation in evidence_by_reference.items():
        if not isinstance(reference, str) or not _REFERENCE_PATTERN.fullmatch(reference):
            raise GroundedAnswerContractError
        if not isinstance(citation, AgentCitation):
            raise GroundedAnswerContractError

    try:
        citations = tuple(evidence_by_reference[ref] for ref in result.citation_refs)
    except KeyError as error:
        raise GroundedAnswerContractError from error

    normalized_answer = _normalize_for_echo_check(result.answer)
    for fragment in protected_context_fragments:
        if not isinstance(fragment, str):
            raise GroundedAnswerContractError
        normalized_fragment = _normalize_for_echo_check(fragment)
        if normalized_fragment and normalized_fragment in normalized_answer:
            raise GroundedAnswerContractError
    return ValidatedGroundedAnswer(result.answer, citations)


def map_grounded_answer_failure(error: BaseException) -> GroundedAnswerFailure:
    """Collapse validation and Provider failures to fixed content-free codes."""

    if isinstance(error, GroundedAnswerContractError):
        return GroundedAnswerFailure("invalid_grounded_answer")
    if isinstance(error, TimeoutError):
        return GroundedAnswerFailure("provider_timeout")
    return GroundedAnswerFailure("provider_unavailable")


def _reject_duplicate_fields(pairs: list[tuple[str, object]]) -> dict[str, object]:
    payload: dict[str, object] = {}
    for key, value in pairs:
        if key in payload:
            raise GroundedAnswerContractError
        payload[key] = value
    return payload


def _normalize_for_echo_check(value: str) -> str:
    return " ".join(value.split()).casefold()
