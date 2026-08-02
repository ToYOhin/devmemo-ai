"""Authenticated transport contract for Memos evidence rehydration."""

from __future__ import annotations

import hashlib
import hmac
import json
import re
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable, Literal, Protocol

from app.domain.agent_lifecycle import MAX_DOCUMENT_CHARS
from app.domain.evidence_rehydration import (
    CONTENT_REHYDRATION_PATH,
    CONTENT_REHYDRATION_SIGNATURE_PURPOSE,
    MAX_REHYDRATION_ITEMS,
    ContentRehydrationContractError,
    ContentRehydrationFailure,
    ContentRehydrationRequest,
    ContentRehydrationResponse,
    MemosCurrentAuthoritySnapshot,
    rehydrate_from_memos_authority,
)


REHYDRATION_TRANSPORT_VERSION = "memo-evidence-rehydration-transport-v1"
REHYDRATION_REQUEST_SIGNATURE_HEADER = "X-DevMemo-Rehydration-Signature"
REHYDRATION_REQUEST_TIMESTAMP_HEADER = "X-DevMemo-Rehydration-Timestamp"
REHYDRATION_REQUEST_NONCE_HEADER = "X-DevMemo-Rehydration-Nonce"
REHYDRATION_REQUEST_VERSION_HEADER = "X-DevMemo-Rehydration-Version"
REHYDRATION_RESPONSE_SIGNATURE_HEADER = "X-DevMemo-Rehydration-Response-Signature"
REHYDRATION_RESPONSE_TIMESTAMP_HEADER = "X-DevMemo-Rehydration-Response-Timestamp"
REHYDRATION_RESPONSE_NONCE_HEADER = "X-DevMemo-Rehydration-Response-Nonce"
REHYDRATION_RESPONSE_VERSION_HEADER = "X-DevMemo-Rehydration-Response-Version"
REHYDRATION_SIGNATURE_PREFIX = "sha256="
REHYDRATION_RESPONSE_SIGNATURE_PURPOSE = (
    "devmemo-agent-evidence-rehydration-response-v1"
)
MAX_REHYDRATION_REQUEST_BYTES = 32_768
MAX_REHYDRATION_RESPONSE_BYTES = (
    MAX_REHYDRATION_ITEMS * MAX_DOCUMENT_CHARS * 4 + 65_536
)
REHYDRATION_MAX_AGE_SECONDS = 60
REHYDRATION_TIMEOUT_SECONDS = 5
REHYDRATION_AUTO_RETRY = False

_NONCE_PATTERN = re.compile(r"^[A-Za-z0-9_-]{16,128}$")
_SIGNATURE_PATTERN = re.compile(r"^sha256=[0-9a-f]{64}$")
_TIMESTAMP_PATTERN = re.compile(r"^[0-9]{1,12}$")


class RehydrationTransportError(ValueError):
    """Reject transport state with one fixed content-free message."""

    def __init__(self) -> None:
        super().__init__("authorized retrieval unavailable")

    def to_dict(self) -> dict[str, str]:
        return ContentRehydrationFailure().to_dict()


@dataclass(frozen=True)
class RehydrationRequestHeaders:
    signature: str
    timestamp: str
    nonce: str
    version: str


@dataclass(frozen=True)
class PreparedRehydrationRequest:
    body: bytes
    headers: RehydrationRequestHeaders


@dataclass(frozen=True)
class RehydrationResponseHeaders:
    signature: str
    timestamp: str
    request_nonce: str
    version: str


@dataclass(frozen=True)
class PreparedRehydrationResponse:
    status_code: int
    body: bytes
    headers: RehydrationResponseHeaders


class MemosCurrentAuthorityReader(Protocol):
    def read_current(
        self,
        request: ContentRehydrationRequest,
    ) -> MemosCurrentAuthoritySnapshot:
        ...


class RehydrationReplayStore:
    """Bounded process-local proof; it is not a multi-instance replay store."""

    def __init__(self, max_entries: int = 1_024) -> None:
        if type(max_entries) is not int or max_entries < 1:
            raise ValueError("max_entries must be positive")
        self.max_entries = max_entries
        self._expires_at: dict[str, int] = {}
        self._lock = threading.Lock()

    def consume(
        self,
        scope: Literal["request", "response"],
        nonce: str,
        *,
        now_seconds: int,
        expires_at: int,
    ) -> None:
        if (
            scope not in {"request", "response"}
            or not isinstance(nonce, str)
            or not _NONCE_PATTERN.fullmatch(nonce)
            or type(now_seconds) is not int
            or type(expires_at) is not int
            or expires_at < now_seconds
        ):
            raise RehydrationTransportError
        key = f"{scope}:{nonce}"
        with self._lock:
            expired = [
                stored_key
                for stored_key, stored_expiry in self._expires_at.items()
                if stored_expiry < now_seconds
            ]
            for stored_key in expired:
                del self._expires_at[stored_key]

            if key in self._expires_at or len(self._expires_at) >= self.max_entries:
                raise RehydrationTransportError
            self._expires_at[key] = expires_at


def sign_rehydration_request(
    body: bytes,
    timestamp: int,
    nonce: str,
    secret: str,
    *,
    method: str = "POST",
    path: str = CONTENT_REHYDRATION_PATH,
    version: str = REHYDRATION_TRANSPORT_VERSION,
) -> RehydrationRequestHeaders:
    """Sign the exact request body under the rehydration-only domain."""

    if not _valid_request_inputs(
        body=body,
        timestamp=timestamp,
        nonce=nonce,
        secret=secret,
        method=method,
        path=path,
        version=version,
    ):
        raise RehydrationTransportError
    timestamp_text = str(timestamp)
    digest = hmac.new(
        secret.encode("utf-8"),
        _canonical_request(
            method,
            path,
            version,
            timestamp_text,
            nonce,
            body,
        ),
        hashlib.sha256,
    ).hexdigest()
    return RehydrationRequestHeaders(
        signature=f"{REHYDRATION_SIGNATURE_PREFIX}{digest}",
        timestamp=timestamp_text,
        nonce=nonce,
        version=version,
    )


def prepare_rehydration_request(
    request: ContentRehydrationRequest,
    timestamp: int,
    nonce: str,
    secret: str,
) -> PreparedRehydrationRequest:
    """Serialize and sign only the exact R5-I3 request projection."""

    if not isinstance(request, ContentRehydrationRequest):
        raise RehydrationTransportError
    body = _serialize_exact_object(request.to_dict())
    return PreparedRehydrationRequest(
        body=body,
        headers=sign_rehydration_request(body, timestamp, nonce, secret),
    )


def verify_rehydration_request(
    method: str,
    path: str,
    body: bytes,
    headers: RehydrationRequestHeaders,
    secret: str,
    now: datetime,
    replay_store: RehydrationReplayStore,
    *,
    max_age_seconds: int = REHYDRATION_MAX_AGE_SECONDS,
) -> ContentRehydrationRequest:
    """Authenticate, exactly parse, then consume one request nonce."""

    try:
        if not isinstance(headers, RehydrationRequestHeaders) or not isinstance(
            replay_store, RehydrationReplayStore
        ):
            raise RehydrationTransportError
        issued_at, now_seconds = _validate_time_window(
            headers.timestamp,
            now,
            max_age_seconds,
        )
        if (
            not _valid_request_inputs(
                body=body,
                timestamp=issued_at,
                nonce=headers.nonce,
                secret=secret,
                method=method,
                path=path,
                version=headers.version,
            )
            or not _SIGNATURE_PATTERN.fullmatch(headers.signature)
        ):
            raise RehydrationTransportError
        expected = sign_rehydration_request(
            body,
            issued_at,
            headers.nonce,
            secret,
            method=method,
            path=path,
            version=headers.version,
        )
        if not hmac.compare_digest(expected.signature, headers.signature):
            raise RehydrationTransportError

        request = ContentRehydrationRequest.from_dict(_load_exact_object(body))
        replay_store.consume(
            "request",
            headers.nonce,
            now_seconds=now_seconds,
            expires_at=issued_at + max_age_seconds,
        )
        return request
    except RehydrationTransportError:
        raise
    except (
        ContentRehydrationContractError,
        TypeError,
        ValueError,
        UnicodeDecodeError,
    ):
        raise RehydrationTransportError from None


def sign_rehydration_response(
    body: bytes,
    status_code: int,
    timestamp: int,
    request_nonce: str,
    snapshot_token: str,
    secret: str,
    *,
    method: str = "POST",
    path: str = CONTENT_REHYDRATION_PATH,
    version: str = REHYDRATION_TRANSPORT_VERSION,
) -> RehydrationResponseHeaders:
    """Sign status and body under a response-only integrity domain."""

    if not _valid_response_inputs(
        body=body,
        status_code=status_code,
        timestamp=timestamp,
        request_nonce=request_nonce,
        snapshot_token=snapshot_token,
        secret=secret,
        method=method,
        path=path,
        version=version,
    ):
        raise RehydrationTransportError
    timestamp_text = str(timestamp)
    digest = hmac.new(
        secret.encode("utf-8"),
        _canonical_response(
            method,
            path,
            version,
            timestamp_text,
            request_nonce,
            snapshot_token,
            status_code,
            body,
        ),
        hashlib.sha256,
    ).hexdigest()
    return RehydrationResponseHeaders(
        signature=f"{REHYDRATION_SIGNATURE_PREFIX}{digest}",
        timestamp=timestamp_text,
        request_nonce=request_nonce,
        version=version,
    )


def prepare_rehydration_response(
    result: ContentRehydrationResponse | ContentRehydrationFailure,
    request: ContentRehydrationRequest,
    request_nonce: str,
    timestamp: int,
    secret: str,
) -> PreparedRehydrationResponse:
    """Create one signed exact success or fixed failure response."""

    if not isinstance(request, ContentRehydrationRequest):
        raise RehydrationTransportError
    if isinstance(result, ContentRehydrationResponse):
        if result.snapshot_token != request.snapshot_token:
            raise RehydrationTransportError
        status_code = 200
    elif isinstance(result, ContentRehydrationFailure):
        status_code = 503
    else:
        raise RehydrationTransportError
    body = _serialize_exact_object(result.to_dict())
    return PreparedRehydrationResponse(
        status_code=status_code,
        body=body,
        headers=sign_rehydration_response(
            body,
            status_code,
            timestamp,
            request_nonce,
            request.snapshot_token,
            secret,
        ),
    )


def handle_rehydration_request(
    prepared: PreparedRehydrationRequest,
    secret: str,
    now: datetime,
    request_replay_store: RehydrationReplayStore,
    authority_reader: MemosCurrentAuthorityReader,
    *,
    max_age_seconds: int = REHYDRATION_MAX_AGE_SECONDS,
) -> PreparedRehydrationResponse:
    """Run the authenticated proof in process without a route or client."""

    if not isinstance(prepared, PreparedRehydrationRequest):
        raise RehydrationTransportError
    request = verify_rehydration_request(
        "POST",
        CONTENT_REHYDRATION_PATH,
        prepared.body,
        prepared.headers,
        secret,
        now,
        request_replay_store,
        max_age_seconds=max_age_seconds,
    )
    try:
        authority = authority_reader.read_current(request)
        if not isinstance(authority, MemosCurrentAuthoritySnapshot):
            raise TypeError
        result: ContentRehydrationResponse | ContentRehydrationFailure = (
            rehydrate_from_memos_authority(request, authority)
        )
    except Exception:
        result = ContentRehydrationFailure()
    response_timestamp = int(now.astimezone(timezone.utc).timestamp())
    return prepare_rehydration_response(
        result,
        request,
        prepared.headers.nonce,
        response_timestamp,
        secret,
    )


def parse_rehydration_response(
    prepared: PreparedRehydrationResponse,
    expected_request: ContentRehydrationRequest,
    expected_request_nonce: str,
    secret: str,
    now: datetime,
    response_replay_store: RehydrationReplayStore,
    *,
    max_age_seconds: int = REHYDRATION_MAX_AGE_SECONDS,
) -> ContentRehydrationResponse | ContentRehydrationFailure:
    """Verify response integrity before exact parsing and replay consumption."""

    try:
        if (
            not isinstance(prepared, PreparedRehydrationResponse)
            or not isinstance(expected_request, ContentRehydrationRequest)
            or not isinstance(response_replay_store, RehydrationReplayStore)
        ):
            raise RehydrationTransportError
        headers = prepared.headers
        if not isinstance(headers, RehydrationResponseHeaders):
            raise RehydrationTransportError
        issued_at, now_seconds = _validate_time_window(
            headers.timestamp,
            now,
            max_age_seconds,
        )
        if (
            headers.request_nonce != expected_request_nonce
            or not _SIGNATURE_PATTERN.fullmatch(headers.signature)
            or not _valid_response_inputs(
                body=prepared.body,
                status_code=prepared.status_code,
                timestamp=issued_at,
                request_nonce=headers.request_nonce,
                snapshot_token=expected_request.snapshot_token,
                secret=secret,
                method="POST",
                path=CONTENT_REHYDRATION_PATH,
                version=headers.version,
            )
        ):
            raise RehydrationTransportError
        expected = sign_rehydration_response(
            prepared.body,
            prepared.status_code,
            issued_at,
            headers.request_nonce,
            expected_request.snapshot_token,
            secret,
            version=headers.version,
        )
        if not hmac.compare_digest(expected.signature, headers.signature):
            raise RehydrationTransportError

        payload = _load_exact_object(prepared.body)
        if prepared.status_code == 200:
            result: ContentRehydrationResponse | ContentRehydrationFailure = (
                ContentRehydrationResponse.from_dict(payload)
            )
            if result.snapshot_token != expected_request.snapshot_token:
                raise RehydrationTransportError
            _require_response_matches_request(result, expected_request)
        else:
            result = ContentRehydrationFailure.from_dict(payload)
        response_replay_store.consume(
            "response",
            headers.request_nonce,
            now_seconds=now_seconds,
            expires_at=issued_at + max_age_seconds,
        )
        return result
    except RehydrationTransportError:
        raise
    except (
        ContentRehydrationContractError,
        TypeError,
        ValueError,
        UnicodeDecodeError,
    ):
        raise RehydrationTransportError from None


def _valid_request_inputs(
    *,
    body: object,
    timestamp: object,
    nonce: object,
    secret: object,
    method: object,
    path: object,
    version: object,
) -> bool:
    return bool(
        isinstance(method, str)
        and method.strip().upper() == "POST"
        and path == CONTENT_REHYDRATION_PATH
        and version == REHYDRATION_TRANSPORT_VERSION
        and type(timestamp) is int
        and 0 <= timestamp <= 999_999_999_999
        and isinstance(secret, str)
        and secret.strip()
        and isinstance(nonce, str)
        and _NONCE_PATTERN.fullmatch(nonce)
        and isinstance(body, bytes)
        and 0 < len(body) <= MAX_REHYDRATION_REQUEST_BYTES
    )


def _valid_response_inputs(
    *,
    body: object,
    status_code: object,
    timestamp: object,
    request_nonce: object,
    snapshot_token: object,
    secret: object,
    method: object,
    path: object,
    version: object,
) -> bool:
    return bool(
        isinstance(method, str)
        and method.strip().upper() == "POST"
        and path == CONTENT_REHYDRATION_PATH
        and version == REHYDRATION_TRANSPORT_VERSION
        and type(status_code) is int
        and status_code in {200, 503}
        and type(timestamp) is int
        and 0 <= timestamp <= 999_999_999_999
        and isinstance(request_nonce, str)
        and _NONCE_PATTERN.fullmatch(request_nonce)
        and isinstance(snapshot_token, str)
        and re.fullmatch(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$", snapshot_token)
        and isinstance(secret, str)
        and secret.strip()
        and isinstance(body, bytes)
        and 0 < len(body) <= MAX_REHYDRATION_RESPONSE_BYTES
    )


def _validate_time_window(
    timestamp: object,
    now: object,
    max_age_seconds: object,
) -> tuple[int, int]:
    if (
        type(max_age_seconds) is not int
        or max_age_seconds < 1
        or max_age_seconds > REHYDRATION_MAX_AGE_SECONDS
        or not isinstance(now, datetime)
        or now.tzinfo is None
        or now.utcoffset() is None
    ):
        raise RehydrationTransportError
    if not isinstance(timestamp, str) or not _TIMESTAMP_PATTERN.fullmatch(timestamp):
        raise RehydrationTransportError
    issued_at = int(timestamp)
    now_seconds = int(now.astimezone(timezone.utc).timestamp())
    if issued_at > now_seconds or now_seconds - issued_at > max_age_seconds:
        raise RehydrationTransportError
    return issued_at, now_seconds


def _canonical_request(
    method: str,
    path: str,
    version: str,
    timestamp: str,
    nonce: str,
    body: bytes,
) -> bytes:
    return b"\n".join(
        (
            CONTENT_REHYDRATION_SIGNATURE_PURPOSE.encode("ascii"),
            version.encode("ascii"),
            method.strip().upper().encode("ascii"),
            path.encode("utf-8"),
            timestamp.encode("ascii"),
            nonce.encode("ascii"),
            hashlib.sha256(body).hexdigest().encode("ascii"),
        )
    )


def _canonical_response(
    method: str,
    path: str,
    version: str,
    timestamp: str,
    request_nonce: str,
    snapshot_token: str,
    status_code: int,
    body: bytes,
) -> bytes:
    return b"\n".join(
        (
            REHYDRATION_RESPONSE_SIGNATURE_PURPOSE.encode("ascii"),
            version.encode("ascii"),
            method.strip().upper().encode("ascii"),
            path.encode("utf-8"),
            timestamp.encode("ascii"),
            request_nonce.encode("ascii"),
            snapshot_token.encode("ascii"),
            str(status_code).encode("ascii"),
            hashlib.sha256(body).hexdigest().encode("ascii"),
        )
    )


def _serialize_exact_object(payload: dict[str, object]) -> bytes:
    return json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")


def _load_exact_object(body: bytes) -> dict[str, object]:
    def reject_duplicates(pairs: Iterable[tuple[str, object]]) -> dict[str, object]:
        result: dict[str, object] = {}
        for key, value in pairs:
            if key in result:
                raise RehydrationTransportError
            result[key] = value
        return result

    payload = json.loads(body, object_pairs_hook=reject_duplicates)
    if not isinstance(payload, dict):
        raise RehydrationTransportError
    return payload


def _require_response_matches_request(
    response: ContentRehydrationResponse,
    request: ContentRehydrationRequest,
) -> None:
    if len(response.documents) != len(request.selections):
        raise RehydrationTransportError
    by_ref = {document.selection_ref: document for document in response.documents}
    for selection in request.selections:
        document = by_ref.get(selection.selection_ref)
        if document is None or (
            document.source_sequence != selection.source_sequence
            or document.document_hash != selection.document_hash
            or document.index_version != selection.index_version
        ):
            raise RehydrationTransportError
