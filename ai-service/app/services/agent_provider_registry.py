"""Dynamic Agent provider resolution and synthetic connection verification."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, replace
import json
from pathlib import Path
from threading import Lock
from time import monotonic
from typing import Callable, Protocol

from app.adapters.agent_provider_store import SQLiteAgentProviderStore
from app.domain.agent_provider import (
    AGENT_PROVIDER_CONFIG_VERSION,
    AgentProviderConfig,
    AgentProviderConfigError,
    masked_api_key,
)
from llm import create_provider_from_config, provider_config_from_env


class AgentProviderRuntimeError(RuntimeError):
    """Raised when the selected Agent provider cannot be used safely."""


class ProviderResult(Protocol):
    @property
    def text(self) -> str: ...


class Provider(Protocol):
    @property
    def name(self) -> str: ...

    async def generate(self, prompt: str) -> ProviderResult: ...


@dataclass(frozen=True)
class AgentProviderView:
    version: str
    provider: str
    model: str
    base_url: str
    enabled: bool
    allow_real_memo_data: bool
    api_key_set: bool
    api_key_hint: str
    config_version: int
    source: str


@dataclass(frozen=True)
class AgentProviderTestResult:
    status: str
    provider: str
    model: str
    latency_ms: int


ProviderFactory = Callable[[AgentProviderConfig], Provider]


class AgentProviderRegistry:
    def __init__(
        self,
        database: str | Path,
        internal_secret: str,
        *,
        provider_factory: ProviderFactory | None = None,
        timeout_seconds: float = 20.0,
    ) -> None:
        if timeout_seconds <= 0 or timeout_seconds > 60:
            raise ValueError("invalid Agent provider timeout")
        self._store = SQLiteAgentProviderStore(database, internal_secret)
        self._provider_factory = provider_factory or self._default_provider_factory
        self._timeout_seconds = timeout_seconds
        self._cached_config: AgentProviderConfig | None = None
        self._cached_key: tuple[str, int, str, str, bool] | None = None
        self._cached_provider: Provider | None = None
        self._last_test_started_at: float | None = None
        self._update_lock = Lock()
        self._test_lock = Lock()

    def view(self) -> AgentProviderView:
        return _view(self._current_config())

    def update(self, config: AgentProviderConfig, *, preserve_api_key: bool) -> AgentProviderView:
        with self._update_lock:
            if preserve_api_key:
                current = self._current_config()
                if current.provider == config.provider and current.api_key:
                    config = replace(config, api_key=current.api_key)
                    preserve_api_key = False
                elif not config.enabled:
                    preserve_api_key = False
            saved = self._store.save(config, preserve_api_key=preserve_api_key)
            self._cached_config = saved
            self._cached_key = None
            self._cached_provider = None
            return _view(saved)

    def provider_for_agent(self) -> Provider:
        config = self._effective_config(require_real_memo_consent=True)
        return self._provider(config)

    def dynamic_provider(self) -> Provider:
        return _DynamicProvider(self)

    async def test_connection(self) -> AgentProviderTestResult:
        now = monotonic()
        with self._test_lock:
            if self._last_test_started_at is not None and now - self._last_test_started_at < 5:
                raise AgentProviderRuntimeError("Agent provider connection test is rate limited")
            self._last_test_started_at = now
        config = self._effective_config(require_real_memo_consent=False)
        if config.provider == "deterministic":
            return AgentProviderTestResult("ok", config.provider, config.model, 0)
        provider = self._provider(config)
        prompt = (
            "This is a synthetic connection test. Do not use external context. Return only "
            '{"version":"agent-provider-test-v1","status":"ok"}.'
        )
        started = monotonic()
        try:
            result = await provider.generate(prompt)
            payload = json.loads(result.text)
        except Exception as error:
            raise AgentProviderRuntimeError("Agent provider connection test failed") from error
        if payload != {"version": "agent-provider-test-v1", "status": "ok"}:
            raise AgentProviderRuntimeError("Agent provider connection test failed")
        return AgentProviderTestResult(
            status="ok",
            provider=config.provider,
            model=config.model,
            latency_ms=max(0, round((monotonic() - started) * 1000)),
        )

    def _current_config(self) -> AgentProviderConfig:
        if self._cached_config is None:
            stored = self._store.load()
            self._cached_config = stored if stored is not None else provider_config_from_env()
        return self._cached_config

    def _effective_config(self, *, require_real_memo_consent: bool) -> AgentProviderConfig:
        config = self._current_config()
        if not config.enabled:
            return AgentProviderConfig(
                provider="deterministic",
                model="",
                base_url="",
                api_key=None,
                enabled=True,
                allow_real_memo_data=False,
                config_version=config.config_version,
                source=config.source,
            ).validated()
        if require_real_memo_consent and config.provider != "deterministic" and not config.allow_real_memo_data:
            raise AgentProviderRuntimeError("external Agent provider data use is not enabled")
        return config

    def _provider(self, config: AgentProviderConfig) -> Provider:
        cache_key = (
            config.source,
            config.config_version,
            config.provider,
            config.model,
            config.enabled,
        )
        if self._cached_key != cache_key or self._cached_provider is None:
            try:
                delegate = self._provider_factory(config)
            except (AgentProviderConfigError, RuntimeError) as error:
                raise AgentProviderRuntimeError("Agent provider is unavailable") from error
            self._cached_key = cache_key
            self._cached_provider = _TimeoutProvider(delegate, self._timeout_seconds)
        return self._cached_provider

    def _default_provider_factory(self, config: AgentProviderConfig) -> Provider:
        return create_provider_from_config(config, timeout=self._timeout_seconds)


class _TimeoutProvider:
    def __init__(self, delegate: Provider, timeout_seconds: float) -> None:
        self._delegate = delegate
        self._timeout_seconds = timeout_seconds
        self.name = delegate.name

    async def generate(self, prompt: str) -> ProviderResult:
        try:
            return await asyncio.wait_for(
                self._delegate.generate(prompt),
                timeout=self._timeout_seconds,
            )
        except TimeoutError as error:
            raise AgentProviderRuntimeError("Agent provider timed out") from error


class _DynamicProvider:
    def __init__(self, registry: AgentProviderRegistry) -> None:
        self._registry = registry

    @property
    def name(self) -> str:
        return self._registry.provider_for_agent().name

    async def generate(self, prompt: str) -> ProviderResult:
        return await self._registry.provider_for_agent().generate(prompt)


def _view(config: AgentProviderConfig) -> AgentProviderView:
    return AgentProviderView(
        version=AGENT_PROVIDER_CONFIG_VERSION,
        provider=config.provider,
        model=config.model,
        base_url=config.base_url,
        enabled=config.enabled,
        allow_real_memo_data=config.allow_real_memo_data,
        api_key_set=bool(config.api_key),
        api_key_hint=masked_api_key(config.api_key),
        config_version=config.config_version,
        source=config.source,
    )
