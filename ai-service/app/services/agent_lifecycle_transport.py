"""Pure authenticated transport contracts for dormant memo lifecycle events."""

from __future__ import annotations

import hashlib
import hmac
import json
import re
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable, Protocol

from app.domain.agent_lifecycle import (
    MAX_DOCUMENT_CHARS,
    LifecycleAcknowledgement,
    LifecycleContractError,
    MemoLifecycleEvent,
)


INTERNAL_LIFECYCLE_PATH = "/internal/ai/memo-lifecycle/events"
LIFECYCLE_SIGNATURE_HEADER = "X-DevMemo-Lifecycle-Signature"
LIFECYCLE_TIMESTAMP_HEADER = "X-DevMemo-Lifecycle-Timestamp"
LIFECYCLE_NONCE_HEADER = "X-DevMemo-Lifecycle-Nonce"
LIFECYCLE_SIGNATURE_PREFIX = "sha256="
LIFECYCLE_SIGNATURE_PURPOSE = "devmemo-memo-lifecycle-transport-v1"
MAX_LIFECYCLE_REQUEST_BYTES = MAX_DOCUMENT_CHARS + 4096
MAX_LIFECYCLE_ACKNOWLEDGEMENT_BYTES = 2048

_NONCE_PATTERN = re.compile(r"^[A-Za-z0-9_-]{16,128}$")
_SIGNATURE_PATTERN = re.compile(r"^sha256=[0-9a-f]{64}$")


class LifecycleTransportError(ValueError):
    """Fail closed without exposing request, signature, or event details."""


@dataclass(frozen=True)
class LifecycleTransportHeaders:
    signature: str
    timestamp: str
    nonce: str


@dataclass(frozen=True)
class PreparedLifecycleRequest:
    body: bytes
    headers: LifecycleTransportHeaders


class LifecycleEventProcessor(Protocol):
    def process(self, event: MemoLifecycleEvent) -> LifecycleAcknowledgement:
        ...


class LifecycleNonceReplayStore:
    """Bounded process-local replay window for in-process contract tests."""

    def __init__(self, max_entries: int = 1024) -> None:
        if type(max_entries) is not int or max_entries < 1:
            raise ValueError("max_entries must be positive")
        self.max_entries = max_entries
        self._expires_at: dict[str, int] = {}
        self._lock = threading.Lock()

    def consume(self, nonce: str, *, now_seconds: int, expires_at: int) -> None:
        with self._lock:
            expired = [
                stored_nonce
                for stored_nonce, stored_expiry in self._expires_at.items()
                if stored_expiry < now_seconds
            ]
            for stored_nonce in expired:
                del self._expires_at[stored_nonce]

            if nonce in self._expires_at or len(self._expires_at) >= self.max_entries:
                raise LifecycleTransportError("invalid lifecycle transport")
            self._expires_at[nonce] = expires_at


def sign_lifecycle_request(
    body: bytes,
    timestamp: int,
    nonce: str,
    secret: str,
    *,
    method: str = "POST",
    path: str = INTERNAL_LIFECYCLE_PATH,
) -> LifecycleTransportHeaders:
    """Sign the fixed lifecycle purpose, path, nonce, timestamp, and body digest."""

    if (
        method.strip().upper() != "POST"
        or path != INTERNAL_LIFECYCLE_PATH
        or type(timestamp) is not int
        or not secret.strip()
        or not _NONCE_PATTERN.fullmatch(nonce)
        or not isinstance(body, bytes)
        or not 0 < len(body) <= MAX_LIFECYCLE_REQUEST_BYTES
    ):
        raise LifecycleTransportError("invalid lifecycle transport")
    timestamp_text = str(timestamp)
    digest = hmac.new(
        secret.encode("utf-8"),
        _canonical_request(method, path, timestamp_text, nonce, body),
        hashlib.sha256,
    ).hexdigest()
    return LifecycleTransportHeaders(
        signature=f"{LIFECYCLE_SIGNATURE_PREFIX}{digest}",
        timestamp=timestamp_text,
        nonce=nonce,
    )


def prepare_lifecycle_request(
    event: MemoLifecycleEvent,
    timestamp: int,
    nonce: str,
    secret: str,
) -> PreparedLifecycleRequest:
    """Serialize only the exact A4-I1 event projection and sign those bytes."""

    body = json.dumps(
        event.to_dict(),
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    return PreparedLifecycleRequest(
        body=body,
        headers=sign_lifecycle_request(body, timestamp, nonce, secret),
    )


def verify_lifecycle_request(
    method: str,
    path: str,
    body: bytes,
    headers: LifecycleTransportHeaders,
    secret: str,
    now: datetime,
    replay_store: LifecycleNonceReplayStore,
    *,
    max_age_seconds: int = 60,
) -> MemoLifecycleEvent:
    """Authenticate and parse one exact lifecycle event, then consume its nonce."""

    try:
        if (
            method.strip().upper() != "POST"
            or path != INTERNAL_LIFECYCLE_PATH
            or not secret.strip()
            or type(max_age_seconds) is not int
            or max_age_seconds < 1
            or not _SIGNATURE_PATTERN.fullmatch(headers.signature)
            or not _NONCE_PATTERN.fullmatch(headers.nonce)
            or not isinstance(body, bytes)
            or not 0 < len(body) <= MAX_LIFECYCLE_REQUEST_BYTES
            or now.tzinfo is None
            or now.utcoffset() is None
        ):
            raise LifecycleTransportError("invalid lifecycle transport")

        issued_at = int(headers.timestamp)
        now_seconds = int(now.astimezone(timezone.utc).timestamp())
        if issued_at > now_seconds or now_seconds - issued_at > max_age_seconds:
            raise LifecycleTransportError("invalid lifecycle transport")

        expected = sign_lifecycle_request(
            body,
            issued_at,
            headers.nonce,
            secret,
            method=method,
            path=path,
        )
        if not hmac.compare_digest(expected.signature, headers.signature):
            raise LifecycleTransportError("invalid lifecycle transport")

        event = MemoLifecycleEvent.from_dict(_load_exact_object(body))
        replay_store.consume(
            headers.nonce,
            now_seconds=now_seconds,
            expires_at=issued_at + max_age_seconds,
        )
        return event
    except LifecycleTransportError:
        raise
    except (LifecycleContractError, TypeError, ValueError, UnicodeDecodeError) as error:
        raise LifecycleTransportError("invalid lifecycle transport") from error


def handle_lifecycle_request(
    request: PreparedLifecycleRequest,
    secret: str,
    now: datetime,
    replay_store: LifecycleNonceReplayStore,
    processor: LifecycleEventProcessor,
    *,
    max_age_seconds: int = 60,
) -> bytes:
    """Run the pure authenticated contract without opening a network listener."""

    event = verify_lifecycle_request(
        "POST",
        INTERNAL_LIFECYCLE_PATH,
        request.body,
        request.headers,
        secret,
        now,
        replay_store,
        max_age_seconds=max_age_seconds,
    )
    try:
        acknowledgement = processor.process(event)
        _require_matching_acknowledgement(acknowledgement, event)
    except Exception:
        acknowledgement = LifecycleAcknowledgement(
            event_id=event.event_id,
            memo_uid=event.memo_uid,
            source_sequence=event.source_sequence,
            status="failed",
            operation=event.operation,
            error_code="lifecycle_processing_failed",
        )
    return _serialize_acknowledgement(acknowledgement)


def parse_lifecycle_acknowledgement(
    body: bytes,
    expected_event: MemoLifecycleEvent,
) -> LifecycleAcknowledgement:
    """Accept only the content-free A4-I1 acknowledgement for this event."""

    try:
        if (
            not isinstance(body, bytes)
            or not 0 < len(body) <= MAX_LIFECYCLE_ACKNOWLEDGEMENT_BYTES
        ):
            raise LifecycleTransportError("invalid lifecycle acknowledgement")
        acknowledgement = LifecycleAcknowledgement.from_dict(_load_exact_object(body))
        _require_matching_acknowledgement(acknowledgement, expected_event)
        return acknowledgement
    except (
        LifecycleContractError,
        LifecycleTransportError,
        TypeError,
        ValueError,
        UnicodeDecodeError,
    ) as error:
        raise LifecycleTransportError("invalid lifecycle acknowledgement") from error


def _canonical_request(
    method: str, path: str, timestamp: str, nonce: str, body: bytes
) -> bytes:
    body_digest = hashlib.sha256(body).hexdigest()
    return b"\n".join(
        (
            LIFECYCLE_SIGNATURE_PURPOSE.encode("ascii"),
            method.strip().upper().encode("ascii"),
            path.encode("utf-8"),
            timestamp.encode("ascii"),
            nonce.encode("ascii"),
            body_digest.encode("ascii"),
        )
    )


def _load_exact_object(body: bytes) -> dict[str, object]:
    def reject_duplicates(pairs: Iterable[tuple[str, object]]) -> dict[str, object]:
        result: dict[str, object] = {}
        for key, value in pairs:
            if key in result:
                raise LifecycleTransportError("invalid lifecycle transport")
            result[key] = value
        return result

    payload = json.loads(body, object_pairs_hook=reject_duplicates)
    if not isinstance(payload, dict):
        raise LifecycleTransportError("invalid lifecycle transport")
    return payload


def _require_matching_acknowledgement(
    acknowledgement: LifecycleAcknowledgement,
    event: MemoLifecycleEvent,
) -> None:
    if (
        acknowledgement.event_id != event.event_id
        or acknowledgement.memo_uid != event.memo_uid
        or acknowledgement.source_sequence != event.source_sequence
        or acknowledgement.index_version != event.index_version
        or acknowledgement.operation != event.operation
    ):
        raise LifecycleTransportError("invalid lifecycle acknowledgement")


def _serialize_acknowledgement(acknowledgement: LifecycleAcknowledgement) -> bytes:
    return json.dumps(
        acknowledgement.to_dict(),
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
