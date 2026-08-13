import json
import time
from dataclasses import replace
from pathlib import Path

from fastapi.testclient import TestClient

import main
from app.services.agent_delegation import sign_delegated_request
from app.services.agent_run_api import (
    INTERNAL_AGENT_RUN_CREATE_PATH,
    INTERNAL_AGENT_RUN_STATUS_PATH,
)


client = TestClient(main.app)
_SECRET = "agent-run-route-test-secret"


def _headers(path: str, body: bytes) -> dict[str, str]:
    signed = sign_delegated_request("POST", path, body, int(time.time()), _SECRET)
    return {
        "X-DevMemo-Agent-Signature": signed.signature,
        "X-DevMemo-Agent-Timestamp": signed.timestamp,
    }


def _create_body(**overrides: object) -> bytes:
    payload: dict[str, object] = {
        "subject_id": "user-17",
        "scope_ref": "scope-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        "request_key": "request-" + "b" * 64,
        "request_digest": "a" * 64,
        "source_snapshot": [
            {"source_id": "memo-aaaaaaaaaaaaaaaaaaaaaaaa", "revision": "rev-1700000000"}
        ],
    }
    payload.update(overrides)
    return json.dumps(payload, separators=(",", ":")).encode()


def _enable(monkeypatch, database: Path) -> None:
    monkeypatch.setattr(
        main,
        "settings",
        replace(main.settings, agent_enabled=True, agent_internal_secret=_SECRET),
    )
    monkeypatch.setattr(main, "database_path", lambda: database)


def test_internal_agent_run_create_is_idempotent_and_content_free(monkeypatch, tmp_path):
    database = tmp_path / "agent-runs.db"
    _enable(monkeypatch, database)
    body = _create_body()

    first = client.post(
        INTERNAL_AGENT_RUN_CREATE_PATH,
        content=body,
        headers=_headers(INTERNAL_AGENT_RUN_CREATE_PATH, body),
    )
    second = client.post(
        INTERNAL_AGENT_RUN_CREATE_PATH,
        content=body,
        headers=_headers(INTERNAL_AGENT_RUN_CREATE_PATH, body),
    )

    assert first.status_code == 200
    assert second.status_code == 200
    assert second.json() == first.json()
    assert first.json() == {
        "run_id": first.json()["run_id"],
        "status": "queued",
        "created_at": first.json()["created_at"],
        "updated_at": first.json()["updated_at"],
        "last_event_seq": 0,
        "source_count": 1,
        "terminal_reason": None,
        "artifact_id": None,
    }
    stored = database.read_bytes()
    assert b"private task text" not in stored
    assert b"request-demo-001" not in stored


def test_internal_agent_run_create_rejects_idempotency_conflict(monkeypatch, tmp_path):
    database = tmp_path / "agent-runs.db"
    _enable(monkeypatch, database)
    first_body = _create_body()
    conflict_body = _create_body(request_digest="d" * 64)

    first = client.post(
        INTERNAL_AGENT_RUN_CREATE_PATH,
        content=first_body,
        headers=_headers(INTERNAL_AGENT_RUN_CREATE_PATH, first_body),
    )
    conflict = client.post(
        INTERNAL_AGENT_RUN_CREATE_PATH,
        content=conflict_body,
        headers=_headers(INTERNAL_AGENT_RUN_CREATE_PATH, conflict_body),
    )

    assert first.status_code == 200
    assert conflict.status_code == 409
    assert conflict.json() == {"detail": "AgentRun request conflicts"}


def test_internal_agent_run_status_is_creator_bound(monkeypatch, tmp_path):
    database = tmp_path / "agent-runs.db"
    _enable(monkeypatch, database)
    create_body = _create_body()
    created = client.post(
        INTERNAL_AGENT_RUN_CREATE_PATH,
        content=create_body,
        headers=_headers(INTERNAL_AGENT_RUN_CREATE_PATH, create_body),
    ).json()
    status_body = json.dumps(
        {"subject_id": "user-17", "run_id": created["run_id"]},
        separators=(",", ":"),
    ).encode()

    response = client.post(
        INTERNAL_AGENT_RUN_STATUS_PATH,
        content=status_body,
        headers=_headers(INTERNAL_AGENT_RUN_STATUS_PATH, status_body),
    )
    assert response.status_code == 200
    assert response.json() == created

    other_body = json.dumps(
        {"subject_id": "user-18", "run_id": created["run_id"]},
        separators=(",", ":"),
    ).encode()
    other = client.post(
        INTERNAL_AGENT_RUN_STATUS_PATH,
        content=other_body,
        headers=_headers(INTERNAL_AGENT_RUN_STATUS_PATH, other_body),
    )
    assert other.status_code == 404


def test_internal_agent_run_routes_fail_closed(monkeypatch, tmp_path):
    body = _create_body()
    monkeypatch.setattr(main, "settings", replace(main.settings, agent_enabled=False))
    disabled = client.post(
        INTERNAL_AGENT_RUN_CREATE_PATH,
        content=body,
        headers=_headers(INTERNAL_AGENT_RUN_CREATE_PATH, body),
    )
    assert disabled.status_code == 404

    _enable(monkeypatch, tmp_path / "agent-runs.db")
    unsigned = client.post(INTERNAL_AGENT_RUN_CREATE_PATH, content=body)
    assert unsigned.status_code == 401

    malformed = b'{"subject_id":"user-17","subject_id":"user-18"}'
    invalid = client.post(
        INTERNAL_AGENT_RUN_CREATE_PATH,
        content=malformed,
        headers=_headers(INTERNAL_AGENT_RUN_CREATE_PATH, malformed),
    )
    assert invalid.status_code == 400
