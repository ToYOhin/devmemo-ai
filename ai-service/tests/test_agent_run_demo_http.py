import hashlib
import json
import time
from dataclasses import replace

from fastapi.testclient import TestClient

import main
from app.services.agent_delegation import sign_delegated_request
from app.services.agent_run_api import INTERNAL_AGENT_RUN_CREATE_PATH
from app.services.agent_run_demo_api import (
    INTERNAL_AGENT_RUN_ARTIFACT_PATH,
    INTERNAL_AGENT_RUN_EXECUTE_PATH,
)


client = TestClient(main.app)
SECRET = "agent-run-demo-http-secret"


def _signed(path: str, body: bytes) -> dict[str, str]:
    signed = sign_delegated_request("POST", path, body, int(time.time()), SECRET)
    return {
        "X-DevMemo-Agent-Signature": signed.signature,
        "X-DevMemo-Agent-Timestamp": signed.timestamp,
    }


def _post(path: str, payload: dict[str, object]):
    body = json.dumps(payload, separators=(",", ":")).encode()
    return client.post(path, content=body, headers=_signed(path, body))


def test_signed_demo_routes_execute_and_return_markdown(monkeypatch, tmp_path) -> None:
    database = tmp_path / "agent-runs.db"
    monkeypatch.setattr(
        main,
        "settings",
        replace(main.settings, agent_enabled=True, agent_internal_secret=SECRET),
    )
    monkeypatch.setattr(main, "database_path", lambda: database)
    task_kind = "project_summary"
    created = _post(
        INTERNAL_AGENT_RUN_CREATE_PATH,
        {
            "subject_id": "user-17",
            "scope_ref": "scope-demo-http-001",
            "request_key": "request-demo-http-001",
            "request_digest": hashlib.sha256(task_kind.encode()).hexdigest(),
            "source_snapshot": [{"source_id": "memo-616263", "revision": "rev-1700000000"}],
        },
    )
    run_id = created.json()["run_id"]

    executed = _post(
        INTERNAL_AGENT_RUN_EXECUTE_PATH,
        {
            "subject_id": "user-17",
            "run_id": run_id,
            "task_kind": task_kind,
            "sources": [
                {
                    "source_id": "memo-616263",
                    "revision": "rev-1700000000",
                    "content": "# DevMemo AI\nDelivered a bounded AgentRun demo.",
                }
            ],
        },
    )
    artifact = _post(
        INTERNAL_AGENT_RUN_ARTIFACT_PATH,
        {"subject_id": "user-17", "run_id": run_id},
    )

    assert created.status_code == 200
    assert executed.status_code == 200
    assert executed.json()["status"] == "succeeded"
    assert artifact.status_code == 200
    assert artifact.json()["media_type"] == "text/markdown"
    assert "# Project summary" in artifact.json()["markdown"]


def test_demo_routes_require_valid_signature(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(
        main,
        "settings",
        replace(main.settings, agent_enabled=True, agent_internal_secret=SECRET),
    )
    monkeypatch.setattr(main, "database_path", lambda: tmp_path / "agent-runs.db")

    response = client.post(INTERNAL_AGENT_RUN_EXECUTE_PATH, content=b"{}")

    assert response.status_code == 401
