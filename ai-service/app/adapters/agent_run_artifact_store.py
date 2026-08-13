"""Local SQLite storage for derived AgentRun Markdown artifacts."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
import hashlib
from pathlib import Path
import sqlite3
from typing import Iterator


class AgentRunArtifactStoreError(RuntimeError):
    """Raised when derived artifact content is missing, conflicting, or corrupt."""


@dataclass(frozen=True)
class StoredMarkdownArtifact:
    artifact_id: str
    run_id: str
    storage_ref: str
    file_name: str
    markdown: str
    digest: str


class SQLiteAgentRunArtifactStore:
    def __init__(self, database: str | Path) -> None:
        self.database = Path(database)

    def put(self, artifact: StoredMarkdownArtifact) -> None:
        encoded = artifact.markdown.encode("utf-8")
        if (
            not encoded
            or len(encoded) > 1_048_576
            or hashlib.sha256(encoded).hexdigest() != artifact.digest
        ):
            raise AgentRunArtifactStoreError("AgentRun artifact size is invalid")
        with self._connection() as connection:
            existing = connection.execute(
                "SELECT * FROM agent_run_artifact_content WHERE storage_ref = ?",
                (artifact.storage_ref,),
            ).fetchone()
            if existing is not None:
                if _from_row(existing) != artifact:
                    raise AgentRunArtifactStoreError("AgentRun artifact content conflicts")
                return
            connection.execute(
                """
                INSERT INTO agent_run_artifact_content (
                    storage_ref, artifact_id, run_id, file_name, markdown, digest
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    artifact.storage_ref,
                    artifact.artifact_id,
                    artifact.run_id,
                    artifact.file_name,
                    artifact.markdown,
                    artifact.digest,
                ),
            )
            connection.commit()

    def get(self, storage_ref: str) -> StoredMarkdownArtifact | None:
        with self._connection() as connection:
            row = connection.execute(
                "SELECT * FROM agent_run_artifact_content WHERE storage_ref = ?",
                (storage_ref,),
            ).fetchone()
        return None if row is None else _from_row(row)

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        self.database.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.database, timeout=5.0)
        connection.row_factory = sqlite3.Row
        try:
            connection.execute("PRAGMA busy_timeout = 5000")
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS agent_run_artifact_content (
                    storage_ref TEXT PRIMARY KEY,
                    artifact_id TEXT NOT NULL UNIQUE,
                    run_id TEXT NOT NULL,
                    file_name TEXT NOT NULL,
                    markdown TEXT NOT NULL,
                    digest TEXT NOT NULL CHECK (length(digest) = 64)
                )
                """
            )
            connection.commit()
            yield connection
        except Exception:
            if connection.in_transaction:
                connection.rollback()
            raise
        finally:
            connection.close()


def _from_row(row: sqlite3.Row) -> StoredMarkdownArtifact:
    return StoredMarkdownArtifact(
        artifact_id=row["artifact_id"],
        run_id=row["run_id"],
        storage_ref=row["storage_ref"],
        file_name=row["file_name"],
        markdown=row["markdown"],
        digest=row["digest"],
    )
