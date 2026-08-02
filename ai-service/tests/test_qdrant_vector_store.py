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
    class MatchAny:
        any: list[str]

    @dataclass
    class MatchValue:
        value: str

    @dataclass
    class FieldCondition:
        key: str
        match: object

    @dataclass
    class Filter:
        must: list[object]

    @dataclass
    class FilterSelector:
        filter: object


@dataclass
class FakeScoredPoint:
    id: str
    score: float
    payload: dict[str, object]


class FakeQdrantClient:
    def __init__(self):
        self.collections: dict[str, object] = {}
        self.points: dict[str, FakeModels.PointStruct] = {}
        self.last_query_filter: object | None = None

    def collection_exists(self, collection_name):
        return collection_name in self.collections

    def create_collection(self, collection_name, vectors_config):
        self.collections[collection_name] = vectors_config

    def upsert(self, collection_name, points, wait):
        assert collection_name in self.collections
        for point in points:
            self.points[point.id] = point

    def query_points(
        self, collection_name, query, limit, with_payload, query_filter=None
    ):
        assert collection_name in self.collections
        assert with_payload is True
        self.last_query_filter = query_filter
        visible_ids = None
        required_metadata: dict[str, str] = {}
        if query_filter is not None:
            visible_ids = set(query_filter.must[0].match.any)
            for condition in query_filter.must[1:]:
                required_metadata[condition.key.removeprefix("metadata.")] = (
                    condition.match.value
                )
        return SimpleNamespace(
            points=[
                FakeScoredPoint(point.id, 0.91, point.payload)
                for point in self.points.values()
                if visible_ids is None or point.payload["memo_id"] in visible_ids
                if all(
                    point.payload.get("metadata", {}).get(key) == value
                    for key, value in required_metadata.items()
                )
            ]
            [:limit]
        )

    def delete(self, collection_name, points_selector, wait):
        assert collection_name in self.collections
        if isinstance(points_selector, FakeModels.PointIdsList):
            for point_id in points_selector.points:
                self.points.pop(point_id, None)
            return
        conditions = points_selector.filter.must
        for point_id, point in list(self.points.items()):
            if all(self._matches(point, condition) for condition in conditions):
                self.points.pop(point_id)

    def scroll(
        self,
        collection_name,
        scroll_filter,
        limit,
        offset,
        with_payload,
        with_vectors,
    ):
        assert collection_name in self.collections
        assert offset is None
        assert with_payload is True
        assert with_vectors is False
        points = [
            FakeScoredPoint(point.id, 0.0, point.payload)
            for point in self.points.values()
            if all(self._matches(point, condition) for condition in scroll_filter.must)
        ]
        return points[:limit], None

    @staticmethod
    def _matches(point, condition):
        key = condition.key
        if key == "memo_id":
            value = point.payload["memo_id"]
        else:
            value = point.payload.get("metadata", {}).get(
                key.removeprefix("metadata.")
            )
        match = condition.match
        return value in match.any if hasattr(match, "any") else value == match.value

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


def test_qdrant_adapter_pushes_authorized_memo_scope_into_query():
    client = FakeQdrantClient()
    store = QdrantVectorStore(client, FakeModels, 2, "devmemo-test")
    store.upsert(VectorRecord("embedding-a", "memo-a", (1.0, 0.0), {}))
    store.upsert(VectorRecord("embedding-b", "memo-b", (1.0, 0.0), {}))

    results = store.search_visible_memos(
        (1.0, 0.0), frozenset({"memo-b"}), limit=1
    )

    assert [result.memo_id for result in results] == ["memo-b"]
    assert client.last_query_filter.must[0].key == "memo_id"
    assert client.last_query_filter.must[0].match.any == ["memo-b"]


def test_qdrant_adapter_pushes_active_generation_into_query():
    client = FakeQdrantClient()
    store = QdrantVectorStore(client, FakeModels, 2, "devmemo-test")
    store.upsert(
        VectorRecord(
            "embedding-old",
            "memo-a",
            (1.0, 0.0),
            {"rebuild_generation": "old", "index_version": "memo-v1"},
        )
    )
    store.upsert(
        VectorRecord(
            "embedding-active",
            "memo-a",
            (1.0, 0.0),
            {"rebuild_generation": "active", "index_version": "memo-v1"},
        )
    )

    results = store.search_visible_memos(
        (1.0, 0.0),
        frozenset({"memo-a"}),
        rebuild_generation="active",
        index_version="memo-v1",
    )

    assert [result.embedding_id for result in results] == ["embedding-active"]
    assert [condition.key for condition in client.last_query_filter.must] == [
        "memo_id",
        "metadata.rebuild_generation",
        "metadata.index_version",
    ]


def test_qdrant_adapter_lists_generation_and_deletes_all_memo_versions():
    client = FakeQdrantClient()
    store = QdrantVectorStore(client, FakeModels, 2, "devmemo-test")
    for embedding_id, memo_id, generation in (
        ("memo-a-old", "memo-a", "old"),
        ("memo-a-next", "memo-a", "next"),
        ("memo-b-next", "memo-b", "next"),
    ):
        store.upsert(
            VectorRecord(
                embedding_id,
                memo_id,
                (1.0, 0.0),
                {
                    "source_sequence": 1,
                    "document_hash": "a" * 64,
                    "rebuild_generation": generation,
                    "index_version": "memo-v1",
                },
            )
        )

    records = store.list_lifecycle_records("next", "memo-v1")
    store.delete_memo_versions("memo-a", "memo-v1")

    assert sorted(record.memo_id for record in records) == ["memo-a", "memo-b"]
    assert sorted(point.payload["memo_id"] for point in client.points.values()) == [
        "memo-b"
    ]


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
