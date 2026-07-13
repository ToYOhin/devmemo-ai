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
