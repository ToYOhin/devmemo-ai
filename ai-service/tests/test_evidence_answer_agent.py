import asyncio
import json
from datetime import datetime, timezone

import pytest

from app.adapters.agent_observability import BoundedInMemoryObservabilityAdapter
from app.adapters.embedding import DeterministicEmbeddingProvider
from app.adapters.vector_store import InMemoryVectorStore
from app.domain.durable_authorized_retrieval import (
    AuthorizedRetrievalEvidence,
    AuthorizedRetrievalResult,
    ServerOwnedCitation,
)
from app.domain.retrieval import RetrievalInputError, RetrievalUnavailableError
from app.services.agent_delegation import (
    INTERNAL_ANSWER_PATH,
    AgentDelegationError,
    sign_delegated_request,
)
from app.services.embedding_service import EmbeddingService
from app.services.durable_authorized_retrieval import (
    DurableAuthorizedRetrievalUnavailableError,
)
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


def _agent_with_memos(
    *, observability_recorder=None, monotonic_clock=None
) -> tuple[EvidenceAnswerAgent, RecordingProvider]:
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
    return (
        EvidenceAnswerAgent(
            RetrievalService(service),
            provider,
            observability_recorder=observability_recorder,
            monotonic_clock=monotonic_clock,
        ),
        provider,
    )


def _delegated_call(
    visible_memo_uids: list[str],
    question: str = "Docker ports",
    memos_authority_ref: str | None = None,
):
    timestamp = 1785499200
    payload: dict[str, object] = {
        "question": question,
        "limit": 3,
        "visible_memo_uids": visible_memo_uids,
    }
    if memos_authority_ref is not None:
        payload["memos_authority_ref"] = memos_authority_ref
    body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
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


class FailingLegacyRetrieval:
    def retrieve_authorized(self, *args, **kwargs):
        raise AssertionError("durable selection must not call legacy retrieval")


class FakeDurableRetrieval:
    def __init__(self, result: AuthorizedRetrievalResult) -> None:
        self.result = result
        self.calls = 0
        self.error: Exception | None = None

    async def retrieve(self, request):
        self.calls += 1
        if self.error is not None:
            raise self.error
        return self.result


class SequenceClock:
    def __init__(self, *values: float) -> None:
        self._values = iter(values)
        self.calls = 0

    def __call__(self) -> float:
        self.calls += 1
        return next(self._values)


class RaisingLegacyRetrieval:
    def __init__(self, error: Exception) -> None:
        self.error = error

    def retrieve_authorized(self, *args, **kwargs):
        raise self.error


def _durable_result() -> AuthorizedRetrievalResult:
    return AuthorizedRetrievalResult(
        (
            AuthorizedRetrievalEvidence(
                "evidence-1",
                "Docker ports use the host mapping declared in Compose.",
                ServerOwnedCitation("memo-visible", 7),
            ),
        )
    )


def test_agent_selects_durable_retrieval_after_delegation_verification():
    durable = FakeDurableRetrieval(_durable_result())
    provider = RecordingProvider()
    agent = EvidenceAnswerAgent(FailingLegacyRetrieval(), provider, durable)
    body, headers, now = _delegated_call(
        ["memo-visible"], memos_authority_ref="rehydration-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
    )

    result = asyncio.run(agent.run_delegated(body, headers, "test-agent-secret", now))
    payload = result.to_dict()

    assert durable.calls == 1
    assert len(provider.prompts) == 1
    assert payload["citations"][0]["memo_id"] == "memo-visible"
    assert payload["citations"][0]["source_refs"] == ["memos/memo-visible"]
    assert payload["citations"][0]["metadata"] == {
        "memo_type": "plain",
        "tags": [],
        "index_version": "memo-v1",
    }
    assert "content" not in _keys(payload)


def test_agent_durable_empty_result_does_not_call_provider():
    durable = FakeDurableRetrieval(AuthorizedRetrievalResult(()))
    provider = RecordingProvider()
    agent = EvidenceAnswerAgent(FailingLegacyRetrieval(), provider, durable)
    body, headers, now = _delegated_call(
        ["memo-visible"], memos_authority_ref="rehydration-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
    )

    result = asyncio.run(agent.run_delegated(body, headers, "test-agent-secret", now))

    assert result.trace.terminal_state == "no_context"
    assert provider.prompts == []


def test_agent_durable_failure_never_falls_back_or_calls_provider():
    durable = FakeDurableRetrieval(_durable_result())
    durable.error = DurableAuthorizedRetrievalUnavailableError()
    provider = RecordingProvider()
    agent = EvidenceAnswerAgent(FailingLegacyRetrieval(), provider, durable)
    body, headers, now = _delegated_call(
        ["memo-visible"], memos_authority_ref="rehydration-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
    )

    with pytest.raises(RetrievalUnavailableError):
        asyncio.run(agent.run_delegated(body, headers, "test-agent-secret", now))

    assert durable.calls == 1
    assert provider.prompts == []


def test_agent_records_memory_retrieval_before_provider_answering():
    recorder = BoundedInMemoryObservabilityAdapter(capacity=2)
    clock = SequenceClock(10.0, 10.025)
    agent, provider = _agent_with_memos(
        observability_recorder=recorder,
        monotonic_clock=clock,
    )
    original_generate = provider.generate

    async def generate_after_retrieval(prompt):
        assert clock.calls == 2
        return await original_generate(prompt)

    provider.generate = generate_after_retrieval
    body, headers, now = _delegated_call(["memo-visible"])

    result = asyncio.run(agent.run_delegated(body, headers, "test-agent-secret", now))

    metric, event = recorder.snapshot()
    assert result.trace.terminal_state == "answered"
    assert len(provider.prompts) == 1
    assert clock.calls == 2
    assert metric.to_dict()["value"] == pytest.approx(25.0)
    assert event.to_dict()["outcome"] == "success"


def test_agent_records_memory_no_context_retrieval():
    recorder = BoundedInMemoryObservabilityAdapter(capacity=2)
    clock = SequenceClock(10.0, 10.001)
    agent, provider = _agent_with_memos(
        observability_recorder=recorder,
        monotonic_clock=clock,
    )
    body, headers, now = _delegated_call([])

    result = asyncio.run(agent.run_delegated(body, headers, "test-agent-secret", now))

    assert result.trace.terminal_state == "no_context"
    assert provider.prompts == []
    assert recorder.snapshot()[1].to_dict()["outcome"] == "no_context"


def test_agent_records_durable_retrieval_without_calling_legacy_path():
    recorder = BoundedInMemoryObservabilityAdapter(capacity=2)
    clock = SequenceClock(10.0, 10.002)
    durable = FakeDurableRetrieval(_durable_result())
    agent = EvidenceAnswerAgent(
        FailingLegacyRetrieval(),
        DeterministicProvider(),
        durable,
        observability_recorder=recorder,
        monotonic_clock=clock,
    )
    body, headers, now = _delegated_call(
        ["memo-visible"],
        memos_authority_ref="rehydration-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
    )

    asyncio.run(agent.run_delegated(body, headers, "test-agent-secret", now))

    assert durable.calls == 1
    assert recorder.snapshot()[1].to_dict()["outcome"] == "success"


def test_agent_records_durable_no_context_retrieval():
    recorder = BoundedInMemoryObservabilityAdapter(capacity=2)
    clock = SequenceClock(10.0, 10.002)
    durable = FakeDurableRetrieval(AuthorizedRetrievalResult(()))
    provider = RecordingProvider()
    agent = EvidenceAnswerAgent(
        FailingLegacyRetrieval(),
        provider,
        durable,
        observability_recorder=recorder,
        monotonic_clock=clock,
    )
    body, headers, now = _delegated_call(
        ["memo-visible"],
        memos_authority_ref="rehydration-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
    )

    result = asyncio.run(agent.run_delegated(body, headers, "test-agent-secret", now))

    assert result.trace.terminal_state == "no_context"
    assert provider.prompts == []
    assert recorder.snapshot()[1].to_dict()["outcome"] == "no_context"


@pytest.mark.parametrize(
    ("error", "expected_outcome"),
    [
        (RetrievalInputError("synthetic invalid retrieval"), "invalid"),
        (RetrievalUnavailableError("synthetic unavailable retrieval"), "unavailable"),
    ],
)
def test_agent_records_memory_retrieval_failure_without_changing_error(
    error, expected_outcome
):
    recorder = BoundedInMemoryObservabilityAdapter(capacity=2)
    clock = SequenceClock(10.0, 10.003)
    agent = EvidenceAnswerAgent(
        RaisingLegacyRetrieval(error),
        DeterministicProvider(),
        observability_recorder=recorder,
        monotonic_clock=clock,
    )
    body, headers, now = _delegated_call(["memo-visible"])

    with pytest.raises(type(error)) as raised:
        asyncio.run(agent.run_delegated(body, headers, "test-agent-secret", now))

    assert raised.value is error
    assert recorder.snapshot()[1].to_dict()["outcome"] == expected_outcome


def test_agent_ignores_retrieval_recorder_failure():
    class RaisingRecorder:
        def record(self, _sample):
            raise RuntimeError("raw synthetic recorder failure")

    clock = SequenceClock(10.0, 10.004)
    agent, provider = _agent_with_memos(
        observability_recorder=RaisingRecorder(),
        monotonic_clock=clock,
    )
    body, headers, now = _delegated_call(["memo-visible"])

    result = asyncio.run(agent.run_delegated(body, headers, "test-agent-secret", now))

    assert result.trace.terminal_state == "answered"
    assert len(provider.prompts) == 1


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
