"""Disposable SQLite proof adapter for unwired authorized retrieval.

This module exists only to prove the R5 repository contract with synthetic,
temporary data.  It is not a production content-persistence design, migration,
runtime factory, or replacement for the existing retrieval path.
"""

from __future__ import annotations

import hashlib
import sqlite3
from pathlib import Path

from app.domain.agent_lifecycle import MemoLifecycleState
from app.domain.durable_authorized_retrieval import (
    MAX_AUTHORIZED_MEMO_UIDS,
    MAX_RETRIEVAL_LIMIT,
    DerivedCandidateSnapshot,
    DerivedMemoCandidate,
    DerivedMemoDocument,
)


_EXPECTED_TABLE_COLUMNS = {
    "r5_disposable_repository_meta": {
        "singleton",
        "active_generation",
        "snapshot_revision",
    },
    "r5_disposable_candidates": {
        "record_key",
        "memo_uid",
        "score",
        "source_sequence",
        "document_hash",
        "rebuild_generation",
        "index_version",
        "failure_quarantined",
    },
    "r5_disposable_lifecycle": {
        "memo_uid",
        "index_version",
        "highest_accepted_sequence",
        "accepted_event_id",
        "accepted_event_fingerprint",
        "accepted_operation",
        "accepted_document_hash",
        "status",
        "last_applied_sequence",
        "last_applied_event_id",
        "last_applied_operation",
        "last_applied_document_hash",
        "tombstone_sequence",
    },
    "r5_disposable_documents": {
        "record_key",
        "memo_uid",
        "document",
        "source_sequence",
        "document_hash",
        "rebuild_generation",
        "index_version",
    },
}

_EXPECTED_TRIGGERS = {
    f"r5_revision_{table}_{operation}"
    for table in ("candidates", "lifecycle", "documents")
    for operation in ("insert", "update", "delete")
} | {"r5_revision_active_generation"}


class DisposableSQLiteAuthorizedRetrievalRepository:
    """Reopenable, test-only repository over one disposable SQLite file."""

    def __init__(self, database: str | Path, *, timeout_seconds: float = 0.05) -> None:
        self.database = Path(database)
        self.timeout_seconds = timeout_seconds

    @classmethod
    def create(
        cls, database: str | Path
    ) -> DisposableSQLiteAuthorizedRetrievalRepository:
        """Create the proof schema explicitly; normal repository opens are read-only."""

        repository = cls(database)
        with repository._connection(query_only=False) as connection:
            connection.executescript(_SCHEMA)
            connection.commit()
        return repository

    def seed_synthetic_snapshot(
        self,
        *,
        active_generation: str | None,
        candidates: tuple[DerivedMemoCandidate, ...],
        documents: tuple[DerivedMemoDocument, ...],
    ) -> None:
        """Replace only synthetic proof data in one explicit setup transaction."""

        DerivedCandidateSnapshot(
            active_generation=active_generation,
            snapshot_token="snapshot-seed",
            candidates=candidates,
        )
        if not isinstance(documents, tuple) or any(
            not isinstance(document, DerivedMemoDocument) for document in documents
        ):
            raise TypeError("documents must use DerivedMemoDocument")

        with self._connection(query_only=False) as connection:
            self._validate_schema(connection)
            connection.execute("BEGIN IMMEDIATE")
            connection.execute("DELETE FROM r5_disposable_documents")
            connection.execute("DELETE FROM r5_disposable_candidates")
            connection.execute("DELETE FROM r5_disposable_lifecycle")
            connection.execute(
                """
                UPDATE r5_disposable_repository_meta
                SET active_generation = ?
                WHERE singleton = 1
                """,
                (active_generation,),
            )
            lifecycle_states: dict[tuple[str, str], MemoLifecycleState] = {}
            for candidate in candidates:
                state = candidate.lifecycle_state
                if state is None:
                    continue
                key = (state.memo_uid, state.index_version)
                existing = lifecycle_states.get(key)
                if existing is not None and existing != state:
                    raise ValueError("synthetic lifecycle states are inconsistent")
                lifecycle_states[key] = state
            for state in lifecycle_states.values():
                self._insert_lifecycle(connection, state)
            for candidate in candidates:
                connection.execute(
                    """
                    INSERT INTO r5_disposable_candidates (
                        record_key, memo_uid, score, source_sequence,
                        document_hash, rebuild_generation, index_version,
                        failure_quarantined
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        candidate.record_key,
                        candidate.memo_uid,
                        candidate.score,
                        candidate.source_sequence,
                        candidate.document_hash,
                        candidate.rebuild_generation,
                        candidate.index_version,
                        int(candidate.failure_quarantined),
                    ),
                )
            for document in documents:
                connection.execute(
                    """
                    INSERT INTO r5_disposable_documents (
                        record_key, memo_uid, document, source_sequence,
                        document_hash, rebuild_generation, index_version
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        document.record_key,
                        document.memo_uid,
                        document.document,
                        document.source_sequence,
                        document.document_hash,
                        document.rebuild_generation,
                        document.index_version,
                    ),
                )
            connection.commit()

    def find_candidates(
        self,
        *,
        question: str,
        authorized_memo_uids: frozenset[str],
        limit: int,
    ) -> DerivedCandidateSnapshot:
        """Read active generation and content-free candidate/ledger state atomically."""

        if (
            not isinstance(question, str)
            or not question.strip()
            or not isinstance(authorized_memo_uids, frozenset)
            or len(authorized_memo_uids) > MAX_AUTHORIZED_MEMO_UIDS
            or type(limit) is not int
            or not 1 <= limit <= MAX_RETRIEVAL_LIMIT
        ):
            raise ValueError("invalid repository query")
        if not authorized_memo_uids:
            raise ValueError("empty scope must bypass the repository")

        ordered_uids = tuple(sorted(authorized_memo_uids))
        placeholders = ",".join("?" for _ in ordered_uids)
        with self._connection(query_only=True) as connection:
            self._validate_schema(connection)
            connection.execute("BEGIN")
            meta = self._select_meta(connection)
            rows = connection.execute(
                f"""
                SELECT
                    candidate.record_key,
                    candidate.memo_uid,
                    candidate.score,
                    candidate.source_sequence,
                    candidate.document_hash,
                    candidate.rebuild_generation,
                    candidate.index_version,
                    candidate.failure_quarantined,
                    lifecycle.memo_uid AS lifecycle_memo_uid,
                    lifecycle.index_version AS lifecycle_index_version,
                    lifecycle.highest_accepted_sequence,
                    lifecycle.accepted_event_id,
                    lifecycle.accepted_event_fingerprint,
                    lifecycle.accepted_operation,
                    lifecycle.accepted_document_hash,
                    lifecycle.status,
                    lifecycle.last_applied_sequence,
                    lifecycle.last_applied_event_id,
                    lifecycle.last_applied_operation,
                    lifecycle.last_applied_document_hash,
                    lifecycle.tombstone_sequence
                FROM r5_disposable_candidates AS candidate
                LEFT JOIN r5_disposable_lifecycle AS lifecycle
                  ON lifecycle.memo_uid = candidate.memo_uid
                 AND lifecycle.index_version = candidate.index_version
                WHERE candidate.memo_uid IN ({placeholders})
                ORDER BY candidate.score DESC, candidate.record_key ASC
                LIMIT ?
                """,
                (*ordered_uids, limit),
            ).fetchall()
            connection.commit()

        active_generation = meta["active_generation"]
        revision = meta["snapshot_revision"]
        return DerivedCandidateSnapshot(
            active_generation=active_generation,
            snapshot_token=_snapshot_token(revision, active_generation),
            candidates=tuple(self._candidate_from_row(row) for row in rows),
        )

    def load_documents(
        self,
        *,
        record_keys: tuple[str, ...],
        snapshot_token: str,
    ) -> tuple[DerivedMemoDocument, ...]:
        """Load selected documents only while the candidate snapshot is current."""

        if (
            not isinstance(record_keys, tuple)
            or not record_keys
            or len(record_keys) > MAX_RETRIEVAL_LIMIT
            or len(set(record_keys)) != len(record_keys)
            or not isinstance(snapshot_token, str)
        ):
            raise ValueError("invalid document selection")

        placeholders = ",".join("?" for _ in record_keys)
        with self._connection(query_only=True) as connection:
            self._validate_schema(connection)
            connection.execute("BEGIN")
            meta = self._select_meta(connection)
            current_token = _snapshot_token(
                meta["snapshot_revision"], meta["active_generation"]
            )
            if current_token != snapshot_token:
                raise RuntimeError("derived snapshot is no longer current")
            rows = connection.execute(
                f"""
                SELECT record_key, memo_uid, document, source_sequence,
                       document_hash, rebuild_generation, index_version
                FROM r5_disposable_documents
                WHERE record_key IN ({placeholders})
                """,
                record_keys,
            ).fetchall()
            if len(rows) != len(record_keys):
                raise RuntimeError("materialized document selection is inconsistent")
            connection.commit()

        by_key = {row["record_key"]: row for row in rows}
        if len(by_key) != len(rows):
            raise RuntimeError("materialized document selection is inconsistent")
        return tuple(
            self._document_from_row(by_key[record_key]) for record_key in record_keys
        )

    def _connection(self, *, query_only: bool) -> sqlite3.Connection:
        connection = sqlite3.connect(
            self.database,
            timeout=self.timeout_seconds,
        )
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        if query_only:
            connection.execute("PRAGMA query_only = ON")
        return connection

    @staticmethod
    def _validate_schema(connection: sqlite3.Connection) -> None:
        for table, expected_columns in _EXPECTED_TABLE_COLUMNS.items():
            rows = connection.execute(f"PRAGMA table_info({table})").fetchall()
            if {row["name"] for row in rows} != expected_columns:
                raise RuntimeError("disposable repository schema is unavailable")
        trigger_rows = connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'trigger'"
        ).fetchall()
        if not _EXPECTED_TRIGGERS.issubset({row["name"] for row in trigger_rows}):
            raise RuntimeError("disposable repository schema is unavailable")

    @staticmethod
    def _select_meta(connection: sqlite3.Connection) -> sqlite3.Row:
        rows = connection.execute(
            """
            SELECT active_generation, snapshot_revision
            FROM r5_disposable_repository_meta
            WHERE singleton = 1
            """
        ).fetchall()
        if len(rows) != 1 or type(rows[0]["snapshot_revision"]) is not int:
            raise RuntimeError("disposable repository snapshot is unavailable")
        return rows[0]

    @staticmethod
    def _insert_lifecycle(
        connection: sqlite3.Connection, state: MemoLifecycleState
    ) -> None:
        connection.execute(
            """
            INSERT INTO r5_disposable_lifecycle (
                memo_uid, index_version, highest_accepted_sequence,
                accepted_event_id, accepted_event_fingerprint,
                accepted_operation, accepted_document_hash, status,
                last_applied_sequence, last_applied_event_id,
                last_applied_operation, last_applied_document_hash,
                tombstone_sequence
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
            ),
        )

    @staticmethod
    def _candidate_from_row(row: sqlite3.Row) -> DerivedMemoCandidate:
        quarantine = row["failure_quarantined"]
        if quarantine not in (0, 1):
            raise RuntimeError("disposable candidate state is invalid")
        lifecycle_state = None
        if row["lifecycle_memo_uid"] is not None:
            lifecycle_state = MemoLifecycleState(
                memo_uid=row["lifecycle_memo_uid"],
                index_version=row["lifecycle_index_version"],
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
            )
        return DerivedMemoCandidate(
            record_key=row["record_key"],
            memo_uid=row["memo_uid"],
            score=row["score"],
            source_sequence=row["source_sequence"],
            document_hash=row["document_hash"],
            rebuild_generation=row["rebuild_generation"],
            index_version=row["index_version"],
            lifecycle_state=lifecycle_state,
            failure_quarantined=bool(quarantine),
        )

    @staticmethod
    def _document_from_row(row: sqlite3.Row) -> DerivedMemoDocument:
        return DerivedMemoDocument(
            record_key=row["record_key"],
            memo_uid=row["memo_uid"],
            document=row["document"],
            source_sequence=row["source_sequence"],
            document_hash=row["document_hash"],
            rebuild_generation=row["rebuild_generation"],
            index_version=row["index_version"],
        )


def _snapshot_token(revision: int, active_generation: str | None) -> str:
    generation_digest = hashlib.sha256(
        (active_generation or "unknown-generation").encode("utf-8")
    ).hexdigest()[:12]
    return f"snapshot-{revision}-{generation_digest}"


_SCHEMA = """
CREATE TABLE IF NOT EXISTS r5_disposable_repository_meta (
    singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
    active_generation TEXT,
    snapshot_revision INTEGER NOT NULL DEFAULT 0
        CHECK (snapshot_revision >= 0)
);
INSERT OR IGNORE INTO r5_disposable_repository_meta (
    singleton, active_generation, snapshot_revision
) VALUES (1, NULL, 0);

CREATE TABLE IF NOT EXISTS r5_disposable_candidates (
    record_key TEXT PRIMARY KEY,
    memo_uid TEXT NOT NULL,
    score REAL NOT NULL,
    source_sequence INTEGER NOT NULL CHECK (source_sequence > 0),
    document_hash TEXT NOT NULL CHECK (length(document_hash) = 64),
    rebuild_generation TEXT NOT NULL,
    index_version TEXT NOT NULL,
    failure_quarantined INTEGER NOT NULL DEFAULT 0
        CHECK (failure_quarantined IN (0, 1))
);
CREATE UNIQUE INDEX IF NOT EXISTS r5_disposable_generation_memo
ON r5_disposable_candidates (rebuild_generation, index_version, memo_uid);

CREATE TABLE IF NOT EXISTS r5_disposable_lifecycle (
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
    PRIMARY KEY (memo_uid, index_version)
);

CREATE TABLE IF NOT EXISTS r5_disposable_documents (
    record_key TEXT PRIMARY KEY,
    memo_uid TEXT NOT NULL,
    document TEXT NOT NULL,
    source_sequence INTEGER NOT NULL CHECK (source_sequence > 0),
    document_hash TEXT NOT NULL CHECK (length(document_hash) = 64),
    rebuild_generation TEXT NOT NULL,
    index_version TEXT NOT NULL,
    FOREIGN KEY (record_key) REFERENCES r5_disposable_candidates(record_key)
        ON DELETE CASCADE
);

CREATE TRIGGER IF NOT EXISTS r5_revision_active_generation
AFTER UPDATE OF active_generation ON r5_disposable_repository_meta
WHEN OLD.active_generation IS NOT NEW.active_generation
BEGIN
    UPDATE r5_disposable_repository_meta
    SET snapshot_revision = snapshot_revision + 1
    WHERE singleton = 1;
END;
""" + "\n".join(
    f"""
CREATE TRIGGER IF NOT EXISTS r5_revision_{table}_{operation}
AFTER {operation.upper()} ON r5_disposable_{table}
BEGIN
    UPDATE r5_disposable_repository_meta
    SET snapshot_revision = snapshot_revision + 1
    WHERE singleton = 1;
END;
"""
    for table in ("candidates", "lifecycle", "documents")
    for operation in ("insert", "update", "delete")
)
