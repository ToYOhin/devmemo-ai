"""Provider-neutral, content-free contracts for bounded R7 Agent runs.

The module contains no clock, persistence, provider, HTTP, or execution code.
It only validates values that a later, separately authorized runtime may store
or project.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
import re
from typing import Literal, Mapping


AGENT_RUN_CONTRACT_VERSION: Literal["agent-run-contract-v1"] = "agent-run-contract-v1"
ALLOWED_TOOLS = frozenset(
    {"search_memos", "get_memo_evidence", "create_report_artifact"}
)
MAX_STEPS = 12
MAX_TOOL_CALLS = 8
MAX_TOOL_RETRIES = 1
MAX_ACTIVE_SECONDS = 120
MAX_TOOL_ATTEMPT_SECONDS = 30
MAX_ARTIFACTS = 3
MAX_ARTIFACT_BYTES = 1_048_576

_OPAQUE_PATTERN = re.compile(r"^[a-z][a-z0-9]*(?:[-_][a-z0-9]+)+$")
_CODE_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")
_DIGEST_PATTERN = re.compile(r"^[0-9a-f]{64}$")


class AgentRunContractError(ValueError):
    """Raised when a value falls outside the R7 AgentRun contract."""


class RunStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    WAITING_APPROVAL = "waiting_approval"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class StepKind(str, Enum):
    PLAN = "plan"
    TOOL = "tool"
    APPROVAL = "approval"
    FINALIZE = "finalize"


class StepStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ApprovalStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"
    SUPERSEDED = "superseded"


class ArtifactStatus(str, Enum):
    AVAILABLE = "available"
    REVOKED = "revoked"
    EXPIRED = "expired"


LEGAL_RUN_TRANSITIONS = frozenset(
    {
        (RunStatus.QUEUED, RunStatus.RUNNING),
        (RunStatus.QUEUED, RunStatus.CANCELLED),
        (RunStatus.RUNNING, RunStatus.WAITING_APPROVAL),
        (RunStatus.RUNNING, RunStatus.SUCCEEDED),
        (RunStatus.RUNNING, RunStatus.FAILED),
        (RunStatus.RUNNING, RunStatus.CANCELLED),
        (RunStatus.WAITING_APPROVAL, RunStatus.RUNNING),
        (RunStatus.WAITING_APPROVAL, RunStatus.FAILED),
        (RunStatus.WAITING_APPROVAL, RunStatus.CANCELLED),
    }
)

SAFE_EVENT_DETAIL_FIELDS = frozenset(
    {
        "approval_id",
        "artifact_id",
        "attempt",
        "count",
        "duration_ms",
        "evidence_ref",
        "outcome_code",
        "reason_code",
        "revision",
        "status",
        "tool_name",
    }
)


def _require_opaque(name: str, value: str) -> str:
    normalized = value.strip()
    if not _OPAQUE_PATTERN.fullmatch(normalized):
        raise AgentRunContractError(f"{name} must be an opaque identifier")
    return normalized


def _require_code(name: str, value: str) -> str:
    normalized = value.strip()
    if not _CODE_PATTERN.fullmatch(normalized):
        raise AgentRunContractError(f"{name} must be a fixed safe code")
    return normalized


def _require_digest(name: str, value: str) -> str:
    normalized = value.strip()
    if not _DIGEST_PATTERN.fullmatch(normalized):
        raise AgentRunContractError(f"{name} must be a lowercase sha256 digest")
    return normalized


def _require_utc(name: str, value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() != timezone.utc.utcoffset(value):
        raise AgentRunContractError(f"{name} must be a UTC timestamp")
    return value


def _timestamp(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


def validate_run_transition(current: RunStatus, target: RunStatus) -> None:
    """Reject any transition not explicitly defined by the R7 state machine."""

    if (current, target) not in LEGAL_RUN_TRANSITIONS:
        raise AgentRunContractError(
            f"run transition {current.value}->{target.value} is not permitted"
        )


@dataclass(frozen=True)
class ExecutionBudget:
    """Immutable, finite ceilings accepted with one run."""

    max_steps: int
    max_tool_calls: int
    max_tool_retries: int
    max_active_seconds: int
    max_tool_attempt_seconds: int
    max_artifacts: int
    max_artifact_bytes: int

    def __post_init__(self) -> None:
        ceilings = {
            "max_steps": (self.max_steps, MAX_STEPS),
            "max_tool_calls": (self.max_tool_calls, MAX_TOOL_CALLS),
            "max_tool_retries": (self.max_tool_retries, MAX_TOOL_RETRIES),
            "max_active_seconds": (self.max_active_seconds, MAX_ACTIVE_SECONDS),
            "max_tool_attempt_seconds": (
                self.max_tool_attempt_seconds,
                MAX_TOOL_ATTEMPT_SECONDS,
            ),
            "max_artifacts": (self.max_artifacts, MAX_ARTIFACTS),
            "max_artifact_bytes": (self.max_artifact_bytes, MAX_ARTIFACT_BYTES),
        }
        for name, (value, maximum) in ceilings.items():
            if isinstance(value, bool) or not isinstance(value, int):
                raise AgentRunContractError(f"{name} must be a finite integer")
            minimum = 1
            if not minimum <= value <= maximum:
                raise AgentRunContractError(
                    f"{name} must be between {minimum} and {maximum}"
                )

    def to_dict(self) -> dict[str, int]:
        return {
            "max_steps": self.max_steps,
            "max_tool_calls": self.max_tool_calls,
            "max_tool_retries": self.max_tool_retries,
            "max_active_seconds": self.max_active_seconds,
            "max_tool_attempt_seconds": self.max_tool_attempt_seconds,
            "max_artifacts": self.max_artifacts,
            "max_artifact_bytes": self.max_artifact_bytes,
        }


@dataclass(frozen=True)
class SourceRevision:
    """Content-free binding to one Memos-owned source revision."""

    source_id: str
    revision: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "source_id", _require_opaque("source_id", self.source_id))
        object.__setattr__(self, "revision", _require_opaque("revision", self.revision))

    def to_dict(self) -> dict[str, str]:
        return {"source_id": self.source_id, "revision": self.revision}


@dataclass(frozen=True)
class AgentRun:
    run_id: str
    subject_id: str
    scope_ref: str
    request_key: str
    request_digest: str
    status: RunStatus
    budget: ExecutionBudget
    source_snapshot: tuple[SourceRevision, ...]
    created_at: datetime
    updated_at: datetime
    last_event_seq: int
    checkpoint_ref: str | None = None
    terminal_reason: str | None = None
    contract_version: Literal["agent-run-contract-v1"] = AGENT_RUN_CONTRACT_VERSION

    def __post_init__(self) -> None:
        for name in ("run_id", "subject_id", "scope_ref", "request_key"):
            object.__setattr__(self, name, _require_opaque(name, getattr(self, name)))
        object.__setattr__(self, "request_digest", _require_digest("request_digest", self.request_digest))
        if not isinstance(self.status, RunStatus):
            raise AgentRunContractError("status must use RunStatus")
        if not isinstance(self.budget, ExecutionBudget):
            raise AgentRunContractError("budget must use ExecutionBudget")
        if not self.source_snapshot or any(
            not isinstance(item, SourceRevision) for item in self.source_snapshot
        ):
            raise AgentRunContractError("source_snapshot must contain source revisions")
        if len({item.source_id for item in self.source_snapshot}) != len(self.source_snapshot):
            raise AgentRunContractError("source_snapshot must not repeat a source")
        _require_utc("created_at", self.created_at)
        _require_utc("updated_at", self.updated_at)
        if self.updated_at < self.created_at:
            raise AgentRunContractError("updated_at must not precede created_at")
        if self.last_event_seq < 0:
            raise AgentRunContractError("last_event_seq must not be negative")
        if self.checkpoint_ref is not None:
            object.__setattr__(
                self, "checkpoint_ref", _require_opaque("checkpoint_ref", self.checkpoint_ref)
            )
        terminal = self.status in {
            RunStatus.SUCCEEDED,
            RunStatus.FAILED,
            RunStatus.CANCELLED,
        }
        if terminal != (self.terminal_reason is not None):
            raise AgentRunContractError("terminal_reason must exist only for terminal runs")
        if self.terminal_reason is not None:
            object.__setattr__(
                self,
                "terminal_reason",
                _require_code("terminal_reason", self.terminal_reason),
            )
        if self.contract_version != AGENT_RUN_CONTRACT_VERSION:
            raise AgentRunContractError("contract_version is not supported")

    def validate_resume(self, checkpoint_ref: str, snapshot: tuple[SourceRevision, ...]) -> None:
        if self.checkpoint_ref is None or _require_opaque("checkpoint_ref", checkpoint_ref) != self.checkpoint_ref:
            raise AgentRunContractError("resume checkpoint does not match the committed checkpoint")
        if snapshot != self.source_snapshot:
            raise AgentRunContractError("resume source snapshot is stale")
        if self.status not in {RunStatus.RUNNING, RunStatus.WAITING_APPROVAL}:
            raise AgentRunContractError("only active or paused runs may resume")

    def validate_duplicate_request(
        self, *, subject_id: str, request_key: str, request_digest: str
    ) -> None:
        """Accept only an exactly matching idempotent run-creation replay."""

        if (
            _require_opaque("subject_id", subject_id) != self.subject_id
            or _require_opaque("request_key", request_key) != self.request_key
            or _require_digest("request_digest", request_digest) != self.request_digest
        ):
            raise AgentRunContractError("duplicate request binding conflicts with existing run")


@dataclass(frozen=True)
class AgentStep:
    step_id: str
    run_id: str
    ordinal: int
    kind: StepKind
    status: StepStatus
    attempt: int
    input_digest: str
    checkpoint_ref: str | None = None
    tool_name: str | None = None
    outcome_code: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "step_id", _require_opaque("step_id", self.step_id))
        object.__setattr__(self, "run_id", _require_opaque("run_id", self.run_id))
        if not 1 <= self.ordinal <= MAX_STEPS:
            raise AgentRunContractError(f"ordinal must be between 1 and {MAX_STEPS}")
        if not isinstance(self.kind, StepKind) or not isinstance(self.status, StepStatus):
            raise AgentRunContractError("step kind and status must use contract enums")
        if not 0 <= self.attempt <= MAX_TOOL_RETRIES:
            raise AgentRunContractError(
                f"attempt must be between 0 and {MAX_TOOL_RETRIES}"
            )
        object.__setattr__(self, "input_digest", _require_digest("input_digest", self.input_digest))
        if self.kind is StepKind.TOOL:
            if self.tool_name not in ALLOWED_TOOLS:
                raise AgentRunContractError("tool_name is not in the R7 allowlist")
        elif self.tool_name is not None:
            raise AgentRunContractError("only tool steps may have a tool_name")
        if self.kind is not StepKind.TOOL and self.attempt != 0:
            raise AgentRunContractError("only tool steps may be retried")
        if self.checkpoint_ref is not None:
            object.__setattr__(
                self, "checkpoint_ref", _require_opaque("checkpoint_ref", self.checkpoint_ref)
            )
        if self.outcome_code is not None:
            object.__setattr__(
                self, "outcome_code", _require_code("outcome_code", self.outcome_code)
            )


SafeDetailValue = str | int


@dataclass(frozen=True)
class RunEvent:
    event_id: str
    run_id: str
    seq: int
    event_type: str
    safe_details: Mapping[str, SafeDetailValue]
    occurred_at: datetime
    step_id: str | None = None
    prev_digest: str | None = None
    event_digest: str | None = None
    schema_version: Literal["agent-run-contract-v1"] = AGENT_RUN_CONTRACT_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "event_id", _require_opaque("event_id", self.event_id))
        object.__setattr__(self, "run_id", _require_opaque("run_id", self.run_id))
        if self.seq < 1:
            raise AgentRunContractError("event seq must be positive")
        object.__setattr__(self, "event_type", _require_code("event_type", self.event_type))
        unknown = set(self.safe_details) - SAFE_EVENT_DETAIL_FIELDS
        if unknown:
            raise AgentRunContractError(f"safe_details contains non-allowlisted fields: {sorted(unknown)}")
        normalized: dict[str, SafeDetailValue] = {}
        for key, value in self.safe_details.items():
            if isinstance(value, bool) or not isinstance(value, (str, int)):
                raise AgentRunContractError("safe_details values must be strings or integers")
            if isinstance(value, int) and value < 0:
                raise AgentRunContractError("safe_details integers must not be negative")
            if isinstance(value, str):
                if key == "tool_name":
                    if value not in ALLOWED_TOOLS:
                        raise AgentRunContractError("event tool_name is not allowed")
                elif key in {"reason_code", "outcome_code", "status"}:
                    _require_code(key, value)
                else:
                    _require_opaque(key, value)
            normalized[key] = value
        object.__setattr__(self, "safe_details", normalized)
        _require_utc("occurred_at", self.occurred_at)
        if self.step_id is not None:
            object.__setattr__(self, "step_id", _require_opaque("step_id", self.step_id))
        for name in ("prev_digest", "event_digest"):
            value = getattr(self, name)
            if value is not None:
                object.__setattr__(self, name, _require_digest(name, value))
        if (self.prev_digest is None) != (self.event_digest is None):
            raise AgentRunContractError("event digests must be supplied together")
        if self.schema_version != AGENT_RUN_CONTRACT_VERSION:
            raise AgentRunContractError("schema_version is not supported")

    def to_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "event_id": self.event_id,
            "run_id": self.run_id,
            "seq": self.seq,
            "event_type": self.event_type,
            "schema_version": self.schema_version,
            "safe_details": dict(self.safe_details),
            "occurred_at": _timestamp(self.occurred_at),
        }
        for name in ("step_id", "prev_digest", "event_digest"):
            value = getattr(self, name)
            if value is not None:
                payload[name] = value
        return payload


@dataclass(frozen=True)
class ApprovalRequest:
    approval_id: str
    run_id: str
    step_id: str
    subject_id: str
    action_type: str
    action_digest: str
    source_snapshot: tuple[SourceRevision, ...]
    requested_at: datetime
    expires_at: datetime
    status: ApprovalStatus
    decision_id: str | None = None
    decided_by: str | None = None
    decided_at: datetime | None = None

    def __post_init__(self) -> None:
        for name in ("approval_id", "run_id", "step_id", "subject_id"):
            object.__setattr__(self, name, _require_opaque(name, getattr(self, name)))
        object.__setattr__(self, "action_type", _require_code("action_type", self.action_type))
        object.__setattr__(self, "action_digest", _require_digest("action_digest", self.action_digest))
        if not self.source_snapshot or any(
            not isinstance(item, SourceRevision) for item in self.source_snapshot
        ):
            raise AgentRunContractError("approval must bind a source snapshot")
        _require_utc("requested_at", self.requested_at)
        _require_utc("expires_at", self.expires_at)
        if self.expires_at <= self.requested_at:
            raise AgentRunContractError("approval expiry must be after request time")
        if not isinstance(self.status, ApprovalStatus):
            raise AgentRunContractError("status must use ApprovalStatus")
        decision_fields = (self.decision_id, self.decided_by, self.decided_at)
        if self.status is ApprovalStatus.PENDING:
            if any(value is not None for value in decision_fields):
                raise AgentRunContractError("pending approval must not contain a decision")
        elif any(value is None for value in decision_fields):
            raise AgentRunContractError("decided approval requires complete audit fields")
        if self.decision_id is not None:
            object.__setattr__(self, "decision_id", _require_opaque("decision_id", self.decision_id))
        if self.decided_by is not None:
            object.__setattr__(self, "decided_by", _require_opaque("decided_by", self.decided_by))
        if self.decided_at is not None:
            _require_utc("decided_at", self.decided_at)

    def validate_decision(
        self,
        *,
        decision_id: str,
        subject_id: str,
        action_digest: str,
        source_snapshot: tuple[SourceRevision, ...],
        decided_at: datetime,
        visibility_current: bool,
    ) -> None:
        """Fail closed unless one pending decision is current and fully bound."""

        if self.status is not ApprovalStatus.PENDING:
            raise AgentRunContractError("duplicate or already-consumed approval decision")
        _require_opaque("decision_id", decision_id)
        _require_utc("decided_at", decided_at)
        if decided_at < self.requested_at:
            raise AgentRunContractError("approval decision precedes the request")
        if decided_at >= self.expires_at:
            raise AgentRunContractError("approval has expired")
        if _require_opaque("subject_id", subject_id) != self.subject_id:
            raise AgentRunContractError("approval subject binding does not match")
        if _require_digest("action_digest", action_digest) != self.action_digest:
            raise AgentRunContractError("approval action binding does not match")
        if source_snapshot != self.source_snapshot:
            raise AgentRunContractError("approval source snapshot is stale")
        if not isinstance(visibility_current, bool) or not visibility_current:
            raise AgentRunContractError("approval visibility is no longer current")


@dataclass(frozen=True)
class Artifact:
    artifact_id: str
    run_id: str
    step_id: str
    kind: Literal["report"]
    media_type: Literal["application/json"]
    storage_ref: str
    digest: str
    size_bytes: int
    evidence_refs: tuple[SourceRevision, ...]
    created_at: datetime
    expires_at: datetime
    status: ArtifactStatus
    schema_version: Literal["agent-run-contract-v1"] = AGENT_RUN_CONTRACT_VERSION

    def __post_init__(self) -> None:
        for name in ("artifact_id", "run_id", "step_id", "storage_ref"):
            object.__setattr__(self, name, _require_opaque(name, getattr(self, name)))
        object.__setattr__(self, "digest", _require_digest("digest", self.digest))
        if self.kind != "report" or self.media_type != "application/json":
            raise AgentRunContractError("artifact format is not allowlisted")
        if not 1 <= self.size_bytes <= MAX_ARTIFACT_BYTES:
            raise AgentRunContractError(
                f"size_bytes must be between 1 and {MAX_ARTIFACT_BYTES}"
            )
        if not self.evidence_refs or any(
            not isinstance(item, SourceRevision) for item in self.evidence_refs
        ):
            raise AgentRunContractError("artifact must bind evidence revisions")
        _require_utc("created_at", self.created_at)
        _require_utc("expires_at", self.expires_at)
        if self.expires_at <= self.created_at:
            raise AgentRunContractError("artifact expiry must be after creation")
        if not isinstance(self.status, ArtifactStatus):
            raise AgentRunContractError("status must use ArtifactStatus")
        if self.schema_version != AGENT_RUN_CONTRACT_VERSION:
            raise AgentRunContractError("schema_version is not supported")
