"""Dormant bounded orchestration for persisted R7 AgentRun state.

The runtime is deliberately not composed into FastAPI, a worker, or settings.
It executes only a caller-supplied content-free plan through injected authority,
cancellation, and tool boundaries, then atomically checkpoints safe metadata.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from enum import Enum
import hashlib
import json
import time
from typing import Callable, Protocol

from app.domain.agent_run import (
    MAX_STEPS,
    MAX_TOOL_CALLS,
    AgentRun,
    AgentRunContractError,
    AgentStep,
    ApprovalRequest,
    Artifact,
    ArtifactStatus,
    RunEvent,
    RunStatus,
    SourceRevision,
    StepKind,
    StepStatus,
)


class AgentRunRuntimeError(RuntimeError):
    """Raised when a dormant runtime cannot safely inspect or persist a run."""


class AgentRunSnapshotView(Protocol):
    @property
    def run(self) -> AgentRun: ...

    @property
    def steps(self) -> tuple[AgentStep, ...]: ...

    @property
    def events(self) -> tuple[RunEvent, ...]: ...

    @property
    def approvals(self) -> tuple[ApprovalRequest, ...]: ...

    @property
    def artifacts(self) -> tuple[Artifact, ...]: ...


class AgentRunPersistence(Protocol):
    def load_snapshot(self, run_id: str, *, event_limit: int = 128) -> AgentRunSnapshotView | None: ...

    def commit_checkpoint(
        self,
        *,
        run: AgentRun,
        step: AgentStep,
        event: RunEvent,
        approval: ApprovalRequest | None = None,
        artifact: Artifact | None = None,
    ) -> AgentRunSnapshotView: ...


class CurrentAuthority(Protocol):
    async def resolve(
        self,
        *,
        subject_id: str,
        scope_ref: str,
        expected_snapshot: tuple[SourceRevision, ...],
    ) -> tuple[SourceRevision, ...]: ...


class CancellationProbe(Protocol):
    async def is_cancelled(self, *, run_id: str, subject_id: str) -> bool: ...


class ToolExecutor(Protocol):
    """Cancellation-safe internal port whose adapters also bound their own I/O."""

    async def execute(self, invocation: ToolInvocation) -> ToolResult: ...


class ToolResultStatus(str, Enum):
    SUCCEEDED = "succeeded"
    TRANSIENT_FAILURE = "transient_failure"
    FAILED = "failed"


@dataclass(frozen=True)
class RuntimeToolCall:
    step_id: str
    tool_name: str
    input_digest: str

    def __post_init__(self) -> None:
        AgentStep(
            step_id=self.step_id,
            run_id="validation-run",
            ordinal=1,
            kind=StepKind.TOOL,
            status=StepStatus.QUEUED,
            attempt=0,
            input_digest=self.input_digest,
            tool_name=self.tool_name,
        )


@dataclass(frozen=True)
class BoundedAgentRunPlan:
    request_digest: str
    plan_step_id: str
    tool_calls: tuple[RuntimeToolCall, ...]
    finalize_step_id: str
    finalize_digest: str
    plan_digest: str = field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "tool_calls", tuple(self.tool_calls))
        AgentStep(
            step_id=self.plan_step_id,
            run_id="validation-run",
            ordinal=1,
            kind=StepKind.PLAN,
            status=StepStatus.QUEUED,
            attempt=0,
            input_digest=self.request_digest,
        )
        AgentStep(
            step_id=self.finalize_step_id,
            run_id="validation-run",
            ordinal=1,
            kind=StepKind.FINALIZE,
            status=StepStatus.QUEUED,
            attempt=0,
            input_digest=self.finalize_digest,
        )
        step_ids = [self.plan_step_id, *(item.step_id for item in self.tool_calls), self.finalize_step_id]
        if len(step_ids) != len(set(step_ids)):
            raise AgentRunContractError("runtime plan step identifiers must be unique")
        if len(step_ids) > MAX_STEPS or len(self.tool_calls) > MAX_TOOL_CALLS:
            raise AgentRunContractError("runtime plan exceeds the contract ceiling")
        object.__setattr__(self, "plan_digest", _plan_digest(self))


@dataclass(frozen=True)
class ToolInvocation:
    run_id: str
    step_id: str
    subject_id: str
    scope_ref: str
    tool_name: str
    input_digest: str
    attempt: int
    idempotency_key: str
    source_snapshot: tuple[SourceRevision, ...]


@dataclass(frozen=True)
class ToolResult:
    status: ToolResultStatus
    outcome_code: str
    artifact: Artifact | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.status, ToolResultStatus):
            raise AgentRunContractError("tool result status must use ToolResultStatus")
        _validate_safe_code("outcome_code", self.outcome_code)
        if self.status is not ToolResultStatus.SUCCEEDED and self.artifact is not None:
            raise AgentRunContractError("failed tool result must not contain an artifact")


@dataclass(frozen=True)
class _GuardResult:
    reason_code: str | None
    duration_ms: int


class _NeverCancelled:
    async def is_cancelled(self, *, run_id: str, subject_id: str) -> bool:
        del run_id, subject_id
        return False


class BoundedAgentRunRuntime:
    """Run one persisted, bounded plan without registering a product path."""

    def __init__(
        self,
        *,
        store: AgentRunPersistence,
        authority: CurrentAuthority,
        tool_executor: ToolExecutor,
        cancellation: CancellationProbe | None = None,
        utc_now: Callable[[], datetime] | None = None,
        monotonic: Callable[[], float] | None = None,
    ) -> None:
        self._store = store
        self._authority = authority
        self._tool_executor = tool_executor
        self._cancellation = cancellation or _NeverCancelled()
        self._utc_now = utc_now or (lambda: datetime.now(timezone.utc))
        self._monotonic = monotonic or time.monotonic

    async def run(self, run_id: str, plan: BoundedAgentRunPlan) -> AgentRunSnapshotView:
        """Advance a run until it pauses or reaches a terminal checkpoint."""

        snapshot = self._load(run_id)
        resume_duration_ms = 0
        if plan.request_digest != snapshot.run.request_digest:
            raise AgentRunRuntimeError("runtime plan does not match the accepted request")
        if snapshot.run.status is not RunStatus.QUEUED:
            self._validate_plan_binding(snapshot, plan)
        if snapshot.run.status in {RunStatus.SUCCEEDED, RunStatus.FAILED, RunStatus.CANCELLED}:
            return snapshot
        if snapshot.run.status is RunStatus.QUEUED:
            guard = await self._guard(snapshot)
            initial_plan_step = self._step(
                snapshot, plan.plan_step_id, 1, StepKind.PLAN, plan.plan_digest
            )
            if guard.reason_code is not None:
                return self._terminal_checkpoint(
                    snapshot, initial_plan_step, guard.reason_code, guard.duration_ms
                )
            snapshot = self._checkpoint(
                snapshot,
                initial_plan_step,
                run_status=RunStatus.RUNNING,
                step_status=StepStatus.RUNNING,
                event_type="run_claimed",
                duration_ms=guard.duration_ms,
            )
        else:
            self._validate_resume(snapshot)
            guard = await self._guard(snapshot)
            if snapshot.run.status is RunStatus.WAITING_APPROVAL:
                if guard.reason_code is None:
                    return snapshot
                waiting_step = next(
                    (
                        item
                        for item in reversed(snapshot.steps)
                        if item.status is StepStatus.RUNNING
                    ),
                    None,
                )
                if waiting_step is None:
                    raise AgentRunRuntimeError(
                        "waiting AgentRun has no resumable approval step"
                    )
                return self._terminal_checkpoint(
                    snapshot,
                    waiting_step,
                    guard.reason_code,
                    guard.duration_ms,
                )
            self._validate_persisted_plan(snapshot, plan)
            if guard.reason_code is not None:
                resume_step = self._next_step(snapshot, plan)
                return self._terminal_checkpoint(
                    snapshot, resume_step, guard.reason_code, guard.duration_ms
                )
            resume_duration_ms = guard.duration_ms

        plan_step = self._find_step(snapshot, plan.plan_step_id)
        if plan_step is None:
            raise AgentRunRuntimeError("persisted runtime plan checkpoint is missing")
        if plan_step.status is StepStatus.RUNNING:
            required_steps = len(plan.tool_calls) + 2
            required_calls = len(plan.tool_calls)
            if required_steps > snapshot.run.budget.max_steps or required_calls > snapshot.run.budget.max_tool_calls:
                return self._terminal_checkpoint(
                    snapshot,
                    plan_step,
                    "budget_exhausted",
                    resume_duration_ms,
                )
            snapshot = self._checkpoint(
                snapshot,
                plan_step,
                run_status=RunStatus.RUNNING,
                step_status=StepStatus.SUCCEEDED,
                event_type="plan_committed",
                duration_ms=resume_duration_ms,
                outcome_code="plan_valid",
            )
            resume_duration_ms = 0
        elif plan_step.status is not StepStatus.SUCCEEDED:
            raise AgentRunRuntimeError("persisted runtime plan is not resumable")

        resume_target_id = (
            self._next_step(snapshot, plan).step_id if resume_duration_ms else None
        )
        for ordinal, tool_call in enumerate(plan.tool_calls, start=2):
            snapshot = await self._execute_tool(
                snapshot,
                tool_call,
                ordinal,
                carried_ms=(
                    resume_duration_ms
                    if resume_target_id == tool_call.step_id
                    else 0
                ),
            )
            if snapshot.run.status is not RunStatus.RUNNING:
                return snapshot

        return await self._finalize(
            snapshot,
            plan,
            carried_ms=(
                resume_duration_ms
                if resume_target_id == plan.finalize_step_id
                else 0
            ),
        )

    async def _execute_tool(
        self,
        snapshot: AgentRunSnapshotView,
        tool_call: RuntimeToolCall,
        ordinal: int,
        *,
        carried_ms: int = 0,
    ) -> AgentRunSnapshotView:
        existing = self._find_step(snapshot, tool_call.step_id)
        if existing is not None and existing.status is StepStatus.SUCCEEDED:
            return snapshot
        if existing is not None and existing.status is not StepStatus.RUNNING:
            raise AgentRunRuntimeError("persisted tool step is not resumable")
        step = existing or self._step(
            snapshot,
            tool_call.step_id,
            ordinal,
            StepKind.TOOL,
            tool_call.input_digest,
            tool_name=tool_call.tool_name,
        )
        unknown_attempt_ms = (
            snapshot.run.budget.max_tool_attempt_seconds * 1000
            if existing is not None and self._has_unknown_delivery(snapshot, step)
            else 0
        )
        reserved_ms = carried_ms + unknown_attempt_ms
        guard = await self._guard(snapshot, reserved_ms=reserved_ms)
        pending_ms = reserved_ms + guard.duration_ms
        if guard.reason_code is not None:
            return self._terminal_checkpoint(snapshot, step, guard.reason_code, pending_ms)
        if self._tool_delivery_count(snapshot) >= snapshot.run.budget.max_tool_calls:
            return self._terminal_checkpoint(
                snapshot, step, "budget_exhausted", pending_ms
            )
        if existing is None:
            snapshot = self._checkpoint(
                snapshot,
                step,
                run_status=RunStatus.RUNNING,
                step_status=StepStatus.RUNNING,
                event_type="tool_started",
                duration_ms=pending_ms,
                tool_name=tool_call.tool_name,
            )
            pending_ms = 0
            persisted_step = self._find_step(snapshot, tool_call.step_id)
            if persisted_step is None:
                raise AgentRunRuntimeError("tool start checkpoint disappeared")
            step = persisted_step
        else:
            snapshot = self._checkpoint(
                snapshot,
                step,
                run_status=RunStatus.RUNNING,
                step_status=StepStatus.RUNNING,
                event_type="tool_resumed",
                duration_ms=pending_ms,
                tool_name=tool_call.tool_name,
            )
            pending_ms = 0
            persisted_step = self._find_step(snapshot, tool_call.step_id)
            if persisted_step is None:
                raise AgentRunRuntimeError("resumed tool checkpoint disappeared")
            step = persisted_step
        invocation = ToolInvocation(
            run_id=snapshot.run.run_id,
            step_id=step.step_id,
            subject_id=snapshot.run.subject_id,
            scope_ref=snapshot.run.scope_ref,
            tool_name=tool_call.tool_name,
            input_digest=tool_call.input_digest,
            attempt=step.attempt,
            idempotency_key=_tool_idempotency_key(snapshot.run, step),
            source_snapshot=snapshot.run.source_snapshot,
        )
        started = self._monotonic()
        try:
            timeout_seconds = self._tool_timeout_seconds(
                snapshot, reserved_ms=pending_ms
            )
        except AgentRunRuntimeError:
            return self._terminal_checkpoint(
                snapshot, step, "active_time_exhausted", pending_ms
            )
        try:
            result = await asyncio.wait_for(self._tool_executor.execute(invocation), timeout=timeout_seconds)
        except TimeoutError:
            duration_ms = pending_ms + self._elapsed_ms(started)
            return await self._retry_or_fail(
                snapshot,
                step,
                tool_call,
                ordinal,
                reason_code="tool_timeout",
                outcome_code="tool_timeout",
                duration_ms=duration_ms,
            )
        except Exception:
            duration_ms = pending_ms + self._elapsed_ms(started)
            return self._terminal_checkpoint(snapshot, step, "tool_error", duration_ms)
        duration_ms = pending_ms + self._elapsed_ms(started)
        if not isinstance(result, ToolResult):
            return self._terminal_checkpoint(
                snapshot, step, "invalid_tool_result", duration_ms
            )
        guard = await self._guard(snapshot, reserved_ms=duration_ms)
        duration_ms += guard.duration_ms
        if guard.reason_code is not None:
            return self._terminal_checkpoint(snapshot, step, guard.reason_code, duration_ms)
        if result.status is ToolResultStatus.TRANSIENT_FAILURE:
            return await self._retry_or_fail(
                snapshot,
                step,
                tool_call,
                ordinal,
                reason_code="tool_failed",
                outcome_code=result.outcome_code,
                duration_ms=duration_ms,
            )
        if result.status is ToolResultStatus.FAILED:
            return self._terminal_checkpoint(snapshot, step, "tool_failed", duration_ms)
        artifact = result.artifact
        if (tool_call.tool_name == "create_report_artifact") != (artifact is not None):
            return self._terminal_checkpoint(snapshot, step, "invalid_tool_result", duration_ms)
        if artifact is not None and (
            artifact.status is not ArtifactStatus.AVAILABLE
            or artifact.run_id != snapshot.run.run_id
            or artifact.step_id != step.step_id
            or not set(artifact.evidence_refs).issubset(
                set(snapshot.run.source_snapshot)
            )
            or artifact.created_at > self._utc_now()
        ):
            return self._terminal_checkpoint(snapshot, step, "invalid_tool_result", duration_ms)
        return self._checkpoint(
            snapshot,
            step,
            run_status=RunStatus.RUNNING,
            step_status=StepStatus.SUCCEEDED,
            event_type="tool_completed",
            duration_ms=duration_ms,
            outcome_code=result.outcome_code,
            tool_name=tool_call.tool_name,
            artifact=artifact,
        )

    async def _retry_or_fail(
        self,
        snapshot: AgentRunSnapshotView,
        step: AgentStep,
        tool_call: RuntimeToolCall,
        ordinal: int,
        *,
        reason_code: str,
        outcome_code: str,
        duration_ms: int,
    ) -> AgentRunSnapshotView:
        used_calls = sum(
            item.attempt + 1 for item in snapshot.steps if item.kind is StepKind.TOOL
        )
        can_retry = (
            step.attempt < snapshot.run.budget.max_tool_retries
            and used_calls < snapshot.run.budget.max_tool_calls
            and self._remaining_seconds(snapshot, reserved_ms=duration_ms) > 0
        )
        if not can_retry:
            failure = (
                "budget_exhausted"
                if used_calls >= snapshot.run.budget.max_tool_calls
                or self._remaining_seconds(snapshot, reserved_ms=duration_ms) <= 0
                else reason_code
            )
            return self._terminal_checkpoint(snapshot, step, failure, duration_ms)
        snapshot = self._checkpoint(
            snapshot,
            step,
            run_status=RunStatus.RUNNING,
            step_status=StepStatus.RUNNING,
            event_type="tool_retry_scheduled",
            duration_ms=duration_ms,
            outcome_code=outcome_code,
            tool_name=tool_call.tool_name,
            attempt=step.attempt + 1,
        )
        return await self._execute_tool(snapshot, tool_call, ordinal)

    async def _finalize(
        self,
        snapshot: AgentRunSnapshotView,
        plan: BoundedAgentRunPlan,
        *,
        carried_ms: int = 0,
    ) -> AgentRunSnapshotView:
        ordinal = len(plan.tool_calls) + 2
        existing = self._find_step(snapshot, plan.finalize_step_id)
        if existing is not None and existing.status is StepStatus.SUCCEEDED:
            return snapshot
        if existing is not None and existing.status is not StepStatus.RUNNING:
            raise AgentRunRuntimeError("persisted finalization step is not resumable")
        step = existing or self._step(
            snapshot,
            plan.finalize_step_id,
            ordinal,
            StepKind.FINALIZE,
            plan.finalize_digest,
        )
        guard = await self._guard(snapshot, reserved_ms=carried_ms)
        pending_ms = carried_ms + guard.duration_ms
        if guard.reason_code is not None:
            return self._terminal_checkpoint(snapshot, step, guard.reason_code, pending_ms)
        if existing is None:
            snapshot = self._checkpoint(
                snapshot,
                step,
                run_status=RunStatus.RUNNING,
                step_status=StepStatus.RUNNING,
                event_type="finalization_started",
                duration_ms=pending_ms,
            )
            persisted_step = self._find_step(snapshot, plan.finalize_step_id)
            if persisted_step is None:
                raise AgentRunRuntimeError("finalization checkpoint disappeared")
            step = persisted_step
        return self._checkpoint(
            snapshot,
            step,
            run_status=RunStatus.SUCCEEDED,
            step_status=StepStatus.SUCCEEDED,
            event_type="run_succeeded",
            outcome_code="completed",
            terminal_reason="completed",
        )

    async def _guard(
        self, snapshot: AgentRunSnapshotView, *, reserved_ms: int = 0
    ) -> _GuardResult:
        started = self._monotonic()
        timeout = self._remaining_seconds(snapshot, reserved_ms=reserved_ms)
        if timeout <= 0:
            return _GuardResult("active_time_exhausted", 0)
        try:
            current = await asyncio.wait_for(
                self._authority.resolve(
                    subject_id=snapshot.run.subject_id,
                    scope_ref=snapshot.run.scope_ref,
                    expected_snapshot=snapshot.run.source_snapshot,
                ),
                timeout=timeout,
            )
        except (Exception, TimeoutError):
            return _GuardResult("authority_unavailable", self._elapsed_ms(started))
        if (
            not isinstance(current, tuple)
            or any(not isinstance(item, SourceRevision) for item in current)
            or current != snapshot.run.source_snapshot
        ):
            return _GuardResult("authority_stale", self._elapsed_ms(started))
        timeout = self._remaining_seconds(snapshot, reserved_ms=reserved_ms + self._elapsed_ms(started))
        if timeout <= 0:
            return _GuardResult("active_time_exhausted", self._elapsed_ms(started))
        try:
            cancelled = await asyncio.wait_for(
                self._cancellation.is_cancelled(
                    run_id=snapshot.run.run_id,
                    subject_id=snapshot.run.subject_id,
                ),
                timeout=timeout,
            )
        except (Exception, TimeoutError):
            return _GuardResult("cancel_check_unavailable", self._elapsed_ms(started))
        if not isinstance(cancelled, bool):
            return _GuardResult("cancel_check_invalid", self._elapsed_ms(started))
        return _GuardResult("cancelled" if cancelled else None, self._elapsed_ms(started))

    def _terminal_checkpoint(
        self,
        snapshot: AgentRunSnapshotView,
        step: AgentStep,
        reason_code: str,
        duration_ms: int,
    ) -> AgentRunSnapshotView:
        cancelled = reason_code == "cancelled" or snapshot.run.status is RunStatus.QUEUED
        return self._checkpoint(
            snapshot,
            step,
            run_status=RunStatus.CANCELLED if cancelled else RunStatus.FAILED,
            step_status=StepStatus.CANCELLED if cancelled else StepStatus.FAILED,
            event_type="run_cancelled" if cancelled else "run_failed",
            duration_ms=duration_ms,
            outcome_code=reason_code,
            reason_code=reason_code,
            terminal_reason=reason_code,
            tool_name=step.tool_name,
        )

    def _checkpoint(
        self,
        snapshot: AgentRunSnapshotView,
        step: AgentStep,
        *,
        run_status: RunStatus,
        step_status: StepStatus,
        event_type: str,
        duration_ms: int = 0,
        outcome_code: str | None = None,
        reason_code: str | None = None,
        terminal_reason: str | None = None,
        tool_name: str | None = None,
        artifact: Artifact | None = None,
        attempt: int | None = None,
    ) -> AgentRunSnapshotView:
        now = self._utc_now()
        seq = snapshot.run.last_event_seq + 1
        checkpoint_ref = f"checkpoint-{snapshot.run.run_id}-{seq:03d}"
        proposed_step = replace(
            step,
            status=step_status,
            attempt=step.attempt if attempt is None else attempt,
            checkpoint_ref=checkpoint_ref,
            outcome_code=outcome_code,
        )
        proposed_run = replace(
            snapshot.run,
            status=run_status,
            updated_at=now,
            last_event_seq=seq,
            checkpoint_ref=checkpoint_ref,
            terminal_reason=terminal_reason,
        )
        safe_details: dict[str, str | int] = {
            "duration_ms": max(0, duration_ms),
            "status": run_status.value,
        }
        if outcome_code is not None:
            safe_details["outcome_code"] = outcome_code
        if reason_code is not None:
            safe_details["reason_code"] = reason_code
        if tool_name is not None:
            safe_details["tool_name"] = tool_name
        event = RunEvent(
            event_id=f"event-{snapshot.run.run_id}-{seq:03d}",
            run_id=snapshot.run.run_id,
            seq=seq,
            event_type=event_type,
            safe_details=safe_details,
            occurred_at=now,
            step_id=step.step_id,
        )
        try:
            return self._store.commit_checkpoint(
                run=proposed_run,
                step=proposed_step,
                event=event,
                artifact=artifact,
            )
        except Exception as exc:
            raise AgentRunRuntimeError("runtime checkpoint failed closed") from exc

    def _load(self, run_id: str) -> AgentRunSnapshotView:
        try:
            snapshot = self._store.load_snapshot(run_id)
        except Exception as exc:
            raise AgentRunRuntimeError("runtime persistence is unavailable") from exc
        if snapshot is None:
            raise AgentRunRuntimeError("AgentRun does not exist")
        return snapshot

    @staticmethod
    def _validate_resume(snapshot: AgentRunSnapshotView) -> None:
        if snapshot.run.checkpoint_ref is None:
            raise AgentRunRuntimeError("active AgentRun has no checkpoint")
        try:
            snapshot.run.validate_resume(snapshot.run.checkpoint_ref, snapshot.run.source_snapshot)
        except AgentRunContractError as exc:
            raise AgentRunRuntimeError("AgentRun resume binding is invalid") from exc

    @staticmethod
    def _validate_plan_binding(
        snapshot: AgentRunSnapshotView, plan: BoundedAgentRunPlan
    ) -> None:
        plan_step = BoundedAgentRunRuntime._find_step(
            snapshot, plan.plan_step_id
        )
        if (
            plan_step is None
            or plan_step.kind is not StepKind.PLAN
            or plan_step.ordinal != 1
            or plan_step.input_digest != plan.plan_digest
            or plan_step.tool_name is not None
        ):
            raise AgentRunRuntimeError("persisted runtime plan binding conflicts")

    @staticmethod
    def _validate_persisted_plan(
        snapshot: AgentRunSnapshotView, plan: BoundedAgentRunPlan
    ) -> None:
        expected: dict[str, tuple[int, StepKind, str, str | None]] = {
            plan.plan_step_id: (1, StepKind.PLAN, plan.plan_digest, None),
            plan.finalize_step_id: (
                len(plan.tool_calls) + 2,
                StepKind.FINALIZE,
                plan.finalize_digest,
                None,
            ),
        }
        expected.update(
            {
                item.step_id: (ordinal, StepKind.TOOL, item.input_digest, item.tool_name)
                for ordinal, item in enumerate(plan.tool_calls, start=2)
            }
        )
        for step in snapshot.steps:
            binding = expected.get(step.step_id)
            if binding != (step.ordinal, step.kind, step.input_digest, step.tool_name):
                raise AgentRunRuntimeError("persisted runtime plan binding conflicts")

    def _next_step(
        self, snapshot: AgentRunSnapshotView, plan: BoundedAgentRunPlan
    ) -> AgentStep:
        plan_step = self._find_step(snapshot, plan.plan_step_id)
        if plan_step is None or plan_step.status is StepStatus.RUNNING:
            return plan_step or self._step(
                snapshot, plan.plan_step_id, 1, StepKind.PLAN, plan.plan_digest
            )
        for ordinal, tool_call in enumerate(plan.tool_calls, start=2):
            step = self._find_step(snapshot, tool_call.step_id)
            if step is None or step.status is StepStatus.RUNNING:
                return step or self._step(
                    snapshot,
                    tool_call.step_id,
                    ordinal,
                    StepKind.TOOL,
                    tool_call.input_digest,
                    tool_name=tool_call.tool_name,
                )
        finalize = self._find_step(snapshot, plan.finalize_step_id)
        return finalize or self._step(
            snapshot,
            plan.finalize_step_id,
            len(plan.tool_calls) + 2,
            StepKind.FINALIZE,
            plan.finalize_digest,
        )

    @staticmethod
    def _find_step(snapshot: AgentRunSnapshotView, step_id: str) -> AgentStep | None:
        return next((item for item in snapshot.steps if item.step_id == step_id), None)

    @staticmethod
    def _has_unknown_delivery(
        snapshot: AgentRunSnapshotView, step: AgentStep
    ) -> bool:
        latest = next(
            (
                item
                for item in reversed(snapshot.events)
                if item.step_id == step.step_id
            ),
            None,
        )
        return latest is not None and latest.event_type in {
            "tool_started",
            "tool_resumed",
        }

    @staticmethod
    def _tool_delivery_count(snapshot: AgentRunSnapshotView) -> int:
        return sum(
            item.event_type in {"tool_started", "tool_resumed"}
            for item in snapshot.events
        )

    @staticmethod
    def _step(
        snapshot: AgentRunSnapshotView,
        step_id: str,
        ordinal: int,
        kind: StepKind,
        input_digest: str,
        *,
        tool_name: str | None = None,
    ) -> AgentStep:
        return AgentStep(
            step_id=step_id,
            run_id=snapshot.run.run_id,
            ordinal=ordinal,
            kind=kind,
            status=StepStatus.QUEUED,
            attempt=0,
            input_digest=input_digest,
            tool_name=tool_name,
        )

    def _tool_timeout_seconds(
        self, snapshot: AgentRunSnapshotView, *, reserved_ms: int = 0
    ) -> float:
        remaining = self._remaining_seconds(snapshot, reserved_ms=reserved_ms)
        if remaining <= 0:
            raise AgentRunRuntimeError("AgentRun active-time budget is exhausted")
        return min(float(snapshot.run.budget.max_tool_attempt_seconds), remaining)

    @staticmethod
    def _active_ms(snapshot: AgentRunSnapshotView) -> int:
        if snapshot.run.last_event_seq != len(snapshot.events):
            raise AgentRunRuntimeError(
                "AgentRun active-time timeline is truncated"
            )
        total = 0
        for event in snapshot.events:
            value = event.safe_details.get("duration_ms", 0)
            if type(value) is not int:
                raise AgentRunRuntimeError(
                    "stored runtime duration is not a bounded integer"
                )
            total += value
        return total

    def _remaining_seconds(self, snapshot: AgentRunSnapshotView, *, reserved_ms: int = 0) -> float:
        ceiling_ms = snapshot.run.budget.max_active_seconds * 1000
        return max(0.0, (ceiling_ms - self._active_ms(snapshot) - reserved_ms) / 1000)

    def _elapsed_ms(self, started: float) -> int:
        return max(0, int(round((self._monotonic() - started) * 1000)))


def _tool_idempotency_key(run: AgentRun, step: AgentStep) -> str:
    payload = "\x00".join(
        (run.run_id, step.step_id, str(step.attempt), step.tool_name or "", step.input_digest)
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _plan_digest(plan: BoundedAgentRunPlan) -> str:
    payload = {
        "finalize": [plan.finalize_step_id, plan.finalize_digest],
        "plan_step_id": plan.plan_step_id,
        "request_digest": plan.request_digest,
        "schema": "bounded-agent-run-plan-v1",
        "tools": [
            [item.step_id, item.tool_name, item.input_digest]
            for item in plan.tool_calls
        ],
    }
    encoded = json.dumps(
        payload, ensure_ascii=True, separators=(",", ":"), sort_keys=True
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _validate_safe_code(name: str, value: str) -> None:
    RunEvent(
        event_id="validation-event",
        run_id="validation-run",
        seq=1,
        event_type="validation",
        safe_details={name: value},
        occurred_at=datetime(1970, 1, 1, tzinfo=timezone.utc),
    )
