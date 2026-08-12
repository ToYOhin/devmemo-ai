from dataclasses import FrozenInstanceError
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path

import pytest

from app.domain.agent_run import (
    AGENT_RUN_CONTRACT_VERSION,
    ALLOWED_TOOLS,
    LEGAL_RUN_TRANSITIONS,
    MAX_ACTIVE_SECONDS,
    MAX_ARTIFACT_BYTES,
    MAX_ARTIFACTS,
    MAX_STEPS,
    MAX_TOOL_ATTEMPT_SECONDS,
    MAX_TOOL_CALLS,
    MAX_TOOL_RETRIES,
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
    validate_run_transition,
)


NOW = datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)
DIGEST_A = "a" * 64
DIGEST_B = "b" * 64
SNAPSHOT = (SourceRevision("memo-001", "rev-001"),)
CONTRACTS_DIR = Path(__file__).resolve().parents[2] / "contracts"


def _load_fixture(name: str) -> dict[str, object]:
    return json.loads((CONTRACTS_DIR / name).read_text(encoding="utf-8"))


def _source_snapshot(payload: object) -> tuple[SourceRevision, ...]:
    assert isinstance(payload, list)
    return tuple(
        SourceRevision(source_id=item["source_id"], revision=item["revision"])
        for item in payload
        if isinstance(item, dict)
    )


def _parse_utc(value: object) -> datetime:
    assert isinstance(value, str)
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _budget(**overrides: int) -> ExecutionBudget:
    values = {
        "max_steps": MAX_STEPS,
        "max_tool_calls": MAX_TOOL_CALLS,
        "max_tool_retries": MAX_TOOL_RETRIES,
        "max_active_seconds": MAX_ACTIVE_SECONDS,
        "max_tool_attempt_seconds": MAX_TOOL_ATTEMPT_SECONDS,
        "max_artifacts": MAX_ARTIFACTS,
        "max_artifact_bytes": MAX_ARTIFACT_BYTES,
    }
    values.update(overrides)
    return ExecutionBudget(**values)


def _run(**overrides: object) -> AgentRun:
    values: dict[str, object] = {
        "run_id": "run-001",
        "subject_id": "subject-001",
        "scope_ref": "scope-001",
        "request_key": "request-001",
        "request_digest": DIGEST_A,
        "status": RunStatus.RUNNING,
        "budget": _budget(),
        "source_snapshot": SNAPSHOT,
        "created_at": NOW,
        "updated_at": NOW,
        "last_event_seq": 1,
        "checkpoint_ref": "checkpoint-001",
    }
    values.update(overrides)
    return AgentRun(**values)  # type: ignore[arg-type]


def _approval(**overrides: object) -> ApprovalRequest:
    values: dict[str, object] = {
        "approval_id": "approval-001",
        "run_id": "run-001",
        "step_id": "step-001",
        "subject_id": "subject-001",
        "action_type": "future_action_v1",
        "action_digest": DIGEST_A,
        "source_snapshot": SNAPSHOT,
        "requested_at": NOW,
        "expires_at": NOW + timedelta(minutes=5),
        "status": ApprovalStatus.PENDING,
    }
    values.update(overrides)
    return ApprovalRequest(**values)  # type: ignore[arg-type]


def _artifact(**overrides: object) -> Artifact:
    values: dict[str, object] = {
        "artifact_id": "artifact-001",
        "run_id": "run-001",
        "step_id": "step-001",
        "kind": "report",
        "media_type": "application/json",
        "storage_ref": "object-001",
        "digest": DIGEST_A,
        "size_bytes": MAX_ARTIFACT_BYTES,
        "evidence_refs": SNAPSHOT,
        "created_at": NOW,
        "expires_at": NOW + timedelta(days=1),
        "status": ArtifactStatus.AVAILABLE,
    }
    values.update(overrides)
    return Artifact(**values)  # type: ignore[arg-type]


def test_contract_models_are_frozen_and_provider_neutral() -> None:
    run = _run()

    with pytest.raises(FrozenInstanceError):
        run.status = RunStatus.SUCCEEDED  # type: ignore[misc]

    assert run.contract_version == AGENT_RUN_CONTRACT_VERSION
    assert ALLOWED_TOOLS == {
        "search_memos",
        "get_memo_evidence",
        "create_report_artifact",
    }


def test_source_bindings_are_copied_to_owned_tuples() -> None:
    source_revisions = [SourceRevision("memo-001", "rev-001")]
    run = _run(source_snapshot=source_revisions)
    approval = _approval(source_snapshot=source_revisions)
    artifact = _artifact(evidence_refs=source_revisions)

    source_revisions.append(SourceRevision("memo-002", "rev-001"))

    assert run.source_snapshot == SNAPSHOT
    assert approval.source_snapshot == SNAPSHOT
    assert artifact.evidence_refs == SNAPSHOT
    assert isinstance(run.source_snapshot, tuple)
    assert isinstance(approval.source_snapshot, tuple)
    assert isinstance(artifact.evidence_refs, tuple)


@pytest.mark.parametrize(
    "field",
    ["last_event_seq", "ordinal", "attempt", "seq", "size_bytes"],
)
@pytest.mark.parametrize("invalid", [True, False, 1.0])
def test_bounded_integer_fields_reject_bool_and_non_integer(
    field: str, invalid: object
) -> None:
    with pytest.raises(AgentRunContractError, match=field):
        if field == "last_event_seq":
            _run(last_event_seq=invalid)
        elif field == "ordinal":
            AgentStep(
                step_id="step-001",
                run_id="run-001",
                ordinal=invalid,  # type: ignore[arg-type]
                kind=StepKind.TOOL,
                status=StepStatus.QUEUED,
                attempt=0,
                input_digest=DIGEST_A,
                tool_name="search_memos",
            )
        elif field == "attempt":
            AgentStep(
                step_id="step-001",
                run_id="run-001",
                ordinal=1,
                kind=StepKind.TOOL,
                status=StepStatus.QUEUED,
                attempt=invalid,  # type: ignore[arg-type]
                input_digest=DIGEST_A,
                tool_name="search_memos",
            )
        elif field == "seq":
            RunEvent(
                event_id="event-001",
                run_id="run-001",
                seq=invalid,  # type: ignore[arg-type]
                event_type="run_started",
                safe_details={},
                occurred_at=NOW,
            )
        else:
            _artifact(size_bytes=invalid)


def test_state_machine_allows_exactly_the_documented_transitions() -> None:
    expected = {
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
    assert LEGAL_RUN_TRANSITIONS == expected
    for current in RunStatus:
        for target in RunStatus:
            if (current, target) in expected:
                validate_run_transition(current, target)
            else:
                with pytest.raises(AgentRunContractError, match="not permitted"):
                    validate_run_transition(current, target)


@pytest.mark.parametrize(
    ("field", "invalid"),
    [
        ("max_steps", 0),
        ("max_steps", MAX_STEPS + 1),
        ("max_tool_calls", 0),
        ("max_tool_calls", MAX_TOOL_CALLS + 1),
        ("max_tool_retries", -1),
        ("max_tool_retries", 0),
        ("max_tool_retries", MAX_TOOL_RETRIES + 1),
        ("max_active_seconds", 0),
        ("max_active_seconds", MAX_ACTIVE_SECONDS + 1),
        ("max_tool_attempt_seconds", 0),
        ("max_tool_attempt_seconds", MAX_TOOL_ATTEMPT_SECONDS + 1),
        ("max_artifacts", 0),
        ("max_artifacts", MAX_ARTIFACTS + 1),
        ("max_artifact_bytes", 0),
        ("max_artifact_bytes", MAX_ARTIFACT_BYTES + 1),
    ],
)
def test_budget_rejects_zero_negative_and_ceiling_overruns(field: str, invalid: int) -> None:
    with pytest.raises(AgentRunContractError, match=field):
        _budget(**{field: invalid})


def test_budget_rejects_unbounded_or_non_integer_values() -> None:
    with pytest.raises(AgentRunContractError, match="finite integer"):
        _budget(max_steps=float("inf"))  # type: ignore[arg-type]
    with pytest.raises(AgentRunContractError, match="finite integer"):
        _budget(max_steps=True)  # type: ignore[arg-type]


@pytest.mark.parametrize("tool_name", sorted(ALLOWED_TOOLS))
def test_tool_steps_accept_only_the_fixed_read_and_artifact_allowlist(tool_name: str) -> None:
    step = AgentStep(
        step_id="step-001",
        run_id="run-001",
        ordinal=1,
        kind=StepKind.TOOL,
        status=StepStatus.QUEUED,
        attempt=0,
        input_digest=DIGEST_A,
        tool_name=tool_name,
    )
    assert step.tool_name == tool_name

    with pytest.raises(AgentRunContractError, match="allowlist"):
        AgentStep(
            step_id="step-002",
            run_id="run-001",
            ordinal=2,
            kind=StepKind.TOOL,
            status=StepStatus.QUEUED,
            attempt=0,
            input_digest=DIGEST_A,
            tool_name="write_memo",
        )


def test_step_retries_are_bounded_and_bound_to_safe_input_digest() -> None:
    retry = AgentStep(
        step_id="step-001",
        run_id="run-001",
        ordinal=1,
        kind=StepKind.TOOL,
        status=StepStatus.RUNNING,
        attempt=1,
        input_digest=DIGEST_A,
        checkpoint_ref="checkpoint-001",
        tool_name="search_memos",
    )
    assert retry.attempt == MAX_TOOL_RETRIES

    with pytest.raises(AgentRunContractError, match="attempt"):
        AgentStep(
            step_id="step-001",
            run_id="run-001",
            ordinal=1,
            kind=StepKind.TOOL,
            status=StepStatus.RUNNING,
            attempt=2,
            input_digest=DIGEST_A,
            tool_name="search_memos",
        )
    with pytest.raises(AgentRunContractError, match="sha256"):
        AgentStep(
            step_id="step-001",
            run_id="run-001",
            ordinal=1,
            kind=StepKind.TOOL,
            status=StepStatus.RUNNING,
            attempt=0,
            input_digest="raw-input",
            tool_name="search_memos",
        )


def test_idempotency_and_resume_bindings_fail_closed() -> None:
    run = _run()
    run.validate_duplicate_request(
        subject_id="subject-001",
        request_key="request-001",
        request_digest=DIGEST_A,
    )
    run.validate_resume("checkpoint-001", SNAPSHOT)

    with pytest.raises(AgentRunContractError, match="conflicts"):
        run.validate_duplicate_request(
            subject_id="subject-001",
            request_key="request-001",
            request_digest=DIGEST_B,
        )
    with pytest.raises(AgentRunContractError, match="checkpoint"):
        run.validate_resume("checkpoint-002", SNAPSHOT)
    with pytest.raises(AgentRunContractError, match="stale"):
        run.validate_resume("checkpoint-001", (SourceRevision("memo-001", "rev-002"),))


def test_terminal_runs_require_safe_reason_and_cannot_resume() -> None:
    terminal = _run(
        status=RunStatus.CANCELLED,
        terminal_reason="authorized_cancel",
    )
    with pytest.raises(AgentRunContractError, match="active or paused"):
        terminal.validate_resume("checkpoint-001", SNAPSHOT)
    with pytest.raises(AgentRunContractError, match="terminal_reason"):
        _run(status=RunStatus.FAILED)


def test_run_event_serializes_only_allowlisted_content_free_details() -> None:
    event = RunEvent(
        event_id="event-001",
        run_id="run-001",
        seq=1,
        event_type="tool_succeeded",
        step_id="step-001",
        safe_details={
            "tool_name": "get_memo_evidence",
            "evidence_ref": "memo-001",
            "revision": "rev-001",
            "count": 1,
            "duration_ms": 12,
        },
        occurred_at=NOW,
        prev_digest=DIGEST_A,
        event_digest=DIGEST_B,
    )
    assert event.to_dict() == {
        "event_id": "event-001",
        "run_id": "run-001",
        "seq": 1,
        "event_type": "tool_succeeded",
        "schema_version": AGENT_RUN_CONTRACT_VERSION,
        "step_id": "step-001",
        "safe_details": {
            "tool_name": "get_memo_evidence",
            "evidence_ref": "memo-001",
            "revision": "rev-001",
            "count": 1,
            "duration_ms": 12,
        },
        "occurred_at": "2026-01-02T03:04:05Z",
        "prev_digest": DIGEST_A,
        "event_digest": DIGEST_B,
    }

    with pytest.raises(TypeError):
        event.safe_details["prompt"] = "secret-value"  # type: ignore[index]
    assert "prompt" not in event.to_dict()["safe_details"]

    for forbidden in (
        "prompt",
        "memo_content",
        "secret",
        "embedding",
        "internal_capability",
        "payload",
    ):
        with pytest.raises(AgentRunContractError, match="non-allowlisted"):
            RunEvent(
                event_id="event-002",
                run_id="run-001",
                seq=2,
                event_type="tool_failed",
                safe_details={forbidden: "opaque-001"},
                occurred_at=NOW,
            )


def test_approval_requires_unexpired_current_authority_and_exact_bindings() -> None:
    approval = _approval()
    approval.validate_decision(
        decision_id="decision-001",
        subject_id="subject-001",
        action_digest=DIGEST_A,
        source_snapshot=SNAPSHOT,
        decided_at=NOW + timedelta(minutes=1),
        visibility_current=True,
    )

    with pytest.raises(AgentRunContractError, match="stale"):
        approval.validate_decision(
            decision_id="decision-003",
            subject_id="subject-001",
            action_digest=DIGEST_A,
            source_snapshot=(SourceRevision("memo-001", "rev-002"),),
            decided_at=NOW + timedelta(minutes=1),
            visibility_current=True,
        )
    with pytest.raises(AgentRunContractError, match="visibility"):
        approval.validate_decision(
            decision_id="decision-004",
            subject_id="subject-001",
            action_digest=DIGEST_A,
            source_snapshot=SNAPSHOT,
            decided_at=NOW + timedelta(minutes=1),
            visibility_current=False,
        )


@pytest.mark.parametrize(
    "decided_at",
    [
        NOW - timedelta(seconds=1),
        NOW,
        NOW + timedelta(minutes=5),
        NOW + timedelta(minutes=5, seconds=1),
    ],
)
def test_pending_approval_decision_requires_strict_window(
    decided_at: datetime,
) -> None:
    with pytest.raises(AgentRunContractError):
        _approval().validate_decision(
            decision_id="decision-001",
            subject_id="subject-001",
            action_digest=DIGEST_A,
            source_snapshot=SNAPSHOT,
            decided_at=decided_at,
            visibility_current=True,
        )


def test_duplicate_or_consumed_approval_is_rejected() -> None:
    consumed = _approval(
        status=ApprovalStatus.APPROVED,
        decision_id="decision-001",
        decided_by="subject-001",
        decided_at=NOW + timedelta(minutes=1),
    )
    with pytest.raises(AgentRunContractError, match="duplicate or already-consumed"):
        consumed.validate_decision(
            decision_id="decision-001",
            subject_id="subject-001",
            action_digest=DIGEST_A,
            source_snapshot=SNAPSHOT,
            decided_at=NOW + timedelta(minutes=2),
            visibility_current=True,
        )


@pytest.mark.parametrize(
    "status",
    [ApprovalStatus.APPROVED, ApprovalStatus.REJECTED],
)
@pytest.mark.parametrize(
    "decided_at",
    [
        NOW - timedelta(seconds=1),
        NOW,
        NOW + timedelta(minutes=5),
        NOW + timedelta(minutes=5, seconds=1),
    ],
)
def test_persisted_approval_decision_requires_valid_chronology(
    status: ApprovalStatus,
    decided_at: datetime,
) -> None:
    with pytest.raises(AgentRunContractError):
        _approval(
            status=status,
            decision_id="decision-001",
            decided_by="subject-001",
            decided_at=decided_at,
        )


def test_artifact_is_revision_bound_bounded_and_contains_no_body() -> None:
    artifact = _artifact()
    assert artifact.evidence_refs == SNAPSHOT
    assert not hasattr(artifact, "content")

    with pytest.raises(AgentRunContractError, match="size_bytes"):
        Artifact(
            artifact_id="artifact-002",
            run_id="run-001",
            step_id="step-001",
            kind="report",
            media_type="application/json",
            storage_ref="object-002",
            digest=DIGEST_A,
            size_bytes=MAX_ARTIFACT_BYTES + 1,
            evidence_refs=SNAPSHOT,
            created_at=NOW,
            expires_at=NOW + timedelta(days=1),
            status=ArtifactStatus.AVAILABLE,
        )


def test_contract_fixture_drives_the_executable_contract() -> None:
    fixture = _load_fixture("agent-run-contract-v1.json")
    assert fixture["version"] == AGENT_RUN_CONTRACT_VERSION
    assert fixture["models"] == [
        "AgentRun",
        "AgentStep",
        "RunEvent",
        "ApprovalRequest",
        "Artifact",
    ]
    assert fixture["run_states"] == [status.value for status in RunStatus]
    assert set(fixture["tools"]) == ALLOWED_TOOLS
    assert fixture["budget"] == _budget().to_dict()

    legal = {
        (RunStatus(current), RunStatus(target))
        for current, target in fixture["legal_transitions"]  # type: ignore[union-attr]
    }
    assert legal == LEGAL_RUN_TRANSITIONS
    for current, target in legal:
        validate_run_transition(current, target)
    for current, target in fixture["illegal_transitions"]:  # type: ignore[union-attr]
        with pytest.raises(AgentRunContractError, match="not permitted"):
            validate_run_transition(RunStatus(current), RunStatus(target))

    event_payload = fixture["safe_event_example"]
    assert isinstance(event_payload, dict)
    event = RunEvent(
        event_id=event_payload["event_id"],
        run_id=event_payload["run_id"],
        seq=event_payload["seq"],
        event_type=event_payload["event_type"],
        step_id=event_payload["step_id"],
        safe_details=event_payload["safe_details"],
        occurred_at=_parse_utc(event_payload["occurred_at"]),
    )
    assert event.to_dict() == event_payload


def test_acceptance_fixture_cases_execute_contract_validators() -> None:
    fixture = _load_fixture("agent-run-acceptance-v1.json")
    assert fixture["contract_version"] == AGENT_RUN_CONTRACT_VERSION
    cases = fixture["cases"]
    assert isinstance(cases, list)
    assert {case["name"] for case in cases} == {
        "readonly_multistep_success",
        "no_evidence_termination",
        "safe_refusal",
        "stale_revision",
        "visibility_change",
        "waiting_approval_resume",
        "duplicate_retry",
        "cancel",
        "restart_recovery",
    }

    for case in cases:
        assert isinstance(case, dict)
        snapshot = _source_snapshot(case["source_snapshot"])
        for current, target in case["transitions"]:
            validate_run_transition(RunStatus(current), RunStatus(target))

        tools = case["tools"]
        assert isinstance(tools, list)
        assert case["tool_call_count"] == len(tools)
        assert len(tools) <= _budget().max_tool_calls
        attempts = case.get("retry_attempts", [0] * len(tools))
        assert isinstance(attempts, list)
        for ordinal, (tool_name, attempt) in enumerate(zip(tools, attempts, strict=False), 1):
            AgentStep(
                step_id=f"step-fixture-{ordinal:03d}",
                run_id="run-fixture-001",
                ordinal=ordinal,
                kind=StepKind.TOOL,
                status=StepStatus.SUCCEEDED,
                attempt=attempt,
                input_digest=DIGEST_A,
                checkpoint_ref=f"checkpoint-fixture-{ordinal:03d}",
                tool_name=tool_name,
                outcome_code="fixture_validated",
            )

        events = case["events"]
        assert isinstance(events, list)
        assert [event["seq"] for event in events] == list(range(1, len(events) + 1))
        for event_payload in events:
            event = RunEvent(
                event_id=event_payload["event_id"],
                run_id="run-fixture-001",
                seq=event_payload["seq"],
                event_type=event_payload["event_type"],
                step_id=event_payload.get("step_id"),
                safe_details=event_payload["safe_details"],
                occurred_at=NOW,
            )
            assert event.to_dict()["safe_details"] == event_payload["safe_details"]

        terminal = AgentRun(
            run_id="run-fixture-001",
            subject_id="subject-fixture-001",
            scope_ref="scope-fixture-001",
            request_key="request-fixture-001",
            request_digest=DIGEST_A,
            status=RunStatus(case["terminal_state"]),
            budget=_budget(),
            source_snapshot=snapshot,
            created_at=NOW,
            updated_at=NOW,
            last_event_seq=len(events),
            checkpoint_ref=case.get("checkpoint_ref"),
            terminal_reason=case["terminal_reason"],
        )
        assert terminal.status.value == case["terminal_state"]

        artifact_outcome = case["artifact_outcome"]
        if artifact_outcome != "none":
            artifact = Artifact(
                artifact_id="artifact-fixture-001",
                run_id="run-fixture-001",
                step_id="step-fixture-001",
                kind="report",
                media_type="application/json",
                storage_ref="object-fixture-001",
                digest=DIGEST_A,
                size_bytes=1024,
                evidence_refs=snapshot,
                created_at=NOW,
                expires_at=NOW + timedelta(days=1),
                status=ArtifactStatus(artifact_outcome),
            )
            assert artifact.status.value == artifact_outcome

        if case["name"] == "stale_revision":
            active = _run(source_snapshot=snapshot)
            with pytest.raises(AgentRunContractError, match="stale"):
                active.validate_resume(
                    "checkpoint-001", _source_snapshot(case["current_snapshot"])
                )
        elif case["name"] == "visibility_change":
            approval = _approval(source_snapshot=snapshot)
            with pytest.raises(AgentRunContractError, match="visibility"):
                approval.validate_decision(
                    decision_id="decision-fixture-001",
                    subject_id="subject-001",
                    action_digest=DIGEST_A,
                    source_snapshot=snapshot,
                    decided_at=NOW + timedelta(minutes=1),
                    visibility_current=case["visibility_current"],
                )
        elif case["name"] == "waiting_approval_resume":
            approval_payload = case["approval"]
            assert isinstance(approval_payload, dict)
            approval = ApprovalRequest(
                approval_id=approval_payload["approval_id"],
                run_id="run-fixture-001",
                step_id=approval_payload["step_id"],
                subject_id=approval_payload["subject_id"],
                action_type=approval_payload["action_type"],
                action_digest=approval_payload["action_digest"],
                source_snapshot=snapshot,
                requested_at=_parse_utc(approval_payload["requested_at"]),
                expires_at=_parse_utc(approval_payload["expires_at"]),
                status=ApprovalStatus.PENDING,
            )
            approval.validate_decision(
                decision_id=approval_payload["decision_id"],
                subject_id=approval_payload["subject_id"],
                action_digest=approval_payload["action_digest"],
                source_snapshot=snapshot,
                decided_at=_parse_utc(approval_payload["decided_at"]),
                visibility_current=True,
            )
        elif case["name"] == "duplicate_retry":
            assert case["retry_attempts"] == [0, MAX_TOOL_RETRIES]
            active = _run(source_snapshot=snapshot)
            active.validate_duplicate_request(
                subject_id="subject-001",
                request_key="request-001",
                request_digest=DIGEST_A,
            )
        elif case["name"] == "cancel":
            assert events[-1]["event_type"] == "run_cancelled"
            assert not any(
                event["event_type"] == "artifact_created" for event in events
            )
        elif case["name"] == "restart_recovery":
            active = _run(
                source_snapshot=snapshot,
                checkpoint_ref=case["checkpoint_ref"],
            )
            active.validate_resume(case["checkpoint_ref"], snapshot)
            assert sum(
                event["event_type"] == "artifact_created" for event in events
            ) == 1
