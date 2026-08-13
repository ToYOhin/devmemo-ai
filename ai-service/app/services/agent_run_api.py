"""Private create/status boundary for queued R7 AgentRun records."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Callable
from uuid import uuid4

from app.adapters.agent_run_store import SQLiteAgentRunStore
from app.domain.agent_run import (
    MAX_ACTIVE_SECONDS,
    MAX_ARTIFACT_BYTES,
    MAX_ARTIFACTS,
    MAX_STEPS,
    MAX_TOOL_ATTEMPT_SECONDS,
    MAX_TOOL_CALLS,
    MAX_TOOL_RETRIES,
    AgentRun,
    ExecutionBudget,
    RunStatus,
    SourceRevision,
)


INTERNAL_AGENT_RUN_CREATE_PATH = "/internal/ai/agent/runs"
INTERNAL_AGENT_RUN_STATUS_PATH = "/internal/ai/agent/runs/status"
MAX_AGENT_RUN_REQUEST_BYTES = 16 << 10
MAX_AGENT_RUN_SOURCES = 10


class AgentRunAPIError(ValueError):
    """Raised when an internal AgentRun request is malformed or unauthorized."""


@dataclass(frozen=True)
class AgentRunCreateRequest:
    subject_id: str
    scope_ref: str
    request_key: str
    request_digest: str
    source_snapshot: tuple[SourceRevision, ...]


@dataclass(frozen=True)
class AgentRunStatusRequest:
    subject_id: str
    run_id: str


class AgentRunAPI:
    """Create and read content-free queued runs in the derived SQLite store."""

    def __init__(
        self,
        database: str | Path,
        *,
        utc_now: Callable[[], datetime] | None = None,
        run_id_factory: Callable[[], str] | None = None,
    ) -> None:
        self._store = SQLiteAgentRunStore(database)
        self._utc_now = utc_now or (lambda: datetime.now(timezone.utc))
        self._run_id_factory = run_id_factory or (lambda: f"run-{uuid4().hex}")

    def create(self, request: AgentRunCreateRequest) -> dict[str, object]:
        now = self._utc_now()
        run = AgentRun(
            run_id=self._run_id_factory(),
            subject_id=request.subject_id,
            scope_ref=request.scope_ref,
            request_key=request.request_key,
            request_digest=request.request_digest,
            status=RunStatus.QUEUED,
            budget=_default_budget(),
            source_snapshot=request.source_snapshot,
            created_at=now,
            updated_at=now,
            last_event_seq=0,
        )
        return project_agent_run(self._store.create_run(run))

    def status(self, request: AgentRunStatusRequest) -> dict[str, object] | None:
        run = self._store.get_run(request.run_id)
        if run is None or run.subject_id != request.subject_id:
            return None
        return project_agent_run(run)


def parse_agent_run_create_request(body: bytes) -> AgentRunCreateRequest:
    payload = _exact_json_object(body)
    if set(payload) != {
        "subject_id",
        "scope_ref",
        "request_key",
        "request_digest",
        "source_snapshot",
    }:
        raise AgentRunAPIError("invalid AgentRun request")
    sources = payload["source_snapshot"]
    if not isinstance(sources, list) or not 1 <= len(sources) <= MAX_AGENT_RUN_SOURCES:
        raise AgentRunAPIError("invalid AgentRun request")
    try:
        source_snapshot = tuple(
            SourceRevision(source_id=item["source_id"], revision=item["revision"])
            for item in sources
            if isinstance(item, dict) and set(item) == {"source_id", "revision"}
        )
        if len(source_snapshot) != len(sources):
            raise AgentRunAPIError("invalid AgentRun request")
        return AgentRunCreateRequest(
            subject_id=_string(payload, "subject_id"),
            scope_ref=_string(payload, "scope_ref"),
            request_key=_string(payload, "request_key"),
            request_digest=_string(payload, "request_digest"),
            source_snapshot=source_snapshot,
        )
    except (KeyError, TypeError, ValueError) as error:
        raise AgentRunAPIError("invalid AgentRun request") from error


def parse_agent_run_status_request(body: bytes) -> AgentRunStatusRequest:
    payload = _exact_json_object(body)
    if set(payload) != {"subject_id", "run_id"}:
        raise AgentRunAPIError("invalid AgentRun request")
    return AgentRunStatusRequest(
        subject_id=_string(payload, "subject_id"),
        run_id=_string(payload, "run_id"),
    )


def project_agent_run(run: AgentRun) -> dict[str, object]:
    """Return the internal allowlist consumed by the Memos BFF."""

    return {
        "run_id": run.run_id,
        "status": run.status.value,
        "created_at": _timestamp(run.created_at),
        "updated_at": _timestamp(run.updated_at),
        "last_event_seq": run.last_event_seq,
        "source_count": len(run.source_snapshot),
        "terminal_reason": run.terminal_reason,
    }


def _default_budget() -> ExecutionBudget:
    return ExecutionBudget(
        max_steps=MAX_STEPS,
        max_tool_calls=MAX_TOOL_CALLS,
        max_tool_retries=MAX_TOOL_RETRIES,
        max_active_seconds=MAX_ACTIVE_SECONDS,
        max_tool_attempt_seconds=MAX_TOOL_ATTEMPT_SECONDS,
        max_artifacts=MAX_ARTIFACTS,
        max_artifact_bytes=MAX_ARTIFACT_BYTES,
    )


def _exact_json_object(body: bytes) -> dict[str, object]:
    if not body or len(body) > MAX_AGENT_RUN_REQUEST_BYTES:
        raise AgentRunAPIError("invalid AgentRun request")

    def reject_duplicates(pairs: list[tuple[str, object]]) -> dict[str, object]:
        value: dict[str, object] = {}
        for key, item in pairs:
            if key in value:
                raise AgentRunAPIError("invalid AgentRun request")
            value[key] = item
        return value

    try:
        payload = json.loads(body, object_pairs_hook=reject_duplicates)
    except (TypeError, ValueError, UnicodeDecodeError) as error:
        raise AgentRunAPIError("invalid AgentRun request") from error
    if not isinstance(payload, dict):
        raise AgentRunAPIError("invalid AgentRun request")
    return payload


def _string(payload: dict[str, object], name: str) -> str:
    value = payload[name]
    if not isinstance(value, str):
        raise AgentRunAPIError("invalid AgentRun request")
    return value


def _timestamp(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")
