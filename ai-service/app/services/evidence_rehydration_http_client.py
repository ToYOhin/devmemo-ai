"""Opt-in single-host HTTP client for evidence rehydration."""

from __future__ import annotations

import secrets
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from datetime import datetime, timezone

import httpx

from app.domain.evidence_rehydration import (
    CONTENT_REHYDRATION_PATH,
    ContentRehydrationFailure,
    ContentRehydrationRequest,
    ContentRehydrationResponse,
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
    REHYDRATION_TIMEOUT_SECONDS,
    PreparedRehydrationResponse,
    RehydrationReplayStore,
    RehydrationResponseHeaders,
    RehydrationTransportError,
    parse_rehydration_response,
    prepare_rehydration_request,
)
from app.settings import AiSettings


_CONTENT_TYPE = "application/json"
_CACHE_CONTROL = "no-store"


class EvidenceRehydrationHTTPClient:
    """One-attempt client owning its injected async transport."""

    def __init__(
        self,
        *,
        base_url: str,
        secret: str,
        transport: httpx.AsyncBaseTransport,
        clock: Callable[[], datetime] | None = None,
        nonce_source: Callable[[], str] | None = None,
        response_replay_store: RehydrationReplayStore | None = None,
    ) -> None:
        if (
            not isinstance(base_url, str)
            or not base_url
            or not isinstance(secret, str)
            or not secret
            or not isinstance(transport, httpx.AsyncBaseTransport)
        ):
            raise RehydrationTransportError
        self._secret = secret
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._nonce_source = nonce_source or (lambda: secrets.token_urlsafe(24))
        self._response_replay_store = (
            response_replay_store or RehydrationReplayStore()
        )
        self._client = httpx.AsyncClient(
            base_url=base_url,
            transport=transport,
            timeout=httpx.Timeout(REHYDRATION_TIMEOUT_SECONDS),
            follow_redirects=False,
        )

    @property
    def is_closed(self) -> bool:
        return self._client.is_closed

    async def rehydrate(
        self,
        request: ContentRehydrationRequest,
    ) -> ContentRehydrationResponse | ContentRehydrationFailure:
        if self._client.is_closed:
            raise RehydrationTransportError
        try:
            started_at = self._require_utc_clock()
            nonce = self._nonce_source()
            prepared = prepare_rehydration_request(
                request,
                int(started_at.timestamp()),
                nonce,
                self._secret,
            )
            outbound = self._client.build_request(
                "POST",
                CONTENT_REHYDRATION_PATH,
                content=prepared.body,
                headers={
                    "Content-Type": _CONTENT_TYPE,
                    REHYDRATION_REQUEST_SIGNATURE_HEADER: prepared.headers.signature,
                    REHYDRATION_REQUEST_TIMESTAMP_HEADER: prepared.headers.timestamp,
                    REHYDRATION_REQUEST_NONCE_HEADER: prepared.headers.nonce,
                    REHYDRATION_REQUEST_VERSION_HEADER: prepared.headers.version,
                },
            )
            response = await self._client.send(outbound, stream=True)
            try:
                response_body = await _read_bounded_response(response)
                response_headers = _exact_response_headers(response)
                status_code = response.status_code
            finally:
                await response.aclose()
            return parse_rehydration_response(
                PreparedRehydrationResponse(
                    status_code=status_code,
                    body=response_body,
                    headers=response_headers,
                ),
                request,
                prepared.headers.nonce,
                self._secret,
                self._require_utc_clock(),
                self._response_replay_store,
            )
        except RehydrationTransportError:
            raise
        except Exception:
            raise RehydrationTransportError from None

    async def aclose(self) -> None:
        await self._client.aclose()

    def _require_utc_clock(self) -> datetime:
        value = self._clock()
        if not isinstance(value, datetime) or value.tzinfo is None:
            raise RehydrationTransportError
        return value.astimezone(timezone.utc)


async def _read_bounded_response(response: httpx.Response) -> bytes:
    if response.status_code not in {200, 503}:
        raise RehydrationTransportError
    content_length = response.headers.get_list("Content-Length")
    if len(content_length) > 1:
        raise RehydrationTransportError
    if content_length:
        try:
            declared_length = int(content_length[0])
        except ValueError:
            raise RehydrationTransportError from None
        if declared_length < 1 or declared_length > MAX_REHYDRATION_RESPONSE_BYTES:
            raise RehydrationTransportError
    body = bytearray()
    async for chunk in response.aiter_bytes():
        body.extend(chunk)
        if len(body) > MAX_REHYDRATION_RESPONSE_BYTES:
            raise RehydrationTransportError
    if not body:
        raise RehydrationTransportError
    return bytes(body)


def _exact_response_headers(response: httpx.Response) -> RehydrationResponseHeaders:
    expected = {
        "Content-Type": _CONTENT_TYPE,
        "Cache-Control": _CACHE_CONTROL,
        REHYDRATION_RESPONSE_SIGNATURE_HEADER: None,
        REHYDRATION_RESPONSE_TIMESTAMP_HEADER: None,
        REHYDRATION_RESPONSE_NONCE_HEADER: None,
        REHYDRATION_RESPONSE_VERSION_HEADER: None,
    }
    values: dict[str, str] = {}
    for name, exact in expected.items():
        matches = response.headers.get_list(name)
        if len(matches) != 1 or (exact is not None and matches[0] != exact):
            raise RehydrationTransportError
        values[name] = matches[0]
    return RehydrationResponseHeaders(
        signature=values[REHYDRATION_RESPONSE_SIGNATURE_HEADER],
        timestamp=values[REHYDRATION_RESPONSE_TIMESTAMP_HEADER],
        request_nonce=values[REHYDRATION_RESPONSE_NONCE_HEADER],
        version=values[REHYDRATION_RESPONSE_VERSION_HEADER],
    )


@asynccontextmanager
async def evidence_rehydration_client_lifespan(
    settings: AiSettings,
    *,
    transport_factory: Callable[[], httpx.AsyncBaseTransport] | None = None,
) -> AsyncIterator[EvidenceRehydrationHTTPClient | None]:
    """Create and deterministically close the opt-in client."""

    if not settings.agent_rehydration_enabled:
        yield None
        return
    if (
        settings.agent_rehydration_memos_url is None
        or settings.agent_rehydration_secret_current is None
    ):
        raise RehydrationTransportError
    factory = transport_factory or (lambda: httpx.AsyncHTTPTransport(retries=0))
    transport = factory()
    try:
        client = EvidenceRehydrationHTTPClient(
            base_url=settings.agent_rehydration_memos_url,
            secret=settings.agent_rehydration_secret_current,
            transport=transport,
        )
    except Exception:
        await transport.aclose()
        raise
    try:
        yield client
    finally:
        await client.aclose()
