import asyncio
import json
from datetime import datetime, timezone

import pytest

from app.adapters.embedding import DeterministicEmbeddingProvider
from app.adapters.vector_store import InMemoryVectorStore
from app.services.agent_delegation import (
    INTERNAL_ANSWER_PATH,
    AgentDelegationError,
    sign_delegated_request,
)
from app.services.embedding_service import EmbeddingService
from app.services.evidence_answer_agent import AgentProviderError, EvidenceAnswerAgent
from app.services.memo_indexing import MemoIndexDocument, index_memo
from app.services.retrieval_service import RetrievalService
from llm import DeterministicProvider, LLMResult


class RecordingProvider:
    name = "ollama"

    def __init__(self) -> None:
        self.prompts: list[str] = []

    async def generate(self, prompt: str) -> LLMResult:
        self.prompts.append(prompt)
        return LLMResult(
            text=json.dumps(
                {
                    "version": "grounded-answer-result-v1",
                    "answer": "Safe grounded answer.",
                    "citation_refs": ["evidence-1"],
                },
                separators=(",", ":"),
            ),
            provider=self.name,
        )


class EchoingProvider(RecordingProvider):
    async def generate(self, prompt: str) -> LLMResult:
        self.prompts.append(prompt)
        return LLMResult(
            text=json.dumps(
                {
                    "version": "grounded-answer-result-v1",
                    "answer": "Docker ports use the host mapping declared in Compose.",
                    "citation_refs": ["evidence-1"],
                },
                separators=(",", ":"),
            ),
            provider=self.name,
        )


def _agent_with_memos() -> tuple[EvidenceAnswerAgent, RecordingProvider]:
    service = EmbeddingService(DeterministicEmbeddingProvider(), InMemoryVectorStore(8))
    index_memo(
        service,
        MemoIndexDocument.from_memo(
            "memo-visible",
            "Docker ports use the host mapping declared in Compose.",
            {"title": "Docker ports", "tags": ["docker"]},
        ),
    )
    index_memo(
        service,
        MemoIndexDocument.from_memo(
            "memo-hidden",
            "TOP SECRET: rotate the production credential.",
            {"title": "Private operations", "tags": ["private"]},
        ),
    )
    provider = RecordingProvider()
    return EvidenceAnswerAgent(RetrievalService(service), provider), provider


def _delegated_call(visible_memo_uids: list[str], question: str = "Docker ports"):
    timestamp = 1785499200
    body = json.dumps(
        {
            "question": question,
            "limit": 3,
            "visible_memo_uids": visible_memo_uids,
        },
        separators=(",", ":"),
    ).encode("utf-8")
    headers = sign_delegated_request(
        "POST", INTERNAL_ANSWER_PATH, body, timestamp, "test-agent-secret"
    )
    return body, headers, datetime.fromtimestamp(timestamp + 30, timezone.utc)


def _keys(value: object) -> set[str]:
    if isinstance(value, dict):
        return set(value).union(*(_keys(item) for item in value.values()))
    if isinstance(value, list):
        return set().union(*(_keys(item) for item in value))
    return set()


def test_agent_runs_exactly_one_authorized_search_and_returns_safe_evidence(monkeypatch):
    agent, provider = _agent_with_memos()
    body, headers, now = _delegated_call(["memo-visible"], question="secret Docker ports")
    calls = 0
    original_retrieve = agent._retrieval_service.retrieve_authorized

    def count_retrieval(*args, **kwargs):
        nonlocal calls
        calls += 1
        return original_retrieve(*args, **kwargs)

    monkeypatch.setattr(agent._retrieval_service, "retrieve_authorized", count_retrieval)

    result = asyncio.run(agent.run_delegated(body, headers, "test-agent-secret", now))
    payload = result.to_dict()

    assert calls == 1
    assert len(provider.prompts) == 1
    assert "TOP SECRET" not in provider.prompts[0]
    assert "memo-visible" not in provider.prompts[0]
    assert "memo_id=" not in provider.prompts[0]
    assert "score=" not in provider.prompts[0]
    assert "[evidence-1]" in provider.prompts[0]
    assert "Output JSON only" in provider.prompts[0]
    assert '"citation_refs":["evidence-1"]' in provider.prompts[0]
    assert result.answer == "Safe grounded answer."
    assert payload["citations"][0]["memo_id"] == "memo-visible"
    assert payload["trace"]["steps"][0] == {
        "index": 1,
        "kind": "tool",
        "name": "search_memos",
        "status": "completed",
        "result_count": 1,
    }
    assert "content" not in _keys(payload)


def test_agent_empty_authorized_scope_does_not_call_provider():
    agent, provider = _agent_with_memos()
    body, headers, now = _delegated_call([])

    result = asyncio.run(agent.run_delegated(body, headers, "test-agent-secret", now))

    assert provider.prompts == []
    assert result.trace.terminal_state == "no_context"
    assert result.retrieved_count == 0


def test_agent_rejects_an_invalid_delegation_before_retrieval_or_provider():
    agent, provider = _agent_with_memos()
    body, headers, now = _delegated_call(["memo-visible"])

    with pytest.raises(AgentDelegationError, match="invalid Agent delegation"):
        asyncio.run(agent.run_delegated(body + b" ", headers, "test-agent-secret", now))

    assert provider.prompts == []


def test_agent_rejects_provider_raw_context_echo():
    agent, _ = _agent_with_memos()
    provider = EchoingProvider()
    agent._provider = provider
    body, headers, now = _delegated_call(["memo-visible"])

    with pytest.raises(AgentProviderError) as error:
        asyncio.run(agent.run_delegated(body, headers, "test-agent-secret", now))

    assert len(provider.prompts) == 1
    assert error.value.error_code == "invalid_grounded_answer"
    assert str(error.value) == "Agent provider unavailable"


def test_agent_deterministic_answer_behavior_is_unchanged():
    agent, _ = _agent_with_memos()
    agent._provider = DeterministicProvider()
    body, headers, now = _delegated_call(["memo-visible"])

    result = asyncio.run(agent.run_delegated(body, headers, "test-agent-secret", now))

    assert result.answer == "Found 1 authorized Memo source(s) relevant to the question [1]."
    assert [citation.memo_id for citation in result.citations] == ["memo-visible"]


@pytest.mark.parametrize(
    ("provider_result", "expected_code"),
    [
        (LLMResult(text="not-json", provider="ollama"), "invalid_grounded_answer"),
        (
            LLMResult(
                text=json.dumps(
                    {
                        "version": "grounded-answer-result-v1",
                        "answer": "Unknown source.",
                        "citation_refs": ["evidence-unknown"],
                    }
                ),
                provider="ollama",
            ),
            "invalid_grounded_answer",
        ),
    ],
)
def test_agent_rejects_malformed_or_unknown_provider_results(
    provider_result, expected_code
):
    class FixedProvider:
        name = "ollama"

        async def generate(self, _prompt):
            return provider_result

    agent, _ = _agent_with_memos()
    agent._provider = FixedProvider()
    body, headers, now = _delegated_call(["memo-visible"])

    with pytest.raises(AgentProviderError) as error:
        asyncio.run(agent.run_delegated(body, headers, "test-agent-secret", now))

    assert error.value.error_code == expected_code
    assert str(error.value) == "Agent provider unavailable"


@pytest.mark.parametrize(
    ("provider_error", "expected_code"),
    [
        (TimeoutError("raw endpoint timeout"), "provider_timeout"),
        (OSError("raw upstream secret"), "provider_unavailable"),
    ],
)
def test_agent_maps_provider_failures_to_bounded_codes(
    provider_error, expected_code
):
    class BrokenProvider:
        name = "ollama"

        async def generate(self, _prompt):
            raise provider_error

    agent, _ = _agent_with_memos()
    agent._provider = BrokenProvider()
    body, headers, now = _delegated_call(["memo-visible"])

    with pytest.raises(AgentProviderError) as error:
        asyncio.run(agent.run_delegated(body, headers, "test-agent-secret", now))

    assert error.value.error_code == expected_code
    assert str(provider_error) not in str(error.value)
