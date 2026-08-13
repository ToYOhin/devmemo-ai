"""Strict internal HTTP contract for deterministic AgentRun demo execution."""

from __future__ import annotations

import json
from pathlib import Path

from app.adapters.agent_run_artifact_store import SQLiteAgentRunArtifactStore
from app.adapters.agent_run_store import SQLiteAgentRunStore
from app.domain.agent_run import ArtifactStatus
from app.services.agent_run_api import project_agent_run
from app.services.agent_run_demo import AgentRunDemoExecutor, AgentRunDemoRequest
from app.services.agent_run_report import ALLOWED_DEMO_TASKS, ReportSource


INTERNAL_AGENT_RUN_EXECUTE_PATH = "/internal/ai/agent/runs/execute"
INTERNAL_AGENT_RUN_ARTIFACT_PATH = "/internal/ai/agent/runs/artifact"
MAX_DEMO_REQUEST_BYTES = 128 << 10
MAX_SOURCE_CONTENT_CHARS = 32 << 10


class AgentRunDemoAPIError(ValueError):
    """Raised when an internal demo request is malformed or inaccessible."""


class AgentRunDemoAPI:
    def __init__(self, database: str | Path) -> None:
        self._database = database
        self._runs = SQLiteAgentRunStore(database)
        self._artifacts = SQLiteAgentRunArtifactStore(database)

    async def execute(self, body: bytes) -> dict[str, object]:
        payload = _exact_object(body)
        if set(payload) != {"subject_id", "run_id", "task_kind", "sources"}:
            raise AgentRunDemoAPIError("invalid AgentRun demo request")
        task_kind = _string(payload, "task_kind")
        raw_sources = payload["sources"]
        if task_kind not in ALLOWED_DEMO_TASKS or not isinstance(raw_sources, list) or not 1 <= len(raw_sources) <= 10:
            raise AgentRunDemoAPIError("invalid AgentRun demo request")
        sources: list[ReportSource] = []
        for raw in raw_sources:
            if not isinstance(raw, dict) or set(raw) != {"source_id", "revision", "content"}:
                raise AgentRunDemoAPIError("invalid AgentRun demo request")
            source = ReportSource(
                source_id=_string(raw, "source_id"),
                revision=_string(raw, "revision"),
                content=_string(raw, "content"),
            )
            if not source.content.strip() or len(source.content) > MAX_SOURCE_CONTENT_CHARS:
                raise AgentRunDemoAPIError("invalid AgentRun demo request")
            sources.append(source)
        snapshot = await AgentRunDemoExecutor(self._database).execute(
            AgentRunDemoRequest(
                subject_id=_string(payload, "subject_id"),
                run_id=_string(payload, "run_id"),
                task_kind=task_kind,
                sources=tuple(sources),
            )
        )
        artifact_id = snapshot.artifacts[-1].artifact_id if snapshot.artifacts else None
        return project_agent_run(snapshot.run, artifact_id=artifact_id)

    def artifact(self, body: bytes) -> dict[str, object] | None:
        payload = _exact_object(body)
        if set(payload) != {"subject_id", "run_id"}:
            raise AgentRunDemoAPIError("invalid AgentRun artifact request")
        snapshot = self._runs.load_snapshot(_string(payload, "run_id"))
        if snapshot is None or snapshot.run.subject_id != _string(payload, "subject_id"):
            return None
        available = [item for item in snapshot.artifacts if item.status is ArtifactStatus.AVAILABLE]
        if not available:
            return None
        metadata = available[-1]
        stored = self._artifacts.get(metadata.storage_ref)
        if stored is None or stored.artifact_id != metadata.artifact_id or stored.run_id != snapshot.run.run_id:
            return None
        return {
            "artifact_id": stored.artifact_id,
            "file_name": stored.file_name,
            "media_type": "text/markdown",
            "markdown": stored.markdown,
            "digest": stored.digest,
        }


def _exact_object(body: bytes) -> dict[str, object]:
    if not body or len(body) > MAX_DEMO_REQUEST_BYTES:
        raise AgentRunDemoAPIError("invalid AgentRun demo request")

    def reject_duplicates(pairs: list[tuple[str, object]]) -> dict[str, object]:
        value: dict[str, object] = {}
        for key, item in pairs:
            if key in value:
                raise AgentRunDemoAPIError("invalid AgentRun demo request")
            value[key] = item
        return value

    try:
        payload = json.loads(body, object_pairs_hook=reject_duplicates)
    except (TypeError, ValueError, UnicodeDecodeError) as error:
        raise AgentRunDemoAPIError("invalid AgentRun demo request") from error
    if not isinstance(payload, dict):
        raise AgentRunDemoAPIError("invalid AgentRun demo request")
    return payload


def _string(payload: dict[str, object], name: str) -> str:
    value = payload[name]
    if not isinstance(value, str):
        raise AgentRunDemoAPIError("invalid AgentRun demo request")
    return value
