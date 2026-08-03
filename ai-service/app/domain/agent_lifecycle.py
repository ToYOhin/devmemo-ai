"""Pure contracts for the Memos-owned complete-Memo index lifecycle.

This module deliberately has no HTTP, persistence, provider, or vector-store
dependency. It defines the values a later A4 adapter must validate before it
can reserve or mutate rebuildable derived state.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Literal, Mapping, cast


MEMO_INDEX_VERSION: Literal["memo-v1"] = "memo-v1"
MAX_DOCUMENT_CHARS = 200_000

LifecycleEventType = Literal[
    "memo.index.requested.v1",
    "memo.reindex.requested.v1",
    "memo.delete.requested.v1",
]
LifecycleOperation = Literal["upsert", "delete"]
LifecycleAcknowledgementStatus = Literal["applied", "duplicate", "stale", "failed"]
LifecycleProcessingStatus = Literal["applying", "applied", "failed"]
LifecycleTransitionDecision = Literal["apply", "resume", "duplicate", "stale", "conflict"]

_EVENT_TYPES = frozenset(
    {
        "memo.index.requested.v1",
        "memo.reindex.requested.v1",
        "memo.delete.requested.v1",
    }
)
_EVENT_REASONS = {
    "memo.index.requested.v1": frozenset({"created"}),
    "memo.reindex.requested.v1": frozenset(
        {"content_changed", "indexed_metadata_changed", "restored", "repair"}
    ),
    "memo.delete.requested.v1": frozenset(
        {"deleted", "archived", "became_comment", "blank_content"}
    ),
}
_ACKNOWLEDGEMENT_STATUSES = frozenset({"applied", "duplicate", "stale", "failed"})
_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
_ERROR_CODE_PATTERN = re.compile(r"^[a-z0-9_]{1,64}$")


class LifecycleContractError(ValueError):
    """Raised when an A4 lifecycle value violates the reviewed contract."""


@dataclass(frozen=True)
class MemoLifecycleEvent:
    """One immutable, source-sequenced command to rebuild derived Memo state."""

    event_id: str
    event_type: LifecycleEventType
    memo_uid: str
    source_sequence: int
    operation: LifecycleOperation
    reason: str
    occurred_at: datetime
    document: str | None = None
    document_hash: str | None = None
    index_version: Literal["memo-v1"] = MEMO_INDEX_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "event_id", _bounded_identifier("event_id", self.event_id))
        object.__setattr__(self, "memo_uid", _bounded_identifier("memo_uid", self.memo_uid))
        if not isinstance(self.event_type, str) or self.event_type not in _EVENT_TYPES:
            raise LifecycleContractError("event_type is not supported")
        if type(self.source_sequence) is not int or self.source_sequence < 1:
            raise LifecycleContractError("source_sequence must be a positive integer")
        if self.index_version != MEMO_INDEX_VERSION:
            raise LifecycleContractError("index_version must be memo-v1")
        if not isinstance(self.occurred_at, datetime):
            raise LifecycleContractError("occurred_at must be a datetime")
        if self.occurred_at.tzinfo is None or self.occurred_at.utcoffset() is None:
            raise LifecycleContractError("occurred_at must include a UTC offset")

        expected_operation: LifecycleOperation = (
            "delete" if self.event_type == "memo.delete.requested.v1" else "upsert"
        )
        if self.operation != expected_operation:
            raise LifecycleContractError("operation does not match event_type")
        if not isinstance(self.reason, str) or self.reason not in _EVENT_REASONS[self.event_type]:
            raise LifecycleContractError("reason is not allowed for event_type")

        if self.operation == "delete":
            if self.document is not None or self.document_hash is not None:
                raise LifecycleContractError(
                    "delete events must be tombstones without document data"
                )
            return

        if not isinstance(self.document, str) or not self.document.strip():
            raise LifecycleContractError("index events require a non-blank document")
        if len(self.document) > MAX_DOCUMENT_CHARS:
            raise LifecycleContractError(
                f"document must contain at most {MAX_DOCUMENT_CHARS} characters"
            )
        if not isinstance(self.document_hash, str) or not _SHA256_PATTERN.fullmatch(
            self.document_hash
        ):
            raise LifecycleContractError("document_hash must be a lowercase SHA-256 digest")
        if self.document_hash != hash_lifecycle_document(self.document):
            raise LifecycleContractError("document_hash does not match document")

    @classmethod
    def from_dict(cls, payload: Mapping[str, object]) -> MemoLifecycleEvent:
        """Parse an exact-field event envelope and reject unknown data."""

        event_type = payload.get("event_type")
        if not isinstance(event_type, str) or event_type not in _EVENT_TYPES:
            raise LifecycleContractError("event_type is not supported")
        has_document = event_type != "memo.delete.requested.v1"
        expected_fields = {
            "event_id",
            "event_type",
            "memo_uid",
            "source_sequence",
            "index_version",
            "operation",
            "reason",
            "occurred_at",
        }
        if has_document:
            expected_fields.update({"document", "document_hash"})
        _require_exact_fields(payload, expected_fields, "lifecycle event")

        return cls(
            event_id=cast(str, payload["event_id"]),
            event_type=cast(LifecycleEventType, event_type),
            memo_uid=cast(str, payload["memo_uid"]),
            source_sequence=cast(int, payload["source_sequence"]),
            index_version=cast(Literal["memo-v1"], payload["index_version"]),
            operation=cast(LifecycleOperation, payload["operation"]),
            reason=cast(str, payload["reason"]),
            occurred_at=_parse_occurred_at(payload["occurred_at"]),
            document=cast(str | None, payload.get("document")),
            document_hash=cast(str | None, payload.get("document_hash")),
        )

    def to_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "event_id": self.event_id,
            "event_type": self.event_type,
            "memo_uid": self.memo_uid,
            "source_sequence": self.source_sequence,
            "index_version": self.index_version,
            "operation": self.operation,
            "reason": self.reason,
            "occurred_at": self.occurred_at.isoformat(),
        }
        if self.operation == "upsert":
            payload["document"] = self.document
            payload["document_hash"] = self.document_hash
        return payload


@dataclass(frozen=True)
class LifecycleAcknowledgement:
    """Strict content-free result returned to the Memos lifecycle owner."""

    event_id: str
    memo_uid: str
    source_sequence: int
    status: LifecycleAcknowledgementStatus
    operation: LifecycleOperation
    error_code: str | None = None
    index_version: Literal["memo-v1"] = MEMO_INDEX_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "event_id", _bounded_identifier("event_id", self.event_id))
        object.__setattr__(self, "memo_uid", _bounded_identifier("memo_uid", self.memo_uid))
        if type(self.source_sequence) is not int or self.source_sequence < 1:
            raise LifecycleContractError("source_sequence must be a positive integer")
        if self.index_version != MEMO_INDEX_VERSION:
            raise LifecycleContractError("index_version must be memo-v1")
        if not isinstance(self.status, str) or self.status not in _ACKNOWLEDGEMENT_STATUSES:
            raise LifecycleContractError("acknowledgement status is not supported")
        if not isinstance(self.operation, str) or self.operation not in {"upsert", "delete"}:
            raise LifecycleContractError("acknowledgement operation is not supported")
        if self.status == "failed":
            if not isinstance(self.error_code, str) or not _ERROR_CODE_PATTERN.fullmatch(
                self.error_code
            ):
                raise LifecycleContractError("failed acknowledgement requires a safe error_code")
        elif self.error_code is not None:
            raise LifecycleContractError("only failed acknowledgements may contain error_code")

    @classmethod
    def from_dict(cls, payload: Mapping[str, object]) -> LifecycleAcknowledgement:
        expected_fields = {
            "event_id",
            "memo_uid",
            "source_sequence",
            "index_version",
            "status",
            "operation",
        }
        if "error_code" in payload:
            expected_fields.add("error_code")
        _require_exact_fields(payload, expected_fields, "lifecycle acknowledgement")
        return cls(
            event_id=cast(str, payload["event_id"]),
            memo_uid=cast(str, payload["memo_uid"]),
            source_sequence=cast(int, payload["source_sequence"]),
            index_version=cast(Literal["memo-v1"], payload["index_version"]),
            status=cast(LifecycleAcknowledgementStatus, payload["status"]),
            operation=cast(LifecycleOperation, payload["operation"]),
            error_code=cast(str | None, payload.get("error_code")),
        )

    def to_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "event_id": self.event_id,
            "memo_uid": self.memo_uid,
            "source_sequence": self.source_sequence,
            "index_version": self.index_version,
            "status": self.status,
            "operation": self.operation,
        }
        if self.error_code is not None:
            payload["error_code"] = self.error_code
        return payload


@dataclass(frozen=True)
class MemoLifecycleState:
    """Minimal derived ledger state needed to make one Memo fail closed."""

    memo_uid: str
    highest_accepted_sequence: int
    accepted_event_id: str
    accepted_event_fingerprint: str
    accepted_operation: LifecycleOperation
    accepted_document_hash: str | None
    status: LifecycleProcessingStatus
    last_applied_sequence: int | None = None
    last_applied_event_id: str | None = None
    last_applied_operation: LifecycleOperation | None = None
    last_applied_document_hash: str | None = None
    tombstone_sequence: int | None = None
    index_version: Literal["memo-v1"] = MEMO_INDEX_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "memo_uid", _bounded_identifier("memo_uid", self.memo_uid))
        object.__setattr__(
            self,
            "accepted_event_id",
            _bounded_identifier("accepted_event_id", self.accepted_event_id),
        )
        if not isinstance(
            self.accepted_event_fingerprint, str
        ) or not _SHA256_PATTERN.fullmatch(self.accepted_event_fingerprint):
            raise LifecycleContractError("accepted_event_fingerprint must be SHA-256")
        if type(self.highest_accepted_sequence) is not int or self.highest_accepted_sequence < 1:
            raise LifecycleContractError("highest_accepted_sequence must be positive")
        if self.index_version != MEMO_INDEX_VERSION:
            raise LifecycleContractError("index_version must be memo-v1")
        if self.accepted_operation not in {"upsert", "delete"}:
            raise LifecycleContractError("accepted_operation is not supported")
        _validate_operation_hash(self.accepted_operation, self.accepted_document_hash, "accepted")
        if self.status not in {"applying", "applied", "failed"}:
            raise LifecycleContractError("lifecycle state status is not supported")

        applied_values = (
            self.last_applied_sequence,
            self.last_applied_event_id,
            self.last_applied_operation,
        )
        if any(value is None for value in applied_values) and any(
            value is not None for value in applied_values
        ):
            raise LifecycleContractError("last-applied identity must be complete or absent")
        if self.last_applied_sequence is not None:
            if (
                type(self.last_applied_sequence) is not int
                or self.last_applied_sequence < 1
                or self.last_applied_sequence > self.highest_accepted_sequence
            ):
                raise LifecycleContractError("last_applied_sequence is invalid")
            _bounded_identifier("last_applied_event_id", self.last_applied_event_id)
            _validate_operation_hash(
                self.last_applied_operation,
                self.last_applied_document_hash,
                "last-applied",
            )
        elif self.last_applied_document_hash is not None:
            raise LifecycleContractError("last-applied hash requires last-applied identity")

        if self.status == "applied" and (
            self.last_applied_sequence != self.highest_accepted_sequence
            or self.last_applied_event_id != self.accepted_event_id
            or self.last_applied_operation != self.accepted_operation
            or self.last_applied_document_hash != self.accepted_document_hash
        ):
            raise LifecycleContractError("applied state must finalize the accepted event")
        if self.tombstone_sequence is not None:
            if (
                type(self.tombstone_sequence) is not int
                or self.tombstone_sequence < 1
                or self.tombstone_sequence > self.highest_accepted_sequence
            ):
                raise LifecycleContractError("tombstone_sequence is invalid")
        if self.accepted_operation == "delete" and (
            self.tombstone_sequence != self.highest_accepted_sequence
        ):
            raise LifecycleContractError("accepted delete must reserve a tombstone")


@dataclass(frozen=True)
class LifecycleTransition:
    """Pure decision returned before any persistence or vector mutation."""

    decision: LifecycleTransitionDecision
    state: MemoLifecycleState
    acknowledgement: LifecycleAcknowledgement | None = None


def accept_lifecycle_event(
    state: MemoLifecycleState | None, event: MemoLifecycleEvent
) -> LifecycleTransition:
    """Sequence and reserve an event without performing its requested operation."""

    if state is None:
        return LifecycleTransition("apply", _reserve_event(None, event))
    _require_same_target(state, event)

    if event.source_sequence < state.highest_accepted_sequence:
        return LifecycleTransition("stale", state, _acknowledge(event, "stale"))
    if event.source_sequence == state.highest_accepted_sequence:
        if not _matches_accepted_event(state, event):
            return LifecycleTransition(
                "conflict",
                state,
                _acknowledge(event, "failed", "same_sequence_conflict"),
            )
        if state.status == "applied":
            return LifecycleTransition("duplicate", state, _acknowledge(event, "duplicate"))
        return LifecycleTransition("resume", _reserve_event(state, event))

    return LifecycleTransition("apply", _reserve_event(state, event))


def complete_lifecycle_event(
    state: MemoLifecycleState, event: MemoLifecycleEvent
) -> tuple[MemoLifecycleState, LifecycleAcknowledgement]:
    """Finalize the currently reserved event as applied."""

    _require_current_applying_event(state, event)
    completed = MemoLifecycleState(
        memo_uid=state.memo_uid,
        highest_accepted_sequence=state.highest_accepted_sequence,
        accepted_event_id=state.accepted_event_id,
        accepted_event_fingerprint=state.accepted_event_fingerprint,
        accepted_operation=state.accepted_operation,
        accepted_document_hash=state.accepted_document_hash,
        status="applied",
        last_applied_sequence=event.source_sequence,
        last_applied_event_id=event.event_id,
        last_applied_operation=event.operation,
        last_applied_document_hash=event.document_hash,
        tombstone_sequence=state.tombstone_sequence,
    )
    return completed, _acknowledge(event, "applied")


def fail_lifecycle_event(
    state: MemoLifecycleState, event: MemoLifecycleEvent, error_code: str
) -> tuple[MemoLifecycleState, LifecycleAcknowledgement]:
    """Keep an accepted event retryable while preserving retrieval quarantine."""

    _require_current_applying_event(state, event)
    acknowledgement = _acknowledge(event, "failed", error_code)
    failed = MemoLifecycleState(
        memo_uid=state.memo_uid,
        highest_accepted_sequence=state.highest_accepted_sequence,
        accepted_event_id=state.accepted_event_id,
        accepted_event_fingerprint=state.accepted_event_fingerprint,
        accepted_operation=state.accepted_operation,
        accepted_document_hash=state.accepted_document_hash,
        status="failed",
        last_applied_sequence=state.last_applied_sequence,
        last_applied_event_id=state.last_applied_event_id,
        last_applied_operation=state.last_applied_operation,
        last_applied_document_hash=state.last_applied_document_hash,
        tombstone_sequence=state.tombstone_sequence,
    )
    return failed, acknowledgement


def is_retrieval_eligible(
    state: MemoLifecycleState | None,
    *,
    vector_source_sequence: int,
    vector_document_hash: str,
) -> bool:
    """Allow only the vector matching the latest successfully applied upsert."""

    if state is None or state.status != "applied":
        return False
    if state.last_applied_operation != "upsert":
        return False
    if type(vector_source_sequence) is not int or vector_source_sequence < 1:
        return False
    if not isinstance(vector_document_hash, str):
        return False
    if state.last_applied_sequence != state.highest_accepted_sequence:
        return False
    if vector_source_sequence != state.last_applied_sequence:
        return False
    if vector_document_hash != state.last_applied_document_hash:
        return False
    return state.tombstone_sequence is None or state.tombstone_sequence < vector_source_sequence


def _reserve_event(
    previous: MemoLifecycleState | None, event: MemoLifecycleEvent
) -> MemoLifecycleState:
    last_applied = previous if previous is not None else None
    tombstone_sequence = previous.tombstone_sequence if previous is not None else None
    if event.operation == "delete":
        tombstone_sequence = event.source_sequence
    return MemoLifecycleState(
        memo_uid=event.memo_uid,
        highest_accepted_sequence=event.source_sequence,
        accepted_event_id=event.event_id,
        accepted_event_fingerprint=_event_fingerprint(event),
        accepted_operation=event.operation,
        accepted_document_hash=event.document_hash,
        status="applying",
        last_applied_sequence=(
            last_applied.last_applied_sequence if last_applied is not None else None
        ),
        last_applied_event_id=(
            last_applied.last_applied_event_id if last_applied is not None else None
        ),
        last_applied_operation=(
            last_applied.last_applied_operation if last_applied is not None else None
        ),
        last_applied_document_hash=(
            last_applied.last_applied_document_hash if last_applied is not None else None
        ),
        tombstone_sequence=tombstone_sequence,
    )


def _matches_accepted_event(state: MemoLifecycleState, event: MemoLifecycleEvent) -> bool:
    return _event_fingerprint(event) == state.accepted_event_fingerprint


def _require_same_target(state: MemoLifecycleState, event: MemoLifecycleEvent) -> None:
    if state.memo_uid != event.memo_uid or state.index_version != event.index_version:
        raise LifecycleContractError("event does not target this lifecycle state")


def _require_current_applying_event(
    state: MemoLifecycleState, event: MemoLifecycleEvent
) -> None:
    _require_same_target(state, event)
    if state.status != "applying" or event.source_sequence != state.highest_accepted_sequence:
        raise LifecycleContractError("event is not the current applying event")
    if not _matches_accepted_event(state, event):
        raise LifecycleContractError("event does not match the accepted event")


def _acknowledge(
    event: MemoLifecycleEvent,
    status: LifecycleAcknowledgementStatus,
    error_code: str | None = None,
) -> LifecycleAcknowledgement:
    return LifecycleAcknowledgement(
        event_id=event.event_id,
        memo_uid=event.memo_uid,
        source_sequence=event.source_sequence,
        status=status,
        operation=event.operation,
        error_code=error_code,
    )


def _validate_operation_hash(
    operation: LifecycleOperation | None, document_hash: str | None, field_prefix: str
) -> None:
    if operation == "upsert":
        if not isinstance(document_hash, str) or not _SHA256_PATTERN.fullmatch(document_hash):
            raise LifecycleContractError(f"{field_prefix} upsert requires document hash")
    elif operation == "delete":
        if document_hash is not None:
            raise LifecycleContractError(f"{field_prefix} delete must not contain document hash")
    else:
        raise LifecycleContractError(f"{field_prefix} operation is not supported")


def _event_fingerprint(event: MemoLifecycleEvent) -> str:
    """Hash immutable envelope metadata without retaining the raw document."""

    safe_envelope = {
        "event_id": event.event_id,
        "event_type": event.event_type,
        "memo_uid": event.memo_uid,
        "source_sequence": event.source_sequence,
        "index_version": event.index_version,
        "operation": event.operation,
        "reason": event.reason,
        "occurred_at": event.occurred_at.isoformat(),
        "document_hash": event.document_hash,
    }
    encoded = json.dumps(
        safe_envelope, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def hash_lifecycle_document(document: str) -> str:
    """Return the contract hash of the exact normalized document text."""

    return hashlib.sha256(document.encode("utf-8")).hexdigest()


def _bounded_identifier(field_name: str, value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise LifecycleContractError(f"{field_name} must not be empty")
    normalized = value.strip()
    if len(normalized) > 128:
        raise LifecycleContractError(f"{field_name} must contain at most 128 characters")
    return normalized


def _parse_occurred_at(value: object) -> datetime:
    if not isinstance(value, str):
        raise LifecycleContractError("occurred_at must be an ISO-8601 string")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise LifecycleContractError("occurred_at must be an ISO-8601 string") from error
    return parsed


def _require_exact_fields(
    payload: Mapping[str, object], expected_fields: set[str], contract_name: str
) -> None:
    actual_fields = set(payload)
    if actual_fields != expected_fields:
        missing = sorted(expected_fields - actual_fields)
        unknown = sorted(str(field) for field in actual_fields - expected_fields)
        details = []
        if missing:
            details.append(f"missing={','.join(missing)}")
        if unknown:
            details.append(f"unknown={','.join(unknown)}")
        raise LifecycleContractError(f"{contract_name} fields are invalid ({'; '.join(details)})")
