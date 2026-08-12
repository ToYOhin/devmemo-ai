import asyncio
import json

import httpx
import pytest

from llm import DeepSeekProvider, create_provider


def test_deepseek_provider_uses_bounded_non_thinking_json_request():
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": '{"answer":"ok"}'}}]},
        )

    provider = DeepSeekProvider(
        "test-key",
        transport=httpx.MockTransport(handler),
    )

    result = asyncio.run(provider.generate("Return one JSON object."))

    assert result.text == '{"answer":"ok"}'
    assert result.provider == "deepseek"
    assert len(requests) == 1
    request = requests[0]
    assert request.url == "https://api.deepseek.com/chat/completions"
    assert request.headers["Authorization"] == "Bearer test-key"
    assert request.read()
    payload = json.loads(request.content)
    assert payload == {
        "model": "deepseek-v4-pro",
        "messages": [{"role": "user", "content": "Return one JSON object."}],
        "temperature": 0.2,
        "response_format": {"type": "json_object"},
        "thinking": {"type": "disabled"},
        "max_tokens": 1200,
    }


@pytest.mark.parametrize("status_code", [408, 429, 500, 503])
def test_deepseek_provider_retries_one_transient_http_failure(status_code: int):
    attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            return httpx.Response(status_code, request=request)
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": '{"answer":"ok"}'}}]},
        )

    provider = DeepSeekProvider("test-key", transport=httpx.MockTransport(handler))

    assert asyncio.run(provider.generate("Return JSON.")).text == '{"answer":"ok"}'
    assert attempts == 2


def test_deepseek_provider_retries_transport_failure_only_once():
    attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        raise httpx.ReadError("incomplete response", request=request)

    provider = DeepSeekProvider("test-key", transport=httpx.MockTransport(handler))

    with pytest.raises(httpx.ReadError, match="incomplete response"):
        asyncio.run(provider.generate("Return JSON."))
    assert attempts == 2


@pytest.mark.parametrize("status_code", [400, 401, 403, 404, 422])
def test_deepseek_provider_does_not_retry_non_transient_http_failure(
    status_code: int,
):
    attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        return httpx.Response(status_code, request=request)

    provider = DeepSeekProvider("test-key", transport=httpx.MockTransport(handler))

    with pytest.raises(httpx.HTTPStatusError):
        asyncio.run(provider.generate("Return JSON."))
    assert attempts == 1


def test_create_provider_requires_deepseek_key(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("AI_PROVIDER", "deepseek")
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)

    with pytest.raises(RuntimeError, match="DEEPSEEK_API_KEY is required"):
        create_provider()


def test_create_provider_reads_deepseek_configuration(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("AI_PROVIDER", "deepseek")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    monkeypatch.setenv("DEEPSEEK_MODEL", "deepseek-v4-flash")
    monkeypatch.setenv("DEEPSEEK_BASE_URL", "https://example.invalid/v1/")

    provider = create_provider()

    assert isinstance(provider, DeepSeekProvider)
    assert provider.api_key == "test-key"
    assert provider.model == "deepseek-v4-flash"
    assert provider.base_url == "https://example.invalid/v1"
