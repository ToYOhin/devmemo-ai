"""Thin HTTP adapters for the supported LLM backends."""

from __future__ import annotations

import os
from dataclasses import dataclass
import json
from typing import Any

import httpx

from app.domain.agent_provider import AgentProviderConfig


MAX_PROVIDER_RESPONSE_BYTES = 1 << 20


@dataclass(frozen=True)
class LLMResult:
    text: str
    provider: str


class DeterministicProvider:
    """Safe local provider used for tests and development without API keys."""

    name = "deterministic"

    async def generate(self, prompt: str) -> LLMResult:
        return LLMResult(text=prompt, provider=self.name)


class OpenAIProvider:
    name = "openai"

    def __init__(self, api_key: str, model: str, base_url: str, timeout: float = 60.0):
        self.api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    async def generate(self, prompt: str) -> LLMResult:
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            payload = await _post_bounded_json(
                client,
                f"{self.base_url}/chat/completions",
                headers={"Authorization": f"Bearer {self.api_key}"},
                payload={
                    "model": self.model,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.2,
                    "response_format": {"type": "json_object"},
                    "max_tokens": 1200,
                },
            )
            content = payload["choices"][0]["message"]["content"]
            return LLMResult(text=content, provider=self.name)


class DeepSeekProvider:
    """Bounded OpenAI-compatible adapter for DeepSeek JSON responses."""

    name = "deepseek"
    max_tokens = 1200

    def __init__(
        self,
        api_key: str,
        model: str = "deepseek-v4-pro",
        base_url: str = "https://api.deepseek.com",
        timeout: float = 60.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.transport = transport

    async def generate(self, prompt: str) -> LLMResult:
        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.2,
            "response_format": {"type": "json_object"},
            "thinking": {"type": "disabled"},
            "max_tokens": self.max_tokens,
        }
        async with httpx.AsyncClient(
            timeout=self.timeout,
            transport=self.transport,
        ) as client:
            for attempt in range(2):
                try:
                    response = await _post_bounded_json(
                        client,
                        f"{self.base_url}/chat/completions",
                        headers={"Authorization": f"Bearer {self.api_key}"},
                        payload=payload,
                    )
                    content = response["choices"][0]["message"]["content"]
                    return LLMResult(text=content, provider=self.name)
                except (httpx.TransportError, httpx.HTTPStatusError) as error:
                    if attempt == 1 or not _is_retryable_deepseek_error(error):
                        raise
        raise RuntimeError("DeepSeek provider retry loop exited unexpectedly")


class OllamaProvider:
    name = "ollama"

    def __init__(self, model: str, base_url: str, timeout: float = 120.0):
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    async def generate(self, prompt: str) -> LLMResult:
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            payload = await _post_bounded_json(
                client,
                f"{self.base_url}/api/generate",
                payload={
                    "model": self.model,
                    "prompt": prompt,
                    "stream": False,
                    "options": {"num_predict": 1200},
                },
            )
            return LLMResult(text=payload["response"], provider=self.name)


async def _post_bounded_json(
    client: httpx.AsyncClient,
    url: str,
    *,
    payload: dict[str, object],
    headers: dict[str, str] | None = None,
) -> Any:
    chunks: list[bytes] = []
    size = 0
    async with client.stream("POST", url, headers=headers, json=payload) as response:
        response.raise_for_status()
        async for chunk in response.aiter_bytes():
            size += len(chunk)
            if size > MAX_PROVIDER_RESPONSE_BYTES:
                raise RuntimeError("Agent provider response exceeded the size limit")
            chunks.append(chunk)
    return json.loads(b"".join(chunks))


def create_provider_from_config(
    config: AgentProviderConfig,
    *,
    timeout: float = 60.0,
) -> DeterministicProvider | OpenAIProvider | DeepSeekProvider | OllamaProvider:
    normalized = config.validated()
    provider = normalized.provider
    if provider == "deterministic":
        return DeterministicProvider()
    if provider == "openai":
        return OpenAIProvider(
            api_key=normalized.api_key or "",
            model=normalized.model,
            base_url=normalized.base_url,
            timeout=timeout,
        )
    if provider == "deepseek":
        return DeepSeekProvider(
            api_key=normalized.api_key or "",
            model=normalized.model,
            base_url=normalized.base_url,
            timeout=timeout,
        )
    if provider == "ollama":
        return OllamaProvider(
            model=normalized.model,
            base_url=normalized.base_url,
            timeout=timeout,
        )
    raise RuntimeError(f"Unsupported AI_PROVIDER: {provider}")


def provider_config_from_env() -> AgentProviderConfig:
    provider = os.getenv("AI_PROVIDER", "deterministic").strip().lower()
    if provider == "mock":
        provider = "deterministic"
    if provider == "openai":
        api_key = os.getenv("OPENAI_API_KEY", "")
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY is required when AI_PROVIDER=openai")
        return AgentProviderConfig(
            provider=provider,
            model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
            base_url=os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1"),
            api_key=api_key,
            enabled=True,
            allow_real_memo_data=True,
            source="environment",
        ).validated()
    if provider == "deepseek":
        api_key = os.getenv("DEEPSEEK_API_KEY", "")
        if not api_key:
            raise RuntimeError("DEEPSEEK_API_KEY is required when AI_PROVIDER=deepseek")
        return AgentProviderConfig(
            provider=provider,
            model=os.getenv("DEEPSEEK_MODEL", "deepseek-v4-pro"),
            base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
            api_key=api_key,
            enabled=True,
            allow_real_memo_data=True,
            source="environment",
        ).validated()
    if provider == "ollama":
        return AgentProviderConfig(
            provider=provider,
            model=os.getenv("OLLAMA_MODEL", "llama3.2"),
            base_url=os.getenv("OLLAMA_BASE_URL", "http://ollama:11434"),
            api_key=None,
            enabled=True,
            allow_real_memo_data=True,
            source="environment",
        ).validated()
    if provider != "deterministic":
        raise RuntimeError(f"Unsupported AI_PROVIDER: {provider}")
    return AgentProviderConfig(
        provider="deterministic",
        model="",
        base_url="",
        api_key=None,
        enabled=True,
        allow_real_memo_data=False,
        source="environment",
    ).validated()


def create_provider() -> DeterministicProvider | OpenAIProvider | DeepSeekProvider | OllamaProvider:
    return create_provider_from_config(provider_config_from_env())


def _is_retryable_deepseek_error(
    error: httpx.TransportError | httpx.HTTPStatusError,
) -> bool:
    if isinstance(error, httpx.TransportError):
        return True
    status_code = error.response.status_code
    return status_code in {408, 429} or status_code >= 500
