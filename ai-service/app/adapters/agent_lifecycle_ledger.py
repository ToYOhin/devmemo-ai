"""Dormant SQLite adapter for rebuildable memo-v1 lifecycle state."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from app.domain.agent_lifecycle import (
    MEMO_INDEX_VERSION,
    LifecycleAcknowledgement,
    LifecycleTransition,
    MemoLifecycleEvent,
    MemoLifecycleState,
    accept_lifecycle_event,
    complete_lifecycle_event,
    fail_lifecycle_event,
    is_retrieval_eligible,
)


class SQLiteMemoLifecycleLedger:
    """Persist only the derived state needed for idempotency and quarantine."""

    def __init__(self, database: str | Path) -> None:
        self.database = Path(database)

    def reserve(self, event: MemoLifecycleEvent) -> LifecycleTransition:
        """Atomically reserve an accepted event before any vector mutation."""

        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            current = self._select_state(connection, event.memo_uid, event.index_version)
            transition = accept_lifecycle_event(current, event)
            if transition.decision in {"apply", "resume"}:
                self._upsert_state(connection, transition.state, last_error_code=None)
            connection.commit()
        return transition

    def complete(
        self, event: MemoLifecycleEvent
    ) -> tuple[MemoLifecycleState, LifecycleAcknowledgement]:
        """Finalize the currently reserved event after its vector mutation."""

        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            current = self._require_state(connection, event)
            completed, acknowledgement = complete_lifecycle_event(current, event)
            self._upsert_state(connection, completed, last_error_code=None)
            connection.commit()
        return completed, acknowledgement

    def fail(
        self, event: MemoLifecycleEvent, error_code: str
    ) -> tuple[MemoLifecycleState, LifecycleAcknowledgement]:
        """Persist a safe retryable failure without retaining an exception message."""

        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            current = self._require_state(connection, event)
            failed, acknowledgement = fail_lifecycle_event(current, event, error_code)
            self._upsert_state(
                connection,
                failed,
                last_error_code=acknowledgement.error_code,
            )
            connection.commit()
        return failed, acknowledgement

    def get(
        self, memo_uid: str, index_version: str = MEMO_INDEX_VERSION
    ) -> MemoLifecycleState | None:
        with self._connection() as connection:
            return self._select_state(connection, memo_uid, index_version)

    def last_error_code(
        self, memo_uid: str, index_version: str = MEMO_INDEX_VERSION
    ) -> str | None:
        with self._connection() as connection:
            row = connection.execute(
                """
                SELECT last_error_code
                FROM memo_lifecycle_ledger
                WHERE memo_uid = ? AND index_version = ?
                """,
                (memo_uid, index_version),
            ).fetchone()
        return row[0] if row else None

    def retrieval_eligible(
        self,
        memo_uid: str,
        *,
        vector_source_sequence: int,
        vector_document_hash: str,
    ) -> bool:
        return is_retrieval_eligible(
            self.get(memo_uid),
            vector_source_sequence=vector_source_sequence,
            vector_document_hash=vector_document_hash,
        )

    def _connection(self) -> sqlite3.Connection:
        self.database.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.database)
        connection.row_factory = sqlite3.Row
        _ensure_schema(connection)
        connection.commit()
        return connection

    @staticmethod
    def _select_state(
        connection: sqlite3.Connection, memo_uid: str, index_version: str
    ) -> MemoLifecycleState | None:
        row = connection.execute(
            """
            SELECT memo_uid, highest_accepted_sequence, accepted_event_id,
                   accepted_event_fingerprint, accepted_operation,
                   accepted_document_hash, status, last_applied_sequence,
                   last_applied_event_id, last_applied_operation,
                   last_applied_document_hash, tombstone_sequence, index_version
            FROM memo_lifecycle_ledger
            WHERE memo_uid = ? AND index_version = ?
            """,
            (memo_uid, index_version),
        ).fetchone()
        if row is None:
            return None
        return MemoLifecycleState(
            memo_uid=row["memo_uid"],
            highest_accepted_sequence=row["highest_accepted_sequence"],
            accepted_event_id=row["accepted_event_id"],
            accepted_event_fingerprint=row["accepted_event_fingerprint"],
            accepted_operation=row["accepted_operation"],
            accepted_document_hash=row["accepted_document_hash"],
            status=row["status"],
            last_applied_sequence=row["last_applied_sequence"],
            last_applied_event_id=row["last_applied_event_id"],
            last_applied_operation=row["last_applied_operation"],
            last_applied_document_hash=row["last_applied_document_hash"],
            tombstone_sequence=row["tombstone_sequence"],
            index_version=row["index_version"],
        )

    def _require_state(
        self, connection: sqlite3.Connection, event: MemoLifecycleEvent
    ) -> MemoLifecycleState:
        state = self._select_state(connection, event.memo_uid, event.index_version)
        if state is None:
            raise RuntimeError("lifecycle event was not reserved")
        return state

    @staticmethod
    def _upsert_state(
        connection: sqlite3.Connection,
        state: MemoLifecycleState,
        *,
        last_error_code: str | None,
    ) -> None:
        connection.execute(
            """
            INSERT INTO memo_lifecycle_ledger (
                memo_uid, index_version, highest_accepted_sequence,
                accepted_event_id, accepted_event_fingerprint,
                accepted_operation, accepted_document_hash, status,
                last_applied_sequence, last_applied_event_id,
                last_applied_operation, last_applied_document_hash,
                tombstone_sequence, last_error_code, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(memo_uid, index_version) DO UPDATE SET
                highest_accepted_sequence = excluded.highest_accepted_sequence,
                accepted_event_id = excluded.accepted_event_id,
                accepted_event_fingerprint = excluded.accepted_event_fingerprint,
                accepted_operation = excluded.accepted_operation,
                accepted_document_hash = excluded.accepted_document_hash,
                status = excluded.status,
                last_applied_sequence = excluded.last_applied_sequence,
                last_applied_event_id = excluded.last_applied_event_id,
                last_applied_operation = excluded.last_applied_operation,
                last_applied_document_hash = excluded.last_applied_document_hash,
                tombstone_sequence = excluded.tombstone_sequence,
                last_error_code = excluded.last_error_code,
                updated_at = excluded.updated_at
            """,
            (
                state.memo_uid,
                state.index_version,
                state.highest_accepted_sequence,
                state.accepted_event_id,
                state.accepted_event_fingerprint,
                state.accepted_operation,
                state.accepted_document_hash,
                state.status,
                state.last_applied_sequence,
                state.last_applied_event_id,
                state.last_applied_operation,
                state.last_applied_document_hash,
                state.tombstone_sequence,
                last_error_code,
                datetime.now(timezone.utc).isoformat(),
            ),
        )


def _ensure_schema(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS memo_lifecycle_ledger (
            memo_uid TEXT NOT NULL,
            index_version TEXT NOT NULL CHECK (index_version = 'memo-v1'),
            highest_accepted_sequence INTEGER NOT NULL
                CHECK (highest_accepted_sequence > 0),
            accepted_event_id TEXT NOT NULL,
            accepted_event_fingerprint TEXT NOT NULL
                CHECK (length(accepted_event_fingerprint) = 64),
            accepted_operation TEXT NOT NULL
                CHECK (accepted_operation IN ('upsert', 'delete')),
            accepted_document_hash TEXT,
            status TEXT NOT NULL CHECK (status IN ('applying', 'applied', 'failed')),
            last_applied_sequence INTEGER,
            last_applied_event_id TEXT,
            last_applied_operation TEXT
                CHECK (last_applied_operation IS NULL OR
                       last_applied_operation IN ('upsert', 'delete')),
            last_applied_document_hash TEXT,
            tombstone_sequence INTEGER,
            last_error_code TEXT
                CHECK (last_error_code IS NULL OR length(last_error_code) <= 64),
            updated_at TEXT NOT NULL,
            PRIMARY KEY (memo_uid, index_version),
            CHECK (
                (accepted_operation = 'upsert' AND accepted_document_hash IS NOT NULL)
                OR
                (accepted_operation = 'delete' AND accepted_document_hash IS NULL)
            )
        )
        """
    )
