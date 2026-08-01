from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from app.adapters.disposable_sqlite_authorized_retrieval import (
    DisposableSQLiteAuthorizedRetrievalRepository,
)
from app.domain.agent_lifecycle import (
    MemoLifecycleEvent,
    MemoLifecycleState,
    accept_lifecycle_event,
    complete_lifecycle_event,
    fail_lifecycle_event,
    hash_lifecycle_document,
)
from app.domain.durable_authorized_retrieval import (
    AuthorizedRetrievalQuery,
    DerivedCandidateSnapshot,
    DerivedMemoCandidate,
    DerivedMemoDocument,
)
from app.services.durable_authorized_retrieval import (
    DurableAuthorizedRetrievalService,
    DurableAuthorizedRetrievalUnavailableError,
)


VISIBLE_DOCUMENT = "# Synthetic visible Memo\n\nDisposable SQLite parity evidence."
SECOND_DOCUMENT = "# Synthetic second Memo\n\nA lower-ranked authorized result."
HIDDEN_DOCUMENT = "# Synthetic hidden Memo\n\nThis must never be materialized."
ACTIVE_GENERATION = "generation-active"
_DEFAULT_STATE = object()


def _event(
    memo_uid: str,
    document: str,
    *,
    sequence: int = 1,
) -> MemoLifecycleEvent:
    return MemoLifecycleEvent.from_dict(
        {
            "event_id": f"event-{memo_uid}-{sequence}",
            "event_type": "memo.index.requested.v1",
            "memo_uid": memo_uid,
            "source_sequence": sequence,
            "index_version": "memo-v1",
            "operation": "upsert",
            "reason": "created",
            "occurred_at": "2026-08-01T12:00:00+08:00",
            "document": document,
            "document_hash": hash_lifecycle_document(document),
        }
    )


def _applied_state(
    memo_uid: str,
    document: str,
    *,
    sequence: int = 1,
) -> MemoLifecycleState:
    event = _event(memo_uid, document, sequence=sequence)
    return complete_lifecycle_event(
        accept_lifecycle_event(None, event).state, event
    )[0]


def _applying_state(memo_uid: str, document: str) -> MemoLifecycleState:
    event = _event(memo_uid, document)
    return accept_lifecycle_event(None, event).state


def _failed_state(memo_uid: str, document: str) -> MemoLifecycleState:
    event = _event(memo_uid, document)
    return fail_lifecycle_event(
        accept_lifecycle_event(None, event).state,
        event,
        "vector_store_unavailable",
    )[0]


def _delete_state(memo_uid: str, document: str) -> MemoLifecycleState:
    applied = _applied_state(memo_uid, document)
    deletion = MemoLifecycleEvent.from_dict(
        {
            "event_id": f"event-{memo_uid}-2",
            "event_type": "memo.delete.requested.v1",
            "memo_uid": memo_uid,
            "source_sequence": 2,
            "index_version": "memo-v1",
            "operation": "delete",
            "reason": "deleted",
            "occurred_at": "2026-08-01T12:05:00+08:00",
        }
    )
    return complete_lifecycle_event(
        accept_lifecycle_event(applied, deletion).state, deletion
    )[0]


def _candidate(
    memo_uid: str = "memo-visible",
    document: str = VISIBLE_DOCUMENT,
    *,
    record_key: str = "record-visible",
    score: float = 0.91,
    sequence: int = 1,
    document_hash: str | None = None,
    generation: str = ACTIVE_GENERATION,
    index_version: str = "memo-v1",
    lifecycle_state: MemoLifecycleState | None | object = _DEFAULT_STATE,
    failure_quarantined: bool = False,
) -> DerivedMemoCandidate:
    state = lifecycle_state
    if state is _DEFAULT_STATE:
        state = _applied_state(memo_uid, document, sequence=sequence)
    return DerivedMemoCandidate(
        record_key=record_key,
        memo_uid=memo_uid,
        score=score,
        source_sequence=sequence,
        document_hash=document_hash or hash_lifecycle_document(document),
        rebuild_generation=generation,
        index_version=index_version,
        lifecycle_state=state,  # type: ignore[arg-type]
        failure_quarantined=failure_quarantined,
    )


def _document(
    memo_uid: str = "memo-visible",
    document: str = VISIBLE_DOCUMENT,
    *,
    record_key: str = "record-visible",
    sequence: int = 1,
    generation: str = ACTIVE_GENERATION,
    index_version: str = "memo-v1",
) -> DerivedMemoDocument:
    return DerivedMemoDocument(
        record_key=record_key,
        memo_uid=memo_uid,
        document=document,
        source_sequence=sequence,
        document_hash=hash_lifecycle_document(document),
        rebuild_generation=generation,
        index_version=index_version,
    )


def _query(
    *memo_uids: str,
    limit: int = 3,
    question: str = "Why did the port mapping fail?",
) -> AuthorizedRetrievalQuery:
    return AuthorizedRetrievalQuery(
        question=question,
        limit=limit,
        authorized_memo_uids=tuple(memo_uids),
    )


class RecordingRepository:
    def __init__(self, delegate: object) -> None:
        self.delegate = delegate
        self.candidate_calls: list[dict[str, object]] = []
        self.loaded_keys: list[tuple[str, ...]] = []
        self.snapshot_tokens: list[str] = []

    def find_candidates(
        self,
        *,
        question: str,
        authorized_memo_uids: frozenset[str],
        limit: int,
    ) -> DerivedCandidateSnapshot:
        self.candidate_calls.append(
            {
                "question": question,
                "authorized_memo_uids": authorized_memo_uids,
                "limit": limit,
            }
        )
        return self.delegate.find_candidates(  # type: ignore[attr-defined, no-any-return]
            question=question,
            authorized_memo_uids=authorized_memo_uids,
            limit=limit,
        )

    def load_documents(
        self,
        *,
        record_keys: tuple[str, ...],
        snapshot_token: str,
    ) -> tuple[DerivedMemoDocument, ...]:
        self.loaded_keys.append(record_keys)
        self.snapshot_tokens.append(snapshot_token)
        return self.delegate.load_documents(  # type: ignore[attr-defined,no-any-return]
            record_keys=record_keys,
            snapshot_token=snapshot_token,
        )


class ParityFakeRepository:
    def __init__(
        self,
        candidates: tuple[DerivedMemoCandidate, ...],
        documents: tuple[DerivedMemoDocument, ...],
    ) -> None:
        self.candidates = candidates
        self.documents = documents

    def find_candidates(
        self,
        *,
        question: str,
        authorized_memo_uids: frozenset[str],
        limit: int,
    ) -> DerivedCandidateSnapshot:
        del question
        candidates = tuple(
            candidate
            for candidate in sorted(
                self.candidates,
                key=lambda item: (-item.score, item.record_key),
            )
            if candidate.memo_uid in authorized_memo_uids
        )[:limit]
        return DerivedCandidateSnapshot(
            ACTIVE_GENERATION,
            "snapshot-parity-fake",
            candidates,
        )

    def load_documents(
        self,
        *,
        record_keys: tuple[str, ...],
        snapshot_token: str,
    ) -> tuple[DerivedMemoDocument, ...]:
        assert snapshot_token == "snapshot-parity-fake"
        by_key = {document.record_key: document for document in self.documents}
        return tuple(by_key[key] for key in record_keys)


def _assert_fixed_unavailable(
    error: DurableAuthorizedRetrievalUnavailableError,
) -> None:
    assert error.to_dict() == {
        "error_code": "authorized_retrieval_unavailable"
    }
    assert str(error) == "authorized retrieval unavailable"
    assert error.__cause__ is None


def test_reopened_disposable_store_matches_in_memory_fake_projection(tmp_path: Path):
    database = tmp_path / "r5-parity.db"
    higher = _candidate()
    lower = _candidate(
        "memo-second",
        SECOND_DOCUMENT,
        record_key="record-second",
        score=0.72,
    )
    candidates = (lower, higher)
    documents = (
        _document("memo-second", SECOND_DOCUMENT, record_key="record-second"),
        _document(),
    )
    repository = DisposableSQLiteAuthorizedRetrievalRepository.create(database)
    repository.seed_synthetic_snapshot(
        active_generation=ACTIVE_GENERATION,
        candidates=candidates,
        documents=documents,
    )

    del repository
    reopened = DisposableSQLiteAuthorizedRetrievalRepository(database)
    query = _query("memo-visible", "memo-second")
    sqlite_result = DurableAuthorizedRetrievalService(reopened).retrieve(query)
    fake_result = DurableAuthorizedRetrievalService(
        ParityFakeRepository(candidates, documents)
    ).retrieve(query)

    assert sqlite_result.context == fake_result.context
    assert sqlite_result.context == (
        f"[evidence-1]\n{VISIBLE_DOCUMENT}\n\n"
        f"[evidence-2]\n{SECOND_DOCUMENT}"
    )
    assert sqlite_result.safe_observation() == fake_result.safe_observation()
    assert tuple(
        item.citation.to_dict() for item in sqlite_result.evidence
    ) == tuple(item.citation.to_dict() for item in fake_result.evidence)
    assert [item.reference for item in sqlite_result.evidence] == [
        "evidence-1",
        "evidence-2",
    ]


def test_candidate_query_pushes_scope_and_limit_before_service_intersection(
    tmp_path: Path,
):
    repository = DisposableSQLiteAuthorizedRetrievalRepository.create(
        tmp_path / "scope.db"
    )
    visible = _candidate(score=0.81)
    hidden = _candidate(
        "memo-hidden",
        HIDDEN_DOCUMENT,
        record_key="record-hidden",
        score=0.99,
    )
    repository.seed_synthetic_snapshot(
        active_generation=ACTIVE_GENERATION,
        candidates=(hidden, visible),
        documents=(
            _document(
                "memo-hidden", HIDDEN_DOCUMENT, record_key="record-hidden"
            ),
            _document(),
        ),
    )
    recording = RecordingRepository(repository)

    result = DurableAuthorizedRetrievalService(recording).retrieve(
        _query("memo-visible", limit=1)
    )

    assert recording.candidate_calls == [
        {
            "question": "Why did the port mapping fail?",
            "authorized_memo_uids": frozenset({"memo-visible"}),
            "limit": 1,
        }
    ]
    assert recording.loaded_keys == [("record-visible",)]
    assert HIDDEN_DOCUMENT not in result.context
    assert "memo-hidden" not in repr(result.safe_observation())


def test_service_reintersects_even_if_adapter_wrapper_leaks_hidden_candidate(
    tmp_path: Path,
):
    database = tmp_path / "leaky-wrapper.db"
    repository = DisposableSQLiteAuthorizedRetrievalRepository.create(database)
    visible = _candidate()
    hidden = _candidate(
        "memo-hidden",
        HIDDEN_DOCUMENT,
        record_key="record-hidden",
        score=0.99,
    )
    repository.seed_synthetic_snapshot(
        active_generation=ACTIVE_GENERATION,
        candidates=(hidden, visible),
        documents=(
            _document(
                "memo-hidden", HIDDEN_DOCUMENT, record_key="record-hidden"
            ),
            _document(),
        ),
    )

    class LeakyRepository(RecordingRepository):
        def find_candidates(self, **kwargs: object) -> DerivedCandidateSnapshot:
            snapshot = super().find_candidates(**kwargs)  # type: ignore[arg-type]
            return DerivedCandidateSnapshot(
                snapshot.active_generation,
                snapshot.snapshot_token,
                (hidden, *snapshot.candidates),
            )

    leaky = LeakyRepository(repository)
    result = DurableAuthorizedRetrievalService(leaky).retrieve(
        _query("memo-visible")
    )

    assert leaky.loaded_keys == [("record-visible",)]
    assert result.context == f"[evidence-1]\n{VISIBLE_DOCUMENT}"
    assert [item.citation.memo_uid for item in result.evidence] == ["memo-visible"]


def test_generation_switch_between_phases_invalidates_snapshot_without_partial_result(
    tmp_path: Path,
):
    repository = DisposableSQLiteAuthorizedRetrievalRepository.create(
        tmp_path / "generation-switch.db"
    )
    repository.seed_synthetic_snapshot(
        active_generation=ACTIVE_GENERATION,
        candidates=(_candidate(),),
        documents=(_document(),),
    )

    class SwitchingRepository(RecordingRepository):
        def load_documents(
            self,
            *,
            record_keys: tuple[str, ...],
            snapshot_token: str,
        ) -> tuple[DerivedMemoDocument, ...]:
            repository.seed_synthetic_snapshot(
                active_generation="generation-next",
                candidates=(
                    _candidate(
                        generation="generation-next",
                    ),
                ),
                documents=(_document(generation="generation-next"),),
            )
            return super().load_documents(
                record_keys=record_keys,
                snapshot_token=snapshot_token,
            )

    with pytest.raises(DurableAuthorizedRetrievalUnavailableError) as error:
        DurableAuthorizedRetrievalService(SwitchingRepository(repository)).retrieve(
            _query("memo-visible")
        )

    _assert_fixed_unavailable(error.value)


@pytest.mark.parametrize(
    ("active_generation", "candidate"),
    [
        (ACTIVE_GENERATION, _candidate(lifecycle_state=None)),
        (
            ACTIVE_GENERATION,
            _candidate(
                lifecycle_state=_applying_state("memo-visible", VISIBLE_DOCUMENT)
            ),
        ),
        (
            ACTIVE_GENERATION,
            _candidate(lifecycle_state=_failed_state("memo-visible", VISIBLE_DOCUMENT)),
        ),
        (ACTIVE_GENERATION, _candidate(failure_quarantined=True)),
        (
            ACTIVE_GENERATION,
            _candidate(
                sequence=2,
                lifecycle_state=_applied_state("memo-visible", VISIBLE_DOCUMENT),
            ),
        ),
        (
            ACTIVE_GENERATION,
            _candidate(document_hash=hash_lifecycle_document("stale derived hash")),
        ),
        (ACTIVE_GENERATION, _candidate(generation="generation-old")),
        (
            ACTIVE_GENERATION,
            _candidate(index_version="memo-chunk-v1"),
        ),
        (
            ACTIVE_GENERATION,
            _candidate(
                sequence=2,
                lifecycle_state=_delete_state("memo-visible", VISIBLE_DOCUMENT),
            ),
        ),
        (None, _candidate()),
    ],
    ids=[
        "missing-ledger",
        "pending",
        "failed",
        "conflict-quarantine",
        "stale-sequence",
        "stale-hash",
        "old-generation",
        "chunk-version",
        "tombstone-delete",
        "unknown-generation",
    ],
)
def test_ineligible_disposable_rows_never_request_document_load(
    tmp_path: Path,
    active_generation: str | None,
    candidate: DerivedMemoCandidate,
):
    repository = DisposableSQLiteAuthorizedRetrievalRepository.create(
        tmp_path / "ineligible.db"
    )
    repository.seed_synthetic_snapshot(
        active_generation=active_generation,
        candidates=(candidate,),
        documents=(
            _document(
                sequence=candidate.source_sequence,
                generation=candidate.rebuild_generation,
                index_version=candidate.index_version,
            ),
        ),
    )
    recording = RecordingRepository(repository)

    result = DurableAuthorizedRetrievalService(recording).retrieve(
        _query("memo-visible")
    )

    assert result.evidence == ()
    assert recording.loaded_keys == []


@pytest.mark.parametrize("duplicate_kind", ["record-key", "memo-uid"])
def test_duplicate_candidates_from_an_adapter_are_rejected_before_load(
    tmp_path: Path,
    duplicate_kind: str,
):
    repository = DisposableSQLiteAuthorizedRetrievalRepository.create(
        tmp_path / "duplicate-candidate.db"
    )
    repository.seed_synthetic_snapshot(
        active_generation=ACTIVE_GENERATION,
        candidates=(_candidate(),),
        documents=(_document(),),
    )

    class DuplicateCandidateRepository(RecordingRepository):
        def find_candidates(self, **kwargs: object) -> DerivedCandidateSnapshot:
            snapshot = super().find_candidates(**kwargs)  # type: ignore[arg-type]
            original = snapshot.candidates[0]
            duplicate = original
            if duplicate_kind == "memo-uid":
                duplicate = _candidate(record_key="record-duplicate")
            return DerivedCandidateSnapshot(
                snapshot.active_generation,
                snapshot.snapshot_token,
                (original, duplicate),
            )

    duplicate_repository = DuplicateCandidateRepository(repository)
    with pytest.raises(DurableAuthorizedRetrievalUnavailableError) as error:
        DurableAuthorizedRetrievalService(duplicate_repository).retrieve(
            _query("memo-visible")
        )

    _assert_fixed_unavailable(error.value)
    assert duplicate_repository.loaded_keys == []


def test_duplicate_materialized_row_is_rejected_without_partial_result(tmp_path: Path):
    repository = DisposableSQLiteAuthorizedRetrievalRepository.create(
        tmp_path / "duplicate-document.db"
    )
    repository.seed_synthetic_snapshot(
        active_generation=ACTIVE_GENERATION,
        candidates=(_candidate(),),
        documents=(_document(),),
    )

    class DuplicateDocumentRepository(RecordingRepository):
        def load_documents(self, **kwargs: object) -> tuple[DerivedMemoDocument, ...]:
            documents = super().load_documents(**kwargs)  # type: ignore[arg-type]
            return (*documents, documents[0])

    with pytest.raises(DurableAuthorizedRetrievalUnavailableError) as error:
        DurableAuthorizedRetrievalService(
            DuplicateDocumentRepository(repository)
        ).retrieve(_query("memo-visible"))

    _assert_fixed_unavailable(error.value)


@pytest.mark.parametrize(
    "document",
    [
        _document(memo_uid="memo-other"),
        _document(sequence=2),
        _document(document="different synthetic document"),
        _document(generation="generation-old"),
        _document(index_version="memo-chunk-v1"),
    ],
    ids=[
        "identity",
        "sequence",
        "hash",
        "generation",
        "version",
    ],
)
def test_candidate_document_inconsistency_maps_to_one_fixed_failure(
    tmp_path: Path,
    document: DerivedMemoDocument,
):
    repository = DisposableSQLiteAuthorizedRetrievalRepository.create(
        tmp_path / "inconsistent-document.db"
    )
    repository.seed_synthetic_snapshot(
        active_generation=ACTIVE_GENERATION,
        candidates=(_candidate(),),
        documents=(document,),
    )

    with pytest.raises(DurableAuthorizedRetrievalUnavailableError) as error:
        DurableAuthorizedRetrievalService(repository).retrieve(_query("memo-visible"))

    _assert_fixed_unavailable(error.value)


def test_missing_materialized_row_maps_to_fixed_failure(tmp_path: Path):
    repository = DisposableSQLiteAuthorizedRetrievalRepository.create(
        tmp_path / "missing-document.db"
    )
    repository.seed_synthetic_snapshot(
        active_generation=ACTIVE_GENERATION,
        candidates=(_candidate(),),
        documents=(),
    )

    with pytest.raises(DurableAuthorizedRetrievalUnavailableError) as error:
        DurableAuthorizedRetrievalService(repository).retrieve(_query("memo-visible"))

    _assert_fixed_unavailable(error.value)


@pytest.mark.parametrize("failure_kind", ["open", "schema", "query", "load"])
def test_adapter_failures_have_one_bounded_content_free_projection(
    tmp_path: Path,
    failure_kind: str,
):
    raw_detail = (
        "raw Memo question context payload embedding identity visibility "
        "secret SQL provider citation metadata"
    )
    if failure_kind == "open":
        repository: object = DisposableSQLiteAuthorizedRetrievalRepository(tmp_path)
    elif failure_kind == "schema":
        database = tmp_path / "missing-schema.db"
        sqlite3.connect(database).close()
        repository = DisposableSQLiteAuthorizedRetrievalRepository(database)
    else:
        delegate = DisposableSQLiteAuthorizedRetrievalRepository.create(
            tmp_path / f"{failure_kind}.db"
        )
        delegate.seed_synthetic_snapshot(
            active_generation=ACTIVE_GENERATION,
            candidates=(_candidate(),),
            documents=(_document(),),
        )

        class FailingRepository(RecordingRepository):
            def find_candidates(self, **kwargs: object) -> DerivedCandidateSnapshot:
                if failure_kind == "query":
                    raise sqlite3.OperationalError(raw_detail)
                return super().find_candidates(**kwargs)  # type: ignore[arg-type]

            def load_documents(
                self, **kwargs: object
            ) -> tuple[DerivedMemoDocument, ...]:
                if failure_kind == "load":
                    raise sqlite3.OperationalError(raw_detail)
                return super().load_documents(**kwargs)  # type: ignore[arg-type]

        repository = FailingRepository(delegate)

    with pytest.raises(DurableAuthorizedRetrievalUnavailableError) as error:
        DurableAuthorizedRetrievalService(
            repository  # type: ignore[arg-type]
        ).retrieve(
            _query("memo-visible", question="raw Memo question context")
        )

    _assert_fixed_unavailable(error.value)
    assert raw_detail not in str(error.value)
    assert raw_detail not in repr(error.value.to_dict())
    assert "raw Memo question context" not in repr(error.value.to_dict())


def test_locked_transaction_maps_to_fixed_failure_without_sql_detail(tmp_path: Path):
    database = tmp_path / "locked.db"
    repository = DisposableSQLiteAuthorizedRetrievalRepository.create(database)
    repository.seed_synthetic_snapshot(
        active_generation=ACTIVE_GENERATION,
        candidates=(_candidate(),),
        documents=(_document(),),
    )
    lock = sqlite3.connect(database)
    lock.execute("BEGIN EXCLUSIVE")
    try:
        with pytest.raises(DurableAuthorizedRetrievalUnavailableError) as error:
            DurableAuthorizedRetrievalService(repository).retrieve(
                _query("memo-visible")
            )
    finally:
        lock.rollback()
        lock.close()

    _assert_fixed_unavailable(error.value)
    assert "locked" not in str(error.value).lower()
    assert "select" not in repr(error.value.to_dict()).lower()


def test_disposable_schema_contains_no_authority_or_citation_metadata(tmp_path: Path):
    database = tmp_path / "schema-scan.db"
    DisposableSQLiteAuthorizedRetrievalRepository.create(database)
    with sqlite3.connect(database) as connection:
        schema = "\n".join(
            row[0]
            for row in connection.execute(
                "SELECT sql FROM sqlite_master WHERE sql IS NOT NULL"
            ).fetchall()
        ).lower()

    assert "document" in schema
    for forbidden in (
        "visibility",
        "identity",
        "citation",
        "metadata",
        "provider",
        "embedding",
        "prompt",
        "context",
        "payload",
        "secret",
    ):
        assert forbidden not in schema
