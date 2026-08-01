import sqlite3

import pytest

from app.adapters.agent_lifecycle_ledger import SQLiteMemoLifecycleLedger
from app.domain.agent_lifecycle import (
    LifecycleContractError,
    MemoLifecycleEvent,
    hash_lifecycle_document,
)
from app.services.agent_lifecycle_processor import MemoLifecycleProcessor


DOCUMENT = "# Synthetic memo\n\nA4-I3 temporary ledger proof."


class SimulatedProcessCrash(BaseException):
    pass


class FakeLifecycleVectorWriter:
    def __init__(self) -> None:
        self.records: dict[str, dict[str, object]] = {}
        self.upsert_attempts = 0
        self.delete_attempts = 0
        self.fail_next = False
        self.crash_after_mutation = False

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
            raise RuntimeError(f"unsafe writer detail: {document}")
        self.records[memo_uid] = {
            "source_sequence": source_sequence,
            "document_hash": document_hash,
            "index_version": index_version,
        }
        if self.crash_after_mutation:
            self.crash_after_mutation = False
            raise SimulatedProcessCrash

    def delete_memo(self, *, memo_uid: str, index_version: str) -> None:
        self.delete_attempts += 1
        self.records.pop(memo_uid, None)
        if self.crash_after_mutation:
            self.crash_after_mutation = False
            raise SimulatedProcessCrash


def _event(sequence: int = 1, **overrides: object) -> MemoLifecycleEvent:
    payload: dict[str, object] = {
        "event_id": f"event-{sequence}",
        "event_type": (
            "memo.index.requested.v1"
            if sequence == 1
            else "memo.reindex.requested.v1"
        ),
        "memo_uid": "memo-ledger",
        "source_sequence": sequence,
        "index_version": "memo-v1",
        "operation": "upsert",
        "reason": "created" if sequence == 1 else "content_changed",
        "occurred_at": "2026-08-01T12:00:00+08:00",
        "document": DOCUMENT,
        "document_hash": hash_lifecycle_document(DOCUMENT),
    }
    payload.update(overrides)
    return MemoLifecycleEvent.from_dict(payload)


def _delete_event(sequence: int, **overrides: object) -> MemoLifecycleEvent:
    payload: dict[str, object] = {
        "event_id": f"event-{sequence}",
        "event_type": "memo.delete.requested.v1",
        "memo_uid": "memo-ledger",
        "source_sequence": sequence,
        "index_version": "memo-v1",
        "operation": "delete",
        "reason": "deleted",
        "occurred_at": "2026-08-01T12:00:00+08:00",
    }
    payload.update(overrides)
    return MemoLifecycleEvent.from_dict(payload)


def test_sqlite_ledger_persists_reservation_without_raw_document(tmp_path):
    database = tmp_path / "lifecycle-ledger.db"
    ledger = SQLiteMemoLifecycleLedger(database)
    event = _event()

    transition = ledger.reserve(event)
    reopened = SQLiteMemoLifecycleLedger(database)
    state = reopened.get(event.memo_uid)

    assert transition.decision == "apply"
    assert state == transition.state
    assert state is not None
    assert state.status == "applying"
    assert state.accepted_event_id == event.event_id
    assert state.accepted_event_fingerprint != event.document_hash
    assert not reopened.retrieval_eligible(
        event.memo_uid,
        vector_source_sequence=event.source_sequence,
        vector_document_hash=event.document_hash or "",
    )

    with sqlite3.connect(database) as connection:
        columns = {
            row[1]
            for row in connection.execute(
                "PRAGMA table_info(memo_lifecycle_ledger)"
            ).fetchall()
        }
        serialized_rows = repr(
            connection.execute("SELECT * FROM memo_lifecycle_ledger").fetchall()
        )

    assert "document" not in columns
    assert "raw_document" not in columns
    assert DOCUMENT not in serialized_rows


def test_sqlite_ledger_finalizes_and_rejects_unsafe_failure_details(tmp_path):
    ledger = SQLiteMemoLifecycleLedger(tmp_path / "lifecycle-ledger.db")
    event = _event()
    ledger.reserve(event)

    completed, acknowledgement = ledger.complete(event)

    assert completed.status == "applied"
    assert acknowledgement.status == "applied"
    assert ledger.last_error_code(event.memo_uid) is None
    assert ledger.retrieval_eligible(
        event.memo_uid,
        vector_source_sequence=event.source_sequence,
        vector_document_hash=event.document_hash or "",
    )

    next_event = _event(2, event_id="event-2")
    ledger.reserve(next_event)
    with pytest.raises(LifecycleContractError, match="safe error_code"):
        ledger.fail(next_event, "raw exception: synthetic memo")

    failed, failed_ack = ledger.fail(next_event, "vector_store_unavailable")
    assert failed.status == "failed"
    assert failed_ack.error_code == "vector_store_unavailable"
    assert ledger.last_error_code(event.memo_uid) == "vector_store_unavailable"
    assert not ledger.retrieval_eligible(
        event.memo_uid,
        vector_source_sequence=event.source_sequence,
        vector_document_hash=event.document_hash or "",
    )


def test_processor_is_idempotent_for_duplicate_stale_and_conflicting_events(tmp_path):
    ledger = SQLiteMemoLifecycleLedger(tmp_path / "lifecycle-ledger.db")
    writer = FakeLifecycleVectorWriter()
    processor = MemoLifecycleProcessor(ledger, writer)
    first = _event()

    assert processor.process(first).status == "applied"
    assert processor.process(first).status == "duplicate"
    assert writer.upsert_attempts == 1

    second_document = "updated synthetic memo"
    second = _event(
        2,
        document=second_document,
        document_hash=hash_lifecycle_document(second_document),
    )
    assert processor.process(second).status == "applied"
    assert processor.process(first).status == "stale"

    conflict_document = "conflicting generation"
    conflict = _event(
        2,
        event_id="event-conflict",
        document=conflict_document,
        document_hash=hash_lifecycle_document(conflict_document),
    )
    conflict_ack = processor.process(conflict)
    assert conflict_ack.status == "failed"
    assert conflict_ack.error_code == "same_sequence_conflict"
    assert writer.upsert_attempts == 2
    assert not ledger.retrieval_eligible(
        first.memo_uid,
        vector_source_sequence=first.source_sequence,
        vector_document_hash=first.document_hash or "",
    )
    assert not ledger.retrieval_eligible(
        conflict.memo_uid,
        vector_source_sequence=conflict.source_sequence,
        vector_document_hash=conflict.document_hash or "",
    )


def test_processor_resumes_after_crash_between_reservation_and_vector_write(tmp_path):
    ledger = SQLiteMemoLifecycleLedger(tmp_path / "lifecycle-ledger.db")
    writer = FakeLifecycleVectorWriter()
    event = _event()

    reserved = ledger.reserve(event)
    assert reserved.state.status == "applying"
    assert writer.records == {}

    acknowledgement = MemoLifecycleProcessor(ledger, writer).process(event)

    assert acknowledgement.status == "applied"
    assert writer.upsert_attempts == 1
    assert ledger.retrieval_eligible(
        event.memo_uid,
        vector_source_sequence=event.source_sequence,
        vector_document_hash=event.document_hash or "",
    )


def test_processor_retries_idempotent_upsert_after_vector_write_crash(tmp_path):
    ledger = SQLiteMemoLifecycleLedger(tmp_path / "lifecycle-ledger.db")
    writer = FakeLifecycleVectorWriter()
    writer.crash_after_mutation = True
    processor = MemoLifecycleProcessor(ledger, writer)
    event = _event()

    with pytest.raises(SimulatedProcessCrash):
        processor.process(event)

    assert event.memo_uid in writer.records
    interrupted = ledger.get(event.memo_uid)
    assert interrupted is not None
    assert interrupted.status == "applying"
    assert not ledger.retrieval_eligible(
        event.memo_uid,
        vector_source_sequence=event.source_sequence,
        vector_document_hash=event.document_hash or "",
    )

    assert processor.process(event).status == "applied"
    assert writer.upsert_attempts == 2
    assert len(writer.records) == 1


def test_processor_retries_idempotent_tombstone_delete_after_crash(tmp_path):
    ledger = SQLiteMemoLifecycleLedger(tmp_path / "lifecycle-ledger.db")
    writer = FakeLifecycleVectorWriter()
    processor = MemoLifecycleProcessor(ledger, writer)
    indexed = _event()
    processor.process(indexed)
    deletion = _delete_event(2)
    writer.crash_after_mutation = True

    with pytest.raises(SimulatedProcessCrash):
        processor.process(deletion)

    interrupted = ledger.get(deletion.memo_uid)
    assert interrupted is not None
    assert interrupted.status == "applying"
    assert interrupted.accepted_operation == "delete"
    assert interrupted.accepted_document_hash is None
    assert interrupted.tombstone_sequence == deletion.source_sequence
    assert writer.records == {}

    assert processor.process(deletion).status == "applied"
    assert writer.delete_attempts == 2
    deleted = ledger.get(deletion.memo_uid)
    assert deleted is not None
    assert deleted.last_applied_operation == "delete"
    assert deleted.accepted_document_hash is None
    assert deleted.last_applied_document_hash is None
    assert not ledger.retrieval_eligible(
        indexed.memo_uid,
        vector_source_sequence=indexed.source_sequence,
        vector_document_hash=indexed.document_hash or "",
    )


def test_processor_quarantines_writer_failure_and_redacts_exception(tmp_path):
    database = tmp_path / "lifecycle-ledger.db"
    ledger = SQLiteMemoLifecycleLedger(database)
    writer = FakeLifecycleVectorWriter()
    writer.fail_next = True
    event = _event()

    acknowledgement = MemoLifecycleProcessor(ledger, writer).process(event)

    assert acknowledgement.status == "failed"
    assert acknowledgement.error_code == "vector_store_unavailable"
    failed = ledger.get(event.memo_uid)
    assert failed is not None
    assert failed.status == "failed"
    assert ledger.last_error_code(event.memo_uid) == "vector_store_unavailable"
    assert not ledger.retrieval_eligible(
        event.memo_uid,
        vector_source_sequence=event.source_sequence,
        vector_document_hash=event.document_hash or "",
    )
    assert DOCUMENT not in database.read_bytes().decode("utf-8", errors="ignore")

    assert MemoLifecycleProcessor(ledger, writer).process(event).status == "applied"
