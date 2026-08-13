import asyncio
import hashlib
import json

from app.domain.agent_run import SourceRevision
from app.services.agent_run_api import AgentRunAPI, AgentRunCreateRequest
from app.services.agent_run_demo_api import AgentRunDemoAPI


def _create(database, task_kind: str) -> dict[str, object]:
    return AgentRunAPI(database, run_id_factory=lambda: "run-demo-api-001").create(
        AgentRunCreateRequest(
            subject_id="user-17",
            scope_ref="scope-demo-api-001",
            request_key="request-demo-api-001",
            request_digest=hashlib.sha256(task_kind.encode()).hexdigest(),
            source_snapshot=(SourceRevision("memo-616263", "rev-1700000000"),),
        )
    )


def _execute_body(task_kind: str = "project_summary") -> bytes:
    return json.dumps(
        {
            "subject_id": "user-17",
            "run_id": "run-demo-api-001",
            "task_kind": task_kind,
            "sources": [
                {
                    "source_id": "memo-616263",
                    "revision": "rev-1700000000",
                    "content": "# DevMemo AI\nBuilt a bounded AgentRun runtime.",
                }
            ],
        },
        separators=(",", ":"),
    ).encode()


def test_demo_api_executes_and_returns_markdown_artifact(tmp_path) -> None:
    database = tmp_path / "agent-runs.db"
    _create(database, "project_summary")
    api = AgentRunDemoAPI(database)

    status = asyncio.run(api.execute(_execute_body()))
    artifact = api.artifact(b'{"subject_id":"user-17","run_id":"run-demo-api-001"}')

    assert status["status"] == "succeeded"
    assert status["artifact_id"] == artifact["artifact_id"]  # type: ignore[index]
    assert artifact is not None
    assert artifact["media_type"] == "text/markdown"
    assert "# Project summary" in str(artifact["markdown"])


def test_demo_api_artifact_is_creator_bound(tmp_path) -> None:
    database = tmp_path / "agent-runs.db"
    _create(database, "project_summary")
    api = AgentRunDemoAPI(database)
    asyncio.run(api.execute(_execute_body()))

    assert api.artifact(b'{"subject_id":"user-18","run_id":"run-demo-api-001"}') is None
