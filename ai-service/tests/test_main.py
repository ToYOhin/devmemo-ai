import sqlite3
from types import SimpleNamespace

from fastapi.testclient import TestClient

import main
from app.adapters.embedding import DeterministicEmbeddingProvider
from app.adapters.vector_store import InMemoryVectorStore
from app.domain.embeddings import VectorStoreHealth
from app.services.embedding_service import EmbeddingService
from database import save_chunk_index_state
from main import SummaryRequest, app, parse_llm_json


client = TestClient(app)


def test_llm_json_parser_accepts_markdown_fences():
    parsed = parse_llm_json(
        '```json{"summary":"A summary","keywords":["Docker"],'
        '"category":"DevOps","suggested_tags":["container"]}```',
        SummaryRequest(content="Docker deployment"),
    )

    assert parsed == ("A summary", ["Docker"], "DevOps", ["container"])


def test_health_reports_service_status():
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "devmemo-ai",
        "provider": "deterministic",
    }


def test_index_health_reports_memory_without_qdrant():
    response = client.get("/api/ai/index/health")

    assert response.status_code == 200
    assert response.json() == {
        "provider": "memory",
        "available": True,
        "dimension": 8,
        "status": "ready",
        "collection": None,
        "point_count": 0,
        "detail": None,
    }


def test_index_health_exposes_degraded_qdrant_status(monkeypatch):
    class DegradedStore:
        def health(self):
            return VectorStoreHealth(
                provider="qdrant",
                available=False,
                dimension=8,
                status="unavailable",
                collection="devmemo-test",
                detail="Qdrant health check failed: offline",
            )

    monkeypatch.setattr(main, "embedding_service", SimpleNamespace(store=DegradedStore()))

    response = client.get("/api/ai/index/health")

    assert response.status_code == 200
    assert response.json()["provider"] == "qdrant"
    assert response.json()["available"] is False
    assert response.json()["status"] == "unavailable"


def test_summary_accepts_a_memo(monkeypatch, tmp_path):
    database = tmp_path / "ai_notes.db"
    monkeypatch.setenv("AI_NOTES_DB", str(database))
    response = client.post(
        "/api/ai/summarize",
        json={
            "memo_id": 7,
            "title": "Docker port issue",
            "content": "FastAPI deployment failed because the Docker port mapping was wrong.",
            "tags": ["FastAPI", "Docker"],
        },
    )

    assert response.status_code == 200
    assert response.json()["memo_id"] == 7
    assert response.json()["summary"] == "Docker 容器端口映射问题分析"
    assert response.json()["category"] == "DevOps"
    assert response.json()["provider"] == "deterministic"
    assert response.json()["ai_note_id"] == 1

    with sqlite3.connect(database) as connection:
        row = connection.execute(
            "SELECT memo_id, summary, category FROM ai_notes WHERE id = 1"
        ).fetchone()
    assert row == ("7", "Docker 容器端口映射问题分析", "DevOps")


def test_summary_persists_structured_template_for_detail_page(monkeypatch, tmp_path):
    monkeypatch.setenv("AI_NOTES_DB", str(tmp_path / "summary-template.db"))
    response = client.post(
        "/api/ai/summarize",
        json={
            "memo_id": "memo-summary-code",
            "title": "Port check",
            "content": "---\ntype: code\nlanguage: Python\n---\n```python\nprint(8080)\n```",
        },
    )

    assert response.status_code == 200
    assert response.json()["memo_type"] == "code"
    assert response.json()["template_id"] == 1

    template = client.get("/api/ai/templates/memo-summary-code")
    assert template.status_code == 200
    assert template.json()["payload"]["language"] == "Python"
    assert template.json()["payload"]["code"] == "print(8080)"


def test_summary_creates_pending_insights_and_status_is_versioned(monkeypatch, tmp_path):
    monkeypatch.setenv("AI_NOTES_DB", str(tmp_path / "summary-insights.db"))
    content = "---\ntype: bug\ntitle: Port failure\n---\nError: refused\nRoot cause: wrong port\nSolution: fix mapping"
    response = client.post(
        "/api/ai/summarize",
        json={"memo_id": "memo-insight-api", "content": content},
    )

    assert response.status_code == 200
    insights = client.get("/api/ai/insights/memo-insight-api")
    assert insights.status_code == 200
    assert [item["insight_type"] for item in insights.json()] == ["action", "bug"]

    action = insights.json()[0]
    updated = client.post(
        f"/api/ai/insights/{action['insight_id']}/status",
        json={"status": "accepted", "version": action["version"]},
    )
    assert updated.status_code == 200
    assert updated.json()["status"] == "accepted"
    stale = client.post(
        f"/api/ai/insights/{action['insight_id']}/status",
        json={"status": "rejected", "version": action["version"]},
    )
    assert stale.status_code == 409


def test_insight_preview_does_not_persist(monkeypatch, tmp_path):
    database = tmp_path / "preview.db"
    monkeypatch.setenv("AI_NOTES_DB", str(database))
    response = client.post(
        "/api/ai/insights/preview",
        json={
            "memo_id": "memo-preview",
            "title": "Preview",
            "content": "---\ntype: code\nlanguage: Python\n---\n```python\nprint(1)\n```",
        },
    )

    assert response.status_code == 200
    assert response.json()[0]["insight_type"] == "fact"
    assert not database.exists()


def test_ai_note_read_returns_persisted_summary(monkeypatch, tmp_path):
    database = tmp_path / "read.db"
    monkeypatch.setenv("AI_NOTES_DB", str(database))
    client.post(
        "/api/ai/summarize",
        json={
            "memo_id": "memo-read-1",
            "title": "Docker port issue",
            "content": "FastAPI deployment failed because the Docker port mapping was wrong.",
            "tags": ["Docker"],
        },
    )

    response = client.get("/api/ai/notes/memo-read-1")

    assert response.status_code == 200
    assert response.json()["memo_id"] == "memo-read-1"
    assert response.json()["summary"] == "Docker 容器端口映射问题分析"
    assert response.json()["keywords"]
    assert response.json()["category"] == "DevOps"
    assert response.json()["suggested_tags"]
    assert response.json()["provider"] == "deterministic"
    assert response.json()["created_at"]


def test_ai_note_read_returns_not_found(monkeypatch, tmp_path):
    monkeypatch.setenv("AI_NOTES_DB", str(tmp_path / "not-found-note.db"))

    response = client.get("/api/ai/notes/missing")

    assert response.status_code == 404
    assert response.json()["detail"] == "AI note not found"


def test_memos_webhook_triggers_summary(monkeypatch, tmp_path):
    database = tmp_path / "webhook.db"
    monkeypatch.setenv("AI_NOTES_DB", str(database))
    response = client.post(
        "/api/integrations/memos/webhook",
        json={
            "activityType": "memos.memo.created",
            "memo": {"uid": "memo-42", "content": "Fix a Docker port mapping"},
        },
    )

    assert response.status_code == 200
    assert response.json()["code"] == 0
    assert response.json()["message"] == "accepted"
    assert response.json()["memo_type"] == "plain"
    assert response.json()["index_status"] == "skipped"
    with sqlite3.connect(database) as connection:
        table = connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'memo_templates'"
        ).fetchone()
    assert table is None


def test_memos_webhook_normalizes_memos_resource_name_to_uid(monkeypatch, tmp_path):
    monkeypatch.setenv("AI_NOTES_DB", str(tmp_path / "resource-name.db"))

    response = client.post(
        "/api/integrations/memos/webhook",
        json={
            "activityType": "memos.memo.updated",
            "memo": {
                "name": "memos/memo-resource-name",
                "content": "Bug report: webhook insight must use the detail memo uid.",
            },
        },
    )

    assert response.status_code == 200
    assert response.json()["code"] == 0
    assert client.get("/api/ai/insights/memo-resource-name").json()
    assert client.get("/api/ai/insights/memos%2Fmemo-resource-name").status_code == 404


def test_memos_webhook_returns_code_template(monkeypatch, tmp_path):
    monkeypatch.setenv("AI_NOTES_DB", str(tmp_path / "code.db"))
    response = client.post(
        "/api/integrations/memos/webhook",
        json={
            "activityType": "memos.memo.updated",
            "memo": {
                "uid": "memo-code-1",
                "content": """---
type: code
title: Port check
language: Go
---
```go
fmt.Println(8080)
```
""",
            },
        },
    )

    assert response.status_code == 200
    assert response.json()["memo_type"] == "code"
    assert response.json()["template_id"] == 1
    assert response.json()["template"]["language"] == "Go"
    assert response.json()["template"]["code"] == "fmt.Println(8080)"

    read_response = client.get("/api/ai/templates/memo-code-1")
    assert read_response.status_code == 200
    assert read_response.json()["memo_id"] == "memo-code-1"
    assert read_response.json()["raw_content"].startswith("---")
    assert read_response.json()["payload"]["code"] == "fmt.Println(8080)"


def test_memos_webhook_upserts_template_for_same_memo(monkeypatch, tmp_path):
    monkeypatch.setenv("AI_NOTES_DB", str(tmp_path / "upsert.db"))
    base = {
        "activityType": "memos.memo.created",
        "memo": {
            "uid": "memo-upsert",
            "content": "---\ntype: code\nlanguage: Python\n---\n```python\nprint(1)\n```",
        },
    }
    first = client.post("/api/integrations/memos/webhook", json=base)
    base["activityType"] = "memos.memo.updated"
    base["memo"]["content"] = "---\ntype: code\nlanguage: Python\n---\n```python\nprint(2)\n```"
    second = client.post("/api/integrations/memos/webhook", json=base)

    assert first.json()["template_id"] == second.json()["template_id"]
    assert client.get("/api/ai/templates/memo-upsert").json()["payload"]["code"] == "print(2)"


def test_memos_webhook_indexes_and_upserts_when_enabled(monkeypatch, tmp_path):
    monkeypatch.setenv("AI_NOTES_DB", str(tmp_path / "indexed.db"))
    monkeypatch.setenv("AI_INDEX_ON_WEBHOOK", "true")
    store = InMemoryVectorStore(dimension=8)
    monkeypatch.setattr(
        main,
        "embedding_service",
        EmbeddingService(DeterministicEmbeddingProvider(), store),
    )

    first = client.post(
        "/api/integrations/memos/webhook",
        json={
            "activityType": "memos.memo.created",
            "memo": {"uid": "memo-indexed", "content": "Docker port mapping"},
        },
    )
    second = client.post(
        "/api/integrations/memos/webhook",
        json={
            "activityType": "memos.memo.updated",
            "memo": {"uid": "memo-indexed", "content": "FastAPI port mapping"},
        },
    )

    assert first.json()["index_status"] == "indexed"
    assert second.json()["index_status"] == "indexed"
    assert first.json()["embedding_id"] == second.json()["embedding_id"]
    assert len(store.search(DeterministicEmbeddingProvider().embed("FastAPI port mapping").values)) == 1


def test_memos_webhook_deletes_index_without_blocking(monkeypatch, tmp_path):
    monkeypatch.setenv("AI_NOTES_DB", str(tmp_path / "deleted.db"))
    monkeypatch.setenv("AI_INDEX_ON_WEBHOOK", "true")
    store = InMemoryVectorStore(dimension=8)
    monkeypatch.setattr(
        main,
        "embedding_service",
        EmbeddingService(DeterministicEmbeddingProvider(), store),
    )
    client.post(
        "/api/integrations/memos/webhook",
        json={
            "activityType": "memos.memo.created",
            "memo": {"uid": "memo-delete-webhook", "content": "content"},
        },
    )

    response = client.post(
        "/api/integrations/memos/webhook",
        json={
            "activityType": "memos.memo.deleted",
            "memo": {"uid": "memo-delete-webhook"},
        },
    )

    assert response.json()["code"] == 0
    assert response.json()["index_status"] == "deleted"
    assert response.json()["derived_cleanup"]["ai_notes"] == 1
    assert response.json()["derived_cleanup"]["memo_insights"] == 1
    assert store.search(DeterministicEmbeddingProvider().embed("content").values) == []


def test_memos_webhook_deletes_derived_state_when_indexing_is_disabled(monkeypatch, tmp_path):
    database = tmp_path / "derived-state-delete.db"
    monkeypatch.setenv("AI_NOTES_DB", str(database))
    client.post(
        "/api/integrations/memos/webhook",
        json={
            "activityType": "memos.memo.created",
            "memo": {
                "uid": "memo-derived-delete",
                "content": "---\ntype: bug\ntitle: Port failure\n---\nRoot cause: wrong port\nSolution: fix mapping",
            },
        },
    )
    save_chunk_index_state("memo-derived-delete", "memo-chunk-v1", ("memo-derived-delete:0",))

    response = client.post(
        "/api/integrations/memos/webhook",
        json={
            "activityType": "memos.memo.deleted",
            "memo": {"uid": "memo-derived-delete"},
        },
    )

    assert "index_status" not in response.json()
    assert response.json()["derived_cleanup"] == {
        "ai_notes": 1,
        "memo_templates": 1,
        "memo_insights": 2,
        "chunk_index_state": 1,
    }
    assert client.get("/api/ai/notes/memo-derived-delete").status_code == 404
    assert client.get("/api/ai/templates/memo-derived-delete").status_code == 404
    assert client.get("/api/ai/insights/memo-derived-delete").json() == []


def test_memos_webhook_index_failure_is_acknowledged(monkeypatch, tmp_path):
    monkeypatch.setenv("AI_NOTES_DB", str(tmp_path / "failed-index.db"))
    monkeypatch.setenv("AI_INDEX_ON_WEBHOOK", "true")

    class BrokenEmbeddingService:
        def embed_memo(self, memo_id, content, metadata):
            raise RuntimeError("index unavailable")

    monkeypatch.setattr(main, "embedding_service", BrokenEmbeddingService())

    response = client.post(
        "/api/integrations/memos/webhook",
        json={
            "activityType": "memos.memo.created",
            "memo": {"uid": "memo-index-failed", "content": "content"},
        },
    )

    assert response.status_code == 200
    assert response.json()["code"] == 0
    assert response.json()["index_status"] == "failed"


def test_template_api_allows_the_configured_local_frontend_origin():
    response = client.get("/health", headers={"Origin": "http://localhost:3001"})

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:3001"


def test_summary_api_allows_post_from_the_configured_local_frontend_origin(
    monkeypatch, tmp_path
):
    monkeypatch.setenv("AI_NOTES_DB", str(tmp_path / "cors.db"))
    response = client.post(
        "/api/ai/summarize",
        headers={"Origin": "http://localhost:3001"},
        json={"memo_id": "cors-1", "content": "Docker port mapping"},
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:3001"


def test_ai_api_allows_the_loopback_frontend_origin():
    response = client.get("/health", headers={"Origin": "http://127.0.0.1:3001"})

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://127.0.0.1:3001"


def test_template_read_returns_not_found(monkeypatch, tmp_path):
    monkeypatch.setenv("AI_NOTES_DB", str(tmp_path / "not-found.db"))

    response = client.get("/api/ai/templates/missing")

    assert response.status_code == 404
    assert response.json()["detail"] == "memo template not found"


def test_invalid_template_is_acknowledged_without_persistence(monkeypatch, tmp_path):
    database = tmp_path / "invalid.db"
    monkeypatch.setenv("AI_NOTES_DB", str(database))
    response = client.post(
        "/api/integrations/memos/webhook",
        json={
            "activityType": "memos.memo.created",
            "memo": {
                "uid": "memo-invalid",
                "content": "---\ntype: code\nlanguage: Rust\n---\n```rust\nfn main() {}\n```",
            },
        },
    )

    assert response.status_code == 200
    assert response.json()["code"] == 0
    assert response.json()["memo_type"] == "plain"
    assert "parse_errors" in response.json()


def test_memos_webhook_acknowledges_empty_memo(monkeypatch, tmp_path):
    monkeypatch.setenv("AI_NOTES_DB", str(tmp_path / "empty.db"))
    response = client.post(
        "/api/integrations/memos/webhook",
        json={"activityType": "memos.memo.created", "memo": {"uid": "empty"}},
    )

    assert response.status_code == 200
    assert response.json() == {
        "code": 0,
        "message": "ignored empty memo",
        "memo_type": "plain",
    }
