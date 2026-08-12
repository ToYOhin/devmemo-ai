"""Dormant single-host SQLite persistence for derived R7 AgentRun state."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
import json
from pathlib import Path
import sqlite3
from typing import Iterator, Mapping

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
    validate_run_transition,
)


MAX_TIMELINE_EVENTS = 128
_TERMINAL_RUN_STATUSES = {RunStatus.SUCCEEDED, RunStatus.FAILED, RunStatus.CANCELLED}
_TERMINAL_STEP_STATUSES = {StepStatus.SUCCEEDED, StepStatus.FAILED, StepStatus.CANCELLED}


class AgentRunPersistenceError(RuntimeError):
    """Raised when stored AgentRun state is missing, conflicting, or corrupt."""


@dataclass(frozen=True)
class AgentRunSnapshot:
    """One bounded recovery view of the last committed AgentRun checkpoint."""

    run: AgentRun
    steps: tuple[AgentStep, ...]
    events: tuple[RunEvent, ...]
    approvals: tuple[ApprovalRequest, ...]
    artifacts: tuple[Artifact, ...]


class SQLiteAgentRunStore:
    """Persist content-free, rebuildable AgentRun state without runtime wiring."""

    def __init__(self, database: str | Path) -> None:
        self.database = Path(database)

    def create_run(self, run: AgentRun) -> AgentRun:
        """Create one queued run, or return the exact idempotent replay."""

        if (
            run.status is not RunStatus.QUEUED
            or run.last_event_seq != 0
            or run.checkpoint_ref is not None
        ):
            raise AgentRunPersistenceError("new AgentRun must be an uncheckpointed queued run")
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            existing_row = connection.execute(
                """
                SELECT * FROM agent_run_state
                WHERE subject_id = ? AND request_key = ?
                """,
                (run.subject_id, run.request_key),
            ).fetchone()
            if existing_row is not None:
                existing = _run_from_row(existing_row)
                self._validate_create_replay(existing, run)
                connection.commit()
                return existing
            try:
                connection.execute(
                    """
                    INSERT INTO agent_run_state (
                        run_id, subject_id, scope_ref, request_key, request_digest,
                        status, max_steps, max_tool_calls, max_tool_retries,
                        max_active_seconds, max_tool_attempt_seconds, max_artifacts,
                        max_artifact_bytes, source_snapshot, created_at, updated_at,
                        last_event_seq, checkpoint_ref, terminal_reason, contract_version
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    _run_values(run),
                )
                connection.commit()
            except sqlite3.IntegrityError as exc:
                raise AgentRunPersistenceError("AgentRun creation conflicts with stored state") from exc
        return run

    def get_run(self, run_id: str) -> AgentRun | None:
        """Return one validated run without loading its related collections."""

        with self._connection() as connection:
            row = connection.execute(
                "SELECT * FROM agent_run_state WHERE run_id = ?",
                (run_id,),
            ).fetchone()
        return None if row is None else _run_from_row(row)

    def load_snapshot(
        self, run_id: str, *, event_limit: int = MAX_TIMELINE_EVENTS
    ) -> AgentRunSnapshot | None:
        """Load a bounded, validated recovery snapshot from committed rows only."""

        if isinstance(event_limit, bool) or not isinstance(event_limit, int):
            raise AgentRunPersistenceError("event_limit must be an integer")
        if not 1 <= event_limit <= MAX_TIMELINE_EVENTS:
            raise AgentRunPersistenceError(
                f"event_limit must be between 1 and {MAX_TIMELINE_EVENTS}"
            )
        with self._connection() as connection:
            run_row = connection.execute(
                "SELECT * FROM agent_run_state WHERE run_id = ?",
                (run_id,),
            ).fetchone()
            if run_row is None:
                return None
            run = _run_from_row(run_row)
            step_rows = connection.execute(
                """
                SELECT * FROM agent_run_steps
                WHERE run_id = ? ORDER BY ordinal, step_id LIMIT 13
                """,
                (run_id,),
            ).fetchall()
            approval_rows = connection.execute(
                """
                SELECT * FROM agent_run_approvals
                WHERE run_id = ? ORDER BY requested_at, approval_id LIMIT 13
                """,
                (run_id,),
            ).fetchall()
            artifact_rows = connection.execute(
                """
                SELECT * FROM agent_run_artifacts
                WHERE run_id = ? ORDER BY created_at, artifact_id LIMIT 4
                """,
                (run_id,),
            ).fetchall()
            event_rows = connection.execute(
                """
                SELECT * FROM (
                    SELECT * FROM agent_run_events
                    WHERE run_id = ? ORDER BY seq DESC LIMIT ?
                ) ORDER BY seq
                """,
                (run_id, event_limit),
            ).fetchall()
        if len(step_rows) > run.budget.max_steps:
            raise AgentRunPersistenceError("stored AgentRun exceeds its step budget")
        if len(artifact_rows) > run.budget.max_artifacts:
            raise AgentRunPersistenceError("stored AgentRun exceeds its artifact budget")
        snapshot = AgentRunSnapshot(
            run=run,
            steps=tuple(_step_from_row(row) for row in step_rows),
            events=tuple(_event_from_row(row) for row in event_rows),
            approvals=tuple(_approval_from_row(row) for row in approval_rows),
            artifacts=tuple(_artifact_from_row(row) for row in artifact_rows),
        )
        self._validate_snapshot(snapshot)
        return snapshot

    def commit_checkpoint(
        self,
        *,
        run: AgentRun,
        step: AgentStep,
        event: RunEvent,
        approval: ApprovalRequest | None = None,
        artifact: Artifact | None = None,
    ) -> AgentRunSnapshot:
        """Atomically persist a run checkpoint and its exact related metadata."""

        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            current_row = connection.execute(
                "SELECT * FROM agent_run_state WHERE run_id = ?",
                (run.run_id,),
            ).fetchone()
            if current_row is None:
                raise AgentRunPersistenceError("AgentRun does not exist")
            current = _run_from_row(current_row)
            self._validate_checkpoint(current, run, step, event, approval, artifact)
            existing_step_row = connection.execute(
                "SELECT * FROM agent_run_steps WHERE step_id = ?",
                (step.step_id,),
            ).fetchone()
            if existing_step_row is not None:
                self._validate_step_update(_step_from_row(existing_step_row), step)
            else:
                step_count = connection.execute(
                    """
                    SELECT COUNT(*) FROM (
                        SELECT 1 FROM agent_run_steps WHERE run_id = ? LIMIT ?
                    )
                    """,
                    (run.run_id, run.budget.max_steps + 1),
                ).fetchone()[0]
                if type(step_count) is not int or step_count >= run.budget.max_steps:
                    raise AgentRunPersistenceError("AgentRun step budget is exhausted")
            if step.ordinal > run.budget.max_steps or step.attempt > run.budget.max_tool_retries:
                raise AgentRunPersistenceError("AgentStep exceeds the accepted run budget")
            if step.kind is StepKind.TOOL:
                prior_tool_calls = connection.execute(
                    """
                    SELECT COALESCE(SUM(attempt + 1), 0) FROM (
                        SELECT attempt FROM agent_run_steps
                        WHERE run_id = ? AND kind = 'tool' AND step_id != ?
                        ORDER BY ordinal LIMIT ?
                    )
                    """,
                    (run.run_id, step.step_id, run.budget.max_steps + 1),
                ).fetchone()[0]
                if (
                    type(prior_tool_calls) is not int
                    or prior_tool_calls + step.attempt + 1 > run.budget.max_tool_calls
                ):
                    raise AgentRunPersistenceError("AgentRun tool-call budget is exhausted")
            if artifact is not None:
                artifact_count = connection.execute(
                    """
                    SELECT COUNT(*) FROM (
                        SELECT 1 FROM agent_run_artifacts WHERE run_id = ? LIMIT ?
                    )
                    """,
                    (run.run_id, run.budget.max_artifacts + 1),
                ).fetchone()[0]
                if type(artifact_count) is not int or artifact_count >= run.budget.max_artifacts:
                    raise AgentRunPersistenceError("AgentRun artifact budget is exhausted")
                if artifact.size_bytes > run.budget.max_artifact_bytes:
                    raise AgentRunPersistenceError("Artifact exceeds the accepted run budget")
            try:
                connection.execute(
                    """
                    UPDATE agent_run_state
                    SET status = ?, updated_at = ?, last_event_seq = ?,
                        checkpoint_ref = ?, terminal_reason = ?
                    WHERE run_id = ?
                    """,
                    (
                        run.status.value,
                        _timestamp(run.updated_at),
                        run.last_event_seq,
                        run.checkpoint_ref,
                        run.terminal_reason,
                        run.run_id,
                    ),
                )
                self._write_step(connection, step, existing_step_row is not None)
                if approval is not None:
                    self._insert_approval(connection, approval)
                if artifact is not None:
                    self._insert_artifact(connection, artifact)
                self._insert_event(connection, event)
                connection.commit()
            except sqlite3.IntegrityError as exc:
                raise AgentRunPersistenceError("AgentRun checkpoint conflicts with stored state") from exc
        snapshot = self.load_snapshot(run.run_id)
        if snapshot is None:
            raise AgentRunPersistenceError("committed AgentRun disappeared")
        return snapshot

    def consume_approval_decision(
        self,
        decision: ApprovalRequest,
        *,
        current_subject_id: str,
        current_action_digest: str,
        current_source_snapshot: tuple[SourceRevision, ...],
        visibility_current: bool,
    ) -> ApprovalRequest:
        """Atomically consume the first valid decision, with exact replay only."""

        if decision.status not in {ApprovalStatus.APPROVED, ApprovalStatus.REJECTED}:
            raise AgentRunPersistenceError("approval decision must be approved or rejected")
        if decision.decided_at is None or decision.decision_id is None:
            raise AgentRunPersistenceError("approval decision audit fields are incomplete")
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT * FROM agent_run_approvals WHERE approval_id = ?",
                (decision.approval_id,),
            ).fetchone()
            if row is None:
                raise AgentRunPersistenceError("approval request does not exist")
            current = _approval_from_row(row)
            if current.status is not ApprovalStatus.PENDING:
                if current == decision:
                    connection.commit()
                    return current
                raise AgentRunPersistenceError("approval decision conflicts with the consumed decision")
            run_row = connection.execute(
                "SELECT * FROM agent_run_state WHERE run_id = ?",
                (current.run_id,),
            ).fetchone()
            if run_row is None or _run_from_row(run_row).status is not RunStatus.WAITING_APPROVAL:
                raise AgentRunPersistenceError("approval run is not waiting for a decision")
            self._validate_decision_binding(current, decision)
            try:
                current.validate_decision(
                    decision_id=decision.decision_id,
                    subject_id=current_subject_id,
                    action_digest=current_action_digest,
                    source_snapshot=current_source_snapshot,
                    decided_at=decision.decided_at,
                    visibility_current=visibility_current,
                )
            except AgentRunContractError as exc:
                raise AgentRunPersistenceError("approval decision is not currently valid") from exc
            if decision.decided_by != current_subject_id:
                raise AgentRunPersistenceError("approval decision actor does not match the subject")
            cursor = connection.execute(
                """
                UPDATE agent_run_approvals
                SET status = ?, decision_id = ?, decided_by = ?, decided_at = ?
                WHERE approval_id = ? AND status = 'pending'
                """,
                (
                    decision.status.value,
                    decision.decision_id,
                    decision.decided_by,
                    _timestamp(decision.decided_at),
                    decision.approval_id,
                ),
            )
            if cursor.rowcount != 1:
                raise AgentRunPersistenceError("approval decision was already consumed")
            connection.commit()
        return decision

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        self.database.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.database, timeout=5.0)
        connection.row_factory = sqlite3.Row
        try:
            connection.execute("PRAGMA foreign_keys = ON")
            connection.execute("PRAGMA busy_timeout = 5000")
            _ensure_schema(connection)
            connection.commit()
            yield connection
        except Exception:
            if connection.in_transaction:
                connection.rollback()
            raise
        finally:
            connection.close()

    @staticmethod
    def _validate_create_replay(existing: AgentRun, proposed: AgentRun) -> None:
        try:
            existing.validate_duplicate_request(
                subject_id=proposed.subject_id,
                request_key=proposed.request_key,
                request_digest=proposed.request_digest,
            )
        except AgentRunContractError as exc:
            raise AgentRunPersistenceError("AgentRun replay binding conflicts") from exc
        if (
            existing.scope_ref != proposed.scope_ref
            or existing.budget != proposed.budget
            or existing.source_snapshot != proposed.source_snapshot
            or existing.contract_version != proposed.contract_version
        ):
            raise AgentRunPersistenceError("AgentRun replay payload conflicts")

    @staticmethod
    def _validate_checkpoint(
        current: AgentRun,
        proposed: AgentRun,
        step: AgentStep,
        event: RunEvent,
        approval: ApprovalRequest | None,
        artifact: Artifact | None,
    ) -> None:
        if current.status in _TERMINAL_RUN_STATUSES:
            raise AgentRunPersistenceError("terminal AgentRun is immutable")
        immutable_current = (
            current.run_id,
            current.subject_id,
            current.scope_ref,
            current.request_key,
            current.request_digest,
            current.budget,
            current.source_snapshot,
            current.created_at,
            current.contract_version,
        )
        immutable_proposed = (
            proposed.run_id,
            proposed.subject_id,
            proposed.scope_ref,
            proposed.request_key,
            proposed.request_digest,
            proposed.budget,
            proposed.source_snapshot,
            proposed.created_at,
            proposed.contract_version,
        )
        if immutable_current != immutable_proposed:
            raise AgentRunPersistenceError("AgentRun immutable fields changed")
        if proposed.updated_at < current.updated_at:
            raise AgentRunPersistenceError("AgentRun checkpoint time regressed")
        if proposed.status is not current.status:
            try:
                validate_run_transition(current.status, proposed.status)
            except AgentRunContractError as exc:
                raise AgentRunPersistenceError("AgentRun transition is invalid") from exc
        if proposed.last_event_seq != current.last_event_seq + 1:
            raise AgentRunPersistenceError("AgentRun event sequence is not monotonic")
        if event.run_id != proposed.run_id or event.seq != proposed.last_event_seq:
            raise AgentRunPersistenceError("checkpoint event does not match AgentRun")
        if not current.updated_at <= event.occurred_at <= proposed.updated_at:
            raise AgentRunPersistenceError("checkpoint event time is outside the commit window")
        if proposed.checkpoint_ref is None or step.checkpoint_ref != proposed.checkpoint_ref:
            raise AgentRunPersistenceError("checkpoint references do not match")
        if step.run_id != proposed.run_id:
            raise AgentRunPersistenceError("checkpoint step belongs to another AgentRun")
        if event.step_id is not None and event.step_id != step.step_id:
            raise AgentRunPersistenceError("checkpoint event belongs to another step")
        if approval is not None:
            if (
                approval.status is not ApprovalStatus.PENDING
                or approval.run_id != proposed.run_id
                or approval.step_id != step.step_id
                or approval.subject_id != proposed.subject_id
                or approval.source_snapshot != proposed.source_snapshot
                or proposed.status is not RunStatus.WAITING_APPROVAL
            ):
                raise AgentRunPersistenceError("checkpoint approval binding is invalid")
        if artifact is not None:
            if (
                artifact.run_id != proposed.run_id
                or artifact.step_id != step.step_id
                or not set(artifact.evidence_refs).issubset(set(proposed.source_snapshot))
                or artifact.created_at > proposed.updated_at
            ):
                raise AgentRunPersistenceError("checkpoint artifact binding is invalid")

    @staticmethod
    def _validate_step_update(current: AgentStep, proposed: AgentStep) -> None:
        if current.run_id != proposed.run_id:
            raise AgentRunPersistenceError("step identity belongs to another AgentRun")
        immutable_current = (
            current.step_id,
            current.run_id,
            current.ordinal,
            current.kind,
            current.input_digest,
            current.tool_name,
        )
        immutable_proposed = (
            proposed.step_id,
            proposed.run_id,
            proposed.ordinal,
            proposed.kind,
            proposed.input_digest,
            proposed.tool_name,
        )
        if immutable_current != immutable_proposed or proposed.attempt < current.attempt:
            raise AgentRunPersistenceError("step immutable fields changed")
        if current.status in _TERMINAL_STEP_STATUSES and current != proposed:
            raise AgentRunPersistenceError("terminal AgentStep is immutable")

    @staticmethod
    def _validate_decision_binding(
        current: ApprovalRequest, decision: ApprovalRequest
    ) -> None:
        if (
            current.approval_id != decision.approval_id
            or current.run_id != decision.run_id
            or current.step_id != decision.step_id
            or current.subject_id != decision.subject_id
            or current.action_type != decision.action_type
            or current.action_digest != decision.action_digest
            or current.source_snapshot != decision.source_snapshot
            or current.requested_at != decision.requested_at
            or current.expires_at != decision.expires_at
        ):
            raise AgentRunPersistenceError("approval decision binding conflicts")

    @staticmethod
    def _validate_snapshot(snapshot: AgentRunSnapshot) -> None:
        if any(item.run_id != snapshot.run.run_id for item in snapshot.steps):
            raise AgentRunPersistenceError("stored step belongs to another AgentRun")
        if any(item.run_id != snapshot.run.run_id for item in snapshot.events):
            raise AgentRunPersistenceError("stored event belongs to another AgentRun")
        if any(item.run_id != snapshot.run.run_id for item in snapshot.approvals):
            raise AgentRunPersistenceError("stored approval belongs to another AgentRun")
        if any(item.run_id != snapshot.run.run_id for item in snapshot.artifacts):
            raise AgentRunPersistenceError("stored artifact belongs to another AgentRun")
        if snapshot.events and snapshot.events[-1].seq != snapshot.run.last_event_seq:
            raise AgentRunPersistenceError("stored timeline does not reach the committed sequence")
        if snapshot.run.last_event_seq and not snapshot.events:
            raise AgentRunPersistenceError("stored timeline is missing")
        if any(
            later.seq != earlier.seq + 1
            for earlier, later in zip(snapshot.events, snapshot.events[1:])
        ):
            raise AgentRunPersistenceError("stored timeline sequence is not contiguous")
        step_ids = {item.step_id for item in snapshot.steps}
        if any(item.step_id not in step_ids for item in snapshot.approvals):
            raise AgentRunPersistenceError("stored approval step is missing")
        if any(item.step_id not in step_ids for item in snapshot.artifacts):
            raise AgentRunPersistenceError("stored artifact step is missing")
        if any(
            item.subject_id != snapshot.run.subject_id
            or item.source_snapshot != snapshot.run.source_snapshot
            for item in snapshot.approvals
        ):
            raise AgentRunPersistenceError("stored approval authority binding is invalid")
        source_snapshot = set(snapshot.run.source_snapshot)
        if any(
            not set(item.evidence_refs).issubset(source_snapshot)
            for item in snapshot.artifacts
        ):
            raise AgentRunPersistenceError("stored artifact evidence binding is invalid")

    @staticmethod
    def _write_step(
        connection: sqlite3.Connection, step: AgentStep, exists: bool
    ) -> None:
        if exists:
            connection.execute(
                """
                UPDATE agent_run_steps
                SET status = ?, attempt = ?, checkpoint_ref = ?, outcome_code = ?
                WHERE step_id = ?
                """,
                (
                    step.status.value,
                    step.attempt,
                    step.checkpoint_ref,
                    step.outcome_code,
                    step.step_id,
                ),
            )
            return
        connection.execute(
            """
            INSERT INTO agent_run_steps (
                step_id, run_id, ordinal, kind, status, attempt, input_digest,
                checkpoint_ref, tool_name, outcome_code
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                step.step_id,
                step.run_id,
                step.ordinal,
                step.kind.value,
                step.status.value,
                step.attempt,
                step.input_digest,
                step.checkpoint_ref,
                step.tool_name,
                step.outcome_code,
            ),
        )

    @staticmethod
    def _insert_event(connection: sqlite3.Connection, event: RunEvent) -> None:
        connection.execute(
            """
            INSERT INTO agent_run_events (
                event_id, run_id, seq, event_type, safe_details, occurred_at,
                step_id, prev_digest, event_digest, schema_version
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event.event_id,
                event.run_id,
                event.seq,
                event.event_type,
                _json_mapping(event.safe_details),
                _timestamp(event.occurred_at),
                event.step_id,
                event.prev_digest,
                event.event_digest,
                event.schema_version,
            ),
        )

    @staticmethod
    def _insert_approval(
        connection: sqlite3.Connection, approval: ApprovalRequest
    ) -> None:
        connection.execute(
            """
            INSERT INTO agent_run_approvals (
                approval_id, run_id, step_id, subject_id, action_type,
                action_digest, source_snapshot, requested_at, expires_at,
                status, decision_id, decided_by, decided_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                approval.approval_id,
                approval.run_id,
                approval.step_id,
                approval.subject_id,
                approval.action_type,
                approval.action_digest,
                _json_revisions(approval.source_snapshot),
                _timestamp(approval.requested_at),
                _timestamp(approval.expires_at),
                approval.status.value,
                approval.decision_id,
                approval.decided_by,
                None if approval.decided_at is None else _timestamp(approval.decided_at),
            ),
        )

    @staticmethod
    def _insert_artifact(connection: sqlite3.Connection, artifact: Artifact) -> None:
        connection.execute(
            """
            INSERT INTO agent_run_artifacts (
                artifact_id, run_id, step_id, kind, media_type, storage_ref,
                digest, size_bytes, evidence_refs, created_at, expires_at,
                status, schema_version
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                artifact.artifact_id,
                artifact.run_id,
                artifact.step_id,
                artifact.kind,
                artifact.media_type,
                artifact.storage_ref,
                artifact.digest,
                artifact.size_bytes,
                _json_revisions(artifact.evidence_refs),
                _timestamp(artifact.created_at),
                _timestamp(artifact.expires_at),
                artifact.status.value,
                artifact.schema_version,
            ),
        )


def _ensure_schema(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS agent_run_state (
            run_id TEXT PRIMARY KEY,
            subject_id TEXT NOT NULL,
            scope_ref TEXT NOT NULL,
            request_key TEXT NOT NULL,
            request_digest TEXT NOT NULL CHECK (length(request_digest) = 64),
            status TEXT NOT NULL CHECK (
                status IN ('queued', 'running', 'waiting_approval', 'succeeded', 'failed', 'cancelled')
            ),
            max_steps INTEGER NOT NULL,
            max_tool_calls INTEGER NOT NULL,
            max_tool_retries INTEGER NOT NULL,
            max_active_seconds INTEGER NOT NULL,
            max_tool_attempt_seconds INTEGER NOT NULL,
            max_artifacts INTEGER NOT NULL,
            max_artifact_bytes INTEGER NOT NULL,
            source_snapshot TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            last_event_seq INTEGER NOT NULL CHECK (last_event_seq >= 0),
            checkpoint_ref TEXT,
            terminal_reason TEXT,
            contract_version TEXT NOT NULL CHECK (contract_version = 'agent-run-contract-v1'),
            UNIQUE (subject_id, request_key)
        );

        CREATE TABLE IF NOT EXISTS agent_run_steps (
            step_id TEXT PRIMARY KEY,
            run_id TEXT NOT NULL REFERENCES agent_run_state(run_id),
            ordinal INTEGER NOT NULL,
            kind TEXT NOT NULL CHECK (kind IN ('plan', 'tool', 'approval', 'finalize')),
            status TEXT NOT NULL CHECK (status IN ('queued', 'running', 'succeeded', 'failed', 'cancelled')),
            attempt INTEGER NOT NULL,
            input_digest TEXT NOT NULL CHECK (length(input_digest) = 64),
            checkpoint_ref TEXT,
            tool_name TEXT,
            outcome_code TEXT,
            UNIQUE (run_id, ordinal),
            UNIQUE (run_id, step_id)
        );

        CREATE TABLE IF NOT EXISTS agent_run_events (
            event_id TEXT PRIMARY KEY,
            run_id TEXT NOT NULL REFERENCES agent_run_state(run_id),
            seq INTEGER NOT NULL CHECK (seq > 0),
            event_type TEXT NOT NULL,
            safe_details TEXT NOT NULL,
            occurred_at TEXT NOT NULL,
            step_id TEXT,
            prev_digest TEXT,
            event_digest TEXT,
            schema_version TEXT NOT NULL CHECK (schema_version = 'agent-run-contract-v1'),
            UNIQUE (run_id, seq),
            FOREIGN KEY (run_id, step_id) REFERENCES agent_run_steps(run_id, step_id)
        );

        CREATE TRIGGER IF NOT EXISTS agent_run_events_no_update
        BEFORE UPDATE ON agent_run_events
        BEGIN SELECT RAISE(ABORT, 'agent run events are append-only'); END;

        CREATE TRIGGER IF NOT EXISTS agent_run_events_no_delete
        BEFORE DELETE ON agent_run_events
        BEGIN SELECT RAISE(ABORT, 'agent run events are append-only'); END;

        CREATE TABLE IF NOT EXISTS agent_run_approvals (
            approval_id TEXT PRIMARY KEY,
            run_id TEXT NOT NULL REFERENCES agent_run_state(run_id),
            step_id TEXT NOT NULL,
            subject_id TEXT NOT NULL,
            action_type TEXT NOT NULL,
            action_digest TEXT NOT NULL CHECK (length(action_digest) = 64),
            source_snapshot TEXT NOT NULL,
            requested_at TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            status TEXT NOT NULL CHECK (
                status IN ('pending', 'approved', 'rejected', 'expired', 'superseded')
            ),
            decision_id TEXT,
            decided_by TEXT,
            decided_at TEXT,
            UNIQUE (run_id, step_id),
            FOREIGN KEY (run_id, step_id) REFERENCES agent_run_steps(run_id, step_id)
        );

        CREATE TABLE IF NOT EXISTS agent_run_artifacts (
            artifact_id TEXT PRIMARY KEY,
            run_id TEXT NOT NULL REFERENCES agent_run_state(run_id),
            step_id TEXT NOT NULL,
            kind TEXT NOT NULL CHECK (kind = 'report'),
            media_type TEXT NOT NULL CHECK (media_type = 'application/json'),
            storage_ref TEXT NOT NULL,
            digest TEXT NOT NULL CHECK (length(digest) = 64),
            size_bytes INTEGER NOT NULL CHECK (size_bytes > 0),
            evidence_refs TEXT NOT NULL,
            created_at TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            status TEXT NOT NULL CHECK (status IN ('available', 'revoked', 'expired')),
            schema_version TEXT NOT NULL CHECK (schema_version = 'agent-run-contract-v1'),
            FOREIGN KEY (run_id, step_id) REFERENCES agent_run_steps(run_id, step_id)
        );

        CREATE INDEX IF NOT EXISTS agent_run_events_run_seq
        ON agent_run_events(run_id, seq);
        CREATE INDEX IF NOT EXISTS agent_run_steps_run_ordinal
        ON agent_run_steps(run_id, ordinal);
        CREATE INDEX IF NOT EXISTS agent_run_approvals_run_requested
        ON agent_run_approvals(run_id, requested_at);
        CREATE INDEX IF NOT EXISTS agent_run_artifacts_run_created
        ON agent_run_artifacts(run_id, created_at);
        """
    )


def _run_values(run: AgentRun) -> tuple[object, ...]:
    return (
        run.run_id,
        run.subject_id,
        run.scope_ref,
        run.request_key,
        run.request_digest,
        run.status.value,
        run.budget.max_steps,
        run.budget.max_tool_calls,
        run.budget.max_tool_retries,
        run.budget.max_active_seconds,
        run.budget.max_tool_attempt_seconds,
        run.budget.max_artifacts,
        run.budget.max_artifact_bytes,
        _json_revisions(run.source_snapshot),
        _timestamp(run.created_at),
        _timestamp(run.updated_at),
        run.last_event_seq,
        run.checkpoint_ref,
        run.terminal_reason,
        run.contract_version,
    )


def _run_from_row(row: sqlite3.Row) -> AgentRun:
    try:
        return AgentRun(
            run_id=row["run_id"],
            subject_id=row["subject_id"],
            scope_ref=row["scope_ref"],
            request_key=row["request_key"],
            request_digest=row["request_digest"],
            status=RunStatus(row["status"]),
            budget=ExecutionBudget(
                max_steps=row["max_steps"],
                max_tool_calls=row["max_tool_calls"],
                max_tool_retries=row["max_tool_retries"],
                max_active_seconds=row["max_active_seconds"],
                max_tool_attempt_seconds=row["max_tool_attempt_seconds"],
                max_artifacts=row["max_artifacts"],
                max_artifact_bytes=row["max_artifact_bytes"],
            ),
            source_snapshot=_parse_revisions(row["source_snapshot"]),
            created_at=_parse_timestamp(row["created_at"]),
            updated_at=_parse_timestamp(row["updated_at"]),
            last_event_seq=row["last_event_seq"],
            checkpoint_ref=row["checkpoint_ref"],
            terminal_reason=row["terminal_reason"],
            contract_version=row["contract_version"],
        )
    except (AgentRunContractError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise AgentRunPersistenceError("stored AgentRun row is invalid") from exc


def _step_from_row(row: sqlite3.Row) -> AgentStep:
    try:
        return AgentStep(
            step_id=row["step_id"],
            run_id=row["run_id"],
            ordinal=row["ordinal"],
            kind=StepKind(row["kind"]),
            status=StepStatus(row["status"]),
            attempt=row["attempt"],
            input_digest=row["input_digest"],
            checkpoint_ref=row["checkpoint_ref"],
            tool_name=row["tool_name"],
            outcome_code=row["outcome_code"],
        )
    except (AgentRunContractError, KeyError, TypeError, ValueError) as exc:
        raise AgentRunPersistenceError("stored AgentStep row is invalid") from exc


def _event_from_row(row: sqlite3.Row) -> RunEvent:
    try:
        details = json.loads(row["safe_details"])
        if not isinstance(details, dict):
            raise AgentRunPersistenceError("stored RunEvent details are invalid")
        return RunEvent(
            event_id=row["event_id"],
            run_id=row["run_id"],
            seq=row["seq"],
            event_type=row["event_type"],
            safe_details=details,
            occurred_at=_parse_timestamp(row["occurred_at"]),
            step_id=row["step_id"],
            prev_digest=row["prev_digest"],
            event_digest=row["event_digest"],
            schema_version=row["schema_version"],
        )
    except (AgentRunContractError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise AgentRunPersistenceError("stored RunEvent row is invalid") from exc


def _approval_from_row(row: sqlite3.Row) -> ApprovalRequest:
    try:
        decided_at = row["decided_at"]
        return ApprovalRequest(
            approval_id=row["approval_id"],
            run_id=row["run_id"],
            step_id=row["step_id"],
            subject_id=row["subject_id"],
            action_type=row["action_type"],
            action_digest=row["action_digest"],
            source_snapshot=_parse_revisions(row["source_snapshot"]),
            requested_at=_parse_timestamp(row["requested_at"]),
            expires_at=_parse_timestamp(row["expires_at"]),
            status=ApprovalStatus(row["status"]),
            decision_id=row["decision_id"],
            decided_by=row["decided_by"],
            decided_at=None if decided_at is None else _parse_timestamp(decided_at),
        )
    except (AgentRunContractError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise AgentRunPersistenceError("stored ApprovalRequest row is invalid") from exc


def _artifact_from_row(row: sqlite3.Row) -> Artifact:
    try:
        return Artifact(
            artifact_id=row["artifact_id"],
            run_id=row["run_id"],
            step_id=row["step_id"],
            kind=row["kind"],
            media_type=row["media_type"],
            storage_ref=row["storage_ref"],
            digest=row["digest"],
            size_bytes=row["size_bytes"],
            evidence_refs=_parse_revisions(row["evidence_refs"]),
            created_at=_parse_timestamp(row["created_at"]),
            expires_at=_parse_timestamp(row["expires_at"]),
            status=ArtifactStatus(row["status"]),
            schema_version=row["schema_version"],
        )
    except (AgentRunContractError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise AgentRunPersistenceError("stored Artifact row is invalid") from exc


def _json_revisions(revisions: tuple[SourceRevision, ...]) -> str:
    return json.dumps(
        [item.to_dict() for item in revisions],
        sort_keys=True,
        separators=(",", ":"),
    )


def _json_mapping(values: Mapping[str, str | int]) -> str:
    return json.dumps(dict(values), sort_keys=True, separators=(",", ":"))


def _parse_revisions(value: object) -> tuple[SourceRevision, ...]:
    if not isinstance(value, str):
        raise AgentRunPersistenceError("stored source snapshot is invalid")
    payload = json.loads(value)
    if not isinstance(payload, list) or any(not isinstance(item, dict) for item in payload):
        raise AgentRunPersistenceError("stored source snapshot is invalid")
    revisions: list[SourceRevision] = []
    for item in payload:
        if set(item) != {"source_id", "revision"}:
            raise AgentRunPersistenceError("stored source snapshot is invalid")
        source_id = item["source_id"]
        revision = item["revision"]
        if not isinstance(source_id, str) or not isinstance(revision, str):
            raise AgentRunPersistenceError("stored source snapshot is invalid")
        revisions.append(SourceRevision(source_id=source_id, revision=revision))
    return tuple(revisions)


def _timestamp(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


def _parse_timestamp(value: object) -> datetime:
    if not isinstance(value, str):
        raise AgentRunPersistenceError("stored timestamp is invalid")
    return datetime.fromisoformat(value.replace("Z", "+00:00"))
