"""Verification for the private Memos-to-AI Agent delegation boundary."""

from __future__ import annotations

import hashlib
import hmac
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone


INTERNAL_ANSWER_PATH = "/internal/ai/agent/answer"
SIGNATURE_HEADER = "X-DevMemo-Agent-Signature"
TIMESTAMP_HEADER = "X-DevMemo-Agent-Timestamp"
SIGNATURE_PREFIX = "sha256="
SIGNATURE_VERSION = "devmemo-agent-v1"
_MEMOS_AUTHORITY_REF_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{31,63}$")


class AgentDelegationError(ValueError):
    """Raised without exposing request details when internal delegation is invalid."""


@dataclass(frozen=True)
class DelegatedAnswerRequest:
    """Memos-authorized Agent input with no user identity or raw Memo content."""

    question: str
    limit: int
    visible_memo_uids: tuple[str, ...]
    memos_authority_ref: str | None = None

    def __post_init__(self) -> None:
        normalized_question = self.question.strip()
        if not normalized_question:
            raise AgentDelegationError("invalid Agent delegation")
        if type(self.limit) is not int or not 1 <= self.limit <= 10:
            raise AgentDelegationError("invalid Agent delegation")

        normalized_uids = tuple(uid.strip() for uid in self.visible_memo_uids)
        if any(not uid for uid in normalized_uids) or len(set(normalized_uids)) != len(normalized_uids):
            raise AgentDelegationError("invalid Agent delegation")
        object.__setattr__(self, "question", normalized_question)
        object.__setattr__(self, "visible_memo_uids", normalized_uids)
        if (
            self.memos_authority_ref is not None
            and not _MEMOS_AUTHORITY_REF_PATTERN.fullmatch(self.memos_authority_ref)
        ):
            raise AgentDelegationError("invalid Agent delegation")


@dataclass(frozen=True)
class AgentDelegationHeaders:
    signature: str
    timestamp: str


def sign_delegated_request(
    method: str,
    path: str,
    body: bytes,
    timestamp: int,
    secret: str,
) -> AgentDelegationHeaders:
    """Return headers compatible with Memos internal/aiagent.SignRequest."""

    if not secret.strip() or not method.strip() or not path.strip():
        raise AgentDelegationError("invalid Agent delegation")
    timestamp_text = str(timestamp)
    digest = hmac.new(
        secret.encode("utf-8"),
        _canonical_request(method, path, timestamp_text, body),
        hashlib.sha256,
    ).hexdigest()
    return AgentDelegationHeaders(
        signature=f"{SIGNATURE_PREFIX}{digest}",
        timestamp=timestamp_text,
    )


def verify_delegated_request(
    method: str,
    path: str,
    body: bytes,
    headers: AgentDelegationHeaders,
    secret: str,
    now: datetime,
    max_age_seconds: int = 60,
) -> DelegatedAnswerRequest:
    """Verify Memos delegation before parsing its caller-authorized UID scope."""

    verify_agent_internal_request(
        method,
        path,
        body,
        headers,
        secret,
        now,
        max_age_seconds,
    )
    return _parse_request(body)


def verify_agent_internal_request(
    method: str,
    path: str,
    body: bytes,
    headers: AgentDelegationHeaders,
    secret: str,
    now: datetime,
    max_age_seconds: int = 60,
) -> None:
    """Verify one signed internal request without assuming its JSON schema."""

    if not secret.strip() or max_age_seconds <= 0 or not headers.signature.startswith(SIGNATURE_PREFIX):
        raise AgentDelegationError("invalid Agent delegation")
    try:
        issued_at = int(headers.timestamp)
    except (TypeError, ValueError) as error:
        raise AgentDelegationError("invalid Agent delegation") from error

    now_seconds = int(now.astimezone(timezone.utc).timestamp())
    if issued_at > now_seconds + max_age_seconds or now_seconds - issued_at > max_age_seconds:
        raise AgentDelegationError("invalid Agent delegation")

    expected = sign_delegated_request(method, path, body, issued_at, secret)
    if not hmac.compare_digest(expected.signature, headers.signature):
        raise AgentDelegationError("invalid Agent delegation")


def _canonical_request(method: str, path: str, timestamp: str, body: bytes) -> bytes:
    prefix = b"\n".join(
        (
            SIGNATURE_VERSION.encode("ascii"),
            method.strip().upper().encode("ascii"),
            path.encode("utf-8"),
            timestamp.encode("ascii"),
            b"",
        )
    )
    return prefix + body


def _parse_request(body: bytes) -> DelegatedAnswerRequest:
    try:
        payload = json.loads(body)
    except (TypeError, ValueError, UnicodeDecodeError) as error:
        raise AgentDelegationError("invalid Agent delegation") from error
    required_fields = {"question", "limit", "visible_memo_uids"}
    if not isinstance(payload, dict) or frozenset(payload) not in {
        frozenset(required_fields),
        frozenset(required_fields | {"memos_authority_ref"}),
    }:
        raise AgentDelegationError("invalid Agent delegation")
    visible_memo_uids = payload["visible_memo_uids"]
    if not isinstance(visible_memo_uids, list) or any(not isinstance(uid, str) for uid in visible_memo_uids):
        raise AgentDelegationError("invalid Agent delegation")
    if not isinstance(payload["question"], str):
        raise AgentDelegationError("invalid Agent delegation")
    memos_authority_ref = payload.get("memos_authority_ref")
    if memos_authority_ref is not None and not isinstance(memos_authority_ref, str):
        raise AgentDelegationError("invalid Agent delegation")
    return DelegatedAnswerRequest(
        question=payload["question"],
        limit=payload["limit"],
        visible_memo_uids=tuple(visible_memo_uids),
        memos_authority_ref=memos_authority_ref,
    )
