"""Existing-listener HTTP contract for the single-host lifecycle runtime."""

from __future__ import annotations

import hashlib
import hmac
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone

from app.services.agent_lifecycle_runtime import (
    LifecycleActivationRequest,
    MemoLifecycleRuntime,
)
from app.services.agent_lifecycle_transport import (
    INTERNAL_LIFECYCLE_PATH,
    LifecycleNonceReplayStore,
    LifecycleTransportError,
    LifecycleTransportHeaders,
    PreparedLifecycleRequest,
    handle_lifecycle_request,
)


INTERNAL_LIFECYCLE_ACTIVATION_PATH = "/internal/ai/memo-lifecycle/activate"
LIFECYCLE_ACTIVATION_SIGNATURE_PURPOSE = (
    "devmemo-memo-lifecycle-activation-v1"
)
MAX_LIFECYCLE_ACTIVATION_BYTES = 512

_NONCE_PATTERN = re.compile(r"^[A-Za-z0-9_-]{16,128}$")
_SIGNATURE_PATTERN = re.compile(r"^sha256=[0-9a-f]{64}$")


@dataclass(frozen=True)
class LifecycleHTTPResponse:
    status_code: int
    body: bytes = b""
    content_type: str | None = None


class MemoLifecycleHTTPAdapter:
    """Authenticate both lifecycle purposes before touching derived state."""

    def __init__(
        self,
        runtime: MemoLifecycleRuntime,
        secret: str,
        replay_store: LifecycleNonceReplayStore | None = None,
    ) -> None:
        if not secret.strip():
            raise ValueError("lifecycle secret must not be empty")
        self.runtime = runtime
        self.secret = secret
        self.replay_store = replay_store or LifecycleNonceReplayStore()

    def handle_event(
        self,
        *,
        method: str,
        path: str,
        body: bytes,
        headers: LifecycleTransportHeaders,
        now: datetime,
    ) -> LifecycleHTTPResponse:
        try:
            if method.strip().upper() != "POST" or path != INTERNAL_LIFECYCLE_PATH:
                raise LifecycleTransportError("invalid lifecycle transport")
            response = handle_lifecycle_request(
                PreparedLifecycleRequest(body, headers),
                self.secret,
                now,
                self.replay_store,
                self.runtime,
            )
            return LifecycleHTTPResponse(200, response, "application/json")
        except LifecycleTransportError:
            return LifecycleHTTPResponse(404)

    def handle_activation(
        self,
        *,
        method: str,
        path: str,
        body: bytes,
        headers: LifecycleTransportHeaders,
        now: datetime,
    ) -> LifecycleHTTPResponse:
        try:
            request = verify_lifecycle_activation_request(
                method,
                path,
                body,
                headers,
                self.secret,
                now,
                self.replay_store,
            )
        except LifecycleTransportError:
            return LifecycleHTTPResponse(404)
        try:
            self.runtime.activate(request)
            return LifecycleHTTPResponse(204)
        except Exception:
            return LifecycleHTTPResponse(503)


def prepare_lifecycle_activation_request(
    request: LifecycleActivationRequest,
    timestamp: int,
    nonce: str,
    secret: str,
) -> PreparedLifecycleRequest:
    body = json.dumps(
        {
            "generation": request.generation,
            "eligible_count": request.eligible_count,
            "manifest_digest": request.manifest_digest,
        },
        separators=(",", ":"),
    ).encode("utf-8")
    return PreparedLifecycleRequest(
        body,
        _sign_activation(body, timestamp, nonce, secret),
    )


def verify_lifecycle_activation_request(
    method: str,
    path: str,
    body: bytes,
    headers: LifecycleTransportHeaders,
    secret: str,
    now: datetime,
    replay_store: LifecycleNonceReplayStore,
    *,
    max_age_seconds: int = 60,
) -> LifecycleActivationRequest:
    try:
        if (
            method.strip().upper() != "POST"
            or path != INTERNAL_LIFECYCLE_ACTIVATION_PATH
            or not secret.strip()
            or not _SIGNATURE_PATTERN.fullmatch(headers.signature)
            or not _NONCE_PATTERN.fullmatch(headers.nonce)
            or not isinstance(body, bytes)
            or not 0 < len(body) <= MAX_LIFECYCLE_ACTIVATION_BYTES
            or now.tzinfo is None
            or now.utcoffset() is None
            or type(max_age_seconds) is not int
            or max_age_seconds < 1
        ):
            raise LifecycleTransportError("invalid lifecycle activation")
        issued_at = int(headers.timestamp)
        now_seconds = int(now.astimezone(timezone.utc).timestamp())
        if issued_at > now_seconds or now_seconds - issued_at > max_age_seconds:
            raise LifecycleTransportError("invalid lifecycle activation")
        expected = _sign_activation(body, issued_at, headers.nonce, secret)
        if not hmac.compare_digest(expected.signature, headers.signature):
            raise LifecycleTransportError("invalid lifecycle activation")
        payload = _load_exact_activation(body)
        generation = payload["generation"]
        eligible_count = payload["eligible_count"]
        manifest_digest = payload["manifest_digest"]
        if (
            not isinstance(generation, str)
            or type(eligible_count) is not int
            or not isinstance(manifest_digest, str)
        ):
            raise LifecycleTransportError("invalid lifecycle activation")
        request = LifecycleActivationRequest(
            generation,
            eligible_count,
            manifest_digest,
        )
        replay_store.consume(
            headers.nonce,
            now_seconds=now_seconds,
            expires_at=issued_at + max_age_seconds,
        )
        return request
    except LifecycleTransportError:
        raise
    except (KeyError, TypeError, ValueError, UnicodeDecodeError) as error:
        raise LifecycleTransportError("invalid lifecycle activation") from error


def _sign_activation(
    body: bytes, timestamp: int, nonce: str, secret: str
) -> LifecycleTransportHeaders:
    if (
        type(timestamp) is not int
        or not secret.strip()
        or not _NONCE_PATTERN.fullmatch(nonce)
        or not isinstance(body, bytes)
        or not 0 < len(body) <= MAX_LIFECYCLE_ACTIVATION_BYTES
    ):
        raise LifecycleTransportError("invalid lifecycle activation")
    timestamp_text = str(timestamp)
    body_digest = hashlib.sha256(body).hexdigest()
    canonical = "\n".join(
        (
            LIFECYCLE_ACTIVATION_SIGNATURE_PURPOSE,
            "POST",
            INTERNAL_LIFECYCLE_ACTIVATION_PATH,
            timestamp_text,
            nonce,
            body_digest,
        )
    ).encode("utf-8")
    digest = hmac.new(secret.encode("utf-8"), canonical, hashlib.sha256).hexdigest()
    return LifecycleTransportHeaders(f"sha256={digest}", timestamp_text, nonce)


def _load_exact_activation(body: bytes) -> dict[str, object]:
    def exact_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
        result: dict[str, object] = {}
        for key, value in pairs:
            if key in result:
                raise LifecycleTransportError("invalid lifecycle activation")
            result[key] = value
        return result

    payload = json.loads(body.decode("utf-8"), object_pairs_hook=exact_object)
    if not isinstance(payload, dict) or set(payload) != {
        "generation",
        "eligible_count",
        "manifest_digest",
    }:
        raise LifecycleTransportError("invalid lifecycle activation")
    return payload
