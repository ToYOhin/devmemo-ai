import sqlite3

from fastapi.testclient import TestClient

import main


client = TestClient(main.app)


def test_webhook_event_id_is_idempotent_and_outbox_is_readable(monkeypatch, tmp_path):
    monkeypatch.setenv("AI_NOTES_DB", str(tmp_path / "webhook-outbox.db"))
    payload = {
        "eventId": "event-idempotent-1",
        "activityType": "memos.memo.created",
        "memo": {"uid": "memo-outbox", "content": "Docker port mapping"},
    }

    first = client.post("/api/integrations/memos/webhook", json=payload)
    duplicate = client.post("/api/integrations/memos/webhook", json=payload)

    assert first.status_code == 200
    assert first.json()["code"] == 0
    assert duplicate.status_code == 200
    assert duplicate.json() == {
        "code": 0,
        "message": "duplicate webhook ignored",
        "event_id": "event-idempotent-1",
        "outbox_status": "processed",
    }

    response = client.get("/api/ai/ops/outbox?status=processed")
    assert response.status_code == 200
    assert response.json()["count"] == 1
    assert response.json()["items"][0]["event_id"] == "event-idempotent-1"
    assert response.json()["items"][0]["attempts"] == 1
    assert response.json()["items"][0]["event_type"] == "memos.memo.created"
    assert "payload" not in response.json()["items"][0]


def test_webhook_processing_failure_is_acknowledged_and_readable(monkeypatch, tmp_path):
    monkeypatch.setenv("AI_NOTES_DB", str(tmp_path / "webhook-failure.db"))

    async def broken_summary(request):
        raise RuntimeError("summary unavailable")

    monkeypatch.setattr(main, "summarize", broken_summary)
    response = client.post(
        "/api/integrations/memos/webhook",
        json={
            "eventId": "event-failed-1",
            "activityType": "memos.memo.created",
            "memo": {"uid": "memo-failed", "content": "content"},
        },
    )

    assert response.status_code == 200
    assert response.json() == {
        "code": 0,
        "message": "webhook processing failed",
        "event_id": "event-failed-1",
        "outbox_status": "failed",
    }
    failed = client.get("/api/ai/ops/outbox?status=failed")
    assert failed.status_code == 200
    assert failed.json()["items"][0]["last_error"] == "summary unavailable"
    assert failed.json()["items"][0]["attempts"] == 1


def test_outbox_api_rejects_unknown_status_or_invalid_limit():
    assert client.get("/api/ai/ops/outbox?status=running").status_code == 422
    assert client.get("/api/ai/ops/outbox?limit=101").status_code == 422


def test_failed_webhook_can_be_explicitly_retried_once(monkeypatch, tmp_path):
    monkeypatch.setenv("AI_NOTES_DB", str(tmp_path / "webhook-retry.db"))
    original_summary = main.summarize

    async def broken_summary(request):
        raise RuntimeError("temporary summary failure")

    monkeypatch.setattr(main, "summarize", broken_summary)
    failed = client.post(
        "/api/integrations/memos/webhook",
        json={
            "eventId": "event-retry-1",
            "activityType": "memos.memo.created",
            "memo": {"uid": "memo-retry", "content": "FastAPI retry"},
        },
    )
    assert failed.json()["outbox_status"] == "failed"

    monkeypatch.setattr(main, "summarize", original_summary)
    retried = client.post("/api/ai/ops/outbox/event-retry-1/retry")

    assert retried.status_code == 200
    assert retried.json()["outbox_status"] == "processed"
    assert retried.json()["attempts"] == 2
    assert retried.json()["max_attempts"] == 3
    stats = client.get("/api/ai/ops/outbox").json()
    assert stats["by_status"] == {"pending": 0, "processed": 1, "failed": 0}
    assert stats["recent_errors"] == []


def test_retry_rejects_missing_or_already_processed_event(monkeypatch, tmp_path):
    monkeypatch.setenv("AI_NOTES_DB", str(tmp_path / "webhook-retry-errors.db"))
    assert client.post("/api/ai/ops/outbox/missing/retry").status_code == 404

    response = client.post(
        "/api/integrations/memos/webhook",
        json={
            "eventId": "event-processed-1",
            "activityType": "memos.memo.created",
            "memo": {"uid": "memo-processed", "content": "content"},
        },
    )
    assert response.status_code == 200
    retry = client.post("/api/ai/ops/outbox/event-processed-1/retry")
    assert retry.status_code == 409
    assert "only failed" in retry.json()["detail"]


def test_retry_returns_conflict_after_max_attempts(monkeypatch, tmp_path):
    monkeypatch.setenv("AI_NOTES_DB", str(tmp_path / "webhook-retry-limit.db"))

    async def broken_summary(request):
        raise RuntimeError("still unavailable")

    monkeypatch.setattr(main, "summarize", broken_summary)
    payload = {
        "eventId": "event-retry-limit-1",
        "activityType": "memos.memo.created",
        "memo": {"uid": "memo-retry-limit", "content": "content"},
    }
    initial = client.post("/api/integrations/memos/webhook", json=payload)
    assert initial.status_code == 200
    assert initial.json()["outbox_status"] == "failed"
    for expected_attempts in (2, 3):
        retry = client.post("/api/ai/ops/outbox/event-retry-limit-1/retry")
        assert retry.status_code == 200
        assert retry.json()["attempts"] == expected_attempts
        assert retry.json()["outbox_status"] == "failed"

    exhausted = client.post("/api/ai/ops/outbox/event-retry-limit-1/retry")
    assert exhausted.status_code == 409
    assert exhausted.json()["detail"] == "webhook retry limit reached"
    alerts = client.get("/api/ai/ops/alerts").json()
    assert alerts["exhausted_count"] == 1
    assert alerts["alerts"][0]["severity"] == "critical"


def test_ops_token_is_optional_then_protects_read_and_retry(monkeypatch, tmp_path):
    monkeypatch.setenv("AI_NOTES_DB", str(tmp_path / "ops-token.db"))
    monkeypatch.delenv("AI_OPS_TOKEN", raising=False)
    assert client.get("/api/ai/ops/outbox").status_code == 200

    monkeypatch.setenv("AI_OPS_TOKEN", "ops-secret")
    assert client.get("/api/ai/ops/outbox").status_code == 401
    assert client.get(
        "/api/ai/ops/outbox", headers={"X-DevMemo-Ops-Token": "wrong"}
    ).status_code == 401
    assert client.get(
        "/api/ai/ops/outbox", headers={"X-DevMemo-Ops-Token": "ops-secret"}
    ).status_code == 200
    assert client.post("/api/ai/ops/outbox/missing/retry").status_code == 401
    assert client.post(
        "/api/ai/ops/outbox/missing/retry",
        headers={"X-DevMemo-Ops-Token": "ops-secret"},
    ).status_code == 404
    assert client.get("/api/ai/ops/alerts").status_code == 401
    assert client.get(
        "/api/ai/ops/alerts",
        headers={"X-DevMemo-Ops-Token": "ops-secret"},
    ).status_code == 200
    assert client.get("/api/ai/ops/outbox/retention-preview").status_code == 401
    assert client.get(
        "/api/ai/ops/outbox/retention-preview",
        headers={"X-DevMemo-Ops-Token": "ops-secret"},
    ).status_code == 200
    assert client.post(
        "/api/ai/ops/outbox/retention-cleanup",
        json={
            "approval_id": "auth-check",
            "cutoff": "2025-01-01T00:00:00Z",
            "candidate_ids": ["event-1"],
            "preview_limit": 1,
        },
    ).status_code == 401
    assert client.get("/api/ai/ops/outbox/cleanup-audits").status_code == 401


def test_ops_error_summary_is_single_line_and_bounded(monkeypatch, tmp_path):
    monkeypatch.setenv("AI_NOTES_DB", str(tmp_path / "ops-errors.db"))
    monkeypatch.delenv("AI_OPS_TOKEN", raising=False)
    long_error = "summary unavailable: " + "sensitive-detail " * 30

    async def broken_summary(request):
        raise RuntimeError(long_error)

    monkeypatch.setattr(main, "summarize", broken_summary)
    response = client.post(
        "/api/integrations/memos/webhook",
        json={
            "eventId": "event-error-summary-1",
            "activityType": "memos.memo.created",
            "memo": {"uid": "memo-error-summary", "content": "content"},
        },
    )
    assert response.status_code == 200

    output = client.get("/api/ai/ops/outbox").json()
    item_error = output["items"][0]["last_error"]
    recent_error = output["recent_errors"][0]["last_error"]
    assert len(item_error) <= 240
    assert len(recent_error) <= 240
    assert "\n" not in item_error
    assert item_error.endswith("…")
    assert recent_error == item_error


def test_retention_preview_is_read_only(monkeypatch, tmp_path):
    database = tmp_path / "retention-preview.db"
    monkeypatch.setenv("AI_NOTES_DB", str(database))
    monkeypatch.delenv("AI_OPS_TOKEN", raising=False)
    response = client.post(
        "/api/integrations/memos/webhook",
        json={
            "eventId": "event-retention-preview-1",
            "activityType": "memos.memo.created",
            "memo": {"uid": "memo-retention", "content": "retention"},
        },
    )
    assert response.status_code == 200
    with sqlite3.connect(database) as connection:
        connection.execute(
            "UPDATE webhook_events SET updated_at = '2020-01-01T00:00:00+00:00' WHERE event_id = ?",
            ("event-retention-preview-1",),
        )

    preview = client.get("/api/ai/ops/outbox/retention-preview?older_than_days=30")

    assert preview.status_code == 200
    assert preview.json()["count"] == 1
    preview_body = preview.json()
    assert preview_body["candidate_ids"] == ["event-retention-preview-1"]
    assert preview_body["candidates"][0]["event_id"] == "event-retention-preview-1"
    assert "payload" not in preview.json()["candidates"][0]
    current = client.get("/api/ai/ops/outbox").json()
    assert current["count"] == 1
    assert current["items"][0]["status"] == "processed"


def test_alert_export_is_empty_for_missing_database(monkeypatch, tmp_path):
    monkeypatch.setenv("AI_NOTES_DB", str(tmp_path / "empty-alerts.db"))
    monkeypatch.delenv("AI_OPS_TOKEN", raising=False)

    alerts = client.get("/api/ai/ops/alerts")
    preview = client.get("/api/ai/ops/outbox/retention-preview")
    audits = client.get("/api/ai/ops/outbox/cleanup-audits")

    assert alerts.json() == {
        "has_alert": False,
        "failed_count": 0,
        "exhausted_count": 0,
        "alert_count": 0,
        "alerts": [],
    }
    assert preview.json() == {
        "older_than_days": 30,
        "cutoff": preview.json()["cutoff"],
        "preview_limit": 100,
        "count": 0,
        "candidate_ids": [],
        "candidates": [],
    }
    assert audits.json() == {"items": [], "count": 0}


def test_cleanup_requires_confirmation_protects_pending_and_is_idempotent(monkeypatch, tmp_path):
    database = tmp_path / "retention-cleanup.db"
    monkeypatch.setenv("AI_NOTES_DB", str(database))
    monkeypatch.delenv("AI_OPS_TOKEN", raising=False)
    created = client.post(
        "/api/integrations/memos/webhook",
        json={
            "eventId": "event-cleanup-1",
            "activityType": "memos.memo.created",
            "memo": {"uid": "memo-cleanup", "content": "cleanup"},
        },
    )
    assert created.status_code == 200
    second = client.post(
        "/api/integrations/memos/webhook",
        json={
            "eventId": "event-cleanup-2",
            "activityType": "memos.memo.created",
            "memo": {"uid": "memo-cleanup-2", "content": "cleanup"},
        },
    )
    assert second.status_code == 200

    with sqlite3.connect(database) as connection:
        connection.execute(
            "UPDATE webhook_events SET updated_at = '2020-01-01T00:00:00+00:00' "
            "WHERE event_id = 'event-cleanup-1'"
        )
        connection.execute(
            "UPDATE webhook_events SET updated_at = '2020-01-02T00:00:00+00:00' "
            "WHERE event_id = 'event-cleanup-2'"
        )
        connection.execute(
            "INSERT INTO webhook_events "
            "(event_id, event_type, payload, status, attempts, max_attempts, created_at, updated_at) "
            "VALUES ('event-pending-cleanup', 'memo.created', '{}', 'pending', 0, 3, "
            "'2020-01-01T00:00:00+00:00', '2020-01-01T00:00:00+00:00')"
        )

    preview = client.get(
        "/api/ai/ops/outbox/retention-preview?older_than_days=30&limit=1"
    ).json()
    request = {
        "approval_id": "approval-cleanup-1",
        "cutoff": preview["cutoff"],
        "candidate_ids": preview["candidate_ids"],
        "preview_limit": preview["preview_limit"],
    }
    dry_run = client.post("/api/ai/ops/outbox/retention-cleanup", json=request)
    assert dry_run.status_code == 200
    assert dry_run.json()["executed"] is False
    assert dry_run.json()["deleted_count"] == 0
    assert client.get("/api/ai/ops/outbox").json()["count"] == 3

    unconfirmed = client.post(
        "/api/ai/ops/outbox/retention-cleanup",
        json={**request, "dry_run": False},
    )
    assert unconfirmed.status_code == 409

    out_of_preview = client.post(
        "/api/ai/ops/outbox/retention-cleanup",
        json={
            **request,
            "approval_id": "approval-out-of-preview",
            "candidate_ids": ["event-cleanup-2"],
            "confirm": True,
            "dry_run": False,
        },
    )
    assert out_of_preview.status_code == 409

    pending = client.post(
        "/api/ai/ops/outbox/retention-cleanup",
        json={
            **request,
            "approval_id": "approval-pending-cleanup",
            "candidate_ids": ["event-pending-cleanup"],
            "confirm": True,
            "dry_run": False,
        },
    )
    assert pending.status_code == 409

    executed = client.post(
        "/api/ai/ops/outbox/retention-cleanup",
        headers={"X-DevMemo-Ops-Actor": "local-admin"},
        json={**request, "confirm": True, "dry_run": False},
    )
    assert executed.status_code == 200
    assert executed.json()["deleted_count"] == 1
    assert executed.json()["replayed"] is False
    assert len(executed.json()["actor_digest"]) == 64
    assert "local-admin" not in executed.text

    replay = client.post(
        "/api/ai/ops/outbox/retention-cleanup",
        headers={"X-DevMemo-Ops-Actor": "local-admin"},
        json={**request, "confirm": True, "dry_run": False},
    )
    assert replay.status_code == 200
    assert replay.json()["replayed"] is True
    assert replay.json()["deleted_count"] == 1
    remaining_items = client.get("/api/ai/ops/outbox").json()["items"]
    assert {item["event_id"] for item in remaining_items} == {
        "event-cleanup-2",
        "event-pending-cleanup",
    }

    audits = client.get("/api/ai/ops/outbox/cleanup-audits")
    assert audits.status_code == 200
    assert audits.json()["count"] == 1
    assert audits.json()["items"][0]["approval_id"] == "approval-cleanup-1"
    assert audits.json()["items"][0]["deleted_count"] == 1
    assert audits.json()["items"][0]["actor_digest"] == executed.json()["actor_digest"]
