import json
from pathlib import Path

import pytest

from app.domain.agent_lifecycle import (
    LifecycleAcknowledgement,
    LifecycleContractError,
    MemoLifecycleEvent,
    accept_lifecycle_event,
    complete_lifecycle_event,
    fail_lifecycle_event,
    hash_lifecycle_document,
    is_retrieval_eligible,
)


DOCUMENT = "# Docker\n\nPort mapping uses the Memos BFF."


def _event_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "event_id": "event-1",
        "event_type": "memo.index.requested.v1",
        "memo_uid": "memo-1",
        "source_sequence": 1,
        "index_version": "memo-v1",
        "operation": "upsert",
        "reason": "created",
        "occurred_at": "2026-08-01T10:00:00+08:00",
        "document": DOCUMENT,
        "document_hash": hash_lifecycle_document(DOCUMENT),
    }
    payload.update(overrides)
    return payload


def _event(sequence: int, *, event_id: str | None = None, document: str = DOCUMENT):
    return MemoLifecycleEvent.from_dict(
        _event_payload(
            event_id=event_id or f"event-{sequence}",
            source_sequence=sequence,
            document=document,
            document_hash=hash_lifecycle_document(document),
        )
    )


def _delete_event(sequence: int, *, event_id: str | None = None):
    payload = _event_payload(
        event_id=event_id or f"event-{sequence}",
        event_type="memo.delete.requested.v1",
        source_sequence=sequence,
        operation="delete",
        reason="deleted",
    )
    del payload["document"]
    del payload["document_hash"]
    return MemoLifecycleEvent.from_dict(payload)


def _reindex_event(sequence: int, *, reason: str = "restored", document: str = "restored"):
    return MemoLifecycleEvent.from_dict(
        _event_payload(
            event_id=f"event-{sequence}",
            event_type="memo.reindex.requested.v1",
            source_sequence=sequence,
            reason=reason,
            document=document,
            document_hash=hash_lifecycle_document(document),
        )
    )


def test_lifecycle_event_round_trips_exact_index_contract():
    event = MemoLifecycleEvent.from_dict(_event_payload())

    assert event.occurred_at.isoformat() == "2026-08-01T10:00:00+08:00"
    assert event.to_dict() == _event_payload()


def test_shared_lifecycle_fixture_round_trips_strict_contracts():
    fixture_path = Path(__file__).resolve().parents[2] / "contracts" / "memo-lifecycle-v1.json"
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))

    events = [MemoLifecycleEvent.from_dict(payload) for payload in fixture["events"]]
    acknowledgements = [
        LifecycleAcknowledgement.from_dict(payload)
        for payload in fixture["acknowledgements"]
    ]

    assert fixture["version"] == "memo-lifecycle-v1"
    assert [event.to_dict() for event in events] == fixture["events"]
    assert [ack.to_dict() for ack in acknowledgements] == fixture["acknowledgements"]


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"event_type": "memo.unknown.v1"}, "event_type"),
        ({"index_version": "memo-chunk-v1"}, "memo-v1"),
        ({"source_sequence": 0}, "positive integer"),
        ({"source_sequence": True}, "positive integer"),
        ({"operation": "delete"}, "operation does not match"),
        ({"reason": "deleted"}, "reason is not allowed"),
        ({"occurred_at": "2026-08-01T10:00:00"}, "UTC offset"),
        ({"document": "  "}, "non-blank document"),
        ({"document_hash": "0" * 64}, "does not match"),
    ],
)
def test_lifecycle_event_rejects_invalid_values(overrides: dict[str, object], message: str):
    with pytest.raises(LifecycleContractError, match=message):
        MemoLifecycleEvent.from_dict(_event_payload(**overrides))


@pytest.mark.parametrize("field", ["event_id", "memo_uid", "source_sequence", "document"])
def test_lifecycle_event_rejects_missing_fields(field: str):
    payload = _event_payload()
    del payload[field]

    with pytest.raises(LifecycleContractError, match="missing="):
        MemoLifecycleEvent.from_dict(payload)


def test_lifecycle_event_rejects_unknown_fields():
    with pytest.raises(LifecycleContractError, match="unknown=visibility"):
        MemoLifecycleEvent.from_dict(_event_payload(visibility="private"))


def test_delete_event_is_a_content_free_tombstone():
    payload = _event_payload(
        event_type="memo.delete.requested.v1",
        operation="delete",
        reason="deleted",
    )
    del payload["document"]
    del payload["document_hash"]

    event = MemoLifecycleEvent.from_dict(payload)

    assert event.document is None
    assert event.document_hash is None
    assert event.to_dict() == payload


@pytest.mark.parametrize("field", ["document", "document_hash"])
def test_delete_event_rejects_document_fields(field: str):
    payload = _event_payload(
        event_type="memo.delete.requested.v1",
        operation="delete",
        reason="deleted",
    )
    other_field = "document_hash" if field == "document" else "document"
    del payload[other_field]

    with pytest.raises(LifecycleContractError, match=f"unknown={field}"):
        MemoLifecycleEvent.from_dict(payload)


def test_acknowledgement_serializes_only_the_allowlisted_projection():
    acknowledgement = LifecycleAcknowledgement(
        event_id="event-1",
        memo_uid="memo-1",
        source_sequence=1,
        status="failed",
        operation="upsert",
        error_code="same_sequence_conflict",
    )

    assert acknowledgement.to_dict() == {
        "event_id": "event-1",
        "memo_uid": "memo-1",
        "source_sequence": 1,
        "index_version": "memo-v1",
        "status": "failed",
        "operation": "upsert",
        "error_code": "same_sequence_conflict",
    }


@pytest.mark.parametrize(
    "unsafe_field",
    [
        "document",
        "document_hash",
        "prompt",
        "context",
        "embedding",
        "identity",
        "visibility",
        "secret",
    ],
)
def test_acknowledgement_parser_rejects_non_allowlisted_fields(unsafe_field: str):
    payload = {
        "event_id": "event-1",
        "memo_uid": "memo-1",
        "source_sequence": 1,
        "index_version": "memo-v1",
        "status": "applied",
        "operation": "upsert",
        unsafe_field: "not allowed",
    }

    with pytest.raises(LifecycleContractError, match=f"unknown={unsafe_field}"):
        LifecycleAcknowledgement.from_dict(payload)


def test_acknowledgement_error_code_is_bounded_and_failure_only():
    with pytest.raises(LifecycleContractError, match="requires a safe error_code"):
        LifecycleAcknowledgement(
            event_id="event-1",
            memo_uid="memo-1",
            source_sequence=1,
            status="failed",
            operation="upsert",
            error_code="raw Memo: Docker",
        )

    with pytest.raises(LifecycleContractError, match="only failed"):
        LifecycleAcknowledgement(
            event_id="event-1",
            memo_uid="memo-1",
            source_sequence=1,
            status="applied",
            operation="upsert",
            error_code="unexpected",
        )


def test_new_event_reserves_applying_state_before_becoming_retrievable():
    event = _event(1)

    transition = accept_lifecycle_event(None, event)

    assert transition.decision == "apply"
    assert transition.acknowledgement is None
    assert transition.state.status == "applying"
    assert transition.state.highest_accepted_sequence == 1
    assert not is_retrieval_eligible(
        transition.state,
        vector_source_sequence=1,
        vector_document_hash=event.document_hash or "",
    )


def test_completed_upsert_is_retrievable_only_with_matching_sequence_and_hash():
    event = _event(1)
    applying = accept_lifecycle_event(None, event).state

    applied, acknowledgement = complete_lifecycle_event(applying, event)

    assert acknowledgement.status == "applied"
    assert is_retrieval_eligible(
        applied,
        vector_source_sequence=1,
        vector_document_hash=event.document_hash or "",
    )
    assert not is_retrieval_eligible(
        applied,
        vector_source_sequence=2,
        vector_document_hash=event.document_hash or "",
    )
    assert not is_retrieval_eligible(
        applied,
        vector_source_sequence=1,
        vector_document_hash=hash_lifecycle_document("other"),
    )


def test_applied_identical_event_is_acknowledged_as_duplicate():
    event = _event(1)
    applied, _ = complete_lifecycle_event(accept_lifecycle_event(None, event).state, event)

    replay = accept_lifecycle_event(applied, event)

    assert replay.decision == "duplicate"
    assert replay.state is applied
    assert replay.acknowledgement is not None
    assert replay.acknowledgement.status == "duplicate"


@pytest.mark.parametrize("initial_status", ["applying", "failed"])
def test_interrupted_identical_event_resumes_idempotently(initial_status: str):
    event = _event(1)
    state = accept_lifecycle_event(None, event).state
    if initial_status == "failed":
        state, _ = fail_lifecycle_event(state, event, "vector_store_unavailable")

    replay = accept_lifecycle_event(state, event)

    assert replay.decision == "resume"
    assert replay.state.status == "applying"
    assert replay.state.highest_accepted_sequence == 1
    assert replay.acknowledgement is None


def test_failed_event_keeps_previous_vector_quarantined_until_retry_completes():
    first = _event(1)
    applied, _ = complete_lifecycle_event(accept_lifecycle_event(None, first).state, first)
    second = _event(2, document="updated")
    applying = accept_lifecycle_event(applied, second).state

    failed, acknowledgement = fail_lifecycle_event(
        applying, second, "vector_store_unavailable"
    )

    assert acknowledgement.to_dict()["error_code"] == "vector_store_unavailable"
    assert failed.last_applied_sequence == 1
    assert failed.highest_accepted_sequence == 2
    assert not is_retrieval_eligible(
        failed,
        vector_source_sequence=1,
        vector_document_hash=first.document_hash or "",
    )


def test_lower_sequence_is_stale_and_cannot_change_state():
    newer = _event(2)
    state = accept_lifecycle_event(None, newer).state

    stale = accept_lifecycle_event(state, _event(1))

    assert stale.decision == "stale"
    assert stale.state is state
    assert stale.acknowledgement is not None
    assert stale.acknowledgement.status == "stale"


@pytest.mark.parametrize(
    "conflicting_event",
    [
        _event(1, event_id="different-event"),
        _event(1, document="different document"),
        _delete_event(1),
        MemoLifecycleEvent.from_dict(
            _event_payload(occurred_at="2026-08-01T10:00:01+08:00")
        ),
    ],
)
def test_same_sequence_conflict_fails_without_replacing_state(conflicting_event):
    original = _event(1)
    state = accept_lifecycle_event(None, original).state

    conflict = accept_lifecycle_event(state, conflicting_event)

    assert conflict.decision == "conflict"
    assert conflict.state is state
    assert conflict.acknowledgement is not None
    assert conflict.acknowledgement.to_dict()["error_code"] == "same_sequence_conflict"
    assert accept_lifecycle_event(conflict.state, original).decision == "resume"


def test_higher_sequence_supersedes_and_quarantines_previous_applied_vector():
    first = _event(1)
    first_applied, _ = complete_lifecycle_event(
        accept_lifecycle_event(None, first).state, first
    )
    second = _event(2, document="updated")

    superseding = accept_lifecycle_event(first_applied, second)

    assert superseding.decision == "apply"
    assert superseding.state.status == "applying"
    assert superseding.state.last_applied_sequence == 1
    assert not is_retrieval_eligible(
        superseding.state,
        vector_source_sequence=1,
        vector_document_hash=first.document_hash or "",
    )

    second_applied, _ = complete_lifecycle_event(superseding.state, second)
    assert is_retrieval_eligible(
        second_applied,
        vector_source_sequence=2,
        vector_document_hash=second.document_hash or "",
    )


def test_delete_reserves_tombstone_and_blocks_stale_resurrection():
    first = _event(1)
    first_applied, _ = complete_lifecycle_event(
        accept_lifecycle_event(None, first).state, first
    )
    deletion = _delete_event(2)

    deleting = accept_lifecycle_event(first_applied, deletion)

    assert deleting.state.tombstone_sequence == 2
    assert not is_retrieval_eligible(
        deleting.state,
        vector_source_sequence=1,
        vector_document_hash=first.document_hash or "",
    )

    deleted, acknowledgement = complete_lifecycle_event(deleting.state, deletion)
    assert acknowledgement.status == "applied"
    assert deleted.last_applied_operation == "delete"
    assert not is_retrieval_eligible(
        deleted,
        vector_source_sequence=1,
        vector_document_hash=first.document_hash or "",
    )

    delayed = accept_lifecycle_event(deleted, first)
    assert delayed.decision == "stale"
    assert delayed.state.tombstone_sequence == 2


def test_higher_reindex_can_restore_after_an_older_tombstone():
    deletion = _delete_event(2)
    deleted, _ = complete_lifecycle_event(
        accept_lifecycle_event(None, deletion).state, deletion
    )
    restored = _reindex_event(3)

    restored_state, _ = complete_lifecycle_event(
        accept_lifecycle_event(deleted, restored).state, restored
    )

    assert restored_state.tombstone_sequence == 2
    assert is_retrieval_eligible(
        restored_state,
        vector_source_sequence=3,
        vector_document_hash=restored.document_hash or "",
    )


def test_state_rejects_an_event_for_another_memo():
    event = _event(1)
    state = accept_lifecycle_event(None, event).state
    other_payload = _event_payload(event_id="other-event", memo_uid="memo-2")

    with pytest.raises(LifecycleContractError, match="does not target"):
        accept_lifecycle_event(state, MemoLifecycleEvent.from_dict(other_payload))


def test_event_state_keeps_only_a_safe_fingerprint_not_the_document():
    event = _event(1)

    state = accept_lifecycle_event(None, event).state

    assert state.accepted_event_fingerprint != event.document_hash
    assert DOCUMENT not in repr(state)
