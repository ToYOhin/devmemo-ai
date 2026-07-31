import json
import time
from dataclasses import replace

from fastapi.testclient import TestClient

import main
from app.adapters.embedding import DeterministicEmbeddingProvider
from app.adapters.vector_store import InMemoryVectorStore
from app.services.agent_delegation import INTERNAL_ANSWER_PATH, sign_delegated_request
from app.services.embedding_service import EmbeddingService
from app.services.memo_indexing import MemoIndexDocument, index_memo
from llm import DeterministicProvider


client = TestClient(main.app)
_SECRET = "agent-route-test-secret"


def _enabled_settings():
    return replace(main.settings, agent_enabled=True, agent_internal_secret=_SECRET)


def _body(visible_memo_uids: list[str]) -> bytes:
    return json.dumps(
        {
            "question": "Docker ports",
            "limit": 3,
            "visible_memo_uids": visible_memo_uids,
        },
        separators=(",", ":"),
    ).encode("utf-8")


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
