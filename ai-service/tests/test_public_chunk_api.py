import json
from pathlib import Path
from types import SimpleNamespace

from fastapi.testclient import TestClient

import main
from app.domain.retrieval import ChunkCitation, ChunkRetrievalResult
from app.services.webhook_security import sign_payload


client = TestClient(main.app)


def _fixture():
    path = Path(__file__).resolve().parents[2] / "contracts" / "public-chunk-v1.json"
    return json.loads(path.read_text(encoding="utf-8"))


def _coordinator(*, available=True):
    return SimpleNamespace(
        provider=SimpleNamespace(name="deterministic"),
        health=lambda: SimpleNamespace(
            available=available,
            status="ready" if available else "degraded",
            provider="qdrant",
        ),
        retrieve=lambda question, limit: ChunkRetrievalResult(
            context="private context",
            citations=(
                ChunkCitation(
                    memo_id="memo-a",
                    chunk_id="memo-chunk-v1:a:0000",
                    chunk_index=0,
                    index_version="memo-chunk-v1",
                    score=0.91,
                    metadata={"title": "Docker ports", "content": "private duplicate"},
                ),
                ChunkCitation(
                    memo_id="memo-a",
                    chunk_id="memo-chunk-v1:a:0001",
                    chunk_index=1,
                    index_version="memo-chunk-v1",
                    score=0.92,
                    metadata={"title": "Docker ports", "content": "private best chunk"},
                ),
                ChunkCitation(
                    memo_id="memo-b",
                    chunk_id="memo-chunk-v1:b:0000",
                    chunk_index=0,
                    index_version="memo-chunk-v1",
                    score=0.8,
                    metadata={"title": "Proxy setup", "content": "private second memo"},
                ),
                ChunkCitation(
                    memo_id="memo-hidden",
                    chunk_id="memo-chunk-v1:hidden:0000",
                    chunk_index=0,
                    index_version="memo-chunk-v1",
                    score=0.99,
                    metadata={"title": "Hidden", "content": "must not be returned"},
                ),
            ),
        ),
    )


def _signed_request(payload, secret="public-secret"):
    body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    return body, {
        "Content-Type": "application/json",
        "X-DevMemo-Chunk-Signature": sign_payload(body, secret),
    }


def test_public_chunk_api_is_disabled_by_default(monkeypatch):
    monkeypatch.delenv("AI_PUBLIC_CHUNK_RETRIEVAL", raising=False)
    response = client.post("/api/ai/v1/chunks/search", json=_fixture()["request"])

    assert response.status_code == 503
    assert response.json()["detail"] == "public chunk retrieval is disabled"


def test_public_chunk_api_requires_a_secret_when_enabled(monkeypatch):
    monkeypatch.setenv("AI_PUBLIC_CHUNK_RETRIEVAL", "true")
    monkeypatch.delenv("AI_PUBLIC_CHUNK_SECRET", raising=False)
    response = client.post("/api/ai/v1/chunks/search", json=_fixture()["request"])

    assert response.status_code == 503
    assert response.json()["detail"] == "public chunk retrieval is unavailable"


def test_public_chunk_api_requires_a_valid_gateway_signature(monkeypatch):
    monkeypatch.setenv("AI_PUBLIC_CHUNK_RETRIEVAL", "true")
    monkeypatch.setenv("AI_PUBLIC_CHUNK_SECRET", "public-secret")
    response = client.post("/api/ai/v1/chunks/search", json=_fixture()["request"])

    assert response.status_code == 401
    assert response.json()["detail"] == "invalid public chunk signature"


def test_public_chunk_api_returns_only_authorized_redacted_deduplicated_chunks(monkeypatch):
    monkeypatch.setenv("AI_PUBLIC_CHUNK_RETRIEVAL", "true")
    monkeypatch.setenv("AI_PUBLIC_CHUNK_SECRET", "public-secret")
    monkeypatch.setattr(main, "chunk_lifecycle_coordinator", _coordinator())
    fixture = _fixture()
    body, headers = _signed_request(fixture["request"])

    response = client.post("/api/ai/v1/chunks/search", content=body, headers=headers)

    assert response.status_code == 200
    assert response.json() == fixture["response"]
    assert "private" not in response.text
    assert "memo-hidden" not in response.text


def test_public_chunk_api_rejects_degraded_chunk_store(monkeypatch):
    monkeypatch.setenv("AI_PUBLIC_CHUNK_RETRIEVAL", "true")
    monkeypatch.setenv("AI_PUBLIC_CHUNK_SECRET", "public-secret")
    monkeypatch.setattr(main, "chunk_lifecycle_coordinator", _coordinator(available=False))
    body, headers = _signed_request(_fixture()["request"])

    response = client.post("/api/ai/v1/chunks/search", content=body, headers=headers)

    assert response.status_code == 503
    assert response.json()["detail"] == "public chunk retrieval is unavailable"


def test_public_chunk_api_rejects_ambiguous_gateway_visibility_scope(monkeypatch):
    monkeypatch.setenv("AI_PUBLIC_CHUNK_RETRIEVAL", "true")
    monkeypatch.setenv("AI_PUBLIC_CHUNK_SECRET", "public-secret")
    payload = {**_fixture()["request"], "visible_memo_ids": ["memo-a", "memo-a"]}
    body, headers = _signed_request(payload)

    response = client.post("/api/ai/v1/chunks/search", content=body, headers=headers)

    assert response.status_code == 422
    assert response.json()["detail"] == "visible_memo_ids must contain unique non-empty values"
