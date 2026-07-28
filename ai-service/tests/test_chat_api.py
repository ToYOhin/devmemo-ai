from types import SimpleNamespace

from fastapi.testclient import TestClient

import main
from app.adapters.embedding import DeterministicEmbeddingProvider
from app.adapters.vector_store import InMemoryVectorStore
from app.services.embedding_service import EmbeddingService
from llm import DeterministicProvider, LLMResult


client = TestClient(main.app)


def _configured_service() -> EmbeddingService:
    return EmbeddingService(DeterministicEmbeddingProvider(), InMemoryVectorStore(8))


def test_chat_api_retrieves_memo_and_returns_citations(monkeypatch):
    service = _configured_service()
    monkeypatch.setattr(main, "embedding_service", service)
    monkeypatch.setattr(main, "provider", DeterministicProvider())

    indexed = client.post(
        "/api/ai/embed",
        json={
            "memo_id": "memo-chat-1",
            "content": "Docker port mapping fixed in docker-compose.",
            "metadata": {"title": "Docker port issue", "tags": ["docker"]},
        },
    )
    response = client.post("/api/ai/chat", json={"question": "Docker port mapping", "limit": 3})

    assert indexed.status_code == 200
    assert response.status_code == 200
    payload = response.json()
    assert payload["provider"] == "deterministic"
    assert payload["retrieved_count"] == 1
    assert payload["citations"][0]["memo_id"] == "memo-chat-1"
    assert payload["citations"][0]["metadata"]["title"] == "Docker port issue"
    assert "content" not in payload["citations"][0]["metadata"]
    assert "docker-compose" in payload["answer"]
    assert "[1]" in payload["answer"]


def test_chat_api_returns_explicit_empty_knowledge_base_answer(monkeypatch):
    monkeypatch.setattr(main, "embedding_service", _configured_service())
    monkeypatch.setattr(main, "provider", DeterministicProvider())

    response = client.post("/api/ai/chat", json={"question": "Unknown topic"})

    assert response.status_code == 200
    assert response.json() == {
        "answer": "知识库中没有找到相关 Memo。",
        "citations": [],
        "provider": "deterministic",
        "retrieved_count": 0,
    }


def test_chat_api_rejects_invalid_limit():
    response = client.post("/api/ai/chat", json={"question": "Docker", "limit": 11})

    assert response.status_code == 422


def test_chat_api_reports_retrieval_failure(monkeypatch):
    class BrokenStore:
        dimension = 8

        def search(self, query, limit=5):
            raise OSError("offline")

    monkeypatch.setattr(
        main,
        "embedding_service",
        SimpleNamespace(provider=DeterministicEmbeddingProvider(), store=BrokenStore()),
    )

    response = client.post("/api/ai/chat", json={"question": "Docker"})

    assert response.status_code == 503
    assert response.json()["detail"] == "knowledge-base retrieval unavailable"


def test_chat_api_reports_llm_failure(monkeypatch):
    service = _configured_service()
    service.embed_memo("memo-llm-failure", "Docker port mapping", {"title": "Docker"})

    class BrokenProvider:
        name = "openai"

        async def generate(self, prompt):
            raise OSError("provider offline")

    monkeypatch.setattr(main, "embedding_service", service)
    monkeypatch.setattr(main, "provider", BrokenProvider())

    response = client.post("/api/ai/chat", json={"question": "Docker"})

    assert response.status_code == 502
    assert response.json()["detail"] == "LLM provider failed"


def test_chat_api_returns_non_deterministic_llm_text(monkeypatch):
    service = _configured_service()
    service.embed_memo("memo-llm", "FastAPI deployment solution", {"title": "FastAPI"})

    class FakeProvider:
        name = "ollama"

        async def generate(self, prompt):
            assert "FastAPI" in prompt
            return LLMResult(text="答案 [1]：请参考 FastAPI Memo。", provider=self.name)

    monkeypatch.setattr(main, "embedding_service", service)
    monkeypatch.setattr(main, "provider", FakeProvider())

    response = client.post("/api/ai/chat", json={"question": "FastAPI deployment"})

    assert response.status_code == 200
    assert response.json()["answer"] == "答案 [1]：请参考 FastAPI Memo。"
    assert response.json()["provider"] == "ollama"
