"""Strict, provider-neutral contracts for the proposed Evidence Answer Agent.

This module deliberately contains no provider, retrieval, HTTP, or persistence
code. It defines the safe boundary that a later, explicitly enabled runtime
must satisfy.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


AGENT_VERSION = "evidence-answer-agent-v1"
SEARCH_MEMOS_TOOL = "search_memos"
MEMO_INDEX_VERSION = "memo-v1"
MAX_RETRIEVAL_LIMIT = 10


class AgentContractError(ValueError):
    """Raised when a value falls outside the Evidence Answer Agent contract."""


@dataclass(frozen=True)
class AgentAnswerRequest:
    """Provider-neutral public request; it carries no content or tool override."""

    question: str
    limit: int = 5

    def __post_init__(self) -> None:
        normalized_question = self.question.strip()
        if not normalized_question:
            raise AgentContractError("question must not be empty")
        if not 1 <= self.limit <= MAX_RETRIEVAL_LIMIT:
            raise AgentContractError(
                f"retrieval limit must be between 1 and {MAX_RETRIEVAL_LIMIT}"
            )
        object.__setattr__(self, "question", normalized_question)


@dataclass(frozen=True)
class MemoVisibilityScope:
    """Caller-authorized complete Memo identifiers supplied by Memos authority."""

    visible_memo_ids: frozenset[str]

    def __post_init__(self) -> None:
        normalized_ids = frozenset(memo_id.strip() for memo_id in self.visible_memo_ids)
        if "" in normalized_ids:
            raise AgentContractError("visible_memo_ids must not contain empty values")
        object.__setattr__(self, "visible_memo_ids", normalized_ids)


@dataclass(frozen=True)
class SearchMemosToolCall:
    """The sole read-only tool call available to this Agent contract."""

    question: str
    limit: int
    visibility: MemoVisibilityScope
    name: Literal["search_memos"] = SEARCH_MEMOS_TOOL

    def __post_init__(self) -> None:
        request = AgentAnswerRequest(question=self.question, limit=self.limit)
        if self.name != SEARCH_MEMOS_TOOL:
            raise AgentContractError("the only permitted Agent tool is search_memos")
        object.__setattr__(self, "question", request.question)


@dataclass(frozen=True)
class EvidenceMetadata:
    """Allowlisted metadata that may accompany a safe complete-Memo citation."""

    memo_type: str = "plain"
    tags: tuple[str, ...] = ()
    index_version: Literal["memo-v1"] = MEMO_INDEX_VERSION

    def __post_init__(self) -> None:
        memo_type = self.memo_type.strip()
        if not memo_type:
            raise AgentContractError("memo_type must not be empty")
        if self.index_version != MEMO_INDEX_VERSION:
            raise AgentContractError("Agent evidence must use complete-Memo memo-v1")

        normalized_tags = tuple(tag.strip() for tag in self.tags)
        if any(not tag for tag in normalized_tags):
            raise AgentContractError("tags must not contain empty values")
        if len(normalized_tags) > 20:
            raise AgentContractError("tags must contain at most 20 values")
        object.__setattr__(self, "memo_type", memo_type)
        object.__setattr__(self, "tags", normalized_tags)

    def to_dict(self) -> dict[str, object]:
        return {
            "memo_type": self.memo_type,
            "tags": list(self.tags),
            "index_version": self.index_version,
        }


@dataclass(frozen=True)
class VisibleMemoEvidence:
    """A bounded, content-free view of one caller-visible complete Memo."""

    memo_id: str
    embedding_id: str
    score: float
    title: str
    summary: str
    source_refs: tuple[str, ...]
    metadata: EvidenceMetadata

    def __post_init__(self) -> None:
        if not isinstance(self.metadata, EvidenceMetadata):
            raise AgentContractError("metadata must use the controlled EvidenceMetadata type")
        for field_name, value in (("memo_id", self.memo_id), ("embedding_id", self.embedding_id)):
            if not value.strip():
                raise AgentContractError(f"{field_name} must not be empty")
        if len(self.title) > 240:
            raise AgentContractError("title must contain at most 240 characters")
        if len(self.summary) > 1000:
            raise AgentContractError("summary must contain at most 1000 characters")
        if len(self.source_refs) > 20:
            raise AgentContractError("source_refs must contain at most 20 values")

        normalized_refs = tuple(source_ref.strip() for source_ref in self.source_refs)
        if any(not source_ref for source_ref in normalized_refs):
            raise AgentContractError("source_refs must not contain empty values")
        object.__setattr__(self, "memo_id", self.memo_id.strip())
        object.__setattr__(self, "embedding_id", self.embedding_id.strip())
        object.__setattr__(self, "title", self.title.strip())
        object.__setattr__(self, "summary", self.summary.strip())
        object.__setattr__(self, "source_refs", normalized_refs)

    def citation_for(self, visibility: MemoVisibilityScope) -> AgentCitation:
        """Project evidence only when Memos has authorized this Memo for the caller."""

        if self.memo_id not in visibility.visible_memo_ids:
            raise AgentContractError("evidence memo is not visible to the caller")
        return AgentCitation(
            memo_id=self.memo_id,
            embedding_id=self.embedding_id,
            score=self.score,
            title=self.title,
            summary=self.summary,
            source_refs=self.source_refs,
            metadata=self.metadata,
        )


@dataclass(frozen=True)
class AgentCitation:
    """The only evidence projection permitted in an Agent answer result."""

    memo_id: str
    embedding_id: str
    score: float
    title: str
    summary: str
    source_refs: tuple[str, ...]
    metadata: EvidenceMetadata

    def __post_init__(self) -> None:
        evidence = VisibleMemoEvidence(
            memo_id=self.memo_id,
            embedding_id=self.embedding_id,
            score=self.score,
            title=self.title,
            summary=self.summary,
            source_refs=self.source_refs,
            metadata=self.metadata,
        )
        object.__setattr__(self, "memo_id", evidence.memo_id)
        object.__setattr__(self, "embedding_id", evidence.embedding_id)
        object.__setattr__(self, "title", evidence.title)
        object.__setattr__(self, "summary", evidence.summary)
        object.__setattr__(self, "source_refs", evidence.source_refs)

    def to_dict(self) -> dict[str, object]:
        return {
            "memo_id": self.memo_id,
            "embedding_id": self.embedding_id,
            "score": self.score,
            "title": self.title,
            "summary": self.summary,
            "source_refs": list(self.source_refs),
            "metadata": self.metadata.to_dict(),
        }


@dataclass(frozen=True)
class AgentStep:
    """Sanitized control-flow record, with no context or tool payload."""

    index: int
    kind: Literal["tool", "final"]
    name: str
    status: Literal["completed"]
    result_count: int | None = None

    def __post_init__(self) -> None:
        if self.index < 1:
            raise AgentContractError("trace step index must be positive")
        if self.kind == "tool" and self.name != SEARCH_MEMOS_TOOL:
            raise AgentContractError("the only permitted Agent tool is search_memos")
        if self.kind == "final" and self.name != "answer_from_evidence":
            raise AgentContractError("the only permitted final action is answer_from_evidence")
        if self.result_count is not None and self.result_count < 0:
            raise AgentContractError("trace result_count must not be negative")

    def to_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "index": self.index,
            "kind": self.kind,
            "name": self.name,
            "status": self.status,
        }
        if self.result_count is not None:
            payload["result_count"] = self.result_count
        return payload


@dataclass(frozen=True)
class AgentTrace:
    """One bounded tool call followed by a final answer, or no-context exit."""

    terminal_state: Literal["answered", "no_context"]
    steps: tuple[AgentStep, ...]

    def __post_init__(self) -> None:
        if tuple(step.index for step in self.steps) != tuple(range(1, len(self.steps) + 1)):
            raise AgentContractError("trace step indexes must be sequential")
        tool_steps = tuple(step for step in self.steps if step.kind == "tool")
        final_steps = tuple(step for step in self.steps if step.kind == "final")
        if len(tool_steps) != 1:
            raise AgentContractError("an Agent trace must contain exactly one search_memos step")
        if self.terminal_state == "answered" and len(final_steps) != 1:
            raise AgentContractError("answered traces must contain one final step")
        if self.terminal_state == "no_context" and final_steps:
            raise AgentContractError("no_context traces must not contain a final step")

    def to_dict(self) -> dict[str, object]:
        return {
            "terminal_state": self.terminal_state,
            "steps": [step.to_dict() for step in self.steps],
        }


@dataclass(frozen=True)
class AgentAnswerResult:
    """Provider-neutral, content-free result returned by a future Agent runtime."""

    answer: str
    citations: tuple[AgentCitation, ...]
    visibility: MemoVisibilityScope
    provider: str
    retrieved_count: int
    trace: AgentTrace
    agent_version: Literal["evidence-answer-agent-v1"] = AGENT_VERSION

    def __post_init__(self) -> None:
        if not self.provider.strip():
            raise AgentContractError("provider must not be empty")
        if not isinstance(self.trace, AgentTrace):
            raise AgentContractError("trace must use the controlled AgentTrace type")
        if any(not isinstance(citation, AgentCitation) for citation in self.citations):
            raise AgentContractError("citations must use the controlled AgentCitation type")
        if any(
            citation.memo_id not in self.visibility.visible_memo_ids
            for citation in self.citations
        ):
            raise AgentContractError("citations must be visible to the caller")
        if self.retrieved_count != len(self.citations):
            raise AgentContractError("retrieved_count must equal the citation count")
        if self.trace.terminal_state == "no_context" and self.citations:
            raise AgentContractError("no_context results must not contain citations")
        if self.agent_version != AGENT_VERSION:
            raise AgentContractError("agent_version is not supported")

    def to_dict(self) -> dict[str, object]:
        return {
            "answer": self.answer,
            "citations": [citation.to_dict() for citation in self.citations],
            "provider": self.provider,
            "retrieved_count": self.retrieved_count,
            "agent_version": self.agent_version,
            "trace": self.trace.to_dict(),
        }
