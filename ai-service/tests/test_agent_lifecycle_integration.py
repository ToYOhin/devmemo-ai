import hashlib
import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import pytest

from app.adapters.agent_lifecycle_ledger import SQLiteMemoLifecycleLedger
from app.domain.agent_lifecycle import (
    LifecycleAcknowledgement,
    MemoLifecycleEvent,
    hash_lifecycle_document,
)
from app.services.agent_lifecycle_processor import MemoLifecycleProcessor
from app.services.agent_lifecycle_transport import (
    LifecycleNonceReplayStore,
    handle_lifecycle_request,
    parse_lifecycle_acknowledgement,
    prepare_lifecycle_request,
)


TRANSPORT_TIMESTAMP = 1_785_556_800
TRANSPORT_NOW = datetime.fromtimestamp(TRANSPORT_TIMESTAMP + 30, timezone.utc)
SYNTHETIC_SECRET = "synthetic-a4-i5-lifecycle-secret"


@dataclass(frozen=True)
class SourceLifecycleStats:
    pending: int
    failed: int
    exhausted: int
    produced_high_water: int
    acknowledged_high_water: int
    eligible_count: int
    manifest_digest: str


@dataclass(frozen=True)
class DerivedLifecycleStats:
    applying: int
    applied: int
    failed: int
    applied_high_water: int
    vector_count: int
    eligible_vector_count: int
    manifest_digest: str
    generation: str


@dataclass(frozen=True)
class ReconciliationResult:
    synced: bool
    reasons: tuple[str, ...]
    source: SourceLifecycleStats
    derived: DerivedLifecycleStats


class SimulatedLifecycleCrash(BaseException):
    """Model a process interruption without transport exception mapping."""


class SyntheticMemosOutbox:
    """Test-only authoritative Memo store using the real SQLite outbox schema."""

    def __init__(self, database: Path) -> None:
        self.database = database
        migration = (
            Path(__file__).resolve().parents[2]
            / "store"
            / "migration"
            / "sqlite"
            / "0.29"
            / "00__memo_index_outbox.sql"
        ).read_text(encoding="utf-8")
        with self._connection() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS synthetic_memo (
                    memo_uid TEXT PRIMARY KEY,
                    content TEXT NOT NULL,
                    row_status TEXT NOT NULL CHECK (row_status IN ('NORMAL', 'ARCHIVED'))
                )
                """
            )
            outbox_exists = connection.execute(
                """
                SELECT 1 FROM sqlite_master
                WHERE type = 'table' AND name = 'memo_index_outbox'
                """
            ).fetchone()
            if outbox_exists is None:
                connection.executescript(migration)

    def create(self, memo_uid: str, document: str, event_id: str) -> MemoLifecycleEvent:
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                "INSERT INTO synthetic_memo (memo_uid, content, row_status) VALUES (?, ?, 'NORMAL')",
                (memo_uid, document),
            )
            self._enqueue(
                connection,
                memo_uid=memo_uid,
                event_id=event_id,
                event_type="memo.index.requested.v1",
                operation="upsert",
                reason="created",
                document=document,
            )
            connection.commit()
        return self.event(event_id)

    def update(self, memo_uid: str, document: str, event_id: str) -> MemoLifecycleEvent:
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            changed = connection.execute(
                "UPDATE synthetic_memo SET content = ?, row_status = 'NORMAL' WHERE memo_uid = ?",
                (document, memo_uid),
            )
            if changed.rowcount != 1:
                raise AssertionError("synthetic Memo does not exist")
            self._enqueue(
                connection,
                memo_uid=memo_uid,
                event_id=event_id,
                event_type="memo.reindex.requested.v1",
                operation="upsert",
                reason="content_changed",
                document=document,
            )
            connection.commit()
        return self.event(event_id)

    def archive(self, memo_uid: str, event_id: str) -> MemoLifecycleEvent:
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            changed = connection.execute(
                "UPDATE synthetic_memo SET row_status = 'ARCHIVED' WHERE memo_uid = ?",
                (memo_uid,),
            )
            if changed.rowcount != 1:
                raise AssertionError("synthetic Memo does not exist")
            self._enqueue(
                connection,
                memo_uid=memo_uid,
                event_id=event_id,
                event_type="memo.delete.requested.v1",
                operation="delete",
                reason="archived",
                document=None,
            )
            connection.commit()
        return self.event(event_id)

    def delete(self, memo_uid: str, event_id: str) -> MemoLifecycleEvent:
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            exists = connection.execute(
                "SELECT 1 FROM synthetic_memo WHERE memo_uid = ?", (memo_uid,)
            ).fetchone()
            if exists is None:
                raise AssertionError("synthetic Memo does not exist")
            self._enqueue(
                connection,
                memo_uid=memo_uid,
                event_id=event_id,
                event_type="memo.delete.requested.v1",
                operation="delete",
                reason="deleted",
                document=None,
            )
            connection.execute(
                "DELETE FROM synthetic_memo WHERE memo_uid = ?", (memo_uid,)
            )
            connection.commit()
        return self.event(event_id)

    def repair(self, memo_uid: str, event_id: str) -> MemoLifecycleEvent:
        """Emit a fresh operator repair from the current authoritative snapshot."""

        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                """
                SELECT content FROM synthetic_memo
                WHERE memo_uid = ? AND row_status = 'NORMAL'
                  AND length(trim(content)) > 0
                """,
                (memo_uid,),
            ).fetchone()
            if row is None:
                raise AssertionError("synthetic Memo is not rebuild-eligible")
            self._enqueue(
                connection,
                memo_uid=memo_uid,
                event_id=event_id,
                event_type="memo.reindex.requested.v1",
                operation="upsert",
                reason="repair",
                document=row["content"],
            )
            connection.commit()
        return self.event(event_id)

    def event(self, event_id: str) -> MemoLifecycleEvent:
        with self._connection() as connection:
            row = connection.execute(
                """
                SELECT event_id, event_type, memo_uid, source_sequence,
                       index_version, operation, reason, occurred_at,
                       document, document_hash
                FROM memo_index_outbox
                WHERE event_id = ?
                """,
                (event_id,),
            ).fetchone()
        if row is None:
            raise AssertionError("synthetic lifecycle event does not exist")
        payload: dict[str, object] = {
            "event_id": row["event_id"],
            "event_type": row["event_type"],
            "memo_uid": row["memo_uid"],
            "source_sequence": row["source_sequence"],
            "index_version": row["index_version"],
            "operation": row["operation"],
            "reason": row["reason"],
            "occurred_at": row["occurred_at"],
        }
        if row["operation"] == "upsert":
            payload["document"] = row["document"]
            payload["document_hash"] = row["document_hash"]
        return MemoLifecycleEvent.from_dict(payload)

    def acknowledge(
        self,
        event: MemoLifecycleEvent,
        acknowledgement: LifecycleAcknowledgement,
    ) -> None:
        expected = (
            event.event_id,
            event.memo_uid,
            event.source_sequence,
            event.index_version,
            event.operation,
        )
        actual = (
            acknowledgement.event_id,
            acknowledgement.memo_uid,
            acknowledgement.source_sequence,
            acknowledgement.index_version,
            acknowledgement.operation,
        )
        if actual != expected or acknowledgement.status == "failed":
            raise AssertionError("unsafe or failed acknowledgement cannot finalize outbox")
        with self._connection() as connection:
            changed = connection.execute(
                """
                UPDATE memo_index_outbox
                SET status = 'ACKNOWLEDGED', last_error_code = NULL,
                    updated_ts = strftime('%s', 'now')
                WHERE event_id = ? AND memo_uid = ? AND source_sequence = ?
                  AND index_version = ? AND operation = ? AND status = 'PENDING'
                """,
                expected,
            )
            if changed.rowcount == 0:
                row = connection.execute(
                    "SELECT status FROM memo_index_outbox WHERE event_id = ?",
                    (event.event_id,),
                ).fetchone()
                if row is None or row["status"] != "ACKNOWLEDGED":
                    raise AssertionError("acknowledgement did not match pending outbox event")

    def record_failure(
        self,
        event: MemoLifecycleEvent,
        acknowledgement: LifecycleAcknowledgement,
    ) -> None:
        if (
            acknowledgement.status != "failed"
            or acknowledgement.error_code is None
            or acknowledgement.event_id != event.event_id
            or acknowledgement.memo_uid != event.memo_uid
            or acknowledgement.source_sequence != event.source_sequence
            or acknowledgement.index_version != event.index_version
            or acknowledgement.operation != event.operation
        ):
            raise AssertionError("failure acknowledgement is not a safe event projection")
        with self._connection() as connection:
            changed = connection.execute(
                """
                UPDATE memo_index_outbox
                SET attempts = attempts + 1,
                    status = CASE WHEN attempts + 1 >= 3
                                  THEN 'EXHAUSTED' ELSE 'PENDING' END,
                    last_error_code = ?, updated_ts = strftime('%s', 'now')
                WHERE event_id = ? AND status = 'PENDING' AND attempts < 3
                """,
                (acknowledgement.error_code, event.event_id),
            )
            if changed.rowcount != 1:
                raise AssertionError("failure did not match a retryable outbox event")

    def rows(self, memo_uid: str) -> list[sqlite3.Row]:
        with self._connection() as connection:
            return connection.execute(
                """
                SELECT event_id, source_sequence, event_type, operation, status,
                       attempts, last_error_code, document, document_hash
                FROM memo_index_outbox
                WHERE memo_uid = ? ORDER BY source_sequence
                """,
                (memo_uid,),
            ).fetchall()

    def eligible_snapshots(self) -> list[tuple[str, str]]:
        with self._connection() as connection:
            rows = connection.execute(
                """
                SELECT memo_uid, content FROM synthetic_memo
                WHERE row_status = 'NORMAL' AND length(trim(content)) > 0
                ORDER BY memo_uid
                """
            ).fetchall()
        return [(row["memo_uid"], row["content"]) for row in rows]

    def stats(self, memo_uid: str) -> SourceLifecycleStats:
        with self._connection() as connection:
            outbox = connection.execute(
                """
                SELECT
                    SUM(CASE WHEN status = 'PENDING' THEN 1 ELSE 0 END) AS pending,
                    SUM(CASE WHEN status = 'PENDING' AND last_error_code IS NOT NULL
                             THEN 1 ELSE 0 END) AS failed,
                    SUM(CASE WHEN status = 'EXHAUSTED' THEN 1 ELSE 0 END) AS exhausted,
                    COALESCE(MAX(source_sequence), 0) AS produced_high_water,
                    COALESCE(MAX(CASE WHEN status = 'ACKNOWLEDGED'
                                      THEN source_sequence ELSE 0 END), 0)
                        AS acknowledged_high_water
                FROM memo_index_outbox WHERE memo_uid = ?
                """,
                (memo_uid,),
            ).fetchone()
            memo = connection.execute(
                """
                SELECT content FROM synthetic_memo
                WHERE memo_uid = ? AND row_status = 'NORMAL'
                  AND length(trim(content)) > 0
                """,
                (memo_uid,),
            ).fetchone()
        manifest = [] if memo is None else [(memo_uid, hash_lifecycle_document(memo["content"]))]
        return SourceLifecycleStats(
            pending=outbox["pending"] or 0,
            failed=outbox["failed"] or 0,
            exhausted=outbox["exhausted"] or 0,
            produced_high_water=outbox["produced_high_water"],
            acknowledged_high_water=outbox["acknowledged_high_water"],
            eligible_count=len(manifest),
            manifest_digest=_manifest_digest(manifest),
        )

    def global_backlog(self) -> tuple[int, int, int]:
        with self._connection() as connection:
            row = connection.execute(
                """
                SELECT
                    SUM(CASE WHEN status = 'PENDING' THEN 1 ELSE 0 END),
                    SUM(CASE WHEN status = 'PENDING' AND last_error_code IS NOT NULL
                             THEN 1 ELSE 0 END),
                    SUM(CASE WHEN status = 'EXHAUSTED' THEN 1 ELSE 0 END)
                FROM memo_index_outbox
                """
            ).fetchone()
        return tuple(value or 0 for value in row)

    def manifest_digest(self) -> str:
        return _manifest_digest(
            (memo_uid, hash_lifecycle_document(document))
            for memo_uid, document in self.eligible_snapshots()
        )

    def _enqueue(
        self,
        connection: sqlite3.Connection,
        *,
        memo_uid: str,
        event_id: str,
        event_type: str,
        operation: str,
        reason: str,
        document: str | None,
    ) -> None:
        sequence = connection.execute(
            """
            SELECT COALESCE(MAX(source_sequence), 0) + 1
            FROM memo_index_outbox
            WHERE memo_uid = ? AND index_version = 'memo-v1'
            """,
            (memo_uid,),
        ).fetchone()[0]
        occurred_at = datetime(2026, 8, 1, 4, 0, sequence, tzinfo=timezone.utc).isoformat()
        document_hash = hash_lifecycle_document(document) if document is not None else None
        connection.execute(
            """
            INSERT INTO memo_index_outbox (
                event_id, memo_uid, source_sequence, event_type, index_version,
                operation, reason, occurred_at, document, document_hash
            ) VALUES (?, ?, ?, ?, 'memo-v1', ?, ?, ?, ?, ?)
            """,
            (
                event_id,
                memo_uid,
                sequence,
                event_type,
                operation,
                reason,
                occurred_at,
                document,
                document_hash,
            ),
        )

    def _connection(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database)
        connection.row_factory = sqlite3.Row
        return connection


class DisposableSQLiteVectorWriter:
    """Stable fake vector writer that persists no raw document."""

    def __init__(self, database: Path, generation: str = "integration-v1") -> None:
        self.database = database
        self.generation = generation
        self.upsert_attempts = 0
        self.delete_attempts = 0
        self.fail_next = False
        self.crash_after_mutation = False
        with self._connection() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS fake_memo_vectors (
                    memo_uid TEXT PRIMARY KEY,
                    source_sequence INTEGER NOT NULL,
                    document_hash TEXT NOT NULL,
                    index_version TEXT NOT NULL,
                    generation TEXT NOT NULL
                )
                """
            )

    def upsert_memo(
        self,
        *,
        memo_uid: str,
        document: str,
        source_sequence: int,
        document_hash: str,
        index_version: str,
    ) -> None:
        self.upsert_attempts += 1
        if self.fail_next:
            self.fail_next = False
            raise RuntimeError(f"unsafe fake-vector detail: {document}")
        with self._connection() as connection:
            connection.execute(
                """
                INSERT INTO fake_memo_vectors (
                    memo_uid, source_sequence, document_hash, index_version, generation
                ) VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(memo_uid) DO UPDATE SET
                    source_sequence = excluded.source_sequence,
                    document_hash = excluded.document_hash,
                    index_version = excluded.index_version,
                    generation = excluded.generation
                """,
                (
                    memo_uid,
                    source_sequence,
                    document_hash,
                    index_version,
                    self.generation,
                ),
            )
        if self.crash_after_mutation:
            self.crash_after_mutation = False
            raise SimulatedLifecycleCrash

    def delete_memo(self, *, memo_uid: str, index_version: str) -> None:
        self.delete_attempts += 1
        with self._connection() as connection:
            connection.execute(
                "DELETE FROM fake_memo_vectors WHERE memo_uid = ? AND index_version = ?",
                (memo_uid, index_version),
            )
        if self.crash_after_mutation:
            self.crash_after_mutation = False
            raise SimulatedLifecycleCrash

    def records(self) -> list[sqlite3.Row]:
        with self._connection() as connection:
            return connection.execute(
                "SELECT * FROM fake_memo_vectors ORDER BY memo_uid"
            ).fetchall()

    def overwrite_hash(self, memo_uid: str, document_hash: str) -> None:
        with self._connection() as connection:
            changed = connection.execute(
                "UPDATE fake_memo_vectors SET document_hash = ? WHERE memo_uid = ?",
                (document_hash, memo_uid),
            )
            if changed.rowcount != 1:
                raise AssertionError("fake vector does not exist")

    def manifest_digest(self, records: list[sqlite3.Row] | None = None) -> str:
        selected = self.records() if records is None else records
        return _manifest_digest(
            (row["memo_uid"], row["document_hash"]) for row in selected
        )

    def _connection(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database)
        connection.row_factory = sqlite3.Row
        return connection


class LifecycleIntegrationHarness:
    """One process-local authenticated delivery attempt over disposable stores."""

    def __init__(
        self,
        source: SyntheticMemosOutbox,
        ledger_database: Path,
        vector_database: Path,
        *,
        generation: str = "integration-v1",
    ) -> None:
        self.source = source
        self.ledger = SQLiteMemoLifecycleLedger(ledger_database)
        self.writer = DisposableSQLiteVectorWriter(vector_database, generation)
        self.replay_store = LifecycleNonceReplayStore()
        self.last_response: bytes | None = None

    def deliver(
        self,
        event_id: str,
        nonce: str,
        *,
        crash_point: str | None = None,
    ) -> LifecycleAcknowledgement:
        event = self.source.event(event_id)
        if crash_point == "before_send":
            raise SimulatedLifecycleCrash
        request = prepare_lifecycle_request(
            event, TRANSPORT_TIMESTAMP, nonce, SYNTHETIC_SECRET
        )
        processor: object = MemoLifecycleProcessor(self.ledger, self.writer)
        if crash_point == "after_reservation":
            processor = CrashAfterReservationProcessor(self.ledger)
        elif crash_point == "after_vector_write":
            self.writer.crash_after_mutation = True
        response = handle_lifecycle_request(
            request,
            SYNTHETIC_SECRET,
            TRANSPORT_NOW,
            self.replay_store,
            processor,
        )
        self.last_response = response
        acknowledgement = parse_lifecycle_acknowledgement(response, event)
        if crash_point == "before_acknowledgement":
            raise SimulatedLifecycleCrash
        if acknowledgement.status == "failed":
            self.source.record_failure(event, acknowledgement)
            return acknowledgement
        state = self.ledger.get(event.memo_uid)
        if acknowledgement.status in {"applied", "duplicate"}:
            if (
                state is None
                or state.status != "applied"
                or state.last_applied_sequence != event.source_sequence
                or state.last_applied_event_id != event.event_id
            ):
                raise AssertionError("outbox acknowledgement preceded ledger finalize")
        self.source.acknowledge(event, acknowledgement)
        return acknowledgement

    def reconcile(self, memo_uid: str) -> ReconciliationResult:
        source = self.source.stats(memo_uid)
        state = self.ledger.get(memo_uid)
        vector_records = [
            row for row in self.writer.records() if row["memo_uid"] == memo_uid
        ]
        eligible_records = [
            row
            for row in vector_records
            if self.ledger.retrieval_eligible(
                memo_uid,
                vector_source_sequence=row["source_sequence"],
                vector_document_hash=row["document_hash"],
            )
        ]
        derived = DerivedLifecycleStats(
            applying=int(state is not None and state.status == "applying"),
            applied=int(state is not None and state.status == "applied"),
            failed=int(state is not None and state.status == "failed"),
            applied_high_water=(
                state.last_applied_sequence
                if state is not None and state.last_applied_sequence is not None
                else 0
            ),
            vector_count=len(vector_records),
            eligible_vector_count=len(eligible_records),
            manifest_digest=self.writer.manifest_digest(eligible_records),
            generation=self.writer.generation,
        )
        reasons: list[str] = []
        if source.pending:
            reasons.append("pending_backlog")
        if source.failed:
            reasons.append("failed_delivery")
        if source.exhausted:
            reasons.append("exhausted_delivery")
        if derived.applying or derived.failed:
            reasons.append("derived_state_incomplete")
        if source.acknowledged_high_water != source.produced_high_water:
            reasons.append("source_ack_high_water_mismatch")
        if derived.applied_high_water != source.produced_high_water:
            reasons.append("applied_high_water_mismatch")
        if source.eligible_count != derived.eligible_vector_count:
            reasons.append("eligible_count_mismatch")
        if source.manifest_digest != derived.manifest_digest:
            reasons.append("manifest_digest_mismatch")
        return ReconciliationResult(not reasons, tuple(reasons), source, derived)


class CrashAfterReservationProcessor:
    def __init__(self, ledger: SQLiteMemoLifecycleLedger) -> None:
        self.ledger = ledger

    def process(self, event: MemoLifecycleEvent) -> LifecycleAcknowledgement:
        self.ledger.reserve(event)
        raise SimulatedLifecycleCrash


def _manifest_digest(entries) -> str:
    serialized = json.dumps(
        sorted(entries), ensure_ascii=False, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(serialized).hexdigest()


def _rebuild_validation(
    source: SyntheticMemosOutbox,
    harness: LifecycleIntegrationHarness,
    expected_generation: str,
) -> tuple[bool, tuple[str, ...]]:
    reasons: list[str] = []
    pending, failed, exhausted = source.global_backlog()
    records = harness.writer.records()
    eligible_snapshots = source.eligible_snapshots()
    if pending or failed or exhausted:
        reasons.append("source_backlog_not_clear")
    if len(records) != len(eligible_snapshots):
        reasons.append("rebuild_count_mismatch")
    if source.manifest_digest() != harness.writer.manifest_digest(records):
        reasons.append("rebuild_manifest_mismatch")
    if any(row["generation"] != expected_generation for row in records):
        reasons.append("rebuild_generation_mismatch")
    for row in records:
        state = harness.ledger.get(row["memo_uid"])
        if (
            state is None
            or state.status != "applied"
            or not harness.ledger.retrieval_eligible(
                row["memo_uid"],
                vector_source_sequence=row["source_sequence"],
                vector_document_hash=row["document_hash"],
            )
        ):
            reasons.append("rebuild_state_incomplete")
            break
    return not reasons, tuple(reasons)


def test_synthetic_create_update_archive_delete_converges_through_authenticated_harness(
    tmp_path: Path,
):
    source = SyntheticMemosOutbox(tmp_path / "memos.db")
    harness = LifecycleIntegrationHarness(
        source, tmp_path / "ai-ledger.db", tmp_path / "fake-vectors.db"
    )
    memo_uid = "synthetic-lifecycle-memo"

    source.create(memo_uid, "synthetic create document", "event-create-1")
    first = harness.deliver("event-create-1", "a4i5-create-nonce-0001")
    assert first.status == "applied"
    assert len(harness.writer.records()) == 1

    source.update(memo_uid, "synthetic updated document", "event-update-2")
    second = harness.deliver("event-update-2", "a4i5-update-nonce-0002")
    assert second.status == "applied"
    assert len(harness.writer.records()) == 1
    assert harness.writer.records()[0]["source_sequence"] == 2

    source.archive(memo_uid, "event-archive-3")
    archived = harness.deliver("event-archive-3", "a4i5-archive-nonce-0003")
    assert archived.status == "applied"
    assert harness.writer.records() == []

    source.delete(memo_uid, "event-delete-4")
    deleted = harness.deliver("event-delete-4", "a4i5-delete-nonce-0004")
    assert deleted.status == "applied"
    assert harness.writer.records() == []

    rows = source.rows(memo_uid)
    assert [row["source_sequence"] for row in rows] == [1, 2, 3, 4]
    assert [row["status"] for row in rows] == ["ACKNOWLEDGED"] * 4
    assert rows[2]["document"] is None
    assert rows[3]["document_hash"] is None
    assert harness.last_response is not None
    assert set(json.loads(harness.last_response)) == {
        "event_id",
        "memo_uid",
        "source_sequence",
        "index_version",
        "status",
        "operation",
    }
    ledger_state = harness.ledger.get(memo_uid)
    assert ledger_state is not None
    assert ledger_state.last_applied_sequence == 4
    assert ledger_state.last_applied_operation == "delete"
    assert "synthetic updated document" not in (
        tmp_path / "ai-ledger.db"
    ).read_bytes().decode("utf-8", errors="ignore")
    assert "synthetic updated document" not in (
        tmp_path / "fake-vectors.db"
    ).read_bytes().decode("utf-8", errors="ignore")


@pytest.mark.parametrize(
    ("crash_point", "expected_replay_status"),
    [
        ("before_send", "applied"),
        ("after_reservation", "applied"),
        ("after_vector_write", "applied"),
        ("before_acknowledgement", "duplicate"),
    ],
)
def test_restart_and_replay_converges_after_each_delivery_interruption(
    tmp_path: Path,
    crash_point: str,
    expected_replay_status: str,
):
    case_path = tmp_path / crash_point
    case_path.mkdir()
    source = SyntheticMemosOutbox(case_path / "memos.db")
    source.create("restart-memo", "restart-safe synthetic document", "event-restart-1")
    first_process = LifecycleIntegrationHarness(
        source, case_path / "ai-ledger.db", case_path / "fake-vectors.db"
    )

    with pytest.raises(SimulatedLifecycleCrash):
        first_process.deliver(
            "event-restart-1",
            f"a4i5-{crash_point}-0001",
            crash_point=crash_point,
        )

    assert source.rows("restart-memo")[0]["status"] == "PENDING"
    restarted_source = SyntheticMemosOutbox(case_path / "memos.db")
    restarted_process = LifecycleIntegrationHarness(
        restarted_source, case_path / "ai-ledger.db", case_path / "fake-vectors.db"
    )
    acknowledgement = restarted_process.deliver(
        "event-restart-1", f"a4i5-{crash_point}-0002"
    )

    assert acknowledgement.status == expected_replay_status
    assert restarted_source.rows("restart-memo")[0]["status"] == "ACKNOWLEDGED"
    assert len(restarted_process.writer.records()) == 1
    assert restarted_process.writer.records()[0]["source_sequence"] == 1
    state = restarted_process.ledger.get("restart-memo")
    assert state is not None
    assert state.status == "applied"
    assert restarted_process.ledger.retrieval_eligible(
        "restart-memo",
        vector_source_sequence=1,
        vector_document_hash=hash_lifecycle_document(
            "restart-safe synthetic document"
        ),
    )


def test_vector_failure_is_safe_retryable_and_acknowledged_only_after_finalize(
    tmp_path: Path,
):
    source = SyntheticMemosOutbox(tmp_path / "memos.db")
    source.create("retry-memo", "retry synthetic document", "event-retry-1")
    failing_process = LifecycleIntegrationHarness(
        source, tmp_path / "ai-ledger.db", tmp_path / "fake-vectors.db"
    )
    failing_process.writer.fail_next = True

    failed = failing_process.deliver("event-retry-1", "a4i5-retry-nonce-0001")

    assert failed.status == "failed"
    assert failed.error_code == "vector_store_unavailable"
    failed_row = source.rows("retry-memo")[0]
    assert failed_row["status"] == "PENDING"
    assert failed_row["attempts"] == 1
    assert failed_row["last_error_code"] == "vector_store_unavailable"
    assert failing_process.writer.records() == []
    failed_state = failing_process.ledger.get("retry-memo")
    assert failed_state is not None
    assert failed_state.status == "failed"

    restarted_process = LifecycleIntegrationHarness(
        source, tmp_path / "ai-ledger.db", tmp_path / "fake-vectors.db"
    )
    applied = restarted_process.deliver("event-retry-1", "a4i5-retry-nonce-0002")

    assert applied.status == "applied"
    recovered_row = source.rows("retry-memo")[0]
    assert recovered_row["status"] == "ACKNOWLEDGED"
    assert recovered_row["last_error_code"] is None
    assert len(restarted_process.writer.records()) == 1
    reconciliation = restarted_process.reconcile("retry-memo")
    assert reconciliation.synced
    assert reconciliation.reasons == ()


def test_backlog_failure_and_exhaustion_block_synced_projection(tmp_path: Path):
    source = SyntheticMemosOutbox(tmp_path / "memos.db")
    source.create("exhausted-memo", "bounded failure document", "event-exhausted-1")

    initial = LifecycleIntegrationHarness(
        source, tmp_path / "ai-ledger.db", tmp_path / "fake-vectors.db"
    )
    before_delivery = initial.reconcile("exhausted-memo")
    assert not before_delivery.synced
    assert "pending_backlog" in before_delivery.reasons
    assert before_delivery.source.produced_high_water == 1
    assert before_delivery.source.acknowledged_high_water == 0

    for attempt in range(1, 4):
        process = LifecycleIntegrationHarness(
            source, tmp_path / "ai-ledger.db", tmp_path / "fake-vectors.db"
        )
        process.writer.fail_next = True
        acknowledgement = process.deliver(
            "event-exhausted-1", f"a4i5-exhausted-{attempt:04d}"
        )
        assert acknowledgement.status == "failed"

    exhausted_row = source.rows("exhausted-memo")[0]
    assert exhausted_row["attempts"] == 3
    assert exhausted_row["status"] == "EXHAUSTED"
    exhausted = process.reconcile("exhausted-memo")
    assert not exhausted.synced
    assert exhausted.source.pending == 0
    assert exhausted.source.failed == 0
    assert exhausted.source.exhausted == 1
    assert "exhausted_delivery" in exhausted.reasons
    assert "derived_state_incomplete" in exhausted.reasons
    assert "bounded failure document" not in repr(exhausted)


def test_tombstone_blocks_delayed_upsert_and_old_acknowledgement(tmp_path: Path):
    source = SyntheticMemosOutbox(tmp_path / "memos.db")
    source.create("tombstone-memo", "soon deleted document", "event-index-1")
    harness = LifecycleIntegrationHarness(
        source, tmp_path / "ai-ledger.db", tmp_path / "fake-vectors.db"
    )
    original_ack = harness.deliver("event-index-1", "a4i5-tombstone-index-0001")
    deletion = source.delete("tombstone-memo", "event-delete-2")
    delete_ack = harness.deliver("event-delete-2", "a4i5-tombstone-delete-0002")

    assert delete_ack.status == "applied"
    assert harness.writer.records() == []
    assert harness.reconcile("tombstone-memo").synced

    restarted = LifecycleIntegrationHarness(
        source, tmp_path / "ai-ledger.db", tmp_path / "fake-vectors.db"
    )
    delayed = restarted.deliver("event-index-1", "a4i5-tombstone-delayed-0003")
    assert delayed.status == "stale"
    assert restarted.writer.records() == []
    state = restarted.ledger.get("tombstone-memo")
    assert state is not None
    assert state.tombstone_sequence == 2
    assert state.last_applied_operation == "delete"

    with pytest.raises(AssertionError, match="unsafe or failed acknowledgement"):
        source.acknowledge(deletion, original_ack)
    assert source.rows("tombstone-memo")[1]["status"] == "ACKNOWLEDGED"


def test_discarded_derived_state_rebuilds_from_synthetic_memos_and_gates_activation(
    tmp_path: Path,
):
    source = SyntheticMemosOutbox(tmp_path / "memos.db")
    ledger_database = tmp_path / "ai-ledger.db"
    vector_database = tmp_path / "fake-vectors.db"
    initial = LifecycleIntegrationHarness(source, ledger_database, vector_database)

    source.create("kept-memo", "authoritative rebuild document", "event-kept-1")
    initial.deliver("event-kept-1", "a4i5-rebuild-kept-0001")
    source.create("archived-memo", "must not be rebuilt", "event-archived-1")
    initial.deliver("event-archived-1", "a4i5-rebuild-archived-0001")
    source.archive("archived-memo", "event-archived-2")
    initial.deliver("event-archived-2", "a4i5-rebuild-archived-0002")
    assert [row["memo_uid"] for row in initial.writer.records()] == ["kept-memo"]

    discarded_ledger_database = ledger_database
    discarded_vector_database = vector_database
    ledger_database = tmp_path / "rebuilt-ai-ledger.db"
    vector_database = tmp_path / "rebuilt-fake-vectors.db"
    assert discarded_ledger_database.exists()
    assert discarded_vector_database.exists()
    assert not ledger_database.exists()
    assert not vector_database.exists()
    generation = "synthetic-rebuild-generation-2"
    rebuilt = LifecycleIntegrationHarness(
        source, ledger_database, vector_database, generation=generation
    )
    source.repair("kept-memo", "event-kept-rebuild-2")
    rebuilt.deliver("event-kept-rebuild-2", "a4i5-rebuild-repair-0002")

    can_activate, reasons = _rebuild_validation(source, rebuilt, generation)
    assert can_activate
    assert reasons == ()
    assert [row["memo_uid"] for row in rebuilt.writer.records()] == ["kept-memo"]
    assert "must not be rebuilt" not in vector_database.read_bytes().decode(
        "utf-8", errors="ignore"
    )

    rebuilt.writer.overwrite_hash("kept-memo", "0" * 64)
    can_activate, reasons = _rebuild_validation(source, rebuilt, generation)
    assert not can_activate
    assert "rebuild_manifest_mismatch" in reasons
    assert not rebuilt.reconcile("kept-memo").synced

    source.repair("kept-memo", "event-kept-repair-3")
    repaired = LifecycleIntegrationHarness(
        source, ledger_database, vector_database, generation=generation
    )
    repaired.deliver("event-kept-repair-3", "a4i5-rebuild-repair-0003")
    can_activate, reasons = _rebuild_validation(source, repaired, generation)
    assert can_activate
    assert reasons == ()
