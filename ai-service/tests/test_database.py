import sqlite3

import pytest

from database import (
    begin_webhook_retry,
    get_ai_note,
    get_memo_template,
    get_webhook_event,
    get_webhook_event_stats,
    list_webhook_events,
    save_ai_note,
    save_memo_template,
    save_webhook_event,
    update_webhook_event,
)


def test_ai_note_create_and_read(monkeypatch, tmp_path):
    database = tmp_path / "notes.db"
    monkeypatch.setenv("AI_NOTES_DB", str(database))

    saved = save_ai_note(
        "memo-1",
        "Docker 端口映射问题分析",
        ["Docker", "FastAPI"],
        "DevOps",
        suggested_tags=["docker", "network"],
        provider="deterministic",
    )

    note = get_ai_note("memo-1")
    assert note is not None
    assert note["id"] == saved["id"]
    assert note["summary"] == "Docker 端口映射问题分析"
    assert note["keywords"] == ["Docker", "FastAPI"]
    assert note["category"] == "DevOps"
    assert note["suggested_tags"] == ["docker", "network"]
    assert note["provider"] == "deterministic"
    assert note["created_at"] == saved["created_at"]


def test_missing_ai_note_returns_none(monkeypatch, tmp_path):
    monkeypatch.setenv("AI_NOTES_DB", str(tmp_path / "missing.db"))

    assert get_ai_note("missing") is None


def test_template_upsert_is_idempotent(monkeypatch, tmp_path):
    database = tmp_path / "templates.db"
    monkeypatch.setenv("AI_NOTES_DB", str(database))

    first = save_memo_template(
        "memo-1",
        "code",
        {"title": "First", "language": "Python", "code": "print(1)"},
        "raw v1",
    )
    second = save_memo_template(
        "memo-1",
        "code",
        {"title": "Updated", "language": "Python", "code": "print(2)"},
        "raw v2",
    )

    assert second["id"] == first["id"]
    assert get_memo_template("memo-1")["payload"]["title"] == "Updated"
    assert get_memo_template("memo-1")["raw_content"] == "raw v2"
    with sqlite3.connect(database) as connection:
        count = connection.execute("SELECT COUNT(*) FROM memo_templates").fetchone()[0]
    assert count == 1


def test_missing_template_returns_none(monkeypatch, tmp_path):
    monkeypatch.setenv("AI_NOTES_DB", str(tmp_path / "missing.db"))

    assert get_memo_template("missing") is None


def test_webhook_event_create_is_idempotent_and_readable(monkeypatch, tmp_path):
    database = tmp_path / "outbox.db"
    monkeypatch.setenv("AI_NOTES_DB", str(database))
    payload = {"activityType": "memos.memo.created", "memo": {"uid": "memo-1"}}

    first = save_webhook_event("event-1", "memos.memo.created", payload)
    second = save_webhook_event("event-1", "memos.memo.created", {"changed": True})

    assert second == first
    assert first["status"] == "pending"
    assert first["attempts"] == 0
    assert first["payload"] == payload
    assert get_webhook_event("event-1") == first
    assert len(list_webhook_events()) == 1


def test_webhook_event_status_tracks_success_and_failure(monkeypatch, tmp_path):
    monkeypatch.setenv("AI_NOTES_DB", str(tmp_path / "outbox-status.db"))
    save_webhook_event("event-success", "memo.created", {})
    save_webhook_event("event-failed", "memo.updated", {})

    processed = update_webhook_event("event-success", "processed")
    failed = update_webhook_event("event-failed", "failed", "summary provider unavailable")

    assert processed["status"] == "processed"
    assert processed["attempts"] == 1
    assert failed["status"] == "failed"
    assert failed["attempts"] == 1
    assert failed["last_error"] == "summary provider unavailable"
    assert [item["event_id"] for item in list_webhook_events(status="failed")] == [
        "event-failed"
    ]


def test_webhook_retry_migrates_existing_table_and_clears_error_on_success(monkeypatch, tmp_path):
    database = tmp_path / "legacy-outbox.db"
    monkeypatch.setenv("AI_NOTES_DB", str(database))
    with sqlite3.connect(database) as connection:
        connection.execute(
            """
            CREATE TABLE webhook_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_id TEXT NOT NULL UNIQUE,
                event_type TEXT NOT NULL,
                payload TEXT NOT NULL,
                status TEXT NOT NULL,
                attempts INTEGER NOT NULL DEFAULT 0,
                last_error TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            INSERT INTO webhook_events
                (event_id, event_type, payload, status, attempts, last_error, created_at, updated_at)
            VALUES ('legacy-failed', 'memo.created', '{}', 'failed', 1, 'old error', '2026-07-13', '2026-07-13')
            """
        )

    failed = get_webhook_event("legacy-failed")
    assert failed["max_attempts"] == 3
    pending = begin_webhook_retry("legacy-failed")
    assert pending["status"] == "pending"
    processed = update_webhook_event("legacy-failed", "processed")
    assert processed["attempts"] == 2
    assert processed["last_error"] is None


def test_webhook_retry_is_limited_and_stats_are_bounded(monkeypatch, tmp_path):
    monkeypatch.setenv("AI_NOTES_DB", str(tmp_path / "retry-limit.db"))
    save_webhook_event("retry-limit", "memo.created", {})
    update_webhook_event("retry-limit", "failed", "first failure")
    begin_webhook_retry("retry-limit")
    update_webhook_event("retry-limit", "failed", "second failure")
    begin_webhook_retry("retry-limit")
    update_webhook_event("retry-limit", "failed", "third failure")

    with pytest.raises(ValueError, match="retry limit"):
        begin_webhook_retry("retry-limit")

    stats = get_webhook_event_stats()
    assert stats["by_status"] == {"pending": 0, "processed": 0, "failed": 1}
    assert stats["recent_errors"][0]["last_error"] == "third failure"
    assert stats["recent_errors"][0]["attempts"] == 3
