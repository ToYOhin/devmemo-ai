from __future__ import annotations

import asyncio
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sqlite3

import pytest

from app.adapters.agent_run_store import SQLiteAgentRunStore
from app.domain.agent_run import (
    AgentRun,
    AgentRunContractError,
    AgentStep,
    ApprovalRequest,
    ApprovalStatus,
    Artifact,
    ArtifactStatus,
    ExecutionBudget,
    RunEvent,
    RunStatus,
    SourceRevision,
    StepKind,
    StepStatus,
)
from app.services.agent_run_runtime import (
    AgentRunRuntimeError,
    BoundedAgentRunPlan,
    BoundedAgentRunRuntime,
    RuntimeToolCall,
    ToolInvocation,
    ToolResult,
    ToolResultStatus,
)


DIGEST_A = "a" * 64
DIGEST_B = "b" * 64
DIGEST_C = "c" * 64
DIGEST_D = "d" * 64
DIGEST_E = "e" * 64
STARTED_AT = datetime(2026, 8, 12, 0, 0, tzinfo=timezone.utc)
SNAPSHOT = (SourceRevision("memo-001", "revision-001"),)


class UtcClock:
    def __init__(self, initial: datetime = STARTED_AT) -> None:
        self._value = initial

    def __call__(self) -> datetime:
        self._value += timedelta(milliseconds=10)
        return self._value


class MonotonicClock:
    def __init__(self) -> None:
        self._value = 0.0

    def __call__(self) -> float:
        self._value += 0.001
        return self._value

    def advance(self, seconds: float) -> None:
        self._value += seconds


@dataclass
class StaticAuthority:
    snapshot: tuple[SourceRevision, ...] = SNAPSHOT
    calls: int = 0

    async def resolve(
        self,
        *,
        subject_id: str,
        scope_ref: str,
        expected_snapshot: tuple[SourceRevision, ...],
    ) -> tuple[SourceRevision, ...]:
        del subject_id, scope_ref, expected_snapshot
        self.calls += 1
        await asyncio.sleep(0)
        return self.snapshot


class SequencedAuthority(StaticAuthority):
    def __init__(self, snapshots: list[tuple[SourceRevision, ...]]) -> None:
        super().__init__(snapshots[0])
        self._snapshots = snapshots

    async def resolve(
        self,
        *,
        subject_id: str,
        scope_ref: str,
        expected_snapshot: tuple[SourceRevision, ...],
    ) -> tuple[SourceRevision, ...]:
        del subject_id, scope_ref, expected_snapshot
        index = min(self.calls, len(self._snapshots) - 1)
        self.calls += 1
        await asyncio.sleep(0)
        return self._snapshots[index]


class NeverCancelled:
    async def is_cancelled(self, *, run_id: str, subject_id: str) -> bool:
        del run_id, subject_id
        await asyncio.sleep(0)
        return False


class CancelOnCheck(NeverCancelled):
    def __init__(self, cancel_on: int) -> None:
        self.cancel_on = cancel_on
        self.calls = 0

    async def is_cancelled(self, *, run_id: str, subject_id: str) -> bool:
        del run_id, subject_id
        self.calls += 1
        await asyncio.sleep(0)
        return self.calls >= self.cancel_on


class RecordingToolExecutor:
    def __init__(self) -> None:
        self.invocations: list[ToolInvocation] = []

    async def execute(self, invocation: ToolInvocation) -> ToolResult:
        self.invocations.append(invocation)
        await asyncio.sleep(0)
        artifact = None
        if invocation.tool_name == "create_report_artifact":
            artifact = Artifact(
                artifact_id="artifact-001",
                run_id=invocation.run_id,
                step_id=invocation.step_id,
                kind="report",
                media_type="application/json",
                storage_ref="storage-report-001",
                digest=DIGEST_E,
                size_bytes=512,
                evidence_refs=SNAPSHOT,
                created_at=STARTED_AT,
                expires_at=STARTED_AT + timedelta(hours=1),
                status=ArtifactStatus.AVAILABLE,
            )
        return ToolResult(
            status=ToolResultStatus.SUCCEEDED,
            outcome_code="completed",
            artifact=artifact,
        )


class SimulatedProcessExit(BaseException):
    pass


class CrashOnceToolExecutor(RecordingToolExecutor):
    async def execute(self, invocation: ToolInvocation) -> ToolResult:
        self.invocations.append(invocation)
        await asyncio.sleep(0)
        if len(self.invocations) == 1:
            raise SimulatedProcessExit
        return ToolResult(ToolResultStatus.SUCCEEDED, "completed")


class AlwaysCrashToolExecutor(RecordingToolExecutor):
    async def execute(self, invocation: ToolInvocation) -> ToolResult:
        self.invocations.append(invocation)
        await asyncio.sleep(0)
        raise SimulatedProcessExit


class DelayedCrashToolExecutor(RecordingToolExecutor):
    def __init__(self, monotonic: MonotonicClock, delay_seconds: float) -> None:
        super().__init__()
        self._monotonic = monotonic
        self._delay_seconds = delay_seconds

    async def execute(self, invocation: ToolInvocation) -> ToolResult:
        self.invocations.append(invocation)
        await asyncio.sleep(0)
        self._monotonic.advance(self._delay_seconds)
        raise SimulatedProcessExit


class TransientOnceToolExecutor(RecordingToolExecutor):
    async def execute(self, invocation: ToolInvocation) -> ToolResult:
        self.invocations.append(invocation)
        await asyncio.sleep(0)
        if len(self.invocations) == 1:
            return ToolResult(ToolResultStatus.TRANSIENT_FAILURE, "temporary_failure")
        return ToolResult(ToolResultStatus.SUCCEEDED, "completed")


class SlowToolExecutor(RecordingToolExecutor):
    async def execute(self, invocation: ToolInvocation) -> ToolResult:
        self.invocations.append(invocation)
        await asyncio.sleep(2)
        return ToolResult(ToolResultStatus.SUCCEEDED, "completed")


class SecretFailureToolExecutor(RecordingToolExecutor):
    async def execute(self, invocation: ToolInvocation) -> ToolResult:
        self.invocations.append(invocation)
        raise ValueError("provider prompt and raw-secret-value must never persist")


class FailedToolExecutor(RecordingToolExecutor):
    async def execute(self, invocation: ToolInvocation) -> ToolResult:
        self.invocations.append(invocation)
        return ToolResult(ToolResultStatus.FAILED, "permanent_failure")


class InvalidToolExecutor(RecordingToolExecutor):
    async def execute(self, invocation: ToolInvocation) -> ToolResult:
        self.invocations.append(invocation)
        return object()  # type: ignore[return-value]


class FailingAuthority(StaticAuthority):
    async def resolve(
        self,
        *,
        subject_id: str,
        scope_ref: str,
        expected_snapshot: tuple[SourceRevision, ...],
    ) -> tuple[SourceRevision, ...]:
        del subject_id, scope_ref, expected_snapshot
        raise RuntimeError("authority details must not escape")


class InvalidCancellation(NeverCancelled):
    async def is_cancelled(self, *, run_id: str, subject_id: str) -> bool:
        del run_id, subject_id
        return "yes"  # type: ignore[return-value]


def _budget(**overrides: int) -> ExecutionBudget:
    values = {
        "max_steps": 5,
        "max_tool_calls": 3,
        "max_tool_retries": 1,
        "max_active_seconds": 20,
        "max_tool_attempt_seconds": 5,
        "max_artifacts": 1,
        "max_artifact_bytes": 1024,
    }
    values.update(overrides)
    return ExecutionBudget(**values)


def _queued_run(*, budget: ExecutionBudget | None = None) -> AgentRun:
    return AgentRun(
        run_id="run-001",
        subject_id="subject-001",
        scope_ref="scope-001",
        request_key="request-001",
        request_digest=DIGEST_A,
        status=RunStatus.QUEUED,
        budget=budget or _budget(),
        source_snapshot=SNAPSHOT,
        created_at=STARTED_AT,
        updated_at=STARTED_AT,
        last_event_seq=0,
    )


def _plan(*tools: RuntimeToolCall) -> BoundedAgentRunPlan:
    return BoundedAgentRunPlan(
        request_digest=DIGEST_A,
        plan_step_id="step-plan-001",
        tool_calls=tools,
        finalize_step_id="step-finalize-001",
        finalize_digest=DIGEST_E,
    )


def _runtime(
    store: SQLiteAgentRunStore,
    authority: StaticAuthority,
    executor: RecordingToolExecutor,
) -> BoundedAgentRunRuntime:
    return BoundedAgentRunRuntime(
        store=store,
        authority=authority,
        tool_executor=executor,
        cancellation=NeverCancelled(),
        utc_now=UtcClock(),
        monotonic=MonotonicClock(),
    )


def _event(run_id: str, step_id: str, seq: int, occurred_at: datetime) -> RunEvent:
    return RunEvent(
        event_id=f"event-{run_id}-{seq:03d}",
        run_id=run_id,
        seq=seq,
        event_type="checkpoint_committed",
        safe_details={"status": "running"},
        occurred_at=occurred_at,
        step_id=step_id,
    )


def _waiting_approval_store(database: Path) -> SQLiteAgentRunStore:
    store = SQLiteAgentRunStore(database)
    queued = store.create_run(_queued_run(budget=_budget(max_steps=3, max_tool_calls=1)))
    plan = _plan()
    first_time = STARTED_AT + timedelta(milliseconds=10)
    first_checkpoint = "checkpoint-run-001-001"
    running = replace(
        queued,
        status=RunStatus.RUNNING,
        updated_at=first_time,
        last_event_seq=1,
        checkpoint_ref=first_checkpoint,
    )
    plan_step = AgentStep(
        step_id="step-plan-001",
        run_id=queued.run_id,
        ordinal=1,
        kind=StepKind.PLAN,
        status=StepStatus.SUCCEEDED,
        attempt=0,
        input_digest=plan.plan_digest,
        checkpoint_ref=first_checkpoint,
        outcome_code="plan_valid",
    )
    store.commit_checkpoint(
        run=running,
        step=plan_step,
        event=_event(queued.run_id, plan_step.step_id, 1, first_time),
    )
    second_time = STARTED_AT + timedelta(milliseconds=20)
    second_checkpoint = "checkpoint-run-001-002"
    waiting = replace(
        running,
        status=RunStatus.WAITING_APPROVAL,
        updated_at=second_time,
        last_event_seq=2,
        checkpoint_ref=second_checkpoint,
    )
    approval_step = AgentStep(
        step_id="step-approval-001",
        run_id=queued.run_id,
        ordinal=2,
        kind=StepKind.APPROVAL,
        status=StepStatus.RUNNING,
        attempt=0,
        input_digest=DIGEST_B,
        checkpoint_ref=second_checkpoint,
    )
    approval = ApprovalRequest(
        approval_id="approval-001",
        run_id=queued.run_id,
        step_id=approval_step.step_id,
        subject_id=queued.subject_id,
        action_type="future_action",
        action_digest=DIGEST_C,
        source_snapshot=SNAPSHOT,
        requested_at=second_time,
        expires_at=second_time + timedelta(minutes=5),
        status=ApprovalStatus.PENDING,
    )
    store.commit_checkpoint(
        run=waiting,
        step=approval_step,
        event=_event(queued.run_id, approval_step.step_id, 2, second_time),
        approval=approval,
    )
    return store


def test_runtime_executes_bounded_plan_and_commits_complete_timeline(tmp_path: Path) -> None:
    store = SQLiteAgentRunStore(tmp_path / "agent-runs.db")
    store.create_run(_queued_run())
    authority = StaticAuthority()
    executor = RecordingToolExecutor()
    plan = _plan(
        RuntimeToolCall("step-search-001", "search_memos", DIGEST_B),
        RuntimeToolCall("step-evidence-001", "get_memo_evidence", DIGEST_C),
        RuntimeToolCall("step-artifact-001", "create_report_artifact", DIGEST_D),
    )

    result = asyncio.run(_runtime(store, authority, executor).run("run-001", plan))

    assert result.run.status is RunStatus.SUCCEEDED
    assert result.run.terminal_reason == "completed"
    assert [step.kind for step in result.steps] == [
        StepKind.PLAN,
        StepKind.TOOL,
        StepKind.TOOL,
        StepKind.TOOL,
        StepKind.FINALIZE,
    ]
    assert all(step.status is StepStatus.SUCCEEDED for step in result.steps)
    assert [event.seq for event in result.events] == list(range(1, 11))
    assert len(result.artifacts) == 1
    assert len(executor.invocations) == 3
    assert len({item.idempotency_key for item in executor.invocations}) == 3
    assert authority.calls == 8


def test_runtime_rejects_plan_that_cannot_fit_committed_budget(tmp_path: Path) -> None:
    store = SQLiteAgentRunStore(tmp_path / "agent-runs.db")
    store.create_run(_queued_run(budget=_budget(max_steps=2, max_tool_calls=1)))
    authority = StaticAuthority()
    executor = RecordingToolExecutor()
    plan = _plan(RuntimeToolCall("step-search-001", "search_memos", DIGEST_B))

    result = asyncio.run(_runtime(store, authority, executor).run("run-001", plan))

    assert result.run.status is RunStatus.FAILED
    assert result.run.terminal_reason == "budget_exhausted"
    assert len(result.steps) == 1
    assert result.steps[0].kind is StepKind.PLAN
    assert result.steps[0].status is StepStatus.FAILED
    assert executor.invocations == []
    assert [event.event_type for event in result.events] == ["run_claimed", "run_failed"]


def test_runtime_restart_reuses_inflight_attempt_idempotency_key(tmp_path: Path) -> None:
    database = tmp_path / "agent-runs.db"
    store = SQLiteAgentRunStore(database)
    store.create_run(_queued_run(budget=_budget(max_steps=3, max_tool_calls=2)))
    authority = StaticAuthority()
    executor = CrashOnceToolExecutor()
    plan = _plan(RuntimeToolCall("step-search-001", "search_memos", DIGEST_B))
    utc_now = UtcClock()
    monotonic = MonotonicClock()
    first_runtime = BoundedAgentRunRuntime(
        store=store,
        authority=authority,
        tool_executor=executor,
        cancellation=NeverCancelled(),
        utc_now=utc_now,
        monotonic=monotonic,
    )

    try:
        asyncio.run(first_runtime.run("run-001", plan))
    except SimulatedProcessExit:
        pass
    else:
        raise AssertionError("simulated process exit was not propagated")

    interrupted = SQLiteAgentRunStore(database).load_snapshot("run-001")
    assert interrupted is not None
    assert interrupted.run.status is RunStatus.RUNNING
    assert interrupted.steps[-1].status is StepStatus.RUNNING

    restarted = BoundedAgentRunRuntime(
        store=SQLiteAgentRunStore(database),
        authority=authority,
        tool_executor=executor,
        cancellation=NeverCancelled(),
        utc_now=utc_now,
        monotonic=monotonic,
    )
    result = asyncio.run(restarted.run("run-001", plan))

    assert result.run.status is RunStatus.SUCCEEDED
    assert len(result.steps) == 3
    assert len(executor.invocations) == 2
    assert executor.invocations[0].idempotency_key == executor.invocations[1].idempotency_key
    assert executor.invocations[0].attempt == executor.invocations[1].attempt == 0
    assert "tool_resumed" in [event.event_type for event in result.events]


def test_runtime_restart_rejects_changed_uncommitted_plan_suffix(
    tmp_path: Path,
) -> None:
    database = tmp_path / "agent-runs.db"
    store = SQLiteAgentRunStore(database)
    store.create_run(_queued_run(budget=_budget(max_steps=4, max_tool_calls=2)))
    executor = CrashOnceToolExecutor()
    original = _plan(
        RuntimeToolCall("step-search-001", "search_memos", DIGEST_B),
        RuntimeToolCall("step-evidence-001", "get_memo_evidence", DIGEST_C),
    )
    runtime = _runtime(store, StaticAuthority(), executor)

    with pytest.raises(SimulatedProcessExit):
        asyncio.run(runtime.run("run-001", original))

    changed = _plan(
        RuntimeToolCall("step-search-001", "search_memos", DIGEST_B),
        RuntimeToolCall(
            "step-evidence-001", "create_report_artifact", DIGEST_C
        ),
    )
    with pytest.raises(AgentRunRuntimeError, match="plan binding conflicts"):
        asyncio.run(runtime.run("run-001", changed))
    assert len(executor.invocations) == 1


def test_runtime_restart_does_not_redeliver_after_actual_call_budget(
    tmp_path: Path,
) -> None:
    database = tmp_path / "agent-runs.db"
    store = SQLiteAgentRunStore(database)
    store.create_run(_queued_run(budget=_budget(max_steps=3, max_tool_calls=1)))
    executor = AlwaysCrashToolExecutor()
    runtime = _runtime(store, StaticAuthority(), executor)
    plan = _plan(RuntimeToolCall("step-search-001", "search_memos", DIGEST_B))

    with pytest.raises(SimulatedProcessExit):
        asyncio.run(runtime.run("run-001", plan))
    result = asyncio.run(runtime.run("run-001", plan))

    assert result.run.status is RunStatus.FAILED
    assert result.run.terminal_reason == "budget_exhausted"
    assert len(executor.invocations) == 1
    assert [
        event.event_type
        for event in result.events
        if event.event_type in {"tool_started", "tool_resumed"}
    ] == ["tool_started"]


def test_interrupted_attempt_conservatively_consumes_active_time_before_replay(
    tmp_path: Path,
) -> None:
    database = tmp_path / "agent-runs.db"
    store = SQLiteAgentRunStore(database)
    store.create_run(
        _queued_run(
            budget=_budget(
                max_steps=3,
                max_tool_calls=2,
                max_active_seconds=5,
                max_tool_attempt_seconds=5,
            )
        )
    )
    monotonic = MonotonicClock()
    executor = DelayedCrashToolExecutor(monotonic, delay_seconds=2.0)
    plan = _plan(RuntimeToolCall("step-search-001", "search_memos", DIGEST_B))
    first_runtime = BoundedAgentRunRuntime(
        store=store,
        authority=StaticAuthority(),
        tool_executor=executor,
        cancellation=NeverCancelled(),
        utc_now=UtcClock(),
        monotonic=monotonic,
    )

    with pytest.raises(SimulatedProcessExit):
        asyncio.run(first_runtime.run("run-001", plan))

    restarted = BoundedAgentRunRuntime(
        store=SQLiteAgentRunStore(database),
        authority=StaticAuthority(),
        tool_executor=executor,
        cancellation=NeverCancelled(),
        utc_now=UtcClock(STARTED_AT + timedelta(seconds=2)),
        monotonic=monotonic,
    )
    result = asyncio.run(restarted.run("run-001", plan))

    assert result.run.status is RunStatus.FAILED
    assert result.run.terminal_reason == "active_time_exhausted"
    assert len(executor.invocations) == 1
    assert sum(
        event.safe_details.get("duration_ms", 0) for event in result.events
    ) >= 5000


def test_runtime_rechecks_authority_before_restart_execution(tmp_path: Path) -> None:
    database = tmp_path / "agent-runs.db"
    store = SQLiteAgentRunStore(database)
    store.create_run(_queued_run(budget=_budget(max_steps=3, max_tool_calls=2)))
    executor = CrashOnceToolExecutor()
    plan = _plan(RuntimeToolCall("step-search-001", "search_memos", DIGEST_B))
    utc_now = UtcClock()
    monotonic = MonotonicClock()
    first_runtime = BoundedAgentRunRuntime(
        store=store,
        authority=StaticAuthority(),
        tool_executor=executor,
        cancellation=NeverCancelled(),
        utc_now=utc_now,
        monotonic=monotonic,
    )
    try:
        asyncio.run(first_runtime.run("run-001", plan))
    except SimulatedProcessExit:
        pass

    stale_authority = StaticAuthority(
        (SourceRevision("memo-001", "revision-002"),)
    )
    restarted = BoundedAgentRunRuntime(
        store=SQLiteAgentRunStore(database),
        authority=stale_authority,
        tool_executor=executor,
        cancellation=NeverCancelled(),
        utc_now=utc_now,
        monotonic=monotonic,
    )
    result = asyncio.run(restarted.run("run-001", plan))

    assert result.run.status is RunStatus.FAILED
    assert result.run.terminal_reason == "authority_stale"
    assert len(executor.invocations) == 1
    assert result.events[-1].safe_details["reason_code"] == "authority_stale"


def test_runtime_retries_only_classified_transient_failure_with_new_attempt_key(
    tmp_path: Path,
) -> None:
    store = SQLiteAgentRunStore(tmp_path / "agent-runs.db")
    store.create_run(_queued_run(budget=_budget(max_steps=3, max_tool_calls=2)))
    executor = TransientOnceToolExecutor()
    plan = _plan(RuntimeToolCall("step-search-001", "search_memos", DIGEST_B))

    result = asyncio.run(_runtime(store, StaticAuthority(), executor).run("run-001", plan))

    assert result.run.status is RunStatus.SUCCEEDED
    assert len(executor.invocations) == 2
    assert [item.attempt for item in executor.invocations] == [0, 1]
    assert executor.invocations[0].idempotency_key != executor.invocations[1].idempotency_key
    assert "tool_retry_scheduled" in [event.event_type for event in result.events]


def test_waiting_approval_restart_rechecks_authority_and_remains_paused(
    tmp_path: Path,
) -> None:
    database = tmp_path / "agent-runs.db"
    store = _waiting_approval_store(database)
    authority = StaticAuthority()
    executor = RecordingToolExecutor()
    plan = _plan()

    paused = asyncio.run(_runtime(store, authority, executor).run("run-001", plan))

    assert paused.run.status is RunStatus.WAITING_APPROVAL
    assert paused.run.last_event_seq == 2
    assert authority.calls == 1
    assert executor.invocations == []

    stale_authority = StaticAuthority(
        (SourceRevision("memo-001", "revision-002"),)
    )
    stale_runtime = BoundedAgentRunRuntime(
        store=SQLiteAgentRunStore(database),
        authority=stale_authority,
        tool_executor=executor,
        cancellation=NeverCancelled(),
        utc_now=UtcClock(STARTED_AT + timedelta(milliseconds=20)),
        monotonic=MonotonicClock(),
    )
    failed = asyncio.run(stale_runtime.run("run-001", plan))

    assert failed.run.status is RunStatus.FAILED
    assert failed.run.terminal_reason == "authority_stale"
    assert failed.steps[-1].status is StepStatus.FAILED
    assert executor.invocations == []


def test_tool_attempt_timeout_is_bounded_and_retry_budget_is_terminal(
    tmp_path: Path,
) -> None:
    store = SQLiteAgentRunStore(tmp_path / "agent-runs.db")
    store.create_run(
        _queued_run(
            budget=_budget(
                max_steps=3,
                max_tool_calls=2,
                max_active_seconds=3,
                max_tool_attempt_seconds=1,
            )
        )
    )
    executor = SlowToolExecutor()
    runtime = BoundedAgentRunRuntime(
        store=store,
        authority=StaticAuthority(),
        tool_executor=executor,
        cancellation=NeverCancelled(),
        utc_now=UtcClock(),
    )
    plan = _plan(RuntimeToolCall("step-search-001", "search_memos", DIGEST_B))

    result = asyncio.run(runtime.run("run-001", plan))

    assert result.run.status is RunStatus.FAILED
    assert result.run.terminal_reason == "budget_exhausted"
    assert len(executor.invocations) == 2
    assert [item.attempt for item in executor.invocations] == [0, 1]
    for event in result.events:
        duration_ms = event.safe_details.get("duration_ms", 0)
        assert isinstance(duration_ms, int)
        assert duration_ms <= 1100


def test_untrusted_tool_exception_fails_closed_without_persisting_error_text(
    tmp_path: Path,
) -> None:
    store = SQLiteAgentRunStore(tmp_path / "agent-runs.db")
    store.create_run(_queued_run(budget=_budget(max_steps=3, max_tool_calls=1)))
    executor = SecretFailureToolExecutor()
    plan = _plan(RuntimeToolCall("step-search-001", "search_memos", DIGEST_B))

    result = asyncio.run(_runtime(store, StaticAuthority(), executor).run("run-001", plan))

    assert result.run.status is RunStatus.FAILED
    assert result.run.terminal_reason == "tool_error"
    persisted = str([event.to_dict() for event in result.events])
    assert "provider prompt" not in persisted
    assert "raw-secret-value" not in persisted


def test_authority_change_after_tool_discards_uncommitted_artifact(
    tmp_path: Path,
) -> None:
    store = SQLiteAgentRunStore(tmp_path / "agent-runs.db")
    store.create_run(_queued_run(budget=_budget(max_steps=3, max_tool_calls=1)))
    stale = (SourceRevision("memo-001", "revision-002"),)
    authority = SequencedAuthority([SNAPSHOT, SNAPSHOT, stale])
    executor = RecordingToolExecutor()
    plan = _plan(
        RuntimeToolCall(
            "step-artifact-001", "create_report_artifact", DIGEST_D
        )
    )

    result = asyncio.run(_runtime(store, authority, executor).run("run-001", plan))

    assert result.run.status is RunStatus.FAILED
    assert result.run.terminal_reason == "authority_stale"
    assert len(executor.invocations) == 1
    assert result.artifacts == ()
    assert result.steps[-1].status is StepStatus.FAILED


def test_cancellation_after_tool_prevents_success_checkpoint(tmp_path: Path) -> None:
    store = SQLiteAgentRunStore(tmp_path / "agent-runs.db")
    store.create_run(_queued_run(budget=_budget(max_steps=3, max_tool_calls=1)))
    executor = RecordingToolExecutor()
    cancellation = CancelOnCheck(cancel_on=3)
    runtime = BoundedAgentRunRuntime(
        store=store,
        authority=StaticAuthority(),
        tool_executor=executor,
        cancellation=cancellation,
        utc_now=UtcClock(),
        monotonic=MonotonicClock(),
    )
    plan = _plan(RuntimeToolCall("step-search-001", "search_memos", DIGEST_B))

    result = asyncio.run(runtime.run("run-001", plan))

    assert result.run.status is RunStatus.CANCELLED
    assert result.run.terminal_reason == "cancelled"
    assert len(executor.invocations) == 1
    assert result.steps[-1].status is StepStatus.CANCELLED
    assert "tool_completed" not in [event.event_type for event in result.events]


def test_runtime_boundary_models_reject_ambiguous_or_unbounded_values() -> None:
    duplicate = RuntimeToolCall("step-search-001", "search_memos", DIGEST_B)
    with pytest.raises(AgentRunContractError, match="unique"):
        _plan(duplicate, duplicate)

    too_many = tuple(
        RuntimeToolCall(f"step-search-{index:03d}", "search_memos", DIGEST_B)
        for index in range(1, 10)
    )
    with pytest.raises(AgentRunContractError, match="ceiling"):
        _plan(*too_many)

    with pytest.raises(AgentRunContractError, match="ToolResultStatus"):
        ToolResult("succeeded", "completed")  # type: ignore[arg-type]
    with pytest.raises(AgentRunContractError, match="must not contain"):
        ToolResult(
            ToolResultStatus.FAILED,
            "permanent_failure",
            Artifact(
                artifact_id="artifact-001",
                run_id="run-001",
                step_id="step-artifact-001",
                kind="report",
                media_type="application/json",
                storage_ref="storage-report-001",
                digest=DIGEST_E,
                size_bytes=1,
                evidence_refs=SNAPSHOT,
                created_at=STARTED_AT,
                expires_at=STARTED_AT + timedelta(hours=1),
                status=ArtifactStatus.AVAILABLE,
            ),
        )


def test_terminal_run_is_idempotent_and_request_plan_mismatch_fails_closed(
    tmp_path: Path,
) -> None:
    store = SQLiteAgentRunStore(tmp_path / "agent-runs.db")
    store.create_run(_queued_run(budget=_budget(max_steps=2, max_tool_calls=1)))
    authority = StaticAuthority()
    executor = RecordingToolExecutor()
    runtime = _runtime(store, authority, executor)
    completed = asyncio.run(runtime.run("run-001", _plan()))
    event_count = len(completed.events)
    authority_calls = authority.calls

    replay = asyncio.run(runtime.run("run-001", _plan()))

    assert replay == completed
    assert len(replay.events) == event_count
    assert authority.calls == authority_calls

    changed_terminal_plan = BoundedAgentRunPlan(
        request_digest=DIGEST_A,
        plan_step_id="step-plan-001",
        tool_calls=(),
        finalize_step_id="step-finalize-001",
        finalize_digest=DIGEST_D,
    )
    with pytest.raises(AgentRunRuntimeError, match="plan binding conflicts"):
        asyncio.run(runtime.run("run-001", changed_terminal_plan))

    other_store = SQLiteAgentRunStore(tmp_path / "other-agent-runs.db")
    other_store.create_run(_queued_run())
    mismatched = BoundedAgentRunPlan(
        request_digest=DIGEST_B,
        plan_step_id="step-plan-001",
        tool_calls=(),
        finalize_step_id="step-finalize-001",
        finalize_digest=DIGEST_E,
    )
    with pytest.raises(AgentRunRuntimeError, match="accepted request"):
        asyncio.run(
            _runtime(other_store, StaticAuthority(), executor).run(
                "run-001", mismatched
            )
        )


@pytest.mark.parametrize(
    ("authority", "cancellation", "reason_code"),
    [
        (FailingAuthority(), NeverCancelled(), "authority_unavailable"),
        (StaticAuthority(), InvalidCancellation(), "cancel_check_invalid"),
    ],
)
def test_guard_failures_cancel_queued_run_without_tool_execution(
    tmp_path: Path,
    authority: StaticAuthority,
    cancellation: NeverCancelled,
    reason_code: str,
) -> None:
    store = SQLiteAgentRunStore(tmp_path / f"{reason_code}.db")
    store.create_run(_queued_run())
    executor = RecordingToolExecutor()
    runtime = BoundedAgentRunRuntime(
        store=store,
        authority=authority,
        tool_executor=executor,
        cancellation=cancellation,
        utc_now=UtcClock(),
        monotonic=MonotonicClock(),
    )

    result = asyncio.run(runtime.run("run-001", _plan()))

    assert result.run.status is RunStatus.CANCELLED
    assert result.run.terminal_reason == reason_code
    assert executor.invocations == []


@pytest.mark.parametrize(
    ("executor", "reason_code"),
    [
        (FailedToolExecutor(), "tool_failed"),
        (InvalidToolExecutor(), "invalid_tool_result"),
    ],
)
def test_invalid_or_failed_tool_results_are_terminal(
    tmp_path: Path,
    executor: RecordingToolExecutor,
    reason_code: str,
) -> None:
    store = SQLiteAgentRunStore(tmp_path / f"{reason_code}.db")
    store.create_run(_queued_run(budget=_budget(max_steps=3, max_tool_calls=1)))
    plan = _plan(RuntimeToolCall("step-search-001", "search_memos", DIGEST_B))

    result = asyncio.run(_runtime(store, StaticAuthority(), executor).run("run-001", plan))

    assert result.run.status is RunStatus.FAILED
    assert result.run.terminal_reason == reason_code


def test_missing_run_and_malformed_duration_fail_before_execution(tmp_path: Path) -> None:
    database = tmp_path / "agent-runs.db"
    store = SQLiteAgentRunStore(database)
    executor = CrashOnceToolExecutor()
    plan = _plan(RuntimeToolCall("step-search-001", "search_memos", DIGEST_B))
    runtime = _runtime(store, StaticAuthority(), executor)
    with pytest.raises(AgentRunRuntimeError, match="does not exist"):
        asyncio.run(runtime.run("run-001", plan))

    store.create_run(_queued_run(budget=_budget(max_steps=3, max_tool_calls=2)))
    try:
        asyncio.run(runtime.run("run-001", plan))
    except SimulatedProcessExit:
        pass
    with sqlite3.connect(database) as connection:
        connection.execute(
            """
            INSERT INTO agent_run_events (
                event_id, run_id, seq, event_type, safe_details, occurred_at,
                step_id, prev_digest, event_digest, schema_version
            ) VALUES (?, ?, ?, ?, ?, ?, ?, NULL, NULL, ?)
            """,
            (
                "event-corrupt-004",
                "run-001",
                4,
                "checkpoint_committed",
                '{"duration_ms":"duration-001","status":"running"}',
                "2026-08-12T00:00:00.040000Z",
                "step-search-001",
                "agent-run-contract-v1",
            ),
        )
        connection.execute(
            "UPDATE agent_run_state SET last_event_seq = 4 WHERE run_id = ?",
            ("run-001",),
        )
        connection.commit()

    with pytest.raises(AgentRunRuntimeError, match="bounded integer"):
        asyncio.run(
            _runtime(
                SQLiteAgentRunStore(database), StaticAuthority(), executor
            ).run("run-001", plan)
        )
    assert len(executor.invocations) == 1
