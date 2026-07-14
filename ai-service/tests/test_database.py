import sqlite3

import pytest

from database import (
    begin_webhook_retry,
    delete_webhook_retention_candidates,
    get_ai_note,
    get_memo_insights,
    get_memo_template,
    get_webhook_event,
    get_webhook_event_stats,
    list_webhook_cleanup_audits,
    list_webhook_events,
    list_webhook_retention_candidates,
    save_ai_note,
    save_memo_insights,
    save_memo_template,
    save_webhook_event,
    update_webhook_event,
    update_memo_insight_status,
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


def test_memo_insights_upsert_preserves_approval_until_source_changes(monkeypatch, tmp_path):
    database = tmp_path / "insights.db"
    monkeypatch.setenv("AI_NOTES_DB", str(database))
    candidate = {
        "insight_id": "insight-1",
        "memo_id": "memo-1",
        "insight_type": "fact",
        "title": "Port mapping",
        "summary": "Use port 8080",
        "confidence": 0.8,
        "source_refs": ["summary"],
    }

    first = save_memo_insights([candidate])[0]
    accepted = update_memo_insight_status("insight-1", first["version"], "accepted")
    replay = save_memo_insights([candidate])[0]

    assert accepted["status"] == "accepted"
    assert replay["status"] == "accepted"
    assert replay["version"] == accepted["version"]
    assert len(get_memo_insights("memo-1")) == 1

    changed = {**candidate, "summary": "Use port 9090"}
    refreshed = save_memo_insights([changed])[0]
    assert refreshed["status"] == "pending"
    assert refreshed["version"] == replay["version"] + 1


def test_memo_insight_status_rejects_stale_version(monkeypatch, tmp_path):
    monkeypatch.setenv("AI_NOTES_DB", str(tmp_path / "stale-insight.db"))
    saved = save_memo_insights(
        [
            {
                "insight_id": "insight-stale",
                "memo_id": "memo-stale",
                "insight_type": "bug",
                "title": "Failure",
                "summary": "Fix it",
                "confidence": 0.9,
                "source_refs": ["template.error"],
            }
        ]
    )[0]

    update_memo_insight_status("insight-stale", saved["version"], "rejected")
    with pytest.raises(ValueError, match="stale"):
        update_memo_insight_status("insight-stale", saved["version"], "accepted")


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
    assert stats["exhausted_count"] == 1
    assert stats["recent_errors"][0]["last_error"] == "third failure"
    assert stats["recent_errors"][0]["attempts"] == 3


def test_webhook_retention_preview_is_read_only_and_excludes_pending(monkeypatch, tmp_path):
    database = tmp_path / "retention.db"
    monkeypatch.setenv("AI_NOTES_DB", str(database))
    save_webhook_event("old-processed", "memo.created", {})
    update_webhook_event("old-processed", "processed")
    save_webhook_event("old-pending", "memo.created", {})
    with sqlite3.connect(database) as connection:
        connection.execute(
            "UPDATE webhook_events SET updated_at = '2020-01-01T00:00:00+00:00' WHERE event_id = ?",
            ("old-processed",),
        )
        connection.execute(
            "UPDATE webhook_events SET updated_at = '2020-01-01T00:00:00+00:00' WHERE event_id = ?",
            ("old-pending",),
        )

    candidates = list_webhook_retention_candidates(30)

    assert [item["event_id"] for item in candidates] == ["old-processed"]
    assert get_webhook_event("old-processed")["status"] == "processed"
    assert get_webhook_event("old-pending")["status"] == "pending"


def test_webhook_retention_cleanup_deletes_terminal_rows_and_is_idempotent(monkeypatch, tmp_path):
    database = tmp_path / "cleanup.db"
    monkeypatch.setenv("AI_NOTES_DB", str(database))
    save_webhook_event("old-processed", "memo.created", {})
    update_webhook_event("old-processed", "processed")
    save_webhook_event("old-failed", "memo.updated", {})
    update_webhook_event("old-failed", "failed", "old failure")
    save_webhook_event("still-pending", "memo.created", {})
    with sqlite3.connect(database) as connection:
        connection.execute(
            "UPDATE webhook_events SET updated_at = '2020-01-01T00:00:00+00:00'"
        )

    first = delete_webhook_retention_candidates(
        "approval-1",
        ["old-failed", "old-processed"],
        "2025-01-01T00:00:00+00:00",
        "actor-digest",
    )
    replay = delete_webhook_retention_candidates(
        "approval-1",
        ["old-processed", "old-failed"],
        "2025-01-01T00:00:00Z",
        "actor-digest",
    )

    assert first["deleted_count"] == 2
    assert first["replayed"] is False
    assert replay["deleted_count"] == 2
    assert replay["replayed"] is True
    assert get_webhook_event("old-processed") is None
    assert get_webhook_event("old-failed") is None
    assert get_webhook_event("still-pending")["status"] == "pending"
    audits = list_webhook_cleanup_audits()
    assert len(audits) == 1
    assert audits[0]["approval_id"] == "approval-1"
    assert audits[0]["candidate_count"] == 2
    assert audits[0]["deleted_count"] == 2
    assert audits[0]["actor_digest"] == "actor-digest"


def test_webhook_retention_cleanup_rejects_changed_or_duplicate_candidates(monkeypatch, tmp_path):
    database = tmp_path / "cleanup-conflict.db"
    monkeypatch.setenv("AI_NOTES_DB", str(database))
    save_webhook_event("pending", "memo.created", {})
    with pytest.raises(ValueError, match="candidates changed"):
        delete_webhook_retention_candidates(
            "approval-pending",
            ["pending"],
            "2025-01-01T00:00:00Z",
            "actor-digest",
        )
    with pytest.raises(ValueError, match="must be unique"):
        delete_webhook_retention_candidates(
            "approval-duplicate",
            ["pending", "pending"],
            "2025-01-01T00:00:00Z",
            "actor-digest",
        )
