"""Exercise the public-chunk gateway boundary without a deployment.

This local contract smoke represents a trusted gateway by signing exact raw
JSON bodies in-process. It never starts a server, contacts a network service,
or prints its temporary signing secret. A passing result is contract evidence,
not proof of a deployed gateway rollout.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from fastapi.testclient import TestClient

import main
from app.domain.retrieval import ChunkCitation, ChunkRetrievalResult
from app.services.webhook_security import sign_payload


_SECRET = "local-gateway-contract-secret"
_SIGNATURE_HEADER = "X-DevMemo-Chunk-Signature"


def run_gateway_contract_smoke() -> dict[str, int]:
    """Return only status-code evidence for the trusted-gateway contract."""

    fixture = _fixture()
    request = fixture["request"]
    client = TestClient(main.app)
    evidence: dict[str, int] = {}

    with patch.dict(os.environ, {}, clear=False):
        os.environ.pop("AI_PUBLIC_CHUNK_RETRIEVAL", None)
        os.environ.pop("AI_PUBLIC_CHUNK_SECRET", None)
        evidence["disabled"] = client.post("/api/ai/v1/chunks/search", json=request).status_code

    with patch.dict(
        os.environ,
        {"AI_PUBLIC_CHUNK_RETRIEVAL": "true", "AI_PUBLIC_CHUNK_SECRET": _SECRET},
        clear=False,
    ):
        evidence["missing_signature"] = client.post(
            "/api/ai/v1/chunks/search", json=request
        ).status_code

        raw_body, headers = _signed_request(request)
        evidence["tampered_body"] = client.post(
            "/api/ai/v1/chunks/search",
            content=raw_body.replace(b"Docker", b"docker"),
            headers=headers,
        ).status_code

        duplicate_scope = {**request, "visible_memo_ids": ["memo-a", "memo-a"]}
        duplicate_body, duplicate_headers = _signed_request(duplicate_scope)
        evidence["ambiguous_scope"] = client.post(
            "/api/ai/v1/chunks/search", content=duplicate_body, headers=duplicate_headers
        ).status_code

        with patch.object(main, "chunk_lifecycle_coordinator", _coordinator(available=False)):
            evidence["degraded_store"] = client.post(
                "/api/ai/v1/chunks/search", content=raw_body, headers=headers
            ).status_code

        with patch.object(main, "chunk_lifecycle_coordinator", _coordinator(available=True)):
            response = client.post(
                "/api/ai/v1/chunks/search", content=raw_body, headers=headers
            )
        evidence["authorized_redacted_deduplicated"] = response.status_code

    if evidence != {
        "disabled": 503,
        "missing_signature": 401,
        "tampered_body": 401,
        "ambiguous_scope": 422,
        "degraded_store": 503,
        "authorized_redacted_deduplicated": 200,
    }:
        raise RuntimeError(f"public chunk gateway contract smoke failed: {evidence}")
    if response.json() != fixture["response"] or "private" in response.text:
        raise RuntimeError("public chunk gateway response was not redacted and deterministic")
    return evidence


def _fixture() -> dict[str, object]:
    path = Path(__file__).resolve().parents[2] / "contracts" / "public-chunk-v1.json"
    return json.loads(path.read_text(encoding="utf-8"))


def _signed_request(payload: object) -> tuple[bytes, dict[str, str]]:
    raw_body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    return raw_body, {
        "Content-Type": "application/json",
        _SIGNATURE_HEADER: sign_payload(raw_body, _SECRET),
    }


def _coordinator(*, available: bool) -> SimpleNamespace:
    return SimpleNamespace(
        provider=SimpleNamespace(name="deterministic"),
        health=lambda: SimpleNamespace(
            available=available,
            status="ready" if available else "degraded",
            provider="controlled-local",
        ),
        retrieve=lambda question, limit: ChunkRetrievalResult(
            context="private context",
            citations=(
                ChunkCitation(
                    memo_id="memo-a",
                    chunk_id="memo-chunk-v1:a:0000",
                    chunk_index=0,
                    index_version="memo-chunk-v1",
                    score=0.91,
                    metadata={"title": "Docker ports", "content": "private duplicate"},
                ),
                ChunkCitation(
                    memo_id="memo-a",
                    chunk_id="memo-chunk-v1:a:0001",
                    chunk_index=1,
                    index_version="memo-chunk-v1",
                    score=0.92,
                    metadata={"title": "Docker ports", "content": "private best chunk"},
                ),
                ChunkCitation(
                    memo_id="memo-b",
                    chunk_id="memo-chunk-v1:b:0000",
                    chunk_index=0,
                    index_version="memo-chunk-v1",
                    score=0.8,
                    metadata={"title": "Proxy setup", "content": "private second memo"},
                ),
                ChunkCitation(
                    memo_id="memo-hidden",
                    chunk_id="memo-chunk-v1:hidden:0000",
                    chunk_index=0,
                    index_version="memo-chunk-v1",
                    score=0.99,
                    metadata={"title": "Hidden", "content": "must not be returned"},
                ),
            ),
        ),
    )


def main_cli() -> int:
    evidence = run_gateway_contract_smoke()
    print("PUBLIC_CHUNK_GATEWAY_CONTRACT_SMOKE_OK")
    print(json.dumps(evidence, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main_cli())
