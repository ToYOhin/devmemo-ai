"""Request-bound deterministic execution for the first AgentRun product demo."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
from pathlib import Path
from typing import Callable

from app.adapters.agent_run_artifact_store import (
    SQLiteAgentRunArtifactStore,
    StoredMarkdownArtifact,
)
from app.adapters.agent_run_store import SQLiteAgentRunStore
from app.domain.agent_run import Artifact, ArtifactStatus, SourceRevision
from app.services.agent_run_report import (
    ALLOWED_DEMO_TASKS,
    ReportSource,
    build_markdown_report,
)
from app.services.agent_run_runtime import (
    BoundedAgentRunPlan,
    BoundedAgentRunRuntime,
    RuntimeToolCall,
    ToolInvocation,
    ToolResult,
    ToolResultStatus,
)


class AgentRunDemoError(ValueError):
    """Raised when a demo execution is missing or no longer matches its run."""


@dataclass(frozen=True)
class AgentRunDemoRequest:
    subject_id: str
    run_id: str
    task_kind: str
    sources: tuple[ReportSource, ...]


class AgentRunDemoExecutor:
    def __init__(
        self,
        database: str | Path,
        *,
        utc_now: Callable[[], datetime] | None = None,
    ) -> None:
        self._runs = SQLiteAgentRunStore(database)
        self._artifacts = SQLiteAgentRunArtifactStore(database)
        self._utc_now = utc_now or (lambda: datetime.now(timezone.utc))

    async def execute(self, request: AgentRunDemoRequest):
        run = self._runs.get_run(request.run_id)
        snapshot = tuple(SourceRevision(item.source_id, item.revision) for item in request.sources)
        if (
            run is None
            or run.subject_id != request.subject_id
            or request.task_kind not in ALLOWED_DEMO_TASKS
            or run.request_digest != _digest(request.task_kind)
            or run.source_snapshot != snapshot
        ):
            raise AgentRunDemoError("invalid AgentRun demo execution")
        plan = _plan(run.request_digest, request.task_kind, request.sources)
        runtime = BoundedAgentRunRuntime(
            store=self._runs,
            authority=_RequestAuthority(run.subject_id, run.scope_ref, snapshot),
            tool_executor=_MarkdownToolExecutor(
                request.task_kind,
                request.sources,
                self._artifacts,
                self._utc_now,
            ),
            utc_now=self._utc_now,
        )
        return await runtime.run(run.run_id, plan)


class _RequestAuthority:
    def __init__(self, subject_id: str, scope_ref: str, snapshot: tuple[SourceRevision, ...]) -> None:
        self._subject_id = subject_id
        self._scope_ref = scope_ref
        self._snapshot = snapshot

    async def resolve(self, *, subject_id: str, scope_ref: str, expected_snapshot: tuple[SourceRevision, ...]):
        if (subject_id, scope_ref, expected_snapshot) != (
            self._subject_id,
            self._scope_ref,
            self._snapshot,
        ):
            raise AgentRunDemoError("AgentRun authority is stale")
        return self._snapshot


class _MarkdownToolExecutor:
    def __init__(self, task_kind, sources, store, utc_now) -> None:
        self._task_kind = task_kind
        self._sources = sources
        self._store = store
        self._utc_now = utc_now

    async def execute(self, invocation: ToolInvocation) -> ToolResult:
        if invocation.tool_name != "create_report_artifact":
            return ToolResult(ToolResultStatus.FAILED, "unsupported_tool")
        report = build_markdown_report(self._task_kind, self._sources)
        digest = _digest(report.markdown)
        artifact_id = f"artifact-{_digest(invocation.run_id)[:32]}"
        storage_ref = f"storage-{_digest(artifact_id)[:32]}"
        stored = StoredMarkdownArtifact(
            artifact_id=artifact_id,
            run_id=invocation.run_id,
            storage_ref=storage_ref,
            file_name=report.file_name,
            markdown=report.markdown,
            digest=digest,
        )
        self._store.put(stored)
        now = self._utc_now()
        artifact = Artifact(
            artifact_id=artifact_id,
            run_id=invocation.run_id,
            step_id=invocation.step_id,
            kind="report",
            media_type="application/json",
            storage_ref=storage_ref,
            digest=digest,
            size_bytes=len(report.markdown.encode("utf-8")),
            evidence_refs=invocation.source_snapshot,
            created_at=now,
            expires_at=now + timedelta(hours=24),
            status=ArtifactStatus.AVAILABLE,
        )
        return ToolResult(ToolResultStatus.SUCCEEDED, "report_created", artifact)


def _plan(request_digest: str, task_kind: str, sources: tuple[ReportSource, ...]) -> BoundedAgentRunPlan:
    source_material = "|".join(
        f"{item.source_id}:{item.revision}:{_digest(item.content)}" for item in sources
    )
    return BoundedAgentRunPlan(
        request_digest=request_digest,
        plan_step_id="step-plan-001",
        tool_calls=(
            RuntimeToolCall(
                "step-report-001",
                "create_report_artifact",
                _digest(f"{task_kind}|{source_material}"),
            ),
        ),
        finalize_step_id="step-finalize-001",
        finalize_digest=_digest(f"finalize|{task_kind}|{source_material}"),
    )


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()
