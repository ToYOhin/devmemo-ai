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
) -> dict[str, Any]:
    path = database_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    stored_memo_id = str(memo_id) if memo_id is not None else f"anonymous-{uuid.uuid4()}"
    created_at = datetime.now(timezone.utc).isoformat()
    with sqlite3.connect(path) as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS ai_notes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                memo_id TEXT NOT NULL UNIQUE,
                summary TEXT NOT NULL,
                keywords TEXT NOT NULL,
                category TEXT NOT NULL,
                embedding_id TEXT,
                created_at TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            INSERT INTO ai_notes (memo_id, summary, keywords, category, created_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(memo_id) DO UPDATE SET
                summary = excluded.summary,
                keywords = excluded.keywords,
                category = excluded.category,
                created_at = excluded.created_at
            """,
            (stored_memo_id, summary, json.dumps(keywords), category, created_at),
        )
        row = connection.execute(
            "SELECT id, created_at FROM ai_notes WHERE memo_id = ?", (stored_memo_id,)
        ).fetchone()
    return {"id": row[0], "created_at": row[1]}


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
