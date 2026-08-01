import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from app.services.agent_delegation import (
    INTERNAL_ANSWER_PATH,
    AgentDelegationHeaders,
    AgentDelegationError,
    sign_delegated_request,
    verify_delegated_request,
)
from app.services.agent_lifecycle_transport import (
    INTERNAL_LIFECYCLE_PATH,
    LIFECYCLE_SIGNATURE_PURPOSE,
    LifecycleNonceReplayStore,
    PreparedLifecycleRequest,
    LifecycleTransportError,
    LifecycleTransportHeaders,
    handle_lifecycle_request,
    parse_lifecycle_acknowledgement,
    prepare_lifecycle_request,
    sign_lifecycle_request,
    verify_lifecycle_request,
)
from app.domain.agent_lifecycle import LifecycleAcknowledgement, MemoLifecycleEvent


class StubLifecycleProcessor:
    def __init__(
        self,
        acknowledgement: LifecycleAcknowledgement | None = None,
        error: Exception | None = None,
    ) -> None:
        self.acknowledgement = acknowledgement
        self.error = error
        self.events: list[MemoLifecycleEvent] = []

    def process(self, event: MemoLifecycleEvent) -> LifecycleAcknowledgement:
        self.events.append(event)
        if self.error is not None:
            raise self.error
        if self.acknowledgement is None:
            return LifecycleAcknowledgement(
                event_id=event.event_id,
                memo_uid=event.memo_uid,
                source_sequence=event.source_sequence,
                status="applied",
                operation=event.operation,
            )
        return self.acknowledgement


def _fixture() -> dict[str, str]:
    fixture_path = (
        Path(__file__).resolve().parents[2]
        / "contracts"
        / "memo-lifecycle-transport-v1.json"
    )
    return json.loads(fixture_path.read_text(encoding="utf-8"))


def _now(offset: int = 0) -> datetime:
    timestamp = int(_fixture()["timestamp"]) + offset
    return datetime.fromtimestamp(timestamp, timezone.utc)


def test_lifecycle_signature_matches_cross_language_fixture():
    fixture = _fixture()
    body = fixture["raw_body"].encode("utf-8")
    headers = sign_lifecycle_request(
        body,
        int(fixture["timestamp"]),
        fixture["nonce"],
        fixture["secret"],
    )

    event = verify_lifecycle_request(
        fixture["method"],
        fixture["path"],
        body,
        headers,
        fixture["secret"],
        _now(30),
        LifecycleNonceReplayStore(),
    )

    assert fixture["purpose"] == LIFECYCLE_SIGNATURE_PURPOSE
    assert headers.signature == fixture["signature"]
    assert event.event_id == "event-index-1"


@pytest.mark.parametrize(
    ("method", "path", "body_suffix", "secret", "now_offset"),
    [
        ("GET", INTERNAL_LIFECYCLE_PATH, b"", "synthetic-lifecycle-secret", 0),
        ("POST", "/other", b"", "synthetic-lifecycle-secret", 0),
        ("POST", INTERNAL_LIFECYCLE_PATH, b" ", "synthetic-lifecycle-secret", 0),
        ("POST", INTERNAL_LIFECYCLE_PATH, b"", "wrong-secret", 0),
        ("POST", INTERNAL_LIFECYCLE_PATH, b"", "synthetic-lifecycle-secret", 61),
        ("POST", INTERNAL_LIFECYCLE_PATH, b"", "synthetic-lifecycle-secret", -1),
    ],
)
def test_lifecycle_transport_rejects_tampering_expiry_and_future_time(
    method: str,
    path: str,
    body_suffix: bytes,
    secret: str,
    now_offset: int,
):
    fixture = _fixture()
    body = fixture["raw_body"].encode("utf-8")
    headers = LifecycleTransportHeaders(
        fixture["signature"], fixture["timestamp"], fixture["nonce"]
    )

    with pytest.raises(LifecycleTransportError, match="invalid lifecycle transport"):
        verify_lifecycle_request(
            method,
            path,
            body + body_suffix,
            headers,
            secret,
            _now(now_offset),
            LifecycleNonceReplayStore(),
        )


def test_lifecycle_nonce_is_single_use_within_bounded_window():
    fixture = _fixture()
    body = fixture["raw_body"].encode("utf-8")
    headers = LifecycleTransportHeaders(
        fixture["signature"], fixture["timestamp"], fixture["nonce"]
    )
    replay_store = LifecycleNonceReplayStore(max_entries=2)

    verify_lifecycle_request(
        "POST",
        INTERNAL_LIFECYCLE_PATH,
        body,
        headers,
        fixture["secret"],
        _now(30),
        replay_store,
    )

    with pytest.raises(LifecycleTransportError, match="invalid lifecycle transport"):
        verify_lifecycle_request(
            "POST",
            INTERNAL_LIFECYCLE_PATH,
            body,
            headers,
            fixture["secret"],
            _now(31),
            replay_store,
        )


def test_lifecycle_nonce_store_fails_closed_at_capacity_and_reclaims_expired_entries():
    store = LifecycleNonceReplayStore(max_entries=1)
    store.consume("lifecycle-nonce-0001", now_seconds=100, expires_at=160)

    with pytest.raises(LifecycleTransportError, match="invalid lifecycle transport"):
        store.consume("lifecycle-nonce-0002", now_seconds=120, expires_at=180)

    store.consume("lifecycle-nonce-0002", now_seconds=161, expires_at=221)


def test_lifecycle_transport_rejects_nonce_and_timestamp_tampering():
    fixture = _fixture()
    body = fixture["raw_body"].encode("utf-8")
    for headers in (
        LifecycleTransportHeaders(
            fixture["signature"], fixture["timestamp"], "lifecycle-nonce-0002"
        ),
        LifecycleTransportHeaders(
            fixture["signature"], str(int(fixture["timestamp"]) - 1), fixture["nonce"]
        ),
    ):
        with pytest.raises(LifecycleTransportError, match="invalid lifecycle transport"):
            verify_lifecycle_request(
                "POST",
                INTERNAL_LIFECYCLE_PATH,
                body,
                headers,
                fixture["secret"],
                _now(),
                LifecycleNonceReplayStore(),
            )


def test_lifecycle_and_answer_signatures_are_domain_separated():
    fixture = _fixture()
    body = fixture["raw_body"].encode("utf-8")
    timestamp = int(fixture["timestamp"])
    lifecycle_headers = sign_lifecycle_request(
        body, timestamp, fixture["nonce"], fixture["secret"]
    )
    answer_headers = sign_delegated_request(
        "POST", INTERNAL_ANSWER_PATH, body, timestamp, fixture["secret"]
    )

    assert lifecycle_headers.signature != answer_headers.signature
    with pytest.raises(LifecycleTransportError, match="invalid lifecycle transport"):
        verify_lifecycle_request(
            "POST",
            INTERNAL_LIFECYCLE_PATH,
            body,
            LifecycleTransportHeaders(
                answer_headers.signature, answer_headers.timestamp, fixture["nonce"]
            ),
            fixture["secret"],
            _now(),
            LifecycleNonceReplayStore(),
        )
    with pytest.raises(AgentDelegationError, match="invalid Agent delegation"):
        verify_delegated_request(
            "POST",
            INTERNAL_ANSWER_PATH,
            body,
            AgentDelegationHeaders(
                lifecycle_headers.signature, lifecycle_headers.timestamp
            ),
            fixture["secret"],
            _now(),
        )


def test_lifecycle_transport_rejects_body_changed_after_signing():
    fixture = _fixture()
    payload = json.loads(fixture["raw_body"])
    payload["event_id"] = "different-event"
    body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    headers = LifecycleTransportHeaders(
        fixture["signature"], fixture["timestamp"], fixture["nonce"]
    )

    with pytest.raises(LifecycleTransportError, match="invalid lifecycle transport"):
        verify_lifecycle_request(
            "POST",
            INTERNAL_LIFECYCLE_PATH,
            body,
            headers,
            fixture["secret"],
            _now(),
            LifecycleNonceReplayStore(),
        )


@pytest.mark.parametrize("field", ["memo_uid", "source_sequence", "document"])
def test_lifecycle_transport_rejects_signed_event_with_missing_field(field: str):
    fixture = _fixture()
    payload = json.loads(fixture["raw_body"])
    del payload[field]
    body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    headers = sign_lifecycle_request(
        body, int(fixture["timestamp"]), fixture["nonce"], fixture["secret"]
    )

    with pytest.raises(LifecycleTransportError, match="invalid lifecycle transport"):
        verify_lifecycle_request(
            "POST",
            INTERNAL_LIFECYCLE_PATH,
            body,
            headers,
            fixture["secret"],
            _now(),
            LifecycleNonceReplayStore(),
        )


def test_lifecycle_transport_rejects_signed_event_with_unknown_or_duplicate_field():
    fixture = _fixture()
    payload = json.loads(fixture["raw_body"])
    payload["visibility"] = "PRIVATE"
    unknown_body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    duplicate_body = fixture["raw_body"].replace(
        '"event_id":"event-index-1"',
        '"event_id":"event-index-1","event_id":"duplicate"',
    ).encode("utf-8")

    for body, nonce in (
        (unknown_body, "lifecycle-nonce-0002"),
        (duplicate_body, "lifecycle-nonce-0003"),
    ):
        headers = sign_lifecycle_request(
            body, int(fixture["timestamp"]), nonce, fixture["secret"]
        )
        with pytest.raises(LifecycleTransportError, match="invalid lifecycle transport"):
            verify_lifecycle_request(
                "POST",
                INTERNAL_LIFECYCLE_PATH,
                body,
                headers,
                fixture["secret"],
                _now(),
                LifecycleNonceReplayStore(),
            )


def test_in_process_handler_and_client_round_trip_content_free_acknowledgement():
    fixture = _fixture()
    event = MemoLifecycleEvent.from_dict(json.loads(fixture["raw_body"]))
    request = prepare_lifecycle_request(
        event,
        int(fixture["timestamp"]),
        fixture["nonce"],
        fixture["secret"],
    )
    processor = StubLifecycleProcessor()

    response = handle_lifecycle_request(
        request,
        fixture["secret"],
        _now(30),
        LifecycleNonceReplayStore(),
        processor,
    )
    acknowledgement = parse_lifecycle_acknowledgement(response, event)

    assert processor.events == [event]
    assert acknowledgement.status == "applied"
    assert set(json.loads(response)) == {
        "event_id",
        "memo_uid",
        "source_sequence",
        "index_version",
        "status",
        "operation",
    }


def test_handler_rejects_authentication_before_processor_execution():
    fixture = _fixture()
    event = MemoLifecycleEvent.from_dict(json.loads(fixture["raw_body"]))
    request = prepare_lifecycle_request(
        event,
        int(fixture["timestamp"]),
        fixture["nonce"],
        fixture["secret"],
    )
    tampered_request = PreparedLifecycleRequest(
        body=request.body + b" ", headers=request.headers
    )
    processor = StubLifecycleProcessor()

    with pytest.raises(LifecycleTransportError) as error:
        handle_lifecycle_request(
            tampered_request,
            fixture["secret"],
            _now(),
            LifecycleNonceReplayStore(),
            processor,
        )

    assert str(error.value) == "invalid lifecycle transport"
    assert processor.events == []
    assert event.document is not None
    assert event.document not in str(error.value)


@pytest.mark.parametrize(
    "unsafe_field",
    [
        "document",
        "document_hash",
        "prompt",
        "context",
        "embedding",
        "visibility",
        "identity",
        "secret",
    ],
)
def test_client_rejects_acknowledgement_with_unsafe_field(unsafe_field: str):
    fixture = _fixture()
    event = MemoLifecycleEvent.from_dict(json.loads(fixture["raw_body"]))
    payload: dict[str, object] = {
        "event_id": event.event_id,
        "memo_uid": event.memo_uid,
        "source_sequence": event.source_sequence,
        "index_version": event.index_version,
        "status": "applied",
        "operation": event.operation,
        unsafe_field: "forbidden",
    }

    with pytest.raises(LifecycleTransportError, match="invalid lifecycle acknowledgement"):
        parse_lifecycle_acknowledgement(
            json.dumps(payload, separators=(",", ":")).encode("utf-8"), event
        )


def test_client_rejects_acknowledgement_for_another_event():
    fixture = _fixture()
    event = MemoLifecycleEvent.from_dict(json.loads(fixture["raw_body"]))
    payload = LifecycleAcknowledgement(
        event_id="other-event",
        memo_uid=event.memo_uid,
        source_sequence=event.source_sequence,
        status="applied",
        operation=event.operation,
    ).to_dict()

    with pytest.raises(LifecycleTransportError, match="invalid lifecycle acknowledgement"):
        parse_lifecycle_acknowledgement(
            json.dumps(payload, separators=(",", ":")).encode("utf-8"), event
        )


def test_handler_maps_processor_exception_without_raw_details():
    fixture = _fixture()
    event = MemoLifecycleEvent.from_dict(json.loads(fixture["raw_body"]))
    request = prepare_lifecycle_request(
        event,
        int(fixture["timestamp"]),
        fixture["nonce"],
        fixture["secret"],
    )
    processor = StubLifecycleProcessor(error=RuntimeError(event.document or "raw memo"))

    response = handle_lifecycle_request(
        request,
        fixture["secret"],
        _now(),
        LifecycleNonceReplayStore(),
        processor,
    )
    acknowledgement = parse_lifecycle_acknowledgement(response, event)

    assert acknowledgement.status == "failed"
    assert acknowledgement.error_code == "lifecycle_processing_failed"
    assert event.document is not None
    assert event.document not in response.decode("utf-8")


def test_handler_preserves_bounded_vector_failure_acknowledgement():
    fixture = _fixture()
    event = MemoLifecycleEvent.from_dict(json.loads(fixture["raw_body"]))
    failed_ack = LifecycleAcknowledgement(
        event_id=event.event_id,
        memo_uid=event.memo_uid,
        source_sequence=event.source_sequence,
        status="failed",
        operation=event.operation,
        error_code="vector_store_unavailable",
    )
    request = prepare_lifecycle_request(
        event,
        int(fixture["timestamp"]),
        fixture["nonce"],
        fixture["secret"],
    )

    response = handle_lifecycle_request(
        request,
        fixture["secret"],
        _now(),
        LifecycleNonceReplayStore(),
        StubLifecycleProcessor(acknowledgement=failed_ack),
    )

    assert parse_lifecycle_acknowledgement(response, event) == failed_ack
