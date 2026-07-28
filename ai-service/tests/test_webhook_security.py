import pytest

from app.services.webhook_security import sign_payload, verify_signature


def test_sign_and_verify_payload():
    payload = b'{"event":"memo.created"}'

    signature = sign_payload(payload, "test-secret")

    assert signature.startswith("sha256=")
    assert verify_signature(payload, signature, "test-secret") is True
    assert verify_signature(payload + b" ", signature, "test-secret") is False
    assert verify_signature(payload, signature, "other-secret") is False


@pytest.mark.parametrize("signature", [None, "", "sha1=abc", "sha256=bad"])
def test_verify_rejects_invalid_signature_when_secret_is_configured(signature):
    assert verify_signature(b"payload", signature, "test-secret") is False


def test_verify_keeps_legacy_compatibility_when_secret_is_not_configured():
    assert verify_signature(b"payload", None, "") is True
    assert verify_signature(b"payload", "not-used", "") is True


def test_sign_rejects_empty_secret():
    with pytest.raises(ValueError, match="must not be empty"):
        sign_payload(b"payload", "")
