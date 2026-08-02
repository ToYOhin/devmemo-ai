from __future__ import annotations

from dataclasses import replace

import pytest

from app.adapters.agent_lifecycle_ledger import (
    LifecycleSnapshotAuthority,
    SQLiteMemoLifecycleLedger,
)
from app.adapters.durable_vector_candidate_repository import (
    DurableCandidateRepositoryError,
    DurableVectorCandidateRepository,
    LifecycleSnapshotReader,
)
from app.adapters.embedding import DeterministicEmbeddingProvider
from app.adapters.vector_store import InMemoryVectorStore
from app.domain.agent_lifecycle import (
    MemoLifecycleEvent,
    MemoLifecycleState,
    hash_lifecycle_document,
)
from app.domain.embeddings import VectorRecord, VectorSearchResult


DOCUMENT = "# Synthetic durable candidate"
DOCUMENT_HASH = hash_lifecycle_document(DOCUMENT)


def _state(**overrides: object) -> MemoLifecycleState:
    values: dict[str, object] = {
        "memo_uid": "memo-a",
        "highest_accepted_sequence": 1,
        "accepted_event_id": "event-a",
        "accepted_event_fingerprint": "a" * 64,
        "accepted_operation": "upsert",
        "accepted_document_hash": DOCUMENT_HASH,
        "status": "applied",
        "last_applied_sequence": 1,
        "last_applied_event_id": "event-a",
        "last_applied_operation": "upsert",
        "last_applied_document_hash": DOCUMENT_HASH,
    }
    values.update(overrides)
    return MemoLifecycleState(**values)


class FakeLedger:
    def __init__(self, state: MemoLifecycleState | None = None) -> None:
        self.state = state or _state()
        self.snapshots = [
            LifecycleSnapshotAuthority("generation-a", 3, "snapshot-a")
        ]

    def read_snapshot_authority(self) -> LifecycleSnapshotAuthority:
        if len(self.snapshots) > 1:
            return self.snapshots.pop(0)
        return self.snapshots[0]

    def get(self, memo_uid: str, index_version: str) -> MemoLifecycleState | None:
        return self.state if memo_uid == self.state.memo_uid else None


def _repository(
    *,
    metadata: dict[str, object] | None = None,
    ledger: LifecycleSnapshotReader | None = None,
) -> DurableVectorCandidateRepository:
    provider = DeterministicEmbeddingProvider()
    store = InMemoryVectorStore(dimension=8)
    store.upsert(
        VectorRecord(
            "record-a",
            "memo-a",
            provider.embed("question").values,
            metadata
            or {
                "source_sequence": 1,
                "document_hash": DOCUMENT_HASH,
                "rebuild_generation": "generation-a",
                "index_version": "memo-v1",
            },
        )
    )
    return DurableVectorCandidateRepository(provider, store, ledger or FakeLedger())


def test_repository_returns_only_content_free_applied_current_candidates():
    snapshot = _repository().find_candidates(
        question="question", authorized_memo_uids=frozenset({"memo-a"}), limit=1
    )

    assert snapshot.active_generation == "generation-a"
    assert snapshot.snapshot_token == "snapshot-a"
    assert len(snapshot.candidates) == 1
    assert snapshot.candidates[0].memo_uid == "memo-a"
    assert not hasattr(snapshot.candidates[0], "document")


def test_repository_joins_reopened_real_lifecycle_ledger(tmp_path):
    ledger = SQLiteMemoLifecycleLedger(tmp_path / "derived.db")
    ledger.select_active_generation("generation-a")
    event = MemoLifecycleEvent.from_dict(
        {
            "event_id": "event-a",
            "event_type": "memo.index.requested.v1",
            "memo_uid": "memo-a",
            "source_sequence": 1,
            "index_version": "memo-v1",
            "operation": "upsert",
            "reason": "created",
            "occurred_at": "2026-08-03T12:00:00+08:00",
            "document": DOCUMENT,
            "document_hash": DOCUMENT_HASH,
        }
    )
    ledger.reserve(event)
    ledger.complete(event)

    snapshot = _repository(
        ledger=SQLiteMemoLifecycleLedger(tmp_path / "derived.db")
    ).find_candidates(
        question="question", authorized_memo_uids=frozenset({"memo-a"}), limit=1
    )

    assert [candidate.memo_uid for candidate in snapshot.candidates] == ["memo-a"]


def test_repository_rejects_vector_metadata_containing_content():
    repository = _repository(
        metadata={
            "content": DOCUMENT,
            "source_sequence": 1,
            "document_hash": DOCUMENT_HASH,
            "rebuild_generation": "generation-a",
            "index_version": "memo-v1",
        }
    )

    with pytest.raises(DurableCandidateRepositoryError):
        repository.find_candidates(
            question="question", authorized_memo_uids=frozenset({"memo-a"}), limit=1
        )


def test_repository_rejects_snapshot_change_during_candidate_read():
    ledger = FakeLedger()
    ledger.snapshots = [
        LifecycleSnapshotAuthority("generation-a", 3, "snapshot-a"),
        LifecycleSnapshotAuthority("generation-a", 4, "snapshot-b"),
    ]

    with pytest.raises(DurableCandidateRepositoryError):
        _repository(ledger=ledger).find_candidates(
            question="question", authorized_memo_uids=frozenset({"memo-a"}), limit=1
        )


@pytest.mark.parametrize(
    ("metadata", "state"),
    [
        (
            {
                "source_sequence": 2,
                "document_hash": DOCUMENT_HASH,
                "rebuild_generation": "generation-a",
                "index_version": "memo-v1",
            },
            _state(),
        ),
        (
            {
                "source_sequence": 1,
                "document_hash": DOCUMENT_HASH,
                "rebuild_generation": "generation-old",
                "index_version": "memo-v1",
            },
            _state(),
        ),
        (
            None,
            replace(
                _state(),
                highest_accepted_sequence=2,
                accepted_event_id="event-delete",
                accepted_event_fingerprint="b" * 64,
                accepted_operation="delete",
                accepted_document_hash=None,
                status="applied",
                last_applied_sequence=2,
                last_applied_event_id="event-delete",
                last_applied_operation="delete",
                last_applied_document_hash=None,
                tombstone_sequence=2,
            ),
        ),
        (
            None,
            replace(
                _state(),
                highest_accepted_sequence=2,
                accepted_event_id="event-failed",
                accepted_event_fingerprint="c" * 64,
                status="failed",
            ),
        ),
    ],
)
def test_repository_omits_stale_inactive_deleted_and_quarantined_candidates(
    metadata: dict[str, object] | None, state: MemoLifecycleState
):
    snapshot = _repository(metadata=metadata, ledger=FakeLedger(state)).find_candidates(
        question="question", authorized_memo_uids=frozenset({"memo-a"}), limit=1
    )

    assert snapshot.candidates == ()


def test_repository_rejects_missing_candidate_metadata():
    with pytest.raises(DurableCandidateRepositoryError):
        _repository(metadata={"source_sequence": 1}).find_candidates(
            question="question", authorized_memo_uids=frozenset({"memo-a"}), limit=1
        )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("document_hash", "not-a-hash"),
        ("rebuild_generation", "contains spaces"),
        ("index_version", "memo-chunk-v1"),
    ],
)
def test_repository_rejects_unknown_candidate_metadata(field, value):
    metadata = {
        "source_sequence": 1,
        "document_hash": DOCUMENT_HASH,
        "rebuild_generation": "generation-a",
        "index_version": "memo-v1",
    }
    metadata[field] = value

    with pytest.raises(DurableCandidateRepositoryError):
        _repository(metadata=metadata).find_candidates(
            question="question", authorized_memo_uids=frozenset({"memo-a"}), limit=1
        )


def test_repository_rejects_duplicate_candidate_identity():
    provider = DeterministicEmbeddingProvider()

    class DuplicateStore:
        dimension = provider.dimension

        def search_visible_memos(self, query, visible_memo_ids, limit=5):
            result = VectorSearchResult(
                "record-a",
                "memo-a",
                0.9,
                {
                    "source_sequence": 1,
                    "document_hash": DOCUMENT_HASH,
                    "rebuild_generation": "generation-a",
                    "index_version": "memo-v1",
                },
            )
            return [result, result]

    repository = DurableVectorCandidateRepository(provider, DuplicateStore(), FakeLedger())

    with pytest.raises(DurableCandidateRepositoryError):
        repository.find_candidates(
            question="question", authorized_memo_uids=frozenset({"memo-a"}), limit=1
        )
