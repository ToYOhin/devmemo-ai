from __future__ import annotations

from dataclasses import dataclass, replace
import json
import time

from fastapi.testclient import TestClient

import main
from app.adapters.embedding import DeterministicEmbeddingProvider
from app.adapters.vector_store import InMemoryVectorStore
from app.domain.agent_provider import AgentProviderConfig
from app.services.agent_delegation import INTERNAL_ANSWER_PATH, sign_delegated_request
from app.services.embedding_service import EmbeddingService
from app.services.memo_indexing import MemoIndexDocument, index_memo
from app.services.agent_provider_api import (
    INTERNAL_AGENT_PROVIDER_PATH,
    INTERNAL_AGENT_PROVIDER_TEST_PATH,
)
from app.services.agent_provider_registry import AgentProviderRegistry


SECRET = "synthetic-internal-provider-secret"
client = TestClient(main.app)


@dataclass(frozen=True)
class _Result:
    text: str


class _SyntheticProvider:
    name = "openai"

    async def generate(self, prompt: str) -> _Result:
        assert "synthetic connection test" in prompt
        assert "Memo" not in prompt
        return _Result('{"version":"agent-provider-test-v1","status":"ok"}')


class _GroundedProvider:
    name = "openai"

    async def generate(self, _prompt: str) -> _Result:
        return _Result(
            '{"version":"grounded-answer-result-v1","answer":"Dynamic answer [1].","citation_refs":["evidence-1"]}'
        )


def _headers(method: str, path: str, body: bytes) -> dict[str, str]:
    signed = sign_delegated_request(method, path, body, int(time.time()), SECRET)
    return {
        "X-DevMemo-Agent-Signature": signed.signature,
        "X-DevMemo-Agent-Timestamp": signed.timestamp,
        "Content-Type": "application/json",
    }


def _enable(monkeypatch, tmp_path, provider_factory=None) -> AgentProviderRegistry:
    registry = AgentProviderRegistry(
        tmp_path / "agent.db",
        SECRET,
        provider_factory=provider_factory or (lambda _config: _SyntheticProvider()),
    )
    monkeypatch.setattr(
        main,
        "settings",
        replace(main.settings, agent_enabled=True, agent_internal_secret=SECRET),
    )
    monkeypatch.setattr(main, "agent_provider_registry", registry)
    return registry


def test_signed_internal_provider_update_and_masked_read(monkeypatch, tmp_path):
    _enable(monkeypatch, tmp_path)
    body = json.dumps(
        {
            "version": "agent-provider-config-v1",
            "provider": "openai",
            "model": "gpt-4o-mini",
            "base_url": "https://api.openai.com/v1",
            "api_key": "synthetic-internal-key",
            "enabled": True,
            "allow_real_memo_data": True,
        },
        separators=(",", ":"),
    ).encode()

    updated = client.put(
        INTERNAL_AGENT_PROVIDER_PATH,
        content=body,
        headers=_headers("PUT", INTERNAL_AGENT_PROVIDER_PATH, body),
    )
    read = client.get(
        INTERNAL_AGENT_PROVIDER_PATH,
        headers=_headers("GET", INTERNAL_AGENT_PROVIDER_PATH, b""),
    )

    assert updated.status_code == 200
    assert read.status_code == 200
    assert "api_key" not in read.json()
    assert read.json()["api_key_set"] is True
    assert read.json()["api_key_hint"] == "••••-key"
    assert "synthetic-internal-key" not in read.text


def test_blank_key_is_preserved_when_existing_provider_is_disabled(monkeypatch, tmp_path):
    registry = _enable(monkeypatch, tmp_path)
    registry.update(
        AgentProviderConfig(
            provider="openai",
            model="gpt-4o-mini",
            base_url="https://api.openai.com/v1",
            api_key="synthetic-internal-key",
            enabled=True,
            allow_real_memo_data=True,
        ),
        preserve_api_key=False,
    )
    body = json.dumps(
        {
            "version": "agent-provider-config-v1",
            "provider": "openai",
            "model": "gpt-4o-mini",
            "base_url": "https://api.openai.com/v1",
            "enabled": False,
            "allow_real_memo_data": False,
        },
        separators=(",", ":"),
    ).encode()

    response = client.put(
        INTERNAL_AGENT_PROVIDER_PATH,
        content=body,
        headers=_headers("PUT", INTERNAL_AGENT_PROVIDER_PATH, body),
    )

    assert response.status_code == 200
    assert response.json()["enabled"] is False
    assert response.json()["api_key_set"] is True
    assert response.json()["api_key_hint"] == "••••-key"


def test_internal_provider_test_is_signed_and_synthetic(monkeypatch, tmp_path):
    registry = _enable(monkeypatch, tmp_path)
    registry.update(
        AgentProviderConfig(
            provider="openai",
            model="gpt-4o-mini",
            base_url="https://api.openai.com/v1",
            api_key="synthetic-internal-key",
            enabled=True,
            allow_real_memo_data=False,
        ),
        preserve_api_key=False,
    )
    body = b'{"version":"agent-provider-config-v1"}'

    response = client.post(
        INTERNAL_AGENT_PROVIDER_TEST_PATH,
        content=body,
        headers=_headers("POST", INTERNAL_AGENT_PROVIDER_TEST_PATH, body),
    )

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.json()["provider"] == "openai"


def test_internal_provider_route_rejects_invalid_signature(monkeypatch, tmp_path):
    _enable(monkeypatch, tmp_path)
    response = client.get(
        INTERNAL_AGENT_PROVIDER_PATH,
        headers={
            "X-DevMemo-Agent-Signature": "sha256=invalid",
            "X-DevMemo-Agent-Timestamp": str(int(time.time())),
        },
    )
    assert response.status_code == 401


def test_internal_provider_update_rejects_oversized_body(monkeypatch, tmp_path):
    _enable(monkeypatch, tmp_path)
    body = b"x" * ((16 << 10) + 1)

    response = client.put(
        INTERNAL_AGENT_PROVIDER_PATH,
        content=body,
        headers=_headers("PUT", INTERNAL_AGENT_PROVIDER_PATH, body),
    )

    assert response.status_code == 400


def test_evidence_answer_resolves_saved_provider_at_request_time(monkeypatch, tmp_path):
    registry = _enable(monkeypatch, tmp_path, lambda _config: _GroundedProvider())
    registry.update(
        AgentProviderConfig(
            provider="openai",
            model="gpt-4o-mini",
            base_url="https://api.openai.com/v1",
            api_key="synthetic-internal-key",
            enabled=True,
            allow_real_memo_data=True,
        ),
        preserve_api_key=False,
    )
    embedding_service = EmbeddingService(DeterministicEmbeddingProvider(), InMemoryVectorStore(8))
    index_memo(
        embedding_service,
        MemoIndexDocument.from_memo(
            "memo-visible",
            "Docker port mapping is declared in Compose.",
            {"title": "Docker ports", "tags": ["docker"]},
        ),
    )
    monkeypatch.setattr(main, "embedding_service", embedding_service)
    body = json.dumps(
        {
            "question": "Docker ports",
            "limit": 3,
            "visible_memo_uids": ["memo-visible"],
        },
        separators=(",", ":"),
    ).encode()

    response = client.post(
        INTERNAL_ANSWER_PATH,
        content=body,
        headers=_headers("POST", INTERNAL_ANSWER_PATH, body),
    )

    assert response.status_code == 200
    assert response.json()["answer"] == "Dynamic answer [1]."
    assert response.json()["provider"] == "openai"
