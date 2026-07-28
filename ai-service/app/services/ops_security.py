"""Optional access control for AI Service operational endpoints."""

from __future__ import annotations

import hmac


def verify_ops_token(provided_token: str | None, configured_token: str) -> bool:
    """Allow local development by default and require an exact configured token."""

    expected = configured_token.strip()
    if not expected:
        return True
    provided = (provided_token or "").strip()
    return bool(provided) and hmac.compare_digest(provided, expected)


def summarize_error(error: str | None, limit: int = 240) -> str | None:
    """Return a bounded single-line error suitable for an ops response."""

    if error is None:
        return None
    normalized = " ".join(error.split())
    if len(normalized) <= limit:
        return normalized
    return f"{normalized[: limit - 1]}…"
