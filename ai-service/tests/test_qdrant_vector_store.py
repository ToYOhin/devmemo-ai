import sys
from dataclasses import dataclass
from types import SimpleNamespace

import pytest

from app.adapters.qdrant_vector_store import (
    QdrantAdapterError,
    QdrantUnavailableError,
    QdrantVectorStore,
)
from app.domain.embeddings import VectorDimensionError, VectorRecord


class FakeModels:
    Distance = SimpleNamespace(COSINE="Cosine")

    @dataclass
    class VectorParams:
        size: int
        distance: str

    @dataclass
    class PointStruct:
        id: str
        vector: list[float]
        payload: dict[str, object]

    @dataclass
    class PointIdsList:
        points: list[str]


@dataclass
class FakeScoredPoint:
    id: str
    score: float
    payload: dict[str, object]


class FakeQdrantClient:
    def __init__(self):
        self.collections: dict[str, object] = {}
        self.points: dict[str, FakeModels.PointStruct] = {}

    def collection_exists(self, collection_name):
        return collection_name in self.collections

    def create_collection(self, collection_name, vectors_config):
        self.collections[collection_name] = vectors_config

    def upsert(self, collection_name, points, wait):
        assert collection_name in self.collections
        for point in points:
            self.points[point.id] = point

    def query_points(self, collection_name, query, limit, with_payload):
        assert collection_name in self.collections
        assert with_payload is True
        return SimpleNamespace(
            points=[
                FakeScoredPoint(point.id, 0.91, point.payload)
                for point in list(self.points.values())[:limit]
            ]
        )

    def delete(self, collection_name, points_selector, wait):
        assert collection_name in self.collections
        for point_id in points_selector.points:
            self.points.pop(point_id, None)

    def get_collection(self, collection_name):
        assert collection_name in self.collections
        return SimpleNamespace(status="green", points_count=len(self.points))


def test_qdrant_adapter_maps_upsert_search_and_delete_without_network():
    client = FakeQdrantClient()
    store = QdrantVectorStore(client, FakeModels, 2, "devmemo-test")

    store.upsert(VectorRecord("embedding-a", "memo-a", (1.0, 0.0), {"title": "Docker"}))
    results = store.search((1.0, 0.0))

    assert results[0].embedding_id == "embedding-a"
    assert results[0].memo_id == "memo-a"
    assert results[0].score == 0.91
    assert results[0].metadata == {"title": "Docker"}
    assert store.delete("embedding-a") is True
    assert store.search((1.0, 0.0)) == []


def test_qdrant_adapter_creates_the_configured_collection_with_cosine_dimension():
    client = FakeQdrantClient()

    QdrantVectorStore(client, FakeModels, 3, "devmemo_memo_chunks")

    collection = client.collections["devmemo_memo_chunks"]
    assert collection.size == 3
    assert collection.distance == FakeModels.Distance.COSINE


def test_qdrant_adapter_rejects_dimension_mismatch_at_boundary():
    store = QdrantVectorStore(FakeQdrantClient(), FakeModels, 2, "devmemo-test")

    with pytest.raises(VectorDimensionError, match="expected vector dimension 2"):
        store.upsert(VectorRecord("bad", "memo", (1.0,), {}))


def test_qdrant_adapter_rejects_empty_collection_name():
    with pytest.raises(ValueError, match="collection name"):
        QdrantVectorStore(FakeQdrantClient(), FakeModels, 2, " ")


def test_qdrant_adapter_health_reports_collection_status():
    store = QdrantVectorStore(FakeQdrantClient(), FakeModels, 2, "devmemo-test")
    store.upsert(VectorRecord("embedding-a", "memo-a", (1.0, 0.0), {}))

    health = store.health()

    assert health.provider == "qdrant"
    assert health.available is True
    assert health.status == "green"
    assert health.collection == "devmemo-test"
    assert health.point_count == 1


def test_qdrant_adapter_health_degrades_without_network():
    class BrokenHealthClient(FakeQdrantClient):
        def get_collection(self, collection_name):
            raise ConnectionError("qdrant offline")

    store = QdrantVectorStore(BrokenHealthClient(), FakeModels, 2, "devmemo-test")

    health = store.health()

    assert health.available is False
    assert health.status == "unavailable"
    assert "Qdrant health check failed" in (health.detail or "")


def test_qdrant_adapter_reports_missing_optional_dependency(monkeypatch):
    monkeypatch.setitem(sys.modules, "qdrant_client", None)

    with pytest.raises(QdrantUnavailableError, match="qdrant-client"):
        QdrantVectorStore.from_url("http://localhost:6333", 8, "devmemo")


def test_qdrant_adapter_wraps_collection_initialization_failure():
    class BrokenClient(FakeQdrantClient):
        def collection_exists(self, collection_name):
            raise ConnectionError("offline")

    with pytest.raises(QdrantAdapterError, match="failed to initialize"):
        QdrantVectorStore(BrokenClient(), FakeModels, 2, "devmemo-test")
