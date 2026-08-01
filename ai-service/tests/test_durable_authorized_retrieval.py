from __future__ import annotations

import pytest

from app.domain.agent_lifecycle import (
    MemoLifecycleEvent,
    MemoLifecycleState,
    accept_lifecycle_event,
    complete_lifecycle_event,
    fail_lifecycle_event,
    hash_lifecycle_document,
)
from app.domain.durable_authorized_retrieval import (
    MAX_AUTHORIZED_MEMO_UIDS,
    AuthorizedRetrievalContractError,
    AuthorizedRetrievalQuery,
    DerivedCandidateSnapshot,
    DerivedMemoCandidate,
    DerivedMemoDocument,
    DerivedRetrievalContractError,
    project_authorized_result,
    select_eligible_candidates,
)
from app.services.durable_authorized_retrieval import (
    DurableAuthorizedRetrievalService,
    DurableAuthorizedRetrievalUnavailableError,
)


DOCUMENT = "# Synthetic Memo\n\nOnly authorized durable evidence is materialized."
DOCUMENT_HASH = hash_lifecycle_document(DOCUMENT)


def _event(
    memo_uid: str = "memo-visible", sequence: int = 1
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
            "document": DOCUMENT,
            "document_hash": DOCUMENT_HASH,
        }
    )


def _applied_state(
    memo_uid: str = "memo-visible", sequence: int = 1
) -> MemoLifecycleState:
    event = _event(memo_uid, sequence)
    return complete_lifecycle_event(
        accept_lifecycle_event(None, event).state, event
    )[0]


def _delete_state() -> MemoLifecycleState:
    initial = _applied_state()
    deletion = MemoLifecycleEvent.from_dict(
        {
            "event_id": "event-memo-visible-2",
            "event_type": "memo.delete.requested.v1",
            "memo_uid": "memo-visible",
            "source_sequence": 2,
            "index_version": "memo-v1",
            "operation": "delete",
            "reason": "deleted",
            "occurred_at": "2026-08-01T12:05:00+08:00",
        }
    )
    return complete_lifecycle_event(
        accept_lifecycle_event(initial, deletion).state, deletion
    )[0]


def _candidate(**overrides: object) -> DerivedMemoCandidate:
    values: dict[str, object] = {
        "record_key": "record-visible",
        "memo_uid": "memo-visible",
        "score": 0.91,
        "source_sequence": 1,
        "document_hash": DOCUMENT_HASH,
        "rebuild_generation": "generation-active",
        "index_version": "memo-v1",
        "lifecycle_state": _applied_state(),
    }
    values.update(overrides)
    return DerivedMemoCandidate(**values)  # type: ignore[arg-type]


def _document(**overrides: object) -> DerivedMemoDocument:
    values: dict[str, object] = {
        "record_key": "record-visible",
        "memo_uid": "memo-visible",
        "document": DOCUMENT,
        "source_sequence": 1,
        "document_hash": DOCUMENT_HASH,
        "rebuild_generation": "generation-active",
        "index_version": "memo-v1",
    }
    values.update(overrides)
    return DerivedMemoDocument(**values)  # type: ignore[arg-type]


class FakeDurableRepository:
    def __init__(
        self,
        snapshot: DerivedCandidateSnapshot,
        documents: tuple[DerivedMemoDocument, ...] = (),
    ) -> None:
        self.snapshot = snapshot
        self.documents = documents
        self.candidate_calls: list[dict[str, object]] = []
        self.loaded_keys: list[tuple[str, ...]] = []
        self.fail_candidates: BaseException | None = None
        self.fail_documents: BaseException | None = None

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
        if self.fail_candidates is not None:
            raise self.fail_candidates
        return self.snapshot

    def load_documents(
        self, record_keys: tuple[str, ...]
    ) -> tuple[DerivedMemoDocument, ...]:
        self.loaded_keys.append(record_keys)
        if self.fail_documents is not None:
            raise self.fail_documents
        return tuple(
            document for document in self.documents if document.record_key in record_keys
        )


def test_query_accepts_a_bounded_memos_authority_uid_set_and_empty_scope():
    query = AuthorizedRetrievalQuery(
        question="  Docker ports  ",
        limit=3,
        authorized_memo_uids=("memo-visible", "memo-other"),
    )
    empty = AuthorizedRetrievalQuery(
        question="Docker ports", limit=3, authorized_memo_uids=()
    )

    assert query.question == "Docker ports"
    assert query.authorized_uid_set == frozenset({"memo-visible", "memo-other"})
    assert empty.authorized_uid_set == frozenset()


@pytest.mark.parametrize(
    "overrides",
    [
        {"authorized_memo_uids": ("memo-visible", "memo-visible")},
        {"authorized_memo_uids": ("memo with spaces",)},
        {"authorized_memo_uids": ("-memo-edge",)},
        {"authorized_memo_uids": ("memo-",)},
        {"authorized_memo_uids": ("m" * 37,)},
        {"authorized_memo_uids": tuple(f"memo-{i}" for i in range(MAX_AUTHORIZED_MEMO_UIDS + 1))},
        {"question": "  "},
        {"question": "q" * 4_001},
        {"limit": 0},
        {"limit": 11},
    ],
)
def test_query_rejects_duplicate_malformed_or_unbounded_input(overrides):
    values = {
        "question": "Docker ports",
        "limit": 3,
        "authorized_memo_uids": ("memo-visible",),
    }
    values.update(overrides)

    with pytest.raises(
        AuthorizedRetrievalContractError,
        match="^invalid authorized retrieval query$",
    ):
        AuthorizedRetrievalQuery(**values)


def test_pure_selection_and_projection_create_only_opaque_refs_and_server_citations():
    query = AuthorizedRetrievalQuery(
        question="Docker ports", limit=3, authorized_memo_uids=("memo-visible",)
    )
    candidate = _candidate()

    eligible = select_eligible_candidates(
        query,
        DerivedCandidateSnapshot("generation-active", (candidate,)),
    )
    result = project_authorized_result(query, eligible, (_document(),))

    assert eligible == (candidate,)
    assert result.context == f"[evidence-1]\n{DOCUMENT}"
    assert result.protected_context_fragments == (DOCUMENT,)
    assert result.evidence[0].reference == "evidence-1"
    assert result.evidence[0].citation.to_dict() == {
        "memo_uid": "memo-visible",
        "source_sequence": 1,
        "index_version": "memo-v1",
    }
    assert result.safe_observation() == {
        "version": "durable-authorized-retrieval-v1",
        "retrieved_count": 1,
        "references": ["evidence-1"],
    }
    assert DOCUMENT not in repr(result.safe_observation())


def test_projection_rejects_duplicate_or_inconsistent_materialized_records():
    query = AuthorizedRetrievalQuery(
        question="Docker ports", limit=3, authorized_memo_uids=("memo-visible",)
    )
    candidate = _candidate()

    for documents in (
        (),
        (_document(), _document()),
        (_document(memo_uid="memo-other"),),
        (_document(source_sequence=2),),
        (_document(rebuild_generation="generation-old"),),
        (_document(index_version="memo-chunk-v1"),),
    ):
        with pytest.raises(
            DerivedRetrievalContractError,
            match="^invalid derived retrieval state$",
        ):
            project_authorized_result(query, (candidate,), documents)

    unknown_query = AuthorizedRetrievalQuery(
        question="Docker ports", limit=3, authorized_memo_uids=("memo-unknown",)
    )
    with pytest.raises(DerivedRetrievalContractError):
        project_authorized_result(unknown_query, (candidate,), (_document(),))


def test_failed_lifecycle_state_helper_is_not_applied():
    event = _event()
    applying = accept_lifecycle_event(None, event).state
    failed = fail_lifecycle_event(
        applying, event, "vector_store_unavailable"
    )[0]

    assert applying.status == "applying"
    assert failed.status == "failed"


def test_empty_scope_returns_empty_without_querying_the_repository():
    repository = FakeDurableRepository(
        DerivedCandidateSnapshot("generation-active", (_candidate(),)),
        (_document(),),
    )
    query = AuthorizedRetrievalQuery(
        question="Docker ports", limit=3, authorized_memo_uids=()
    )

    result = DurableAuthorizedRetrievalService(repository).retrieve(query)

    assert result.evidence == ()
    assert result.context == ""
    assert repository.candidate_calls == []
    assert repository.loaded_keys == []


def test_unknown_uid_returns_empty_without_loading_any_document():
    repository = FakeDurableRepository(
        DerivedCandidateSnapshot("generation-active", (_candidate(),)),
        (_document(),),
    )
    query = AuthorizedRetrievalQuery(
        question="Docker ports", limit=3, authorized_memo_uids=("memo-unknown",)
    )

    result = DurableAuthorizedRetrievalService(repository).retrieve(query)

    assert result.evidence == ()
    assert repository.loaded_keys == []


def test_visibility_intersects_before_document_loading_context_or_citation_projection():
    hidden_document = "TOP SECRET hidden Memo context and identity."
    hidden_hash = hash_lifecycle_document(hidden_document)
    visible = _candidate()
    hidden = _candidate(
        record_key="record-hidden",
        memo_uid="memo-hidden",
        document_hash=hidden_hash,
        lifecycle_state=_applied_state("memo-hidden"),
    )
    repository = FakeDurableRepository(
        DerivedCandidateSnapshot("generation-active", (hidden, visible)),
        (
            DerivedMemoDocument(
                record_key="record-hidden",
                memo_uid="memo-hidden",
                document=hidden_document,
                source_sequence=1,
                document_hash=hidden_hash,
                rebuild_generation="generation-active",
                index_version="memo-v1",
            ),
            _document(),
        ),
    )
    query = AuthorizedRetrievalQuery(
        question="secret Docker ports",
        limit=3,
        authorized_memo_uids=("memo-visible",),
    )

    result = DurableAuthorizedRetrievalService(repository).retrieve(query)

    assert repository.candidate_calls == [
        {
            "question": "secret Docker ports",
            "authorized_memo_uids": frozenset({"memo-visible"}),
            "limit": 3,
        }
    ]
    assert repository.loaded_keys == [("record-visible",)]
    assert hidden_document not in result.context
    assert "memo-hidden" not in repr(result.safe_observation())
    assert [item.citation.memo_uid for item in result.evidence] == ["memo-visible"]


def _failed_state() -> MemoLifecycleState:
    event = _event()
    applying = accept_lifecycle_event(None, event).state
    return fail_lifecycle_event(
        applying, event, "vector_store_unavailable"
    )[0]


@pytest.mark.parametrize(
    "candidate",
    [
        _candidate(lifecycle_state=None),
        _candidate(lifecycle_state=accept_lifecycle_event(None, _event()).state),
        _candidate(lifecycle_state=_failed_state()),
        _candidate(failure_quarantined=True),
        _candidate(lifecycle_state=_delete_state(), source_sequence=2),
        _candidate(source_sequence=2),
        _candidate(document_hash=hash_lifecycle_document("stale document")),
        _candidate(rebuild_generation="generation-old"),
        _candidate(index_version="memo-chunk-v1"),
    ],
    ids=[
        "missing-ledger",
        "applying-pending",
        "failure-quarantine",
        "conflict-quarantine",
        "delete-tombstone",
        "stale-sequence",
        "inconsistent-hash",
        "old-generation",
        "chunk-index",
    ],
)
def test_noneligible_lifecycle_generation_or_index_records_never_load_content(candidate):
    repository = FakeDurableRepository(
        DerivedCandidateSnapshot("generation-active", (candidate,)),
        (_document(),),
    )
    query = AuthorizedRetrievalQuery(
        question="Docker ports", limit=3, authorized_memo_uids=("memo-visible",)
    )

    result = DurableAuthorizedRetrievalService(repository).retrieve(query)

    assert result.evidence == ()
    assert repository.loaded_keys == []


def test_unknown_active_generation_fails_closed_before_document_loading():
    repository = FakeDurableRepository(
        DerivedCandidateSnapshot(None, (_candidate(),)), (_document(),)
    )
    query = AuthorizedRetrievalQuery(
        question="Docker ports", limit=3, authorized_memo_uids=("memo-visible",)
    )

    result = DurableAuthorizedRetrievalService(repository).retrieve(query)

    assert result.evidence == ()
    assert repository.loaded_keys == []


@pytest.mark.parametrize(
    "candidates",
    [
        (_candidate(), _candidate()),
        (
            _candidate(),
            _candidate(record_key="record-other", score=0.8),
        ),
        (
            _candidate(
                lifecycle_state=_applied_state("memo-other"),
            ),
        ),
    ],
    ids=["duplicate-record", "duplicate-memo", "ledger-target-conflict"],
)
def test_duplicate_or_conflicting_candidates_map_to_fixed_failure_before_content(candidates):
    repository = FakeDurableRepository(
        DerivedCandidateSnapshot("generation-active", candidates), (_document(),)
    )
    query = AuthorizedRetrievalQuery(
        question="Docker ports", limit=3, authorized_memo_uids=("memo-visible",)
    )

    with pytest.raises(DurableAuthorizedRetrievalUnavailableError) as error:
        DurableAuthorizedRetrievalService(repository).retrieve(query)

    assert str(error.value) == "authorized retrieval unavailable"
    assert error.value.to_dict() == {
        "error_code": "authorized_retrieval_unavailable"
    }
    assert repository.loaded_keys == []


@pytest.mark.parametrize("failure_stage", ["candidates", "documents"])
def test_repository_failures_use_one_bounded_content_free_mapping(failure_stage):
    repository = FakeDurableRepository(
        DerivedCandidateSnapshot("generation-active", (_candidate(),)),
        (_document(),),
    )
    raw_detail = (
        "raw Memo context payload embedding identity visibility secret "
        "provider citation metadata"
    )
    if failure_stage == "candidates":
        repository.fail_candidates = RuntimeError(raw_detail)
    else:
        repository.fail_documents = RuntimeError(raw_detail)
    query = AuthorizedRetrievalQuery(
        question="Docker ports", limit=3, authorized_memo_uids=("memo-visible",)
    )

    with pytest.raises(DurableAuthorizedRetrievalUnavailableError) as error:
        DurableAuthorizedRetrievalService(repository).retrieve(query)

    projected = error.value.to_dict()
    assert projected == {"error_code": "authorized_retrieval_unavailable"}
    assert str(error.value) == "authorized retrieval unavailable"
    assert error.value.__cause__ is None
    assert raw_detail not in repr(projected)
    assert raw_detail not in str(error.value)
