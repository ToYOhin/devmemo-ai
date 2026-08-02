from __future__ import annotations

import asyncio
import json
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path

import httpx
import pytest

from app.domain.evidence_rehydration import (
    CONTENT_REHYDRATION_PATH,
    ContentRehydrationRequest,
    ContentRehydrationResponse,
)
from app.services.evidence_rehydration_http_client import (
    EvidenceRehydrationHTTPClient,
    evidence_rehydration_client_lifespan,
)
from app.services.evidence_rehydration_transport import (
    MAX_REHYDRATION_RESPONSE_BYTES,
    REHYDRATION_REQUEST_NONCE_HEADER,
    REHYDRATION_REQUEST_SIGNATURE_HEADER,
    REHYDRATION_REQUEST_TIMESTAMP_HEADER,
    REHYDRATION_REQUEST_VERSION_HEADER,
    REHYDRATION_RESPONSE_NONCE_HEADER,
    REHYDRATION_RESPONSE_SIGNATURE_HEADER,
    REHYDRATION_RESPONSE_TIMESTAMP_HEADER,
    REHYDRATION_RESPONSE_VERSION_HEADER,
    RehydrationReplayStore,
    RehydrationRequestHeaders,
    RehydrationTransportError,
    prepare_rehydration_response,
    verify_rehydration_request,
)
from app.settings import AiSettings


TIMESTAMP = 1_785_643_200
NOW = datetime.fromtimestamp(TIMESTAMP, timezone.utc)
NONCE = "r5-i11c-http-client-nonce-0001"
SECRET = "synthetic-r5-i11c-rehydration-secret"
CONTRACT_PATH = (
    Path(__file__).resolve().parents[2]
    / "contracts"
    / "memo-evidence-rehydration-v1.json"
)


def _request() -> ContentRehydrationRequest:
    payload = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    return ContentRehydrationRequest.from_dict(payload["request"])


def _response() -> ContentRehydrationResponse:
    payload = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    return ContentRehydrationResponse.from_dict(payload["response"])


class TrackingAsyncTransport(httpx.AsyncBaseTransport):
    def __init__(self, handler: Callable[[httpx.Request], httpx.Response]) -> None:
        self.handler = handler
        self.calls = 0
        self.closed = False

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        self.calls += 1
        return self.handler(request)

    async def aclose(self) -> None:
        self.closed = True


def _signed_response(request: httpx.Request) -> httpx.Response:
    request_value = _request()
    headers = RehydrationRequestHeaders(
        signature=request.headers[REHYDRATION_REQUEST_SIGNATURE_HEADER],
        timestamp=request.headers[REHYDRATION_REQUEST_TIMESTAMP_HEADER],
        nonce=request.headers[REHYDRATION_REQUEST_NONCE_HEADER],
        version=request.headers[REHYDRATION_REQUEST_VERSION_HEADER],
    )
    assert request.method == "POST"
    assert request.url == httpx.URL(
        f"http://memos.invalid{CONTENT_REHYDRATION_PATH}"
    )
    assert request.headers.get_list("Content-Type") == ["application/json"]
    assert verify_rehydration_request(
        request.method,
        request.url.path,
        request.content,
        headers,
        SECRET,
        NOW,
        RehydrationReplayStore(),
    ) == request_value
    prepared = prepare_rehydration_response(
        _response(),
        request_value,
        headers.nonce,
        TIMESTAMP,
        SECRET,
    )
    return httpx.Response(
        prepared.status_code,
        content=prepared.body,
        headers={
            "Content-Type": "application/json",
            "Cache-Control": "no-store",
            REHYDRATION_RESPONSE_SIGNATURE_HEADER: prepared.headers.signature,
            REHYDRATION_RESPONSE_TIMESTAMP_HEADER: prepared.headers.timestamp,
            REHYDRATION_RESPONSE_NONCE_HEADER: prepared.headers.request_nonce,
            REHYDRATION_RESPONSE_VERSION_HEADER: prepared.headers.version,
        },
    )


def _connect_error(request: httpx.Request) -> httpx.Response:
    raise httpx.ConnectError("synthetic unavailable", request=request)


def test_http_client_performs_one_exact_call_and_closes_injected_transport():
    async def scenario() -> None:
        transport = TrackingAsyncTransport(_signed_response)
        client = EvidenceRehydrationHTTPClient(
            base_url="http://memos.invalid",
            secret=SECRET,
            transport=transport,
            clock=lambda: NOW,
            nonce_source=lambda: NONCE,
        )

        result = await client.rehydrate(_request())

        assert result == _response()
        assert transport.calls == 1
        assert not client.is_closed
        await client.aclose()
        assert client.is_closed
        assert transport.closed

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "handler",
    [
        lambda request: httpx.Response(
            302,
            headers={"Location": "http://other.invalid"},
            request=request,
        ),
        lambda request: httpx.Response(
            200,
            content=b"{}",
            headers={"Content-Length": str(MAX_REHYDRATION_RESPONSE_BYTES + 1)},
            request=request,
        ),
        lambda request: httpx.Response(
            200,
            content=b"{}",
            headers=[
                ("Content-Type", "application/json"),
                ("Content-Type", "application/json"),
            ],
            request=request,
        ),
        _connect_error,
    ],
    ids=[
        "redirect",
        "declared oversized",
        "duplicate content type",
        "transport error",
    ],
)
def test_http_client_fails_closed_without_retry(
    handler: Callable[[httpx.Request], httpx.Response],
):
    async def scenario() -> None:
        transport = TrackingAsyncTransport(handler)
        client = EvidenceRehydrationHTTPClient(
            base_url="http://memos.invalid",
            secret=SECRET,
            transport=transport,
            clock=lambda: NOW,
            nonce_source=lambda: NONCE,
        )
        with pytest.raises(RehydrationTransportError):
            await client.rehydrate(_request())
        assert transport.calls == 1
        await client.aclose()
        assert transport.closed

    asyncio.run(scenario())


def test_http_client_uses_one_process_local_response_replay_store():
    async def scenario() -> None:
        transport = TrackingAsyncTransport(_signed_response)
        client = EvidenceRehydrationHTTPClient(
            base_url="http://memos.invalid",
            secret=SECRET,
            transport=transport,
            clock=lambda: NOW,
            nonce_source=lambda: NONCE,
        )

        assert await client.rehydrate(_request()) == _response()
        with pytest.raises(RehydrationTransportError):
            await client.rehydrate(_request())
        assert transport.calls == 2
        await client.aclose()

    asyncio.run(scenario())


def test_client_lifespan_is_disabled_without_transport_and_closes_when_enabled():
    async def scenario() -> None:
        factory_calls = 0

        def disabled_factory() -> httpx.AsyncBaseTransport:
            nonlocal factory_calls
            factory_calls += 1
            return TrackingAsyncTransport(_signed_response)

        async with evidence_rehydration_client_lifespan(
            AiSettings(), transport_factory=disabled_factory
        ) as disabled_client:
            assert disabled_client is None
        assert factory_calls == 0

        transport = TrackingAsyncTransport(_signed_response)
        enabled_settings = AiSettings(
            agent_enabled=True,
            agent_internal_secret="synthetic-delegation-secret",
            agent_rehydration_enabled=True,
            agent_rehydration_secret_current=SECRET,
            agent_rehydration_memos_url="http://memos.invalid",
        )
        async with evidence_rehydration_client_lifespan(
            enabled_settings,
            transport_factory=lambda: transport,
        ) as enabled_client:
            assert enabled_client is not None
            assert not enabled_client.is_closed
        assert enabled_client is not None
        assert enabled_client.is_closed
        assert transport.closed

        invalid_transport = TrackingAsyncTransport(_signed_response)
        invalid_settings = AiSettings(
            agent_enabled=True,
            agent_internal_secret="synthetic-delegation-secret",
            agent_rehydration_enabled=True,
            agent_rehydration_secret_current=SECRET,
            agent_rehydration_memos_url="",
        )
        with pytest.raises(RehydrationTransportError):
            async with evidence_rehydration_client_lifespan(
                invalid_settings,
                transport_factory=lambda: invalid_transport,
            ):
                raise AssertionError("invalid client lifespan must not start")
        assert invalid_transport.closed

    asyncio.run(scenario())
