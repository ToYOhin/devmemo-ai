import main
from fastapi.testclient import TestClient

from app.adapters.embedding import DeterministicEmbeddingProvider
from app.adapters.vector_store import InMemoryVectorStore, VectorDimensionError
from app.services.embedding_service import EmbeddingService


client = TestClient(main.app)


def test_embed_api_returns_deterministic_contract(monkeypatch):
    service = EmbeddingService(
        DeterministicEmbeddingProvider(),
        InMemoryVectorStore(dimension=8),
    )
    monkeypatch.setattr(main, "embedding_service", service)

    response = client.post(
        "/api/ai/embed",
        json={
            "memo_id": "memo-embed-1",
            "content": "Docker port mapping",
            "metadata": {"title": "Docker", "tags": ["network"]},
        },
    )

    assert response.status_code == 200
    assert response.json()["memo_id"] == "memo-embed-1"
    assert response.json()["dimension"] == 8
    assert response.json()["provider"] == "deterministic"
    assert response.json()["embedding_id"].startswith("memo-")


def test_embed_api_rejects_empty_content():
    response = client.post(
        "/api/ai/embed",
        json={"memo_id": "memo-empty", "content": "  ", "metadata": {}},
    )

    assert response.status_code == 422
    assert response.json()["detail"] == "embedding content must not be empty"


def test_embed_api_surfaces_vector_dimension_error(monkeypatch):
    class BrokenEmbeddingService:
        def embed_memo(self, memo_id, content, metadata):
            raise VectorDimensionError("expected vector dimension 8, got 4")

    monkeypatch.setattr(main, "embedding_service", BrokenEmbeddingService())

    response = client.post(
        "/api/ai/embed",
        json={"memo_id": "memo-bad", "content": "content"},
    )

    assert response.status_code == 422
    assert response.json()["detail"] == "expected vector dimension 8, got 4"


def test_embed_api_rejects_invalid_request_shape():
    response = client.post(
        "/api/ai/embed",
        json={"memo_id": "memo-invalid", "content": "content", "metadata": []},
    )

    assert response.status_code == 422
