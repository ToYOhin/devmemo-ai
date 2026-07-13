"""Small SQLite persistence layer for AI-generated memo metadata."""

from __future__ import annotations

import json
import os
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


DEFAULT_WEBHOOK_MAX_ATTEMPTS = 3


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
                (event_id, event_type, payload, status, attempts, max_attempts, created_at, updated_at)
            VALUES (?, ?, ?, 'pending', 0, ?, ?, ?)
            ON CONFLICT(event_id) DO NOTHING
            """,
            (
                event_id,
                event_type,
                json.dumps(payload, ensure_ascii=False),
                DEFAULT_WEBHOOK_MAX_ATTEMPTS,
                now,
                now,
            ),
        )
        row = _select_webhook_event(connection, event_id)
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
            (status, last_error if status == "failed" else None, now, event_id),
        )
        row = _select_webhook_event(connection, event_id)
    return _webhook_event_row(row)


def begin_webhook_retry(event_id: str) -> dict[str, Any] | None:
    """Atomically move one failed event to pending for an explicit retry."""

    path = database_path()
    if not path.exists():
        return None
    now = datetime.now(timezone.utc).isoformat()
    with sqlite3.connect(path) as connection:
        _ensure_webhook_events_schema(connection)
        row = _select_webhook_event(connection, event_id)
        if row is None:
            return None
        event = _webhook_event_row(row)
        if event["status"] != "failed":
            raise ValueError("only failed webhook events can be retried")
        if event["attempts"] >= event["max_attempts"]:
            raise ValueError("webhook retry limit reached")
        updated = connection.execute(
            """
            UPDATE webhook_events
            SET status = 'pending', updated_at = ?
            WHERE event_id = ? AND status = 'failed' AND attempts < max_attempts
            """,
            (now, event_id),
        )
        if updated.rowcount != 1:
            raise ValueError("webhook event is no longer retryable")
        row = _select_webhook_event(connection, event_id)
    return _webhook_event_row(row)


def get_webhook_event(event_id: str) -> dict[str, Any] | None:
    """Read one outbox event without starting processing."""

    path = database_path()
    if not path.exists():
        return None
    with sqlite3.connect(path) as connection:
        _ensure_webhook_events_schema(connection)
        row = _select_webhook_event(connection, event_id)
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
                SELECT event_id, event_type, payload, status, attempts, max_attempts,
                       last_error, created_at, updated_at
                FROM webhook_events
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        else:
            rows = connection.execute(
                """
                SELECT event_id, event_type, payload, status, attempts, max_attempts,
                       last_error, created_at, updated_at
                FROM webhook_events
                WHERE status = ?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (status, limit),
            ).fetchall()
    return [_webhook_event_row(row) for row in rows]


def list_webhook_retention_candidates(
    older_than_days: int,
    limit: int = 100,
    cutoff: str | None = None,
) -> list[dict[str, Any]]:
    """List inactive terminal events without deleting or mutating any row."""

    if cutoff is None:
        cutoff = webhook_retention_cutoff(older_than_days)
    else:
        cutoff = _normalize_retention_cutoff(cutoff)
    if limit < 1 or limit > 100:
        raise ValueError("retention limit must be between 1 and 100")
    path = database_path()
    if not path.exists():
        return []
    cutoff = (datetime.now(timezone.utc) - timedelta(days=older_than_days)).isoformat()
    with sqlite3.connect(path) as connection:
        _ensure_webhook_events_schema(connection)
        rows = connection.execute(
            """
            SELECT event_id, event_type, payload, status, attempts, max_attempts,
                   last_error, created_at, updated_at
            FROM webhook_events
            WHERE status IN ('processed', 'failed') AND updated_at < ?
            ORDER BY updated_at ASC, event_id ASC
            LIMIT ?
            """,
            (cutoff, limit),
        ).fetchall()
    return [_webhook_event_row(row) for row in rows]


def webhook_retention_cutoff(older_than_days: int) -> str:
    if older_than_days < 1 or older_than_days > 3650:
        raise ValueError("retention days must be between 1 and 3650")
    return (datetime.now(timezone.utc) - timedelta(days=older_than_days)).isoformat()


def delete_webhook_retention_candidates(
    approval_id: str,
    candidate_ids: list[str],
    cutoff: str,
    actor_digest: str,
    preview_limit: int = 100,
) -> dict[str, Any]:
    """Delete only an approved, unchanged terminal candidate set and audit it."""

    normalized_cutoff = _normalize_retention_cutoff(cutoff)
    normalized_ids = sorted(candidate_ids)
    if not normalized_ids or len(normalized_ids) > 100:
        raise ValueError("retention candidate count must be between 1 and 100")
    if preview_limit < 1 or preview_limit > 100:
        raise ValueError("retention preview limit must be between 1 and 100")
    if len(set(normalized_ids)) != len(normalized_ids):
        raise ValueError("retention candidate ids must be unique")
    path = database_path()
    if not path.exists():
        raise ValueError("retention candidates changed; refresh preview")

    with sqlite3.connect(path) as connection:
        _ensure_webhook_events_schema(connection)
        connection.execute("BEGIN IMMEDIATE")
        existing_row = connection.execute(
            """
            SELECT approval_id, actor_digest, cutoff, candidate_ids,
                   preview_limit, candidate_count, deleted_count, created_at
            FROM webhook_cleanup_audits
            WHERE approval_id = ?
            """,
            (approval_id,),
        ).fetchone()
        if existing_row:
            existing = _cleanup_audit_row(existing_row)
            if (
                existing["actor_digest"] != actor_digest
                or existing["cutoff"] != normalized_cutoff
                or existing["candidate_ids"] != normalized_ids
                or existing["preview_limit"] != preview_limit
            ):
                raise ValueError("approval id already used with a different cleanup request")
            return {**existing, "replayed": True}

        rows = connection.execute(
            """
            SELECT event_id
            FROM webhook_events
            WHERE status IN ('processed', 'failed')
              AND updated_at < ?
            ORDER BY updated_at ASC, event_id ASC
            LIMIT ?
            """,
            (normalized_cutoff, preview_limit),
        ).fetchall()
        if {row[0] for row in rows} != set(normalized_ids):
            raise ValueError("retention candidates changed; refresh preview")

        placeholders = ", ".join("?" for _ in normalized_ids)
        deleted = connection.execute(
            f"""
            DELETE FROM webhook_events
            WHERE event_id IN ({placeholders})
              AND status IN ('processed', 'failed')
              AND updated_at < ?
            """,
            (*normalized_ids, normalized_cutoff),
        ).rowcount
        if deleted != len(normalized_ids):
            raise ValueError("retention candidates changed; refresh preview")
        created_at = datetime.now(timezone.utc).isoformat()
        connection.execute(
            """
            INSERT INTO webhook_cleanup_audits
                (approval_id, actor_digest, cutoff, candidate_ids,
                 preview_limit, candidate_count, deleted_count, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                approval_id,
                actor_digest,
                normalized_cutoff,
                json.dumps(normalized_ids),
                preview_limit,
                len(normalized_ids),
                deleted,
                created_at,
            ),
        )
    return {
        "approval_id": approval_id,
        "actor_digest": actor_digest,
        "cutoff": normalized_cutoff,
        "candidate_ids": normalized_ids,
        "preview_limit": preview_limit,
        "candidate_count": len(normalized_ids),
        "deleted_count": deleted,
        "created_at": created_at,
        "replayed": False,
    }


def list_webhook_cleanup_audits(limit: int = 50) -> list[dict[str, Any]]:
    if limit < 1 or limit > 100:
        raise ValueError("cleanup audit limit must be between 1 and 100")
    path = database_path()
    if not path.exists():
        return []
    with sqlite3.connect(path) as connection:
        _ensure_webhook_events_schema(connection)
        rows = connection.execute(
            """
            SELECT approval_id, actor_digest, cutoff, candidate_ids,
                   preview_limit, candidate_count, deleted_count, created_at
            FROM webhook_cleanup_audits
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [_cleanup_audit_row(row) for row in rows]


def get_webhook_event_stats() -> dict[str, Any]:
    """Return bounded status counts and recent failure summaries."""

    empty_counts = {"pending": 0, "processed": 0, "failed": 0}
    path = database_path()
    if not path.exists():
        return {"by_status": empty_counts, "exhausted_count": 0, "recent_errors": []}
    with sqlite3.connect(path) as connection:
        _ensure_webhook_events_schema(connection)
        counts = connection.execute(
            "SELECT status, COUNT(*) FROM webhook_events GROUP BY status"
        ).fetchall()
        errors = connection.execute(
            """
            SELECT event_id, last_error, attempts, max_attempts, updated_at
            FROM webhook_events
            WHERE status = 'failed' AND last_error IS NOT NULL
            ORDER BY updated_at DESC
            LIMIT 5
            """
        ).fetchall()
        exhausted_count = connection.execute(
            """
            SELECT COUNT(*)
            FROM webhook_events
            WHERE status = 'failed' AND attempts >= max_attempts
            """
        ).fetchone()[0]
    for status, count in counts:
        empty_counts[status] = count
    return {
        "by_status": empty_counts,
        "exhausted_count": exhausted_count,
        "recent_errors": [
            {
                "event_id": row[0],
                "last_error": row[1],
                "attempts": row[2],
                "max_attempts": row[3],
                "updated_at": row[4],
            }
            for row in errors
        ],
    }


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
            max_attempts INTEGER NOT NULL DEFAULT 3,
            last_error TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )
    columns = {
        row[1]
        for row in connection.execute("PRAGMA table_info(webhook_events)").fetchall()
    }
    if "max_attempts" not in columns:
        connection.execute(
            "ALTER TABLE webhook_events ADD COLUMN max_attempts INTEGER NOT NULL DEFAULT 3"
        )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS webhook_cleanup_audits (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            approval_id TEXT NOT NULL UNIQUE,
            actor_digest TEXT NOT NULL,
            cutoff TEXT NOT NULL,
            candidate_ids TEXT NOT NULL,
            preview_limit INTEGER NOT NULL DEFAULT 100,
            candidate_count INTEGER NOT NULL,
            deleted_count INTEGER NOT NULL,
            created_at TEXT NOT NULL
        )
        """
    )
    audit_columns = {
        row[1]
        for row in connection.execute("PRAGMA table_info(webhook_cleanup_audits)").fetchall()
    }
    if "preview_limit" not in audit_columns:
        connection.execute(
            "ALTER TABLE webhook_cleanup_audits "
            "ADD COLUMN preview_limit INTEGER NOT NULL DEFAULT 100"
        )


def _select_webhook_event(
    connection: sqlite3.Connection,
    event_id: str,
) -> tuple[Any, ...] | None:
    return connection.execute(
        """
        SELECT event_id, event_type, payload, status, attempts, max_attempts,
               last_error, created_at, updated_at
        FROM webhook_events
        WHERE event_id = ?
        """,
        (event_id,),
    ).fetchone()


def _webhook_event_row(row: tuple[Any, ...] | None) -> dict[str, Any]:
    if row is None:
        raise RuntimeError("webhook event row was not found")
    return {
        "event_id": row[0],
        "event_type": row[1],
        "payload": json.loads(row[2]),
        "status": row[3],
        "attempts": row[4],
        "max_attempts": row[5],
        "last_error": row[6],
        "created_at": row[7],
        "updated_at": row[8],
    }


def _normalize_retention_cutoff(cutoff: str) -> str:
    try:
        parsed = datetime.fromisoformat(cutoff)
    except ValueError as error:
        raise ValueError("retention cutoff must be an ISO-8601 timestamp") from error
    if parsed.tzinfo is None:
        raise ValueError("retention cutoff must include a timezone")
    return parsed.astimezone(timezone.utc).isoformat()


def _cleanup_audit_row(row: tuple[Any, ...]) -> dict[str, Any]:
    return {
        "approval_id": row[0],
        "actor_digest": row[1],
        "cutoff": row[2],
        "candidate_ids": json.loads(row[3]),
        "preview_limit": row[4],
        "candidate_count": row[5],
        "deleted_count": row[6],
        "created_at": row[7],
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
