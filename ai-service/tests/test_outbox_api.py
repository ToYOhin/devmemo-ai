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
    assert response.json()["items"][0]["payload"]["memo"]["uid"] == "memo-outbox"


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
