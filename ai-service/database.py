"""Small SQLite persistence layer for AI-generated memo metadata."""

from __future__ import annotations

import json
import os
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def database_path() -> Path:
    return Path(os.getenv("AI_NOTES_DB", "data/ai_notes.db"))


def save_ai_note(
    memo_id: str | int | None,
    summary: str,
    keywords: list[str],
    category: str,
    suggested_tags: list[str] | None = None,
    provider: str = "deterministic",
) -> dict[str, Any]:
    path = database_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    stored_memo_id = str(memo_id) if memo_id is not None else f"anonymous-{uuid.uuid4()}"
    created_at = datetime.now(timezone.utc).isoformat()
    with sqlite3.connect(path) as connection:
        _ensure_ai_notes_schema(connection)
        connection.execute(
            """
            INSERT INTO ai_notes
                (memo_id, summary, keywords, category, suggested_tags, provider, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(memo_id) DO UPDATE SET
                summary = excluded.summary,
                keywords = excluded.keywords,
                category = excluded.category,
                suggested_tags = excluded.suggested_tags,
                provider = excluded.provider,
                created_at = excluded.created_at
            """,
            (
                stored_memo_id,
                summary,
                json.dumps(keywords),
                category,
                json.dumps(suggested_tags or []),
                provider,
                created_at,
            ),
        )
        row = connection.execute(
            "SELECT id, created_at FROM ai_notes WHERE memo_id = ?", (stored_memo_id,)
        ).fetchone()
    return {"id": row[0], "created_at": row[1]}


def get_ai_note(memo_id: str | int) -> dict[str, Any] | None:
    """Read one persisted AI summary by Memo identifier."""

    path = database_path()
    if not path.exists():
        return None
    with sqlite3.connect(path) as connection:
        _ensure_ai_notes_schema(connection)
        row = connection.execute(
            """
            SELECT id, memo_id, summary, keywords, category,
                   suggested_tags, provider, created_at
            FROM ai_notes
            WHERE memo_id = ?
            """,
            (str(memo_id),),
        ).fetchone()
    return _ai_note_row(row) if row else None


def _ensure_ai_notes_schema(connection: sqlite3.Connection) -> None:
    """Create or minimally migrate the AI-owned summary table."""

    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS ai_notes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            memo_id TEXT NOT NULL UNIQUE,
            summary TEXT NOT NULL,
            keywords TEXT NOT NULL,
            category TEXT NOT NULL,
            suggested_tags TEXT NOT NULL DEFAULT '[]',
            provider TEXT NOT NULL DEFAULT 'deterministic',
            embedding_id TEXT,
            created_at TEXT NOT NULL
        )
        """
    )
    columns = {
        row[1]
        for row in connection.execute("PRAGMA table_info(ai_notes)").fetchall()
    }
    if "suggested_tags" not in columns:
        connection.execute(
            "ALTER TABLE ai_notes ADD COLUMN suggested_tags TEXT NOT NULL DEFAULT '[]'"
        )
    if "provider" not in columns:
        connection.execute(
            "ALTER TABLE ai_notes ADD COLUMN provider TEXT NOT NULL DEFAULT 'deterministic'"
        )


def _ai_note_row(row: tuple[Any, ...] | None) -> dict[str, Any]:
    if row is None:
        raise RuntimeError("AI note row was not found after save")
    return {
        "id": row[0],
        "memo_id": row[1],
        "summary": row[2],
        "keywords": json.loads(row[3]),
        "category": row[4],
        "suggested_tags": json.loads(row[5]),
        "provider": row[6],
        "created_at": row[7],
    }


def save_memo_template(
    memo_id: str | int,
    kind: str,
    payload: dict[str, Any],
    raw_content: str,
) -> dict[str, Any]:
    """Upsert one parsed Code Snippet or Bug Report for a Memo."""

    path = database_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    stored_memo_id = str(memo_id)
    now = datetime.now(timezone.utc).isoformat()
    with sqlite3.connect(path) as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS memo_templates (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                memo_id TEXT NOT NULL UNIQUE,
                kind TEXT NOT NULL CHECK (kind IN ('code', 'bug')),
                payload TEXT NOT NULL,
                raw_content TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            INSERT INTO memo_templates
                (memo_id, kind, payload, raw_content, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(memo_id) DO UPDATE SET
                kind = excluded.kind,
                payload = excluded.payload,
                raw_content = excluded.raw_content,
                updated_at = excluded.updated_at
            """,
            (stored_memo_id, kind, json.dumps(payload, ensure_ascii=False), raw_content, now, now),
        )
        row = connection.execute(
            """
            SELECT id, memo_id, kind, payload, raw_content, created_at, updated_at
            FROM memo_templates
            WHERE memo_id = ?
            """,
            (stored_memo_id,),
        ).fetchone()
    return _template_row(row)


def get_memo_template(memo_id: str | int) -> dict[str, Any] | None:
    """Read one persisted parsed template by Memo identifier."""

    path = database_path()
    if not path.exists():
        return None
    with sqlite3.connect(path) as connection:
        row = connection.execute(
            """
            SELECT id, memo_id, kind, payload, raw_content, created_at, updated_at
            FROM memo_templates
            WHERE memo_id = ?
            """,
            (str(memo_id),),
        ).fetchone()
    return _template_row(row) if row else None


def save_webhook_event(
    event_id: str,
    event_type: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    """Insert one Webhook event or return its existing idempotent row."""

    path = database_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc).isoformat()
    with sqlite3.connect(path) as connection:
        _ensure_webhook_events_schema(connection)
        connection.execute(
            """
            INSERT INTO webhook_events
                (event_id, event_type, payload, status, attempts, created_at, updated_at)
            VALUES (?, ?, ?, 'pending', 0, ?, ?)
            ON CONFLICT(event_id) DO NOTHING
            """,
            (event_id, event_type, json.dumps(payload, ensure_ascii=False), now, now),
        )
        row = connection.execute(
            """
            SELECT event_id, event_type, payload, status, attempts, last_error,
                   created_at, updated_at
            FROM webhook_events
            WHERE event_id = ?
            """,
            (event_id,),
        ).fetchone()
    return _webhook_event_row(row)


def update_webhook_event(
    event_id: str,
    status: str,
    last_error: str | None = None,
) -> dict[str, Any]:
    """Update processing status and increment the finite attempt counter."""

    if status not in {"pending", "processed", "failed"}:
        raise ValueError("unsupported webhook event status")
    path = database_path()
    if not path.exists():
        raise ValueError("webhook event database does not exist")
    now = datetime.now(timezone.utc).isoformat()
    with sqlite3.connect(path) as connection:
        _ensure_webhook_events_schema(connection)
        connection.execute(
            """
            UPDATE webhook_events
            SET status = ?, attempts = attempts + 1, last_error = ?, updated_at = ?
            WHERE event_id = ?
            """,
            (status, last_error, now, event_id),
        )
        row = connection.execute(
            """
            SELECT event_id, event_type, payload, status, attempts, last_error,
                   created_at, updated_at
            FROM webhook_events
            WHERE event_id = ?
            """,
            (event_id,),
        ).fetchone()
    return _webhook_event_row(row)


def get_webhook_event(event_id: str) -> dict[str, Any] | None:
    """Read one outbox event without starting processing."""

    path = database_path()
    if not path.exists():
        return None
    with sqlite3.connect(path) as connection:
        _ensure_webhook_events_schema(connection)
        row = connection.execute(
            """
            SELECT event_id, event_type, payload, status, attempts, last_error,
                   created_at, updated_at
            FROM webhook_events
            WHERE event_id = ?
            """,
            (event_id,),
        ).fetchone()
    return _webhook_event_row(row) if row else None


def list_webhook_events(status: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
    """Read recent outbox state for a small operational status surface."""

    if limit < 1 or limit > 100:
        raise ValueError("webhook event limit must be between 1 and 100")
    path = database_path()
    if not path.exists():
        return []
    with sqlite3.connect(path) as connection:
        _ensure_webhook_events_schema(connection)
        if status is None:
            rows = connection.execute(
                """
                SELECT event_id, event_type, payload, status, attempts, last_error,
                       created_at, updated_at
                FROM webhook_events
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        else:
            rows = connection.execute(
                """
                SELECT event_id, event_type, payload, status, attempts, last_error,
                       created_at, updated_at
                FROM webhook_events
                WHERE status = ?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (status, limit),
            ).fetchall()
    return [_webhook_event_row(row) for row in rows]


def _ensure_webhook_events_schema(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS webhook_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_id TEXT NOT NULL UNIQUE,
            event_type TEXT NOT NULL,
            payload TEXT NOT NULL,
            status TEXT NOT NULL CHECK (status IN ('pending', 'processed', 'failed')),
            attempts INTEGER NOT NULL DEFAULT 0,
            last_error TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )


def _webhook_event_row(row: tuple[Any, ...] | None) -> dict[str, Any]:
    if row is None:
        raise RuntimeError("webhook event row was not found")
    return {
        "event_id": row[0],
        "event_type": row[1],
        "payload": json.loads(row[2]),
        "status": row[3],
        "attempts": row[4],
        "last_error": row[5],
        "created_at": row[6],
        "updated_at": row[7],
    }


def _template_row(row: tuple[Any, ...] | None) -> dict[str, Any]:
    if row is None:
        raise RuntimeError("memo template row was not found after save")
    return {
        "id": row[0],
        "memo_id": row[1],
        "kind": row[2],
        "payload": json.loads(row[3]),
        "raw_content": row[4],
        "created_at": row[5],
        "updated_at": row[6],
    }
