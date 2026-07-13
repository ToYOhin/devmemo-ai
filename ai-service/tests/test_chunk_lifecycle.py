import sqlite3

from fastapi.testclient import TestClient

import main
from app.adapters.chunk_state import (
    InMemoryChunkIndexStateStore,
    SqliteChunkIndexStateStore,
)
from app.adapters.embedding import DeterministicEmbeddingProvider
from app.adapters.vector_store import InMemoryVectorStore
from app.domain.embeddings import VectorRecord
from app.domain.memo_chunking import chunk_memo
from app.services.chunk_lifecycle import ChunkLifecycleCoordinator


def _coordinator(state_store=None):
    provider = DeterministicEmbeddingProvider()
    store = InMemoryVectorStore(provider.dimension)
    return (
        ChunkLifecycleCoordinator(
            provider=provider,
            store=store,
            state_store=state_store or InMemoryChunkIndexStateStore(),
        ),
        store,
    )


def test_composed_chunk_store_isolated_from_complete_memo_store():
    assert main.chunk_lifecycle_coordinator.store is not main.embedding_service.store


def test_chunk_lifecycle_updates_and_removes_stale_tail_chunks():
    coordinator, store = _coordinator()

    first = coordinator.upsert_memo("memo-lifecycle", "abcdefghij", max_chars=5)
    assert first.chunk_count == 2
    assert store.health().point_count == 2

    second = coordinator.upsert_memo("memo-lifecycle", "abcde", max_chars=5)
    assert second.chunk_count == 1
    assert second.deleted_count == 1
    assert store.health().point_count == 1
    assert len(coordinator.state_store.get("memo-lifecycle").chunk_ids) == 1


def test_chunk_lifecycle_delete_and_empty_update_remove_registered_chunks():
    coordinator, store = _coordinator()

    coordinator.upsert_memo("memo-delete", "abcdefghij", max_chars=5)
    emptied = coordinator.upsert_memo("memo-delete", "", max_chars=5)

    assert emptied.chunk_count == 0
    assert emptied.deleted_count == 2
    assert store.health().point_count == 0
    assert coordinator.state_store.get("memo-delete") is None

    coordinator.upsert_memo("memo-delete", "abcdefghij", max_chars=5)
    deleted = coordinator.delete_memo("memo-delete")
    assert deleted.deleted_count == 2
    assert store.health().point_count == 0
    assert coordinator.state_store.get("memo-delete") is None


def test_chunk_lifecycle_does_not_delete_a_different_index_version():
    state_store = InMemoryChunkIndexStateStore()
    coordinator, store = _coordinator(state_store)
    provider = DeterministicEmbeddingProvider()
    legacy_chunk = chunk_memo(
        "memo-versioned", "legacy", max_chars=20, index_version="memo-chunk-v0"
    )[0]
    vector = provider.embed(legacy_chunk.content)
    store.upsert(
        VectorRecord(
            embedding_id=legacy_chunk.chunk_id,
            memo_id=legacy_chunk.memo_id,
            vector=vector.values,
            metadata=dict(legacy_chunk.metadata),
        )
    )
    state_store.save("memo-versioned", "memo-chunk-v0", (legacy_chunk.chunk_id,))

    result = coordinator.upsert_memo("memo-versioned", "current", max_chars=20)

    assert result.deleted_count == 0
    assert store.health().point_count == 2
    assert state_store.get("memo-versioned").index_version == "memo-chunk-v1"


def test_sqlite_chunk_state_survives_a_new_adapter(monkeypatch, tmp_path):
    database = tmp_path / "chunk-state.db"
    monkeypatch.setenv("AI_NOTES_DB", str(database))

    first = SqliteChunkIndexStateStore()
    first.save("memo-persisted", "memo-chunk-v1", ("chunk-1", "chunk-2"))

    second = SqliteChunkIndexStateStore()
    state = second.get("memo-persisted")
    assert state is not None
    assert state.index_version == "memo-chunk-v1"
    assert state.chunk_ids == ("chunk-1", "chunk-2")
    stats = second.stats()
    assert stats.status == "ready"
    assert stats.tracked_memos == 1
    assert stats.tracked_chunks == 2

    with sqlite3.connect(database) as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM memo_chunk_index_state"
        ).fetchone()[0] == 1


def test_chunk_webhook_is_explicit_and_idempotent(monkeypatch, tmp_path):
    database = tmp_path / "chunk-webhook.db"
    monkeypatch.setenv("AI_NOTES_DB", str(database))
    monkeypatch.setenv("AI_INDEX_ON_WEBHOOK", "true")
    monkeypatch.setenv("AI_INDEX_MODE", "chunk")
    coordinator, store = _coordinator(SqliteChunkIndexStateStore())
    monkeypatch.setattr(main, "chunk_lifecycle_coordinator", coordinator)
    client = TestClient(main.app)

    first = client.post(
        "/api/integrations/memos/webhook",
        json={
            "activityType": "memos.memo.created",
            "eventId": "chunk-event-create",
            "memo": {"uid": "memo-webhook-chunk", "content": "abcdefghij"},
        },
    )
    assert first.json()["index_status"] == "indexed"
    assert first.json()["index_mode"] == "chunk"
    assert first.json()["chunk_count"] == 1

    duplicate = client.post(
        "/api/integrations/memos/webhook",
        json={
            "activityType": "memos.memo.created",
            "eventId": "chunk-event-create",
            "memo": {"uid": "memo-webhook-chunk", "content": "changed"},
        },
    )
    assert duplicate.json()["message"] == "duplicate webhook ignored"
    assert store.health().point_count == 1

    updated = client.post(
        "/api/integrations/memos/webhook",
        json={
            "activityType": "memos.memo.updated",
            "eventId": "chunk-event-update",
            "memo": {"uid": "memo-webhook-chunk", "content": "new"},
        },
    )
    assert updated.json()["index_status"] == "indexed"
    assert updated.json()["deleted_chunk_count"] == 0
    assert store.health().point_count == 1

    deleted = client.post(
        "/api/integrations/memos/webhook",
        json={
            "activityType": "memos.memo.deleted",
            "eventId": "chunk-event-delete",
            "memo": {"uid": "memo-webhook-chunk"},
        },
    )
    assert deleted.json()["index_status"] == "deleted"
    assert deleted.json()["deleted_chunk_count"] == 1
    assert store.health().point_count == 0


def test_chunk_webhook_failure_keeps_code_zero(monkeypatch, tmp_path):
    monkeypatch.setenv("AI_NOTES_DB", str(tmp_path / "chunk-failure.db"))
    monkeypatch.setenv("AI_INDEX_ON_WEBHOOK", "true")
    monkeypatch.setenv("AI_INDEX_MODE", "chunk")

    class BrokenCoordinator:
        def upsert_memo(self, *args, **kwargs):
            raise RuntimeError("chunk store unavailable")

    monkeypatch.setattr(main, "chunk_lifecycle_coordinator", BrokenCoordinator())
    client = TestClient(main.app)

    response = client.post(
        "/api/integrations/memos/webhook",
        json={
            "activityType": "memos.memo.created",
            "eventId": "chunk-event-failure",
            "memo": {"uid": "memo-chunk-failure", "content": "content"},
        },
    )

    assert response.status_code == 200
    assert response.json()["code"] == 0
    assert response.json()["index_status"] == "failed"


def test_chunk_health_reports_store_and_state_counts():
    coordinator, store = _coordinator()

    before = coordinator.health()
    assert before.index_mode == "chunk"
    assert before.index_version == "memo-chunk-v1"
    assert before.status == "ready"
    assert before.point_count == 0
    assert before.tracked_memos == 0
    assert before.tracked_chunks == 0

    coordinator.upsert_memo("memo-health", "abcdefghij", max_chars=5)
    after = coordinator.health()
    assert after.point_count == store.health().point_count == 2
    assert after.tracked_memos == 1
    assert after.tracked_chunks == 2
    assert after.state_backend == "memory"

    coordinator.upsert_memo("memo-health", "abcde", max_chars=5)
    updated = coordinator.health()
    assert updated.point_count == 1
    assert updated.tracked_memos == 1
    assert updated.tracked_chunks == 1

    coordinator.delete_memo("memo-health")
    deleted = coordinator.health()
    assert deleted.point_count == 0
    assert deleted.tracked_memos == 0
    assert deleted.tracked_chunks == 0


def test_chunk_health_api_has_explicit_mode_and_version(monkeypatch, tmp_path):
    monkeypatch.setenv("AI_NOTES_DB", str(tmp_path / "chunk-health.db"))
    coordinator, _ = _coordinator(SqliteChunkIndexStateStore())
    coordinator.upsert_memo("memo-health-api", "chunk content")
    monkeypatch.setattr(main, "chunk_lifecycle_coordinator", coordinator)

    response = TestClient(main.app).get("/api/ai/index/chunk-health")

    assert response.status_code == 200
    assert response.json() == {
        "index_mode": "chunk",
        "index_version": "memo-chunk-v1",
        "provider": "memory",
        "available": True,
        "status": "ready",
        "dimension": 8,
        "point_count": 1,
        "tracked_memos": 1,
        "tracked_chunks": 1,
        "state_backend": "sqlite",
        "detail": None,
    }
