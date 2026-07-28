from fastapi.testclient import TestClient

import main
from app.services.webhook_security import sign_payload


client = TestClient(main.app)


SIGNED_PAYLOAD = b'{"activityType":"memos.memo.created","memo":{"uid":"signed-1","content":"signed memo"}}'


def test_webhook_keeps_legacy_flow_when_secret_is_not_configured(monkeypatch, tmp_path):
    monkeypatch.delenv("AI_WEBHOOK_SECRET", raising=False)
    monkeypatch.setenv("AI_NOTES_DB", str(tmp_path / "legacy.db"))

    response = client.post(
        "/api/integrations/memos/webhook",
        content=SIGNED_PAYLOAD,
        headers={"Content-Type": "application/json"},
    )

    assert response.status_code == 200
    assert response.json()["code"] == 0


def test_webhook_accepts_valid_signature(monkeypatch, tmp_path):
    monkeypatch.setenv("AI_WEBHOOK_SECRET", "test-secret")
    monkeypatch.setenv("AI_NOTES_DB", str(tmp_path / "signed.db"))

    response = client.post(
        "/api/integrations/memos/webhook",
        content=SIGNED_PAYLOAD,
        headers={
            "Content-Type": "application/json",
            "X-DevMemo-Signature": sign_payload(SIGNED_PAYLOAD, "test-secret"),
        },
    )

    assert response.status_code == 200
    assert response.json()["code"] == 0


def test_webhook_rejects_missing_signature_when_secret_is_configured(monkeypatch):
    monkeypatch.setenv("AI_WEBHOOK_SECRET", "test-secret")

    response = client.post(
        "/api/integrations/memos/webhook",
        content=SIGNED_PAYLOAD,
        headers={"Content-Type": "application/json"},
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "invalid webhook signature"


def test_webhook_rejects_tampered_payload(monkeypatch):
    monkeypatch.setenv("AI_WEBHOOK_SECRET", "test-secret")
    tampered_payload = SIGNED_PAYLOAD.replace(b"signed memo", b"tampered memo")

    response = client.post(
        "/api/integrations/memos/webhook",
        content=tampered_payload,
        headers={
            "Content-Type": "application/json",
            "X-DevMemo-Signature": sign_payload(SIGNED_PAYLOAD, "test-secret"),
        },
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "invalid webhook signature"
