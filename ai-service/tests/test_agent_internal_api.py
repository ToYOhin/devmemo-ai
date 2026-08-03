import json
import time
from dataclasses import replace

import pytest
from fastapi.testclient import TestClient

import main
from app.adapters.agent_observability import BoundedInMemoryObservabilityAdapter
from app.adapters.embedding import DeterministicEmbeddingProvider
from app.adapters.vector_store import InMemoryVectorStore
from app.domain.durable_authorized_retrieval import (
    AuthorizedRetrievalEvidence,
    AuthorizedRetrievalResult,
    ServerOwnedCitation,
)
from app.domain.retrieval import RetrievalInputError
from app.services.agent_delegation import INTERNAL_ANSWER_PATH, sign_delegated_request
from app.services.durable_authorized_retrieval import (
    DurableAuthorizedRetrievalUnavailableError,
)
from app.services.embedding_service import EmbeddingService
from app.services.memo_indexing import MemoIndexDocument, index_memo
from llm import DeterministicProvider, LLMResult


client = TestClient(main.app)
_SECRET = "agent-route-test-secret"


def _enabled_settings(**overrides: object):
    return replace(
        main.settings,
        agent_enabled=True,
        agent_internal_secret=_SECRET,
        **overrides,
    )


def _body(
    visible_memo_uids: list[str], memos_authority_ref: str | None = None
) -> bytes:
    payload: dict[str, object] = {
        "question": "Docker ports",
        "limit": 3,
        "visible_memo_uids": visible_memo_uids,
    }
    if memos_authority_ref is not None:
        payload["memos_authority_ref"] = memos_authority_ref
    return json.dumps(payload, separators=(",", ":")).encode("utf-8")


def _signed_headers(body: bytes) -> dict[str, str]:
    signed = sign_delegated_request(
        "POST", INTERNAL_ANSWER_PATH, body, int(time.time()), _SECRET
    )
    return {
        "X-DevMemo-Agent-Signature": signed.signature,
        "X-DevMemo-Agent-Timestamp": signed.timestamp,
    }


def _indexed_service() -> EmbeddingService:
    service = EmbeddingService(DeterministicEmbeddingProvider(), InMemoryVectorStore(8))
    index_memo(
        service,
        MemoIndexDocument.from_memo(
            "memo-visible",
            "Docker port mapping is declared in Compose.",
            {"title": "Docker ports", "tags": ["docker"]},
        ),
    )
    return service


def _keys(value: object) -> set[str]:
    if isinstance(value, dict):
        return set(value).union(*(_keys(item) for item in value.values()))
    if isinstance(value, list):
        return set().union(*(_keys(item) for item in value))
    return set()


def _observability(monkeypatch) -> BoundedInMemoryObservabilityAdapter:
    adapter = BoundedInMemoryObservabilityAdapter(capacity=16)
    monkeypatch.setattr(
        main.app.state,
        "agent_observability",
        adapter,
        raising=False,
    )
    return adapter


def _recorded_outcomes(adapter: BoundedInMemoryObservabilityAdapter) -> list[str]:
    return [
        str(payload["outcome"])
        for sample in adapter.snapshot()
        if (payload := sample.to_dict())["kind"] == "event"
    ]


def _recorded_metrics(
    adapter: BoundedInMemoryObservabilityAdapter,
) -> list[tuple[str, str, str]]:
    return [
        (
            str(payload["component"]),
            str(payload["operation"]),
            str(payload["metric"]),
        )
        for sample in adapter.snapshot()
        if (payload := sample.to_dict())["kind"] == "metric"
    ]


def test_internal_agent_route_is_not_available_when_disabled(monkeypatch):
    body = _body(["memo-visible"])
    monkeypatch.setattr(main, "settings", replace(main.settings, agent_enabled=False))
    adapter = _observability(monkeypatch)

    response = client.post(INTERNAL_ANSWER_PATH, content=body, headers=_signed_headers(body))

    assert response.status_code == 404
    assert response.json() == {"detail": "not found"}
    assert adapter.snapshot() == ()


def test_lifespan_owns_observability_only_under_existing_agent_opt_in(monkeypatch):
    monkeypatch.setattr(main, "settings", replace(main.settings, agent_enabled=False))

    with TestClient(main.app):
        assert main.app.state.agent_observability is None

    monkeypatch.setattr(main, "settings", _enabled_settings())
    with TestClient(main.app):
        adapter = main.app.state.agent_observability
        assert isinstance(adapter, BoundedInMemoryObservabilityAdapter)
        assert adapter.capacity == 256

    assert main.app.state.agent_observability is None


def test_internal_agent_route_returns_only_safe_authorized_result(monkeypatch):
    body = _body(["memo-visible"])
    monkeypatch.setattr(main, "settings", _enabled_settings())
    monkeypatch.setattr(main, "embedding_service", _indexed_service())
    monkeypatch.setattr(main, "provider", DeterministicProvider())
    adapter = _observability(monkeypatch)

    response = client.post(INTERNAL_ANSWER_PATH, content=body, headers=_signed_headers(body))

    assert response.status_code == 200
    payload = response.json()
    assert payload["citations"][0]["memo_id"] == "memo-visible"
    assert payload["trace"]["steps"][0]["name"] == "search_memos"
    assert "content" not in _keys(payload)
    assert len(adapter.snapshot()) == 4
    assert _recorded_metrics(adapter) == [
        ("retrieval", "search_memos", "tool_latency_ms"),
        ("agent", "answer", "request_count"),
    ]
    assert _recorded_outcomes(adapter) == ["success", "success"]


def test_internal_agent_route_records_no_context(monkeypatch):
    body = _body([])
    monkeypatch.setattr(main, "settings", _enabled_settings())
    monkeypatch.setattr(main, "provider", DeterministicProvider())
    adapter = _observability(monkeypatch)

    response = client.post(INTERNAL_ANSWER_PATH, content=body, headers=_signed_headers(body))

    assert response.status_code == 200
    assert response.json()["trace"]["terminal_state"] == "no_context"
    assert _recorded_outcomes(adapter) == ["no_context", "no_context"]


def test_internal_agent_route_injects_owned_durable_runtime(monkeypatch):
    class DurableRuntime:
        calls = 0

        async def retrieve(self, request):
            self.calls += 1
            return AuthorizedRetrievalResult(
                (
                    AuthorizedRetrievalEvidence(
                        "evidence-1",
                        "Docker port mapping is declared in Compose.",
                        ServerOwnedCitation("memo-visible", 4),
                    ),
                )
            )

    class UnavailableStore:
        dimension = 8

    durable = DurableRuntime()
    body = _body(
        ["memo-visible"], "rehydration-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
    )
    monkeypatch.setattr(
        main,
        "settings",
        _enabled_settings(agent_rehydration_enabled=True),
    )
    monkeypatch.setattr(
        main,
        "embedding_service",
        type(
            "UnavailableEmbeddingService",
            (),
            {
                "provider": DeterministicEmbeddingProvider(),
                "store": UnavailableStore(),
            },
        )(),
    )
    monkeypatch.setattr(main, "provider", DeterministicProvider())
    monkeypatch.setattr(
        main.app.state,
        "durable_rehydration_orchestrator",
        durable,
        raising=False,
    )

    response = client.post(INTERNAL_ANSWER_PATH, content=body, headers=_signed_headers(body))

    assert response.status_code == 200
    assert durable.calls == 1
    assert response.json()["citations"][0]["memo_id"] == "memo-visible"
    assert "content" not in _keys(response.json())


def test_internal_agent_route_maps_durable_failure_without_memory_fallback(monkeypatch):
    class FailingDurableRuntime:
        async def retrieve(self, request):
            raise DurableAuthorizedRetrievalUnavailableError

    body = _body(
        ["memo-visible"], "rehydration-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
    )
    monkeypatch.setattr(
        main,
        "settings",
        _enabled_settings(agent_rehydration_enabled=True),
    )
    monkeypatch.setattr(
        main.app.state,
        "durable_rehydration_orchestrator",
        FailingDurableRuntime(),
        raising=False,
    )

    response = client.post(INTERNAL_ANSWER_PATH, content=body, headers=_signed_headers(body))

    assert response.status_code == 503
    assert response.json() == {"detail": "Agent retrieval unavailable"}


def test_internal_agent_route_ignores_durable_state_when_opt_in_is_disabled(
    monkeypatch,
):
    class UnexpectedDurableRuntime:
        calls = 0

        async def retrieve(self, request):
            self.calls += 1
            raise AssertionError("disabled route must use memory retrieval")

    durable = UnexpectedDurableRuntime()
    body = _body(["memo-visible"])
    monkeypatch.setattr(main, "settings", _enabled_settings())
    monkeypatch.setattr(main, "embedding_service", _indexed_service())
    monkeypatch.setattr(main, "provider", DeterministicProvider())
    monkeypatch.setattr(
        main.app.state,
        "durable_rehydration_orchestrator",
        durable,
        raising=False,
    )

    response = client.post(INTERNAL_ANSWER_PATH, content=body, headers=_signed_headers(body))

    assert response.status_code == 200
    assert durable.calls == 0
    assert response.json()["citations"][0]["memo_id"] == "memo-visible"


def test_internal_agent_route_requires_owned_runtime_when_opt_in_is_enabled(
    monkeypatch,
):
    body = _body(
        ["memo-visible"], "rehydration-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
    )
    monkeypatch.setattr(
        main,
        "settings",
        _enabled_settings(agent_rehydration_enabled=True),
    )
    monkeypatch.delattr(
        main.app.state,
        "durable_rehydration_orchestrator",
        raising=False,
    )

    response = client.post(INTERNAL_ANSWER_PATH, content=body, headers=_signed_headers(body))

    assert response.status_code == 503
    assert response.json() == {"detail": "Agent retrieval unavailable"}


def test_internal_agent_route_projects_validated_provider_answer_only(monkeypatch):
    class GroundedProvider:
        name = "remote"

        async def generate(self, _prompt):
            return LLMResult(
                text=json.dumps(
                    {
                        "version": "grounded-answer-result-v1",
                        "answer": "Compose declares the local port mapping.",
                        "citation_refs": ["evidence-1"],
                    },
                    separators=(",", ":"),
                ),
                provider=self.name,
            )

    body = _body(["memo-visible"])
    monkeypatch.setattr(main, "settings", _enabled_settings())
    monkeypatch.setattr(main, "embedding_service", _indexed_service())
    monkeypatch.setattr(main, "provider", GroundedProvider())
    adapter = _observability(monkeypatch)

    response = client.post(INTERNAL_ANSWER_PATH, content=body, headers=_signed_headers(body))

    assert response.status_code == 200
    payload = response.json()
    assert payload["answer"] == "Compose declares the local port mapping."
    assert payload["citations"][0]["memo_id"] == "memo-visible"
    assert "citation_refs" not in _keys(payload)
    assert "version" not in _keys(payload)
    assert _recorded_metrics(adapter) == [
        ("retrieval", "search_memos", "tool_latency_ms"),
        ("provider", "provider_call", "provider_latency_ms"),
        ("agent", "answer", "request_count"),
    ]
    assert _recorded_outcomes(adapter) == ["success", "success", "success"]


def test_internal_agent_route_rejects_invalid_signature_before_execution(monkeypatch):
    body = _body(["memo-visible"])
    monkeypatch.setattr(main, "settings", _enabled_settings())
    adapter = _observability(monkeypatch)

    response = client.post(
        INTERNAL_ANSWER_PATH,
        content=body,
        headers={
            "X-DevMemo-Agent-Signature": "sha256=invalid",
            "X-DevMemo-Agent-Timestamp": str(int(time.time())),
        },
    )

    assert response.status_code == 401
    assert response.json() == {"detail": "invalid Agent delegation"}
    assert _recorded_outcomes(adapter) == ["invalid"]


def test_internal_agent_route_maps_retrieval_and_provider_failures(monkeypatch):
    body = _body(["memo-visible"])
    monkeypatch.setattr(main, "settings", _enabled_settings())
    adapter = _observability(monkeypatch)

    class UnavailableStore:
        dimension = 8

    monkeypatch.setattr(
        main,
        "embedding_service",
        type("UnavailableEmbeddingService", (), {"provider": DeterministicEmbeddingProvider(), "store": UnavailableStore()})(),
    )
    retrieval_response = client.post(
        INTERNAL_ANSWER_PATH, content=body, headers=_signed_headers(body)
    )
    assert retrieval_response.status_code == 503
    assert retrieval_response.json() == {"detail": "Agent retrieval unavailable"}

    class BrokenProvider:
        name = "remote"

        async def generate(self, _prompt):
            raise OSError("raw upstream failure")

    monkeypatch.setattr(main, "embedding_service", _indexed_service())
    monkeypatch.setattr(main, "provider", BrokenProvider())
    provider_response = client.post(
        INTERNAL_ANSWER_PATH, content=body, headers=_signed_headers(body)
    )
    assert provider_response.status_code == 502
    assert provider_response.json() == {"detail": "Agent provider unavailable"}

    class MalformedProvider:
        name = "remote"

        async def generate(self, _prompt):
            return LLMResult(text='{"raw_context":"forbidden"}', provider=self.name)

    monkeypatch.setattr(main, "provider", MalformedProvider())
    malformed_response = client.post(
        INTERNAL_ANSWER_PATH, content=body, headers=_signed_headers(body)
    )
    assert malformed_response.status_code == 502
    assert malformed_response.json() == {"detail": "Agent provider unavailable"}
    assert _recorded_outcomes(adapter) == [
        "unavailable",
        "unavailable",
        "success",
        "unavailable",
        "unavailable",
        "success",
        "success",
        "unavailable",
    ]


def test_internal_agent_route_records_invalid_input_mapping(monkeypatch):
    class InvalidAgent:
        async def run_delegated(self, *_args):
            raise RetrievalInputError

    body = _body(["memo-visible"])
    monkeypatch.setattr(main, "settings", _enabled_settings())
    monkeypatch.setattr(
        main,
        "EvidenceAnswerAgent",
        lambda *_args, **_kwargs: InvalidAgent(),
    )
    adapter = _observability(monkeypatch)

    response = client.post(INTERNAL_ANSWER_PATH, content=body, headers=_signed_headers(body))

    assert response.status_code == 400
    assert response.json() == {"detail": "invalid Agent request"}
    assert _recorded_outcomes(adapter) == ["invalid"]


def test_internal_agent_route_records_unavailable_without_changing_unknown_error(
    monkeypatch,
):
    class BrokenAgent:
        async def run_delegated(self, *_args):
            raise RuntimeError("raw synthetic failure")

    body = _body(["memo-visible"])
    monkeypatch.setattr(main, "settings", _enabled_settings())
    monkeypatch.setattr(
        main,
        "EvidenceAnswerAgent",
        lambda *_args, **_kwargs: BrokenAgent(),
    )
    adapter = _observability(monkeypatch)

    with pytest.raises(RuntimeError, match="raw synthetic failure"):
        client.post(INTERNAL_ANSWER_PATH, content=body, headers=_signed_headers(body))

    error_client = TestClient(main.app, raise_server_exceptions=False)
    response = error_client.post(
        INTERNAL_ANSWER_PATH,
        content=body,
        headers=_signed_headers(body),
    )
    error_client.close()

    assert response.status_code == 500
    assert response.content == b"Internal Server Error"
    assert _recorded_outcomes(adapter) == ["unavailable", "unavailable"]


def test_internal_agent_route_ignores_recorder_failure(monkeypatch):
    class RaisingRecorder:
        calls = 0

        def record(self, _sample):
            self.calls += 1
            raise RuntimeError("raw synthetic recorder failure")

    body = _body(["memo-visible"])
    monkeypatch.setattr(main, "settings", _enabled_settings())
    monkeypatch.setattr(main, "embedding_service", _indexed_service())
    monkeypatch.setattr(main, "provider", DeterministicProvider())
    recorder = RaisingRecorder()
    monkeypatch.setattr(
        main.app.state,
        "agent_observability",
        recorder,
        raising=False,
    )

    response = client.post(INTERNAL_ANSWER_PATH, content=body, headers=_signed_headers(body))

    assert response.status_code == 200
    assert response.json()["trace"]["terminal_state"] == "answered"
    assert recorder.calls == 4
