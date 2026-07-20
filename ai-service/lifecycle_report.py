"""Read-only aggregate diagnostics for the AI-owned DevMemory lifecycle."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from database import database_path


_DERIVED_TABLES = (
    "ai_notes",
    "memo_templates",
    "memo_insights",
    "memo_chunk_index_state",
)


def build_devmemory_lifecycle_report(path: Path | None = None) -> dict[str, Any]:
    """Return aggregate AI lifecycle evidence without changing the SQLite database."""

    resolved_path = Path(path or database_path())
    empty_counts = {table: 0 for table in _DERIVED_TABLES}
    if not resolved_path.exists():
        return {
            "report_version": "devmemory-lifecycle-v1",
            "database_exists": False,
            "derived_records": empty_counts,
            "insights": {"by_status": {}, "version_range": {"min": None, "max": None}},
            "webhook_events": {"by_status": {}},
            "limitations": ["Only AI-owned SQLite aggregates are reported; Memo visibility and deletion remain owned by Memos."],
        }

    with sqlite3.connect(f"{resolved_path.resolve().as_uri()}?mode=ro", uri=True) as connection:
        connection.execute("PRAGMA query_only = ON")
        available_tables = {
            row[0]
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
        }
        derived_records = {
            table: _table_count(connection, table) if table in available_tables else 0
            for table in _DERIVED_TABLES
        }
        insights = _insight_summary(connection) if "memo_insights" in available_tables else _empty_insight_summary()
        webhook_events = _status_counts(connection, "webhook_events") if "webhook_events" in available_tables else {}

    return {
        "report_version": "devmemory-lifecycle-v1",
        "database_exists": True,
        "derived_records": derived_records,
        "insights": insights,
        "webhook_events": {"by_status": webhook_events},
        "limitations": ["Only AI-owned SQLite aggregates are reported; Memo visibility and deletion remain owned by Memos."],
    }


def _table_count(connection: sqlite3.Connection, table: str) -> int:
    return int(connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])


def _insight_summary(connection: sqlite3.Connection) -> dict[str, Any]:
    minimum, maximum = connection.execute("SELECT MIN(version), MAX(version) FROM memo_insights").fetchone()
    return {
        "by_status": _status_counts(connection, "memo_insights"),
        "version_range": {"min": int(minimum) if minimum is not None else None, "max": int(maximum) if maximum is not None else None},
    }


def _empty_insight_summary() -> dict[str, Any]:
    return {"by_status": {}, "version_range": {"min": None, "max": None}}


def _status_counts(connection: sqlite3.Connection, table: str) -> dict[str, int]:
    rows = connection.execute(f"SELECT status, COUNT(*) FROM {table} GROUP BY status ORDER BY status").fetchall()
    return {str(status): int(count) for status, count in rows}
