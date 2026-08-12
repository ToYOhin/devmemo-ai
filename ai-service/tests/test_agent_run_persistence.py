from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sqlite3

import pytest

from app.adapters.agent_run_store import (
    MAX_TIMELINE_EVENTS,
    AgentRunPersistenceError,
    SQLiteAgentRunStore,
)
from app.domain.agent_run import (
    MAX_ACTIVE_SECONDS,
    MAX_ARTIFACT_BYTES,
    MAX_ARTIFACTS,
    MAX_STEPS,
    MAX_TOOL_ATTEMPT_SECONDS,
    MAX_TOOL_CALLS,
    MAX_TOOL_RETRIES,
    AgentRun,
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


NOW = datetime(2026, 8, 12, 1, 2, 3, tzinfo=timezone.utc)
DIGEST_A = "a" * 64
DIGEST_B = "b" * 64
SNAPSHOT = (SourceRevision("memo-001", "revision-001"),)


def _budget() -> ExecutionBudget:
    return ExecutionBudget(
        max_steps=MAX_STEPS,
        max_tool_calls=MAX_TOOL_CALLS,
        max_tool_retries=MAX_TOOL_RETRIES,
        max_active_seconds=MAX_ACTIVE_SECONDS,
        max_tool_attempt_seconds=MAX_TOOL_ATTEMPT_SECONDS,
        max_artifacts=MAX_ARTIFACTS,
        max_artifact_bytes=MAX_ARTIFACT_BYTES,
    )


def _queued_run(**overrides: object) -> AgentRun:
    values: dict[str, object] = {
        "run_id": "run-001",
        "subject_id": "subject-001",
        "scope_ref": "scope-001",
        "request_key": "request-001",
        "request_digest": DIGEST_A,
        "status": RunStatus.QUEUED,
        "budget": _budget(),
        "source_snapshot": SNAPSHOT,
        "created_at": NOW,
        "updated_at": NOW,
        "last_event_seq": 0,
    }
    values.update(overrides)
    return AgentRun(**values)  # type: ignore[arg-type]


def _step(
    *,
    step_id: str = "step-001",
    ordinal: int = 1,
    kind: StepKind = StepKind.PLAN,
    status: StepStatus = StepStatus.RUNNING,
    checkpoint_ref: str = "checkpoint-001",
    input_digest: str = DIGEST_A,
) -> AgentStep:
    return AgentStep(
        step_id=step_id,
        run_id="run-001",
        ordinal=ordinal,
        kind=kind,
        status=status,
        attempt=0,
        input_digest=input_digest,
        checkpoint_ref=checkpoint_ref,
        tool_name="search_memos" if kind is StepKind.TOOL else None,
    )


def _event(
    seq: int,
    *,
    event_id: str | None = None,
    step_id: str = "step-001",
    occurred_at: datetime | None = None,
    event_type: str = "checkpoint_committed",
) -> RunEvent:
    return RunEvent(
        event_id=event_id or f"event-{seq:03d}",
        run_id="run-001",
        seq=seq,
        event_type=event_type,
        safe_details={"status": "running", "count": seq},
        occurred_at=occurred_at or NOW + timedelta(seconds=seq),
        step_id=step_id,
    )


def _checkpointed_run(
    current: AgentRun,
    seq: int,
    *,
    status: RunStatus = RunStatus.RUNNING,
    checkpoint_ref: str | None = None,
    terminal_reason: str | None = None,
) -> AgentRun:
    return replace(
        current,
        status=status,
        updated_at=NOW + timedelta(seconds=seq),
        last_event_seq=seq,
        checkpoint_ref=checkpoint_ref or f"checkpoint-{seq:03d}",
        terminal_reason=terminal_reason,
    )


def _pending_approval() -> ApprovalRequest:
    return ApprovalRequest(
        approval_id="approval-001",
        run_id="run-001",
        step_id="step-002",
        subject_id="subject-001",
        action_type="future_action_v1",
        action_digest=DIGEST_B,
        source_snapshot=SNAPSHOT,
        requested_at=NOW + timedelta(seconds=2),
        expires_at=NOW + timedelta(minutes=5),
        status=ApprovalStatus.PENDING,
    )


def _decision(
    pending: ApprovalRequest,
    *,
    decision_id: str = "decision-001",
    status: ApprovalStatus = ApprovalStatus.APPROVED,
) -> ApprovalRequest:
    return replace(
        pending,
        status=status,
        decision_id=decision_id,
        decided_by="subject-001",
        decided_at=NOW + timedelta(seconds=3),
    )


def _artifact() -> Artifact:
    return Artifact(
        artifact_id="artifact-001",
        run_id="run-001",
        step_id="step-003",
        kind="report",
        media_type="application/json",
        storage_ref="derived-object-001",
        digest=DIGEST_B,
        size_bytes=512,
        evidence_refs=SNAPSHOT,
        created_at=NOW + timedelta(seconds=2),
        expires_at=NOW + timedelta(days=1),
        status=ArtifactStatus.AVAILABLE,
    )


def test_create_is_exactly_idempotent_and_reopens_queued_run(tmp_path: Path) -> None:
    database = tmp_path / "agent-runs.db"
    store = SQLiteAgentRunStore(database)
    original = _queued_run()

    assert store.create_run(original) == original
    replay = _queued_run(
        run_id="run-replayed-001",
        created_at=NOW + timedelta(seconds=1),
        updated_at=NOW + timedelta(seconds=1),
    )
    assert store.create_run(replay) == original
    assert SQLiteAgentRunStore(database).get_run("run-001") == original

    with pytest.raises(AgentRunPersistenceError, match="binding conflicts"):
        store.create_run(_queued_run(run_id="run-conflict-001", request_digest=DIGEST_B))
    with pytest.raises(AgentRunPersistenceError, match="payload conflicts"):
        store.create_run(_queued_run(run_id="run-conflict-002", scope_ref="scope-002"))


def test_checkpoint_atomically_persists_run_step_event_and_artifact(tmp_path: Path) -> None:
    database = tmp_path / "agent-runs.db"
    store = SQLiteAgentRunStore(database)
    queued = store.create_run(_queued_run())
    running = _checkpointed_run(queued, 1)
    step = _step(checkpoint_ref="checkpoint-001")

    first = store.commit_checkpoint(run=running, step=step, event=_event(1))
    assert first.run == running
    assert first.steps == (step,)
    assert first.events[0].safe_details == {"status": "running", "count": 1}
    assert SQLiteAgentRunStore(database).load_snapshot("run-001") == first

    finalize_step = _step(
        step_id="step-003",
        ordinal=3,
        kind=StepKind.FINALIZE,
        status=StepStatus.SUCCEEDED,
        checkpoint_ref="checkpoint-002",
        input_digest=DIGEST_B,
    )
    succeeded = _checkpointed_run(
        running,
        2,
        status=RunStatus.SUCCEEDED,
        checkpoint_ref="checkpoint-002",
        terminal_reason="completed",
    )
    final_event = _event(
        2,
        step_id="step-003",
        occurred_at=NOW + timedelta(seconds=2),
    )
    final = store.commit_checkpoint(
        run=succeeded,
        step=finalize_step,
        event=final_event,
        artifact=_artifact(),
    )

    reopened = SQLiteAgentRunStore(database).load_snapshot("run-001")
    assert reopened == final
    assert reopened is not None
    assert reopened.run.status is RunStatus.SUCCEEDED
    assert reopened.artifacts == (_artifact(),)
    assert reopened.artifacts[0].storage_ref == "derived-object-001"

    with pytest.raises(AgentRunPersistenceError, match="terminal AgentRun"):
        store.commit_checkpoint(
            run=replace(succeeded, updated_at=NOW + timedelta(seconds=3), last_event_seq=3),
            step=finalize_step,
            event=_event(3, step_id="step-003"),
        )


def test_waiting_approval_survives_restart_and_first_valid_decision_wins(
    tmp_path: Path,
) -> None:
    database = tmp_path / "agent-runs.db"
    store = SQLiteAgentRunStore(database)
    queued = store.create_run(_queued_run())
    running = _checkpointed_run(queued, 1)
    store.commit_checkpoint(
        run=running,
        step=_step(checkpoint_ref="checkpoint-001"),
        event=_event(1),
    )
    waiting = _checkpointed_run(
        running,
        2,
        status=RunStatus.WAITING_APPROVAL,
        checkpoint_ref="checkpoint-002",
    )
    approval_step = _step(
        step_id="step-002",
        ordinal=2,
        kind=StepKind.APPROVAL,
        checkpoint_ref="checkpoint-002",
        input_digest=DIGEST_B,
    )
    pending = _pending_approval()
    store.commit_checkpoint(
        run=waiting,
        step=approval_step,
        event=_event(2, step_id="step-002"),
        approval=pending,
    )

    reopened = SQLiteAgentRunStore(database)
    snapshot = reopened.load_snapshot("run-001")
    assert snapshot is not None
    assert snapshot.run.status is RunStatus.WAITING_APPROVAL
    assert snapshot.approvals == (pending,)

    approved = _decision(pending)
    with pytest.raises(AgentRunPersistenceError, match="not currently valid"):
        reopened.consume_approval_decision(
            approved,
            current_subject_id="subject-001",
            current_action_digest=DIGEST_B,
            current_source_snapshot=(SourceRevision("memo-001", "revision-002"),),
            visibility_current=True,
        )
    with pytest.raises(AgentRunPersistenceError, match="not currently valid"):
        reopened.consume_approval_decision(
            approved,
            current_subject_id="subject-001",
            current_action_digest=DIGEST_A,
            current_source_snapshot=SNAPSHOT,
            visibility_current=True,
        )
    with pytest.raises(AgentRunPersistenceError, match="not currently valid"):
        reopened.consume_approval_decision(
            approved,
            current_subject_id="subject-001",
            current_action_digest=DIGEST_B,
            current_source_snapshot=SNAPSHOT,
            visibility_current=False,
        )
    assert reopened.consume_approval_decision(
        approved,
        current_subject_id="subject-001",
        current_action_digest=DIGEST_B,
        current_source_snapshot=SNAPSHOT,
        visibility_current=True,
    ) == approved
    assert reopened.consume_approval_decision(
        approved,
        current_subject_id="subject-001",
        current_action_digest=DIGEST_B,
        current_source_snapshot=SNAPSHOT,
        visibility_current=True,
    ) == approved

    with pytest.raises(AgentRunPersistenceError, match="conflicts"):
        reopened.consume_approval_decision(
            _decision(pending, decision_id="decision-002", status=ApprovalStatus.REJECTED),
            current_subject_id="subject-001",
            current_action_digest=DIGEST_B,
            current_source_snapshot=SNAPSHOT,
            visibility_current=True,
        )


def test_failed_checkpoint_rolls_back_every_partial_write(tmp_path: Path) -> None:
    database = tmp_path / "agent-runs.db"
    store = SQLiteAgentRunStore(database)
    queued = store.create_run(_queued_run())
    running = _checkpointed_run(queued, 1)
    first_step = _step(checkpoint_ref="checkpoint-001")
    store.commit_checkpoint(run=running, step=first_step, event=_event(1))

    next_run = _checkpointed_run(running, 2, checkpoint_ref="checkpoint-002")
    next_step = replace(
        first_step,
        status=StepStatus.SUCCEEDED,
        checkpoint_ref="checkpoint-002",
        outcome_code="completed",
    )
    duplicate_event_id = _event(
        2,
        event_id="event-001",
        occurred_at=NOW + timedelta(seconds=2),
    )
    with pytest.raises(AgentRunPersistenceError, match="checkpoint conflicts"):
        store.commit_checkpoint(run=next_run, step=next_step, event=duplicate_event_id)

    recovered = store.load_snapshot("run-001")
    assert recovered is not None
    assert recovered.run == running
    assert recovered.steps == (first_step,)
    assert [event.seq for event in recovered.events] == [1]


def test_checkpoint_enforces_the_run_specific_step_and_artifact_budgets(
    tmp_path: Path,
) -> None:
    store = SQLiteAgentRunStore(tmp_path / "agent-runs.db")
    budget = replace(_budget(), max_steps=2, max_artifact_bytes=256)
    queued = store.create_run(_queued_run(budget=budget))
    running = _checkpointed_run(queued, 1)
    store.commit_checkpoint(
        run=running,
        step=_step(checkpoint_ref="checkpoint-001"),
        event=_event(1),
    )
    oversized = replace(_artifact(), size_bytes=512)
    next_run = _checkpointed_run(running, 2, checkpoint_ref="checkpoint-002")
    final_step = _step(
        step_id="step-003",
        ordinal=2,
        kind=StepKind.FINALIZE,
        status=StepStatus.SUCCEEDED,
        checkpoint_ref="checkpoint-002",
        input_digest=DIGEST_B,
    )
    with pytest.raises(AgentRunPersistenceError, match="Artifact exceeds"):
        store.commit_checkpoint(
            run=next_run,
            step=final_step,
            event=_event(2, step_id="step-003"),
            artifact=oversized,
        )

    over_budget_step = replace(final_step, ordinal=3)
    with pytest.raises(AgentRunPersistenceError, match="AgentStep exceeds"):
        store.commit_checkpoint(
            run=next_run,
            step=over_budget_step,
            event=_event(2, step_id="step-003"),
        )


def test_event_sequence_is_monotonic_and_rows_are_database_append_only(
    tmp_path: Path,
) -> None:
    database = tmp_path / "agent-runs.db"
    store = SQLiteAgentRunStore(database)
    queued = store.create_run(_queued_run())
    running = _checkpointed_run(queued, 1)
    step = _step(checkpoint_ref="checkpoint-001")
    store.commit_checkpoint(run=running, step=step, event=_event(1))

    with pytest.raises(AgentRunPersistenceError, match="not monotonic"):
        store.commit_checkpoint(
            run=replace(running, updated_at=NOW + timedelta(seconds=2)),
            step=step,
            event=_event(1, event_id="event-002"),
        )

    with sqlite3.connect(database) as connection:
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            connection.execute(
                "UPDATE agent_run_events SET event_type = 'changed' WHERE event_id = 'event-001'"
            )
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            connection.execute("DELETE FROM agent_run_events WHERE event_id = 'event-001'")


def test_corrupt_rows_and_unbounded_queries_fail_closed(tmp_path: Path) -> None:
    database = tmp_path / "agent-runs.db"
    store = SQLiteAgentRunStore(database)
    store.create_run(_queued_run())

    for invalid in (True, 0, MAX_TIMELINE_EVENTS + 1):
        with pytest.raises(AgentRunPersistenceError, match="event_limit"):
            store.load_snapshot("run-001", event_limit=invalid)

    with sqlite3.connect(database) as connection:
        connection.execute(
            "UPDATE agent_run_state SET source_snapshot = '{}' WHERE run_id = 'run-001'"
        )
        connection.commit()
    with pytest.raises(AgentRunPersistenceError, match="source snapshot"):
        SQLiteAgentRunStore(database).get_run("run-001")


def test_schema_and_values_exclude_provider_prompt_memo_body_and_secrets(
    tmp_path: Path,
) -> None:
    database = tmp_path / "agent-runs.db"
    store = SQLiteAgentRunStore(database)
    queued = store.create_run(_queued_run())
    running = _checkpointed_run(queued, 1)
    store.commit_checkpoint(
        run=running,
        step=_step(checkpoint_ref="checkpoint-001"),
        event=_event(1),
    )

    with sqlite3.connect(database) as connection:
        schema = " ".join(
            str(row[0])
            for row in connection.execute(
                "SELECT sql FROM sqlite_master WHERE type IN ('table', 'index', 'trigger') LIMIT 64"
            ).fetchall()
        ).lower()
        stored = " ".join(
            str(row)
            for row in connection.execute(
                "SELECT safe_details FROM agent_run_events WHERE run_id = ? LIMIT ?",
                ("run-001", MAX_TIMELINE_EVENTS),
            ).fetchall()
        ).lower()
    for forbidden in ("provider_prompt", "memo_content", "raw_secret", "hidden_reasoning"):
        assert forbidden not in schema
        assert forbidden not in stored


def test_missing_and_invalid_run_operations_fail_closed(tmp_path: Path) -> None:
    store = SQLiteAgentRunStore(tmp_path / "agent-runs.db")
    queued = _queued_run()
    invalid_new = _checkpointed_run(queued, 1)

    with pytest.raises(AgentRunPersistenceError, match="uncheckpointed queued"):
        store.create_run(invalid_new)
    assert store.get_run("run-missing-001") is None
    assert store.load_snapshot("run-missing-001") is None

    missing_run = replace(invalid_new, run_id="run-missing-001")
    missing_step = replace(_step(), run_id="run-missing-001")
    missing_event = replace(_event(1), run_id="run-missing-001")
    with pytest.raises(AgentRunPersistenceError, match="does not exist"):
        store.commit_checkpoint(
            run=missing_run,
            step=missing_step,
            event=missing_event,
        )

    store.create_run(queued)
    with pytest.raises(AgentRunPersistenceError, match="creation conflicts"):
        store.create_run(
            _queued_run(
                subject_id="subject-002",
                request_key="request-002",
                request_digest=DIGEST_B,
            )
        )


def test_checkpoint_rejects_invalid_state_and_cross_object_bindings(
    tmp_path: Path,
) -> None:
    store = SQLiteAgentRunStore(tmp_path / "agent-runs.db")
    queued = store.create_run(_queued_run())
    running = _checkpointed_run(queued, 1)
    step = _step(checkpoint_ref="checkpoint-001")
    event = _event(1)

    invalid_cases = (
        (replace(running, scope_ref="scope-002"), step, event, None, None, "immutable fields"),
        (
            replace(
                running,
                status=RunStatus.SUCCEEDED,
                terminal_reason="completed",
            ),
            step,
            event,
            None,
            None,
            "transition is invalid",
        ),
        (running, step, replace(event, run_id="run-other-001"), None, None, "event does not match"),
        (
            running,
            step,
            replace(event, occurred_at=NOW - timedelta(seconds=1)),
            None,
            None,
            "event time",
        ),
        (replace(running, checkpoint_ref=None), step, event, None, None, "checkpoint references"),
        (running, replace(step, run_id="run-other-001"), event, None, None, "step belongs"),
        (running, step, replace(event, step_id="step-other-001"), None, None, "another step"),
        (running, step, event, _pending_approval(), None, "approval binding"),
        (running, step, event, None, _artifact(), "artifact binding"),
    )
    for proposed, proposed_step, proposed_event, approval, artifact, message in invalid_cases:
        with pytest.raises(AgentRunPersistenceError, match=message):
            store.commit_checkpoint(
                run=proposed,
                step=proposed_step,
                event=proposed_event,
                approval=approval,
                artifact=artifact,
            )


def test_tool_delivery_events_atomically_enforce_actual_call_budget(
    tmp_path: Path,
) -> None:
    store = SQLiteAgentRunStore(tmp_path / "agent-runs.db")
    budget = replace(_budget(), max_tool_calls=1)
    queued = store.create_run(_queued_run(budget=budget))
    running = _checkpointed_run(queued, 1)
    tool_step = _step(kind=StepKind.TOOL)
    store.commit_checkpoint(
        run=running,
        step=tool_step,
        event=_event(1, event_type="tool_started"),
    )

    resumed = _checkpointed_run(running, 2, checkpoint_ref="checkpoint-002")
    resumed_step = replace(tool_step, checkpoint_ref="checkpoint-002")
    with pytest.raises(AgentRunPersistenceError, match="delivery budget"):
        store.commit_checkpoint(
            run=resumed,
            step=resumed_step,
            event=_event(2, event_type="tool_resumed"),
        )

    snapshot = store.load_snapshot(queued.run_id)
    assert snapshot is not None
    assert snapshot.run.last_event_seq == 1
    assert [event.event_type for event in snapshot.events] == ["tool_started"]


def test_tool_checkpoint_and_approval_delivery_guards_are_persisted(
    tmp_path: Path,
) -> None:
    store = SQLiteAgentRunStore(tmp_path / "agent-runs.db")
    queued = store.create_run(_queued_run())
    running = _checkpointed_run(queued, 1)
    tool_step = _step(
        kind=StepKind.TOOL,
        status=StepStatus.SUCCEEDED,
        checkpoint_ref="checkpoint-001",
    )
    store.commit_checkpoint(run=running, step=tool_step, event=_event(1))

    waiting = _checkpointed_run(
        running,
        2,
        status=RunStatus.WAITING_APPROVAL,
        checkpoint_ref="checkpoint-002",
    )
    approval_step = _step(
        step_id="step-002",
        ordinal=2,
        kind=StepKind.APPROVAL,
        checkpoint_ref="checkpoint-002",
        input_digest=DIGEST_B,
    )
    pending = _pending_approval()
    store.commit_checkpoint(
        run=waiting,
        step=approval_step,
        event=_event(2, step_id="step-002"),
        approval=pending,
    )
    approved = _decision(pending)

    with pytest.raises(AgentRunPersistenceError, match="must be approved or rejected"):
        store.consume_approval_decision(
            pending,
            current_subject_id="subject-001",
            current_action_digest=DIGEST_B,
            current_source_snapshot=SNAPSHOT,
            visibility_current=True,
        )
    with pytest.raises(AgentRunPersistenceError, match="does not exist"):
        store.consume_approval_decision(
            replace(approved, approval_id="approval-missing-001"),
            current_subject_id="subject-001",
            current_action_digest=DIGEST_B,
            current_source_snapshot=SNAPSHOT,
            visibility_current=True,
        )
    with pytest.raises(AgentRunPersistenceError, match="binding conflicts"):
        store.consume_approval_decision(
            replace(approved, action_digest=DIGEST_A),
            current_subject_id="subject-001",
            current_action_digest=DIGEST_A,
            current_source_snapshot=SNAPSHOT,
            visibility_current=True,
        )
    with pytest.raises(AgentRunPersistenceError, match="actor does not match"):
        store.consume_approval_decision(
            replace(approved, decided_by="subject-002"),
            current_subject_id="subject-001",
            current_action_digest=DIGEST_B,
            current_source_snapshot=SNAPSHOT,
            visibility_current=True,
        )
