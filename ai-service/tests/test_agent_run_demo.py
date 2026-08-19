import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json

import pytest

from app.adapters.agent_run_artifact_store import SQLiteAgentRunArtifactStore
from app.adapters.agent_run_store import SQLiteAgentRunStore
from app.domain.agent_run import RunStatus, SourceRevision
from app.services.agent_run_api import AgentRunAPI, AgentRunCreateRequest
from app.services.agent_run_demo import (
    AgentRunDemoError,
    AgentRunDemoExecutor,
    AgentRunDemoRequest,
)
from app.services.agent_run_report import PROVIDER_REPORT_VERSION, ReportSource


NOW = datetime(2026, 8, 13, 9, 0, tzinfo=timezone.utc)
SOURCES = (
    ReportSource(
        "memo-616263",
        "rev-1700000000",
        "# DevMemo AI\nBuilt an authenticated AgentRun BFF.",
    ),
)


def _create_run(database, task_kind="project_summary") -> dict[str, object]:
    return AgentRunAPI(database, utc_now=lambda: NOW, run_id_factory=lambda: "run-demo-001").create(
        AgentRunCreateRequest(
            subject_id="user-17",
            scope_ref="scope-demo-001",
            request_key="request-demo-001",
            request_digest=hashlib.sha256(task_kind.encode()).hexdigest(),
            source_snapshot=(SourceRevision("memo-616263", "rev-1700000000"),),
        )
    )


def test_demo_executor_runs_bounded_runtime_and_persists_markdown(tmp_path) -> None:
    database = tmp_path / "agent-runs.db"
    _create_run(database)
    executor = AgentRunDemoExecutor(database, utc_now=lambda: NOW)

    result = asyncio.run(
        executor.execute(
            AgentRunDemoRequest("user-17", "run-demo-001", "project_summary", SOURCES)
        )
    )

    assert result.run.status is RunStatus.SUCCEEDED
    assert result.run.last_event_seq == 6
    assert len(result.artifacts) == 1
    artifact = SQLiteAgentRunArtifactStore(database).get(result.artifacts[0].storage_ref)
    assert artifact is not None
    assert artifact.file_name == "project-summary.md"
    assert "authenticated AgentRun BFF" in artifact.markdown


def test_demo_executor_is_idempotent_after_terminal_checkpoint(tmp_path) -> None:
    database = tmp_path / "agent-runs.db"
    _create_run(database)
    executor = AgentRunDemoExecutor(database, utc_now=lambda: NOW)
    request = AgentRunDemoRequest("user-17", "run-demo-001", "project_summary", SOURCES)

    first = asyncio.run(executor.execute(request))
    replay = asyncio.run(executor.execute(request))

    assert replay.run == first.run
    assert replay.artifacts == first.artifacts
    assert SQLiteAgentRunStore(database).load_snapshot("run-demo-001") == replay


def test_demo_executor_rejects_task_or_subject_mismatch(tmp_path) -> None:
    database = tmp_path / "agent-runs.db"
    _create_run(database)
    executor = AgentRunDemoExecutor(database, utc_now=lambda: NOW)

    with pytest.raises(AgentRunDemoError):
        asyncio.run(executor.execute(AgentRunDemoRequest("user-18", "run-demo-001", "project_summary", SOURCES)))
    with pytest.raises(AgentRunDemoError):
        asyncio.run(executor.execute(AgentRunDemoRequest("user-17", "run-demo-001", "custom_summary", SOURCES)))


@dataclass(frozen=True)
class _ProviderResult:
    text: str


class _Provider:
    name = "openai"

    async def generate(self, _prompt: str) -> _ProviderResult:
        return _ProviderResult(
            json.dumps(
                {
                    "version": PROVIDER_REPORT_VERSION,
                    "summary": "Provider-backed project summary.",
                    "bullets": ["Authenticated BFF", "Bounded runtime", "Evidence artifact"],
                    "limitations": ["Synthetic verification only"],
                    "citation_refs": ["source-1"],
                }
            )
        )


def test_demo_executor_persists_validated_provider_finalizer_output(tmp_path) -> None:
    database = tmp_path / "agent-runs.db"
    _create_run(database)
    executor = AgentRunDemoExecutor(database, provider=_Provider(), utc_now=lambda: NOW)

    result = asyncio.run(
        executor.execute(
            AgentRunDemoRequest("user-17", "run-demo-001", "project_summary", SOURCES)
        )
    )

    artifact = SQLiteAgentRunArtifactStore(database).get(result.artifacts[0].storage_ref)
    assert artifact is not None
    assert "Provider-backed project summary." in artifact.markdown
    assert "`source-1`: `memo-616263` at `rev-1700000000`" in artifact.markdown
