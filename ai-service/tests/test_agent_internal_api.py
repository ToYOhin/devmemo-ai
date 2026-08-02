import json
import time
from dataclasses import replace

from fastapi.testclient import TestClient

import main
from app.adapters.embedding import DeterministicEmbeddingProvider
from app.adapters.vector_store import InMemoryVectorStore
from app.domain.durable_authorized_retrieval import (
    AuthorizedRetrievalEvidence,
    AuthorizedRetrievalResult,
    ServerOwnedCitation,
)
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


def test_internal_agent_route_is_not_available_when_disabled(monkeypatch):
    body = _body(["memo-visible"])
    monkeypatch.setattr(main, "settings", replace(main.settings, agent_enabled=False))

    response = client.post(INTERNAL_ANSWER_PATH, content=body, headers=_signed_headers(body))

    assert response.status_code == 404
    assert response.json() == {"detail": "not found"}


def test_internal_agent_route_returns_only_safe_authorized_result(monkeypatch):
    body = _body(["memo-visible"])
    monkeypatch.setattr(main, "settings", _enabled_settings())
    monkeypatch.setattr(main, "embedding_service", _indexed_service())
    monkeypatch.setattr(main, "provider", DeterministicProvider())

    response = client.post(INTERNAL_ANSWER_PATH, content=body, headers=_signed_headers(body))

    assert response.status_code == 200
    payload = response.json()
    assert payload["citations"][0]["memo_id"] == "memo-visible"
    assert payload["trace"]["steps"][0]["name"] == "search_memos"
    assert "content" not in _keys(payload)


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

    response = client.post(INTERNAL_ANSWER_PATH, content=body, headers=_signed_headers(body))

    assert response.status_code == 200
    payload = response.json()
    assert payload["answer"] == "Compose declares the local port mapping."
    assert payload["citations"][0]["memo_id"] == "memo-visible"
    assert "citation_refs" not in _keys(payload)
    assert "version" not in _keys(payload)


def test_internal_agent_route_rejects_invalid_signature_before_execution(monkeypatch):
    body = _body(["memo-visible"])
    monkeypatch.setattr(main, "settings", _enabled_settings())

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


def test_internal_agent_route_maps_retrieval_and_provider_failures(monkeypatch):
    body = _body(["memo-visible"])
    monkeypatch.setattr(main, "settings", _enabled_settings())

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
