from __future__ import annotations

import copy
import json
from pathlib import Path

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
    AuthorizedRetrievalQuery,
    DerivedCandidateSnapshot,
    DerivedMemoCandidate,
    project_authorized_result,
    select_eligible_candidates,
)
from app.domain.evidence_rehydration import (
    CONTENT_REHYDRATION_DECISION,
    CONTENT_REHYDRATION_PATH,
    CONTENT_REHYDRATION_SIGNATURE_PURPOSE,
    CONTENT_REHYDRATION_VERSION,
    ContentRehydrationContractError,
    ContentRehydrationDecision,
    ContentRehydrationFailure,
    ContentRehydrationRequest,
    ContentRehydrationResponse,
    MemosAuthorizedCurrentDocument,
    MemosCurrentAuthoritySnapshot,
    RehydratedContent,
    build_content_rehydration_request,
    map_content_rehydration_failure,
    materialize_rehydrated_documents,
    rehydrate_from_memos_authority,
)
from app.services.agent_lifecycle_transport import (
    INTERNAL_LIFECYCLE_PATH,
    LIFECYCLE_SIGNATURE_PURPOSE,
)
from app.services.agent_delegation import INTERNAL_ANSWER_PATH


DOCUMENT = "# Synthetic Memo\n\nMemos remains the current authority."
DOCUMENT_HASH = hash_lifecycle_document(DOCUMENT)
UPDATED_DOCUMENT = "# Synthetic Memo\n\nMemos remains the updated authority."
UPDATED_HASH = hash_lifecycle_document(UPDATED_DOCUMENT)
CONTRACT_PATH = (
    Path(__file__).resolve().parents[2]
    / "contracts"
    / "memo-evidence-rehydration-v1.json"
)
MEMOS_AUTHORITY_REF = "authority-ref-synthetic-4"


def _event(
    memo_uid: str = "memo-visible",
    sequence: int = 3,
    *,
    document: str = DOCUMENT,
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
    memo_uid: str = "memo-visible",
    sequence: int = 3,
    *,
    document: str = DOCUMENT,
) -> MemoLifecycleState:
    event = _event(memo_uid, sequence, document=document)
    return complete_lifecycle_event(
        accept_lifecycle_event(None, event).state, event
    )[0]


def _failed_state() -> MemoLifecycleState:
    event = _event()
    applying = accept_lifecycle_event(None, event).state
    return fail_lifecycle_event(
        applying, event, "vector_store_unavailable"
    )[0]


def _delete_state() -> MemoLifecycleState:
    initial = _applied_state(sequence=2)
    deletion = MemoLifecycleEvent.from_dict(
        {
            "event_id": "event-memo-visible-3",
            "event_type": "memo.delete.requested.v1",
            "memo_uid": "memo-visible",
            "source_sequence": 3,
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
        "source_sequence": 3,
        "document_hash": DOCUMENT_HASH,
        "rebuild_generation": "generation-active",
        "index_version": "memo-v1",
        "lifecycle_state": _applied_state(),
    }
    values.update(overrides)
    return DerivedMemoCandidate(**values)  # type: ignore[arg-type]


def _query(*uids: str) -> AuthorizedRetrievalQuery:
    return AuthorizedRetrievalQuery(
        question="Which content is current?",
        limit=3,
        authorized_memo_uids=uids or ("memo-visible",),
    )


def _snapshot(
    *candidates: DerivedMemoCandidate,
    token: str = "snapshot-synthetic-1",
    active_generation: str | None = "generation-active",
) -> DerivedCandidateSnapshot:
    return DerivedCandidateSnapshot(
        active_generation,
        token,
        candidates or (_candidate(),),
    )


def _request_bundle() -> tuple[
    AuthorizedRetrievalQuery,
    DerivedCandidateSnapshot,
    tuple[DerivedMemoCandidate, ...],
    ContentRehydrationRequest,
]:
    query = _query()
    snapshot = _snapshot()
    candidates = select_eligible_candidates(query, snapshot)
    request = build_content_rehydration_request(
        query,
        snapshot,
        candidates,
        memos_authority_ref=MEMOS_AUTHORITY_REF,
    )
    return query, snapshot, candidates, request


def _authority(
    *documents: MemosAuthorizedCurrentDocument,
) -> MemosCurrentAuthoritySnapshot:
    return MemosCurrentAuthoritySnapshot(
        memos_authority_ref=MEMOS_AUTHORITY_REF,
        authority_token="authority-synthetic-9",
        documents=documents
        or (
            MemosAuthorizedCurrentDocument(
                memo_uid="memo-visible",
                document=DOCUMENT,
                source_sequence=3,
                document_hash=DOCUMENT_HASH,
            ),
        ),
    )


def test_decision_selects_current_memos_authority_and_no_ai_content_retention():
    assert CONTENT_REHYDRATION_DECISION.to_dict() == {
        "content_source": "memos-current-authority",
        "ai_content_retention": "request-memory-only",
        "response_mode": "all-or-nothing",
        "backup_restore_authority": "memos-only",
        "derived_recovery": "discard-and-rebuild-from-memos",
        "runtime_scope": "single-host-authenticated-internal",
        "multi_instance_gate": "encrypted-transport-and-shared-replay-required",
    }


def test_decision_and_failure_objects_reject_runtime_override():
    with pytest.raises(ContentRehydrationContractError):
        ContentRehydrationDecision(
            content_source="derived-store"  # type: ignore[arg-type]
        )
    with pytest.raises(ContentRehydrationContractError):
        ContentRehydrationFailure(error_code="raw_sql_error")  # type: ignore[arg-type]


def test_rehydration_has_independent_path_purpose_and_version():
    assert CONTENT_REHYDRATION_PATH != INTERNAL_ANSWER_PATH
    assert CONTENT_REHYDRATION_PATH != INTERNAL_LIFECYCLE_PATH
    assert CONTENT_REHYDRATION_SIGNATURE_PURPOSE != LIFECYCLE_SIGNATURE_PURPOSE
    assert CONTENT_REHYDRATION_VERSION == "memo-evidence-rehydration-v1"


def test_shared_contract_fixture_round_trips_exactly():
    fixture = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))

    request = ContentRehydrationRequest.from_dict(fixture["request"])
    response = ContentRehydrationResponse.from_dict(fixture["response"])
    failure = ContentRehydrationFailure.from_dict(fixture["failure"])

    assert fixture["version"] == CONTENT_REHYDRATION_VERSION
    assert request.to_dict() == fixture["request"]
    assert response.to_dict() == fixture["response"]
    assert response.documents[0].document_hash == DOCUMENT_HASH
    assert failure.to_dict() == fixture["failure"]


def test_request_contains_only_bounded_eligible_selection_fields():
    _, _, _, request = _request_bundle()

    assert request.to_dict() == {
        "version": CONTENT_REHYDRATION_VERSION,
        "snapshot_token": "snapshot-synthetic-1",
        "memos_authority_ref": MEMOS_AUTHORITY_REF,
        "selections": [
            {
                "selection_ref": "rehydration-1",
                "memo_uid": "memo-visible",
                "source_sequence": 3,
                "document_hash": DOCUMENT_HASH,
                "index_version": "memo-v1",
            }
        ],
    }
    serialized = repr(request.to_dict())
    for forbidden in (
        "question",
        "visibility",
        "citation",
        "provider",
        "embedding",
        "payload",
    ):
        assert forbidden not in serialized.lower()


def test_current_authority_rehydrates_and_materializes_all_or_nothing():
    query, snapshot, candidates, request = _request_bundle()

    response = rehydrate_from_memos_authority(request, _authority())
    documents = materialize_rehydrated_documents(
        query,
        snapshot,
        candidates,
        request,
        response,
        memos_authority_ref=MEMOS_AUTHORITY_REF,
        current_snapshot_token=snapshot.snapshot_token,
    )
    result = project_authorized_result(query, candidates, documents)

    assert response.documents[0].to_dict() == {
        "selection_ref": "rehydration-1",
        "document": DOCUMENT,
        "source_sequence": 3,
        "document_hash": DOCUMENT_HASH,
        "index_version": "memo-v1",
    }
    assert result.evidence[0].reference == "evidence-1"
    assert result.evidence[0].citation.to_dict() == {
        "memo_uid": "memo-visible",
        "source_sequence": 3,
        "index_version": "memo-v1",
    }


def test_memos_authority_reference_must_match_current_visibility_read():
    _, _, _, request = _request_bundle()
    authority = MemosCurrentAuthoritySnapshot(
        memos_authority_ref="authority-ref-other-caller",
        authority_token="authority-synthetic-9",
        documents=_authority().documents,
    )

    with pytest.raises(ContentRehydrationContractError):
        rehydrate_from_memos_authority(request, authority)


@pytest.mark.parametrize(
    "candidate",
    [
        _candidate(lifecycle_state=None),
        _candidate(lifecycle_state=accept_lifecycle_event(None, _event()).state),
        _candidate(lifecycle_state=_failed_state()),
        _candidate(failure_quarantined=True),
        _candidate(lifecycle_state=_delete_state()),
        _candidate(source_sequence=2),
        _candidate(document_hash=UPDATED_HASH),
        _candidate(rebuild_generation="generation-old"),
        _candidate(index_version="memo-chunk-v1"),
    ],
    ids=[
        "missing-ledger",
        "pending",
        "failed",
        "conflict-quarantine",
        "delete-tombstone",
        "stale-sequence",
        "stale-hash",
        "old-generation",
        "chunk-version",
    ],
)
def test_ineligible_candidate_cannot_create_content_request(
    candidate: DerivedMemoCandidate,
):
    query = _query()
    snapshot = _snapshot(candidate)

    assert select_eligible_candidates(query, snapshot) == ()
    with pytest.raises(ContentRehydrationContractError):
        build_content_rehydration_request(
            query,
            snapshot,
            (candidate,),
            memos_authority_ref=MEMOS_AUTHORITY_REF,
        )


def test_unknown_generation_cannot_create_content_request():
    query = _query()
    snapshot = _snapshot(active_generation=None)

    with pytest.raises(ContentRehydrationContractError):
        build_content_rehydration_request(
            query,
            snapshot,
            (_candidate(),),
            memos_authority_ref=MEMOS_AUTHORITY_REF,
        )


def test_unauthorized_candidate_cannot_be_added_to_content_request():
    query = _query()
    snapshot = _snapshot()
    hidden = _candidate(
        memo_uid="memo-hidden",
        lifecycle_state=_applied_state("memo-hidden"),
    )

    with pytest.raises(ContentRehydrationContractError):
        build_content_rehydration_request(
            query,
            snapshot,
            (hidden,),
            memos_authority_ref=MEMOS_AUTHORITY_REF,
        )


@pytest.mark.parametrize(
    "authority_change",
    ["deleted", "archived", "comment", "blank", "visibility-revoked"],
)
def test_missing_authority_document_returns_no_partial_response(authority_change: str):
    query = _query("memo-visible", "memo-other")
    other = _candidate(
        record_key="record-other",
        memo_uid="memo-other",
        score=0.8,
        lifecycle_state=_applied_state("memo-other"),
    )
    snapshot = _snapshot(_candidate(), other)
    candidates = select_eligible_candidates(query, snapshot)
    request = build_content_rehydration_request(
        query,
        snapshot,
        candidates,
        memos_authority_ref=MEMOS_AUTHORITY_REF,
    )
    only_visible = MemosCurrentAuthoritySnapshot(
        memos_authority_ref=MEMOS_AUTHORITY_REF,
        authority_token="authority-synthetic-9",
        documents=(
            MemosAuthorizedCurrentDocument(
                "memo-visible", DOCUMENT, 3, DOCUMENT_HASH
            ),
        ),
    )

    assert authority_change
    with pytest.raises(ContentRehydrationContractError):
        rehydrate_from_memos_authority(request, only_visible)


@pytest.mark.parametrize(
    "authority_document",
    [
        MemosAuthorizedCurrentDocument(
            "memo-visible", UPDATED_DOCUMENT, 4, UPDATED_HASH
        ),
        MemosAuthorizedCurrentDocument(
            "memo-visible", UPDATED_DOCUMENT, 3, UPDATED_HASH
        ),
    ],
    ids=["concurrent-update-sequence", "concurrent-update-hash"],
)
def test_concurrent_update_cannot_mix_candidate_and_current_content(
    authority_document: MemosAuthorizedCurrentDocument,
):
    _, _, _, request = _request_bundle()

    with pytest.raises(ContentRehydrationContractError):
        rehydrate_from_memos_authority(request, _authority(authority_document))


def test_generation_or_revision_switch_after_authority_read_fails_closed():
    query, snapshot, candidates, request = _request_bundle()
    response = rehydrate_from_memos_authority(request, _authority())

    with pytest.raises(ContentRehydrationContractError):
        materialize_rehydrated_documents(
            query,
            snapshot,
            candidates,
            request,
            response,
            memos_authority_ref=MEMOS_AUTHORITY_REF,
            current_snapshot_token="snapshot-after-switch",
        )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("source_sequence", 4),
        ("document_hash", UPDATED_HASH),
        ("index_version", "memo-chunk-v1"),
    ],
)
def test_response_identity_or_version_mismatch_is_rejected(field: str, value: object):
    query, snapshot, candidates, request = _request_bundle()
    item = {
        "selection_ref": "rehydration-1",
        "document": UPDATED_DOCUMENT if field == "document_hash" else DOCUMENT,
        "source_sequence": 3,
        "document_hash": DOCUMENT_HASH,
        "index_version": "memo-v1",
    }
    item[field] = value
    if field == "source_sequence":
        item["document"] = DOCUMENT
    response_payload = {
        "version": CONTENT_REHYDRATION_VERSION,
        "snapshot_token": request.snapshot_token,
        "authority_token": "authority-synthetic-9",
        "documents": [item],
    }

    if field == "index_version":
        with pytest.raises(ContentRehydrationContractError):
            ContentRehydrationResponse.from_dict(response_payload)
        return
    response = ContentRehydrationResponse.from_dict(response_payload)
    with pytest.raises(ContentRehydrationContractError):
        materialize_rehydrated_documents(
            query,
            snapshot,
            candidates,
            request,
            response,
            memos_authority_ref=MEMOS_AUTHORITY_REF,
            current_snapshot_token=request.snapshot_token,
        )


@pytest.mark.parametrize(
    "mutation",
    [
        lambda payload: payload.update({"citation": {"memo_uid": "memo-hidden"}}),
        lambda payload: payload["selections"][0].update({"visibility": "public"}),
        lambda payload: payload.update({"question": "raw question"}),
        lambda payload: payload.update({"version": "memo-evidence-rehydration-v2"}),
    ],
    ids=["provider-citation", "derived-visibility", "raw-question", "unknown-version"],
)
def test_request_exact_schema_rejects_authority_expansion(mutation):
    _, _, _, request = _request_bundle()
    payload = copy.deepcopy(request.to_dict())
    mutation(payload)

    with pytest.raises(ContentRehydrationContractError):
        ContentRehydrationRequest.from_dict(payload)


def test_duplicate_request_identity_and_duplicate_authority_identity_are_rejected():
    _, _, _, request = _request_bundle()
    duplicated = request.to_dict()
    duplicated["selections"] = duplicated["selections"] * 2

    with pytest.raises(ContentRehydrationContractError):
        ContentRehydrationRequest.from_dict(duplicated)
    document = _authority().documents[0]
    with pytest.raises(ContentRehydrationContractError):
        MemosCurrentAuthoritySnapshot(
            MEMOS_AUTHORITY_REF,
            "authority-synthetic-9",
            (document, document),
        )


def test_duplicate_or_unknown_response_selection_is_rejected():
    _, _, _, request = _request_bundle()
    response = rehydrate_from_memos_authority(request, _authority()).to_dict()
    response["documents"] = response["documents"] * 2

    with pytest.raises(ContentRehydrationContractError):
        ContentRehydrationResponse.from_dict(response)
    with pytest.raises(ContentRehydrationContractError):
        RehydratedContent.from_dict(
            {
                **rehydrate_from_memos_authority(
                    request, _authority()
                ).documents[0].to_dict(),
                "memo_uid": "memo-visible",
            }
        )


def test_failure_projection_is_fixed_bounded_and_content_free():
    raw = RuntimeError(
        "SELECT secret FROM memo WHERE question='raw' endpoint=http://private"
    )

    projected = map_content_rehydration_failure(raw)

    assert projected.to_dict() == {
        "error_code": "authorized_retrieval_unavailable"
    }
    serialized = repr(projected.to_dict())
    for forbidden in (
        "select",
        "secret",
        "question",
        "endpoint",
        "memo",
        "identity",
        "visibility",
    ):
        assert forbidden not in serialized.lower()

    with pytest.raises(ContentRehydrationContractError):
        ContentRehydrationFailure.from_dict(
            {
                "error_code": "authorized_retrieval_unavailable",
                "detail": str(raw),
            }
        )
