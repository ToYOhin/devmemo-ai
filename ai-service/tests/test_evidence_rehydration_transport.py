from __future__ import annotations

import copy
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from app.domain.evidence_rehydration import (
    CONTENT_REHYDRATION_PATH,
    CONTENT_REHYDRATION_SIGNATURE_PURPOSE,
    ContentRehydrationFailure,
    ContentRehydrationRequest,
    ContentRehydrationResponse,
    MemosAuthorizedCurrentDocument,
    MemosCurrentAuthoritySnapshot,
)
from app.services.agent_delegation import INTERNAL_ANSWER_PATH, sign_delegated_request
from app.services.agent_lifecycle_transport import (
    sign_lifecycle_request,
)
from app.services.evidence_rehydration_transport import (
    MAX_REHYDRATION_REQUEST_BYTES,
    MAX_REHYDRATION_RESPONSE_BYTES,
    REHYDRATION_AUTO_RETRY,
    REHYDRATION_REQUEST_NONCE_HEADER,
    REHYDRATION_REQUEST_SIGNATURE_HEADER,
    REHYDRATION_REQUEST_TIMESTAMP_HEADER,
    REHYDRATION_REQUEST_VERSION_HEADER,
    REHYDRATION_RESPONSE_NONCE_HEADER,
    REHYDRATION_RESPONSE_SIGNATURE_HEADER,
    REHYDRATION_RESPONSE_SIGNATURE_PURPOSE,
    REHYDRATION_RESPONSE_TIMESTAMP_HEADER,
    REHYDRATION_RESPONSE_VERSION_HEADER,
    REHYDRATION_TIMEOUT_SECONDS,
    REHYDRATION_TRANSPORT_VERSION,
    PreparedRehydrationRequest,
    PreparedRehydrationResponse,
    RehydrationReplayStore,
    RehydrationRequestHeaders,
    RehydrationResponseHeaders,
    RehydrationTransportError,
    handle_rehydration_request,
    parse_rehydration_response,
    prepare_rehydration_request,
    prepare_rehydration_response,
    sign_rehydration_request,
    sign_rehydration_response,
    verify_rehydration_request,
)


TIMESTAMP = 1_785_643_200
NONCE = "rehydration-nonce-0001"
SECRET = "synthetic-rehydration-secret"
CONTRACT_PATH = (
    Path(__file__).resolve().parents[2]
    / "contracts"
    / "memo-evidence-rehydration-v1.json"
)
TRANSPORT_CONTRACT_PATH = (
    Path(__file__).resolve().parents[2]
    / "contracts"
    / "memo-evidence-rehydration-transport-v1.json"
)


def _request_payload() -> dict[str, object]:
    return json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))["request"]


def _response_payload() -> dict[str, object]:
    return json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))["response"]


def _transport_fixture() -> dict[str, object]:
    return json.loads(TRANSPORT_CONTRACT_PATH.read_text(encoding="utf-8"))


def _request() -> ContentRehydrationRequest:
    return ContentRehydrationRequest.from_dict(_request_payload())


def _now(offset: int = 30) -> datetime:
    return datetime.fromtimestamp(TIMESTAMP + offset, timezone.utc)


def _authority() -> MemosCurrentAuthoritySnapshot:
    request = _request()
    response = ContentRehydrationResponse.from_dict(_response_payload())
    return MemosCurrentAuthoritySnapshot(
        memos_authority_ref=request.memos_authority_ref,
        authority_token=response.authority_token,
        documents=tuple(
            MemosAuthorizedCurrentDocument(
                memo_uid=selection.memo_uid,
                document=document.document,
                source_sequence=document.source_sequence,
                document_hash=document.document_hash,
                index_version=document.index_version,
            )
            for selection, document in zip(
                request.selections,
                response.documents,
                strict=True,
            )
        ),
    )


class StubAuthorityReader:
    def __init__(
        self,
        snapshot: MemosCurrentAuthoritySnapshot | None = None,
        error: BaseException | None = None,
    ) -> None:
        self.snapshot = snapshot or _authority()
        self.error = error
        self.requests: list[ContentRehydrationRequest] = []

    def read_current(
        self,
        request: ContentRehydrationRequest,
    ) -> MemosCurrentAuthoritySnapshot:
        self.requests.append(request)
        if self.error is not None:
            raise self.error
        return self.snapshot


def test_request_round_trip_uses_distinct_bounded_transport_policy():
    prepared = prepare_rehydration_request(_request(), TIMESTAMP, NONCE, SECRET)

    parsed = verify_rehydration_request(
        "POST",
        CONTENT_REHYDRATION_PATH,
        prepared.body,
        prepared.headers,
        SECRET,
        _now(),
        RehydrationReplayStore(),
    )

    assert parsed == _request()
    assert prepared.body == json.dumps(
        _request_payload(),
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    assert prepared.headers.version == REHYDRATION_TRANSPORT_VERSION
    assert REHYDRATION_TIMEOUT_SECONDS == 5
    assert REHYDRATION_AUTO_RETRY is False


def test_request_and_response_signatures_match_shared_transport_fixture():
    fixture = _transport_fixture()
    request_fixture = fixture["request"]
    response_fixture = fixture["response"]
    request_body = request_fixture["raw_body"].encode()
    response_body = response_fixture["raw_body"].encode()

    request_headers = sign_rehydration_request(
        request_body,
        int(request_fixture["timestamp"]),
        request_fixture["nonce"],
        fixture["secret"],
    )
    response_headers = sign_rehydration_response(
        response_body,
        response_fixture["status"],
        int(response_fixture["timestamp"]),
        response_fixture["request_nonce"],
        response_fixture["snapshot_token"],
        fixture["secret"],
    )

    assert fixture["version"] == REHYDRATION_TRANSPORT_VERSION
    assert fixture["path"] == CONTENT_REHYDRATION_PATH
    assert fixture["request_purpose"] == CONTENT_REHYDRATION_SIGNATURE_PURPOSE
    assert fixture["response_purpose"] == REHYDRATION_RESPONSE_SIGNATURE_PURPOSE
    assert request_headers.signature == request_fixture["signature"]
    assert response_headers.signature == response_fixture["signature"]
    assert json.loads(request_body) == _request_payload()
    assert json.loads(response_body) == _response_payload()


def test_request_header_namespace_is_independent():
    headers = {
        REHYDRATION_REQUEST_SIGNATURE_HEADER,
        REHYDRATION_REQUEST_TIMESTAMP_HEADER,
        REHYDRATION_REQUEST_NONCE_HEADER,
        REHYDRATION_REQUEST_VERSION_HEADER,
    }

    assert len(headers) == 4
    assert all(header.startswith("X-DevMemo-Rehydration-") for header in headers)


@pytest.mark.parametrize(
    ("method", "path", "body_suffix", "secret", "now_offset", "version"),
    [
        (
            "GET",
            CONTENT_REHYDRATION_PATH,
            b"",
            SECRET,
            30,
            REHYDRATION_TRANSPORT_VERSION,
        ),
        ("POST", "/other", b"", SECRET, 30, REHYDRATION_TRANSPORT_VERSION),
        (
            "POST",
            CONTENT_REHYDRATION_PATH,
            b" ",
            SECRET,
            30,
            REHYDRATION_TRANSPORT_VERSION,
        ),
        (
            "POST",
            CONTENT_REHYDRATION_PATH,
            b"",
            "wrong-secret",
            30,
            REHYDRATION_TRANSPORT_VERSION,
        ),
        (
            "POST",
            CONTENT_REHYDRATION_PATH,
            b"",
            SECRET,
            61,
            REHYDRATION_TRANSPORT_VERSION,
        ),
        (
            "POST",
            CONTENT_REHYDRATION_PATH,
            b"",
            SECRET,
            -1,
            REHYDRATION_TRANSPORT_VERSION,
        ),
        ("POST", CONTENT_REHYDRATION_PATH, b"", SECRET, 30, "unknown-version"),
    ],
)
def test_request_rejects_tampering_expiry_future_time_and_version(
    method: str,
    path: str,
    body_suffix: bytes,
    secret: str,
    now_offset: int,
    version: str,
):
    prepared = prepare_rehydration_request(_request(), TIMESTAMP, NONCE, SECRET)
    headers = RehydrationRequestHeaders(
        signature=prepared.headers.signature,
        timestamp=prepared.headers.timestamp,
        nonce=prepared.headers.nonce,
        version=version,
    )

    with pytest.raises(RehydrationTransportError) as error:
        verify_rehydration_request(
            method,
            path,
            prepared.body + body_suffix,
            headers,
            secret,
            _now(now_offset),
            RehydrationReplayStore(),
        )

    assert str(error.value) == "authorized retrieval unavailable"


def test_request_nonce_is_single_use_for_same_or_different_signed_body():
    first = prepare_rehydration_request(_request(), TIMESTAMP, NONCE, SECRET)
    changed_payload = copy.deepcopy(_request_payload())
    changed_payload["snapshot_token"] = "snapshot-synthetic-2"
    changed_body = json.dumps(changed_payload, separators=(",", ":")).encode()
    changed_headers = sign_rehydration_request(
        changed_body,
        TIMESTAMP,
        NONCE,
        SECRET,
    )
    store = RehydrationReplayStore()

    verify_rehydration_request(
        "POST",
        CONTENT_REHYDRATION_PATH,
        first.body,
        first.headers,
        SECRET,
        _now(),
        store,
    )

    for body, headers in (
        (first.body, first.headers),
        (changed_body, changed_headers),
    ):
        with pytest.raises(RehydrationTransportError):
            verify_rehydration_request(
                "POST",
                CONTENT_REHYDRATION_PATH,
                body,
                headers,
                SECRET,
                _now(31),
                store,
            )


@pytest.mark.parametrize("timestamp", ["1785643200.0", " 1785643200", "true"])
def test_request_rejects_noncanonical_timestamp_text(timestamp: str):
    prepared = prepare_rehydration_request(_request(), TIMESTAMP, NONCE, SECRET)
    headers = RehydrationRequestHeaders(
        prepared.headers.signature,
        timestamp,
        prepared.headers.nonce,
        prepared.headers.version,
    )

    with pytest.raises(RehydrationTransportError):
        verify_rehydration_request(
            "POST",
            CONTENT_REHYDRATION_PATH,
            prepared.body,
            headers,
            SECRET,
            _now(),
            RehydrationReplayStore(),
        )


def test_request_replay_store_fails_at_capacity_and_reclaims_expired_entry():
    store = RehydrationReplayStore(max_entries=1)
    store.consume("request", NONCE, now_seconds=100, expires_at=160)

    with pytest.raises(RehydrationTransportError):
        store.consume(
            "request",
            "rehydration-nonce-0002",
            now_seconds=120,
            expires_at=180,
        )

    store.consume(
        "request",
        "rehydration-nonce-0002",
        now_seconds=161,
        expires_at=221,
    )


def test_request_replay_store_rejects_invalid_expiry_and_scope():
    store = RehydrationReplayStore()

    with pytest.raises(RehydrationTransportError):
        store.consume("request", NONCE, now_seconds=101, expires_at=100)
    with pytest.raises(RehydrationTransportError):
        store.consume("shared", NONCE, now_seconds=100, expires_at=160)  # type: ignore[arg-type]


def test_request_age_window_cannot_be_expanded_past_contract_bound():
    prepared = prepare_rehydration_request(_request(), TIMESTAMP, NONCE, SECRET)

    with pytest.raises(RehydrationTransportError):
        verify_rehydration_request(
            "POST",
            CONTENT_REHYDRATION_PATH,
            prepared.body,
            prepared.headers,
            SECRET,
            _now(),
            RehydrationReplayStore(),
            max_age_seconds=61,
        )


def test_request_signature_is_separate_from_answer_and_lifecycle_domains():
    prepared = prepare_rehydration_request(_request(), TIMESTAMP, NONCE, SECRET)
    answer = sign_delegated_request(
        "POST",
        INTERNAL_ANSWER_PATH,
        prepared.body,
        TIMESTAMP,
        SECRET,
    )
    lifecycle = sign_lifecycle_request(
        prepared.body,
        TIMESTAMP,
        "lifecycle-nonce-0001",
        SECRET,
    )

    assert prepared.headers.signature not in {answer.signature, lifecycle.signature}


@pytest.mark.parametrize(
    "mutation",
    [
        lambda payload: payload.update({"visibility": "private"}),
        lambda payload: payload["selections"][0].update({"identity": "caller"}),
        lambda payload: payload.update({"version": "memo-evidence-rehydration-v2"}),
        lambda payload: payload.pop("memos_authority_ref"),
    ],
)
def test_signed_request_rejects_unknown_missing_or_unsafe_fields(mutation):
    payload = copy.deepcopy(_request_payload())
    mutation(payload)
    body = json.dumps(payload, separators=(",", ":")).encode()
    headers = sign_rehydration_request(body, TIMESTAMP, NONCE, SECRET)

    with pytest.raises(RehydrationTransportError):
        verify_rehydration_request(
            "POST",
            CONTENT_REHYDRATION_PATH,
            body,
            headers,
            SECRET,
            _now(),
            RehydrationReplayStore(),
        )


def test_signed_request_rejects_duplicate_json_key():
    body = json.dumps(_request_payload(), separators=(",", ":")).replace(
        '"snapshot_token":"snapshot-synthetic-1"',
        '"snapshot_token":"snapshot-synthetic-1","snapshot_token":"duplicate"',
    ).encode()
    headers = sign_rehydration_request(body, TIMESTAMP, NONCE, SECRET)

    with pytest.raises(RehydrationTransportError):
        verify_rehydration_request(
            "POST",
            CONTENT_REHYDRATION_PATH,
            body,
            headers,
            SECRET,
            _now(),
            RehydrationReplayStore(),
        )


def test_request_size_is_bounded_before_parsing():
    body = b"{" + b"x" * MAX_REHYDRATION_REQUEST_BYTES

    with pytest.raises(RehydrationTransportError):
        sign_rehydration_request(body, TIMESTAMP, NONCE, SECRET)


def test_request_failure_never_echoes_capability_body_or_signature():
    prepared = prepare_rehydration_request(_request(), TIMESTAMP, NONCE, SECRET)
    tampered = PreparedRehydrationRequest(
        body=prepared.body + b"raw",
        headers=prepared.headers,
    )

    with pytest.raises(RehydrationTransportError) as caught:
        verify_rehydration_request(
            "POST",
            CONTENT_REHYDRATION_PATH,
            tampered.body,
            tampered.headers,
            SECRET,
            _now(),
            RehydrationReplayStore(),
        )

    error = str(caught.value)
    for protected in (
        _request().memos_authority_ref,
        _request().selections[0].memo_uid,
        prepared.headers.signature,
        SECRET,
    ):
        assert protected not in error


def test_signed_handler_and_client_round_trip_exact_current_content():
    request = _request()
    prepared = prepare_rehydration_request(request, TIMESTAMP, NONCE, SECRET)
    reader = StubAuthorityReader()

    response = handle_rehydration_request(
        prepared,
        SECRET,
        _now(),
        RehydrationReplayStore(),
        reader,
    )
    result = parse_rehydration_response(
        response,
        request,
        NONCE,
        SECRET,
        _now(31),
        RehydrationReplayStore(),
    )

    assert isinstance(result, ContentRehydrationResponse)
    assert result.to_dict() == _response_payload()
    assert reader.requests == [request]
    assert response.status_code == 200
    assert response.headers.signature != prepared.headers.signature
    assert request.memos_authority_ref not in response.body.decode()
    assert request.memos_authority_ref not in repr(response.headers)


def test_response_header_namespace_and_signature_purpose_are_independent():
    headers = {
        REHYDRATION_RESPONSE_SIGNATURE_HEADER,
        REHYDRATION_RESPONSE_TIMESTAMP_HEADER,
        REHYDRATION_RESPONSE_NONCE_HEADER,
        REHYDRATION_RESPONSE_VERSION_HEADER,
    }

    assert len(headers) == 4
    assert all(
        header.startswith("X-DevMemo-Rehydration-Response-")
        for header in headers
    )
    assert REHYDRATION_RESPONSE_SIGNATURE_PURPOSE != REHYDRATION_TRANSPORT_VERSION


def test_handler_authenticates_and_exactly_parses_before_authority_read():
    prepared = prepare_rehydration_request(_request(), TIMESTAMP, NONCE, SECRET)
    tampered = PreparedRehydrationRequest(
        body=prepared.body + b" ",
        headers=prepared.headers,
    )
    reader = StubAuthorityReader()

    with pytest.raises(RehydrationTransportError):
        handle_rehydration_request(
            tampered,
            SECRET,
            _now(),
            RehydrationReplayStore(),
            reader,
        )

    assert reader.requests == []


@pytest.mark.parametrize(
    "failure",
    [
        TimeoutError("raw timeout endpoint"),
        RuntimeError("raw Memo visibility failure"),
    ],
    ids=["timeout", "authority-failure"],
)
def test_handler_maps_timeout_and_authority_failure_to_signed_fixed_response(
    failure: BaseException,
):
    request = _request()
    prepared = prepare_rehydration_request(request, TIMESTAMP, NONCE, SECRET)
    reader = StubAuthorityReader(error=failure)

    response = handle_rehydration_request(
        prepared,
        SECRET,
        _now(),
        RehydrationReplayStore(),
        reader,
    )
    result = parse_rehydration_response(
        response,
        request,
        NONCE,
        SECRET,
        _now(31),
        RehydrationReplayStore(),
    )

    assert result == ContentRehydrationFailure()
    assert response.status_code == 503
    assert response.body == b'{"error_code":"authorized_retrieval_unavailable"}'
    assert str(failure) not in response.body.decode()
    assert reader.requests == [request]


def test_handler_maps_authority_reference_mismatch_without_partial_content():
    request = _request()
    prepared = prepare_rehydration_request(request, TIMESTAMP, NONCE, SECRET)
    mismatched = MemosCurrentAuthoritySnapshot(
        memos_authority_ref="authority-ref-other-caller",
        authority_token=_authority().authority_token,
        documents=_authority().documents,
    )

    response = handle_rehydration_request(
        prepared,
        SECRET,
        _now(),
        RehydrationReplayStore(),
        StubAuthorityReader(snapshot=mismatched),
    )
    result = parse_rehydration_response(
        response,
        request,
        NONCE,
        SECRET,
        _now(31),
        RehydrationReplayStore(),
    )

    assert result == ContentRehydrationFailure()
    assert _response_payload()["documents"][0]["document"] not in response.body.decode()


@pytest.mark.parametrize(
    ("status_delta", "body_suffix", "secret", "now_offset", "nonce", "version"),
    [
        (1, b"", SECRET, 31, NONCE, REHYDRATION_TRANSPORT_VERSION),
        (0, b" ", SECRET, 31, NONCE, REHYDRATION_TRANSPORT_VERSION),
        (0, b"", "wrong-secret", 31, NONCE, REHYDRATION_TRANSPORT_VERSION),
        (0, b"", SECRET, 91, NONCE, REHYDRATION_TRANSPORT_VERSION),
        (0, b"", SECRET, 29, NONCE, REHYDRATION_TRANSPORT_VERSION),
        (0, b"", SECRET, 31, "rehydration-nonce-9999", REHYDRATION_TRANSPORT_VERSION),
        (0, b"", SECRET, 31, NONCE, "unknown-version"),
    ],
)
def test_response_rejects_status_body_auth_time_nonce_and_version_tampering(
    status_delta: int,
    body_suffix: bytes,
    secret: str,
    now_offset: int,
    nonce: str,
    version: str,
):
    request = _request()
    response = prepare_rehydration_response(
        ContentRehydrationResponse.from_dict(_response_payload()),
        request,
        NONCE,
        TIMESTAMP + 30,
        SECRET,
    )
    tampered = PreparedRehydrationResponse(
        status_code=response.status_code + status_delta,
        body=response.body + body_suffix,
        headers=RehydrationResponseHeaders(
            signature=response.headers.signature,
            timestamp=response.headers.timestamp,
            request_nonce=nonce,
            version=version,
        ),
    )

    with pytest.raises(RehydrationTransportError):
        parse_rehydration_response(
            tampered,
            request,
            NONCE,
            secret,
            _now(now_offset),
            RehydrationReplayStore(),
        )


def test_response_snapshot_replacement_is_rejected_by_signature_binding():
    request = _request()
    response = prepare_rehydration_response(
        ContentRehydrationResponse.from_dict(_response_payload()),
        request,
        NONCE,
        TIMESTAMP + 30,
        SECRET,
    )
    changed_request_payload = copy.deepcopy(_request_payload())
    changed_request_payload["snapshot_token"] = "snapshot-synthetic-2"
    changed_request = ContentRehydrationRequest.from_dict(changed_request_payload)

    with pytest.raises(RehydrationTransportError):
        parse_rehydration_response(
            response,
            changed_request,
            NONCE,
            SECRET,
            _now(31),
            RehydrationReplayStore(),
        )


@pytest.mark.parametrize(
    ("field", "value"),
    [("selection_ref", "rehydration-2"), ("source_sequence", 4)],
)
def test_signed_response_must_match_original_selection(field: str, value: object):
    request = _request()
    payload = copy.deepcopy(_response_payload())
    payload["documents"][0][field] = value
    body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode()
    headers = sign_rehydration_response(
        body,
        200,
        TIMESTAMP + 30,
        NONCE,
        request.snapshot_token,
        SECRET,
    )

    with pytest.raises(RehydrationTransportError):
        parse_rehydration_response(
            PreparedRehydrationResponse(200, body, headers),
            request,
            NONCE,
            SECRET,
            _now(31),
            RehydrationReplayStore(),
        )


def test_response_rejects_noncanonical_timestamp_text():
    request = _request()
    response = prepare_rehydration_response(
        ContentRehydrationResponse.from_dict(_response_payload()),
        request,
        NONCE,
        TIMESTAMP + 30,
        SECRET,
    )
    headers = RehydrationResponseHeaders(
        response.headers.signature,
        "1785643230.0",
        response.headers.request_nonce,
        response.headers.version,
    )

    with pytest.raises(RehydrationTransportError):
        parse_rehydration_response(
            PreparedRehydrationResponse(200, response.body, headers),
            request,
            NONCE,
            SECRET,
            _now(31),
            RehydrationReplayStore(),
        )


def test_response_nonce_is_single_use_at_client():
    request = _request()
    response = prepare_rehydration_response(
        ContentRehydrationResponse.from_dict(_response_payload()),
        request,
        NONCE,
        TIMESTAMP + 30,
        SECRET,
    )
    store = RehydrationReplayStore()

    parse_rehydration_response(
        response,
        request,
        NONCE,
        SECRET,
        _now(31),
        store,
    )

    with pytest.raises(RehydrationTransportError):
        parse_rehydration_response(
            response,
            request,
            NONCE,
            SECRET,
            _now(32),
            store,
        )


@pytest.mark.parametrize(
    "mutation",
    [
        lambda payload: payload.update({"memos_authority_ref": "forbidden"}),
        lambda payload: payload.update({"visibility": "private"}),
        lambda payload: payload["documents"][0].update({"memo_uid": "memo-visible"}),
        lambda payload: payload.update({"documents": []}),
    ],
)
def test_signed_success_response_rejects_unknown_authority_and_partial_fields(
    mutation,
):
    request = _request()
    payload = copy.deepcopy(_response_payload())
    mutation(payload)
    body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode()
    headers = sign_rehydration_response(
        body,
        200,
        TIMESTAMP + 30,
        NONCE,
        request.snapshot_token,
        SECRET,
    )

    with pytest.raises(RehydrationTransportError):
        parse_rehydration_response(
            PreparedRehydrationResponse(200, body, headers),
            request,
            NONCE,
            SECRET,
            _now(31),
            RehydrationReplayStore(),
        )


def test_signed_response_rejects_duplicate_json_key_before_replay_consumption():
    request = _request()
    body = json.dumps(_response_payload(), separators=(",", ":")).replace(
        '"authority_token":"authority-synthetic-9"',
        '"authority_token":"authority-synthetic-9","authority_token":"duplicate"',
    ).encode()
    headers = sign_rehydration_response(
        body,
        200,
        TIMESTAMP + 30,
        NONCE,
        request.snapshot_token,
        SECRET,
    )

    with pytest.raises(RehydrationTransportError):
        parse_rehydration_response(
            PreparedRehydrationResponse(200, body, headers),
            request,
            NONCE,
            SECRET,
            _now(31),
            RehydrationReplayStore(),
        )


def test_signed_failure_response_rejects_raw_detail():
    request = _request()
    body = b'{"error_code":"authorized_retrieval_unavailable","detail":"raw"}'
    headers = sign_rehydration_response(
        body,
        503,
        TIMESTAMP + 30,
        NONCE,
        request.snapshot_token,
        SECRET,
    )

    with pytest.raises(RehydrationTransportError):
        parse_rehydration_response(
            PreparedRehydrationResponse(503, body, headers),
            request,
            NONCE,
            SECRET,
            _now(31),
            RehydrationReplayStore(),
        )


def test_request_signature_cannot_authenticate_a_response():
    request = _request()
    prepared = prepare_rehydration_request(request, TIMESTAMP, NONCE, SECRET)
    response = PreparedRehydrationResponse(
        status_code=200,
        body=json.dumps(_response_payload(), separators=(",", ":")).encode(),
        headers=RehydrationResponseHeaders(
            signature=prepared.headers.signature,
            timestamp=str(TIMESTAMP),
            request_nonce=NONCE,
            version=REHYDRATION_TRANSPORT_VERSION,
        ),
    )

    with pytest.raises(RehydrationTransportError):
        parse_rehydration_response(
            response,
            request,
            NONCE,
            SECRET,
            _now(),
            RehydrationReplayStore(),
        )


def test_response_size_is_bounded_before_signing_or_parsing():
    body = b"{" + b"x" * MAX_REHYDRATION_RESPONSE_BYTES

    with pytest.raises(RehydrationTransportError):
        sign_rehydration_response(
            body,
            200,
            TIMESTAMP,
            NONCE,
            _request().snapshot_token,
            SECRET,
        )


def test_transport_error_projection_never_echoes_response_or_secret():
    error = RehydrationTransportError()

    assert error.to_dict() == {
        "error_code": "authorized_retrieval_unavailable"
    }
    serialized = repr(error.to_dict()) + str(error)
    for forbidden in (
        SECRET,
        _request().memos_authority_ref,
        _response_payload()["documents"][0]["document"],
        "signature",
        "digest",
        "endpoint",
        "visibility",
        "identity",
    ):
        assert forbidden not in serialized
