import sqlite3

from fastapi.testclient import TestClient

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
    with sqlite3.connect(database) as connection:
        table = connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'memo_templates'"
        ).fetchone()
    assert table is None


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


def test_memos_webhook_acknowledges_empty_memo():
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
