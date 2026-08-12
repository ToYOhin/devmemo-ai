"""Thin HTTP adapters for the supported LLM backends."""

from __future__ import annotations

import os
from dataclasses import dataclass

import httpx


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
            response = await client.post(
                f"{self.base_url}/chat/completions",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={
                    "model": self.model,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.2,
                    "response_format": {"type": "json_object"},
                },
            )
            response.raise_for_status()
            content = response.json()["choices"][0]["message"]["content"]
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
                    response = await client.post(
                        f"{self.base_url}/chat/completions",
                        headers={"Authorization": f"Bearer {self.api_key}"},
                        json=payload,
                    )
                    response.raise_for_status()
                    content = response.json()["choices"][0]["message"]["content"]
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
            response = await client.post(
                f"{self.base_url}/api/generate",
                json={"model": self.model, "prompt": prompt, "stream": False},
            )
            response.raise_for_status()
            return LLMResult(text=response.json()["response"], provider=self.name)


def create_provider() -> (
    DeterministicProvider | OpenAIProvider | DeepSeekProvider | OllamaProvider
):
    provider = os.getenv("AI_PROVIDER", "deterministic").lower()
    if provider in {"deterministic", "mock"}:
        return DeterministicProvider()
    if provider == "openai":
        api_key = os.getenv("OPENAI_API_KEY", "")
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY is required when AI_PROVIDER=openai")
        return OpenAIProvider(
            api_key=api_key,
            model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
            base_url=os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1"),
        )
    if provider == "deepseek":
        api_key = os.getenv("DEEPSEEK_API_KEY", "")
        if not api_key:
            raise RuntimeError(
                "DEEPSEEK_API_KEY is required when AI_PROVIDER=deepseek"
            )
        return DeepSeekProvider(
            api_key=api_key,
            model=os.getenv("DEEPSEEK_MODEL", "deepseek-v4-pro"),
            base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
        )
    if provider == "ollama":
        return OllamaProvider(
            model=os.getenv("OLLAMA_MODEL", "llama3.2"),
            base_url=os.getenv("OLLAMA_BASE_URL", "http://ollama:11434"),
        )
    raise RuntimeError(f"Unsupported AI_PROVIDER: {provider}")


def _is_retryable_deepseek_error(
    error: httpx.TransportError | httpx.HTTPStatusError,
) -> bool:
    if isinstance(error, httpx.TransportError):
        return True
    status_code = error.response.status_code
    return status_code in {408, 429} or status_code >= 500
