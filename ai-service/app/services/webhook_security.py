"""Provider-neutral Webhook request signing helpers."""

from __future__ import annotations

import hashlib
import hmac


SIGNATURE_PREFIX = "sha256="


def sign_payload(payload: bytes, secret: str) -> str:
    """Return the canonical SHA-256 HMAC header value for a raw request body."""

    if not secret:
        raise ValueError("webhook signing secret must not be empty")
    digest = hmac.new(secret.encode("utf-8"), payload, hashlib.sha256).hexdigest()
    return f"{SIGNATURE_PREFIX}{digest}"


def verify_signature(payload: bytes, signature: str | None, secret: str) -> bool:
    """Verify a signature without revealing whether its format or digest failed."""

    if not secret:
        return True
    if not signature or not signature.startswith(SIGNATURE_PREFIX):
        return False
    expected = sign_payload(payload, secret)
    return hmac.compare_digest(expected, signature.strip())
