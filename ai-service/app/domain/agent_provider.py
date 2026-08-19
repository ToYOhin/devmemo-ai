"""Validated, provider-neutral Agent runtime configuration."""

from __future__ import annotations

from dataclasses import dataclass
import re
from urllib.parse import urlparse


AGENT_PROVIDER_CONFIG_VERSION = "agent-provider-config-v1"
SUPPORTED_AGENT_PROVIDERS = frozenset({"deterministic", "openai", "deepseek", "ollama"})
_MODEL_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}$")


class AgentProviderConfigError(ValueError):
    """Raised when an Agent provider setting is unsafe or incomplete."""


@dataclass(frozen=True)
class AgentProviderConfig:
    provider: str
    model: str
    base_url: str
    api_key: str | None
    enabled: bool
    allow_real_memo_data: bool
    config_version: int = 0
    source: str = "stored"

    def validated(self) -> AgentProviderConfig:
        provider = self.provider.strip().lower()
        model = self.model.strip()
        base_url = self.base_url.strip().rstrip("/")
        api_key = self.api_key.strip() if self.api_key is not None else None
        if provider not in SUPPORTED_AGENT_PROVIDERS:
            raise AgentProviderConfigError("unsupported Agent provider")
        if type(self.enabled) is not bool or type(self.allow_real_memo_data) is not bool:
            raise AgentProviderConfigError("invalid Agent provider flags")
        if type(self.config_version) is not int or self.config_version < 0:
            raise AgentProviderConfigError("invalid Agent provider config version")
        if self.source not in {"stored", "environment"}:
            raise AgentProviderConfigError("invalid Agent provider config source")
        if api_key is not None and (not api_key or len(api_key) > 4096 or "\n" in api_key or "\r" in api_key):
            raise AgentProviderConfigError("invalid Agent provider credential")

        if provider == "deterministic":
            if model or base_url or api_key:
                raise AgentProviderConfigError("deterministic provider does not accept remote settings")
            if self.allow_real_memo_data:
                raise AgentProviderConfigError("deterministic provider does not require external data consent")
        else:
            if not _MODEL_PATTERN.fullmatch(model):
                raise AgentProviderConfigError("invalid Agent provider model")
            _validate_base_url(provider, base_url, self.source)
            if provider in {"openai", "deepseek"} and self.enabled and not api_key:
                raise AgentProviderConfigError("Agent provider credential is required")
            if provider == "ollama" and api_key:
                raise AgentProviderConfigError("Ollama provider does not accept an API key")

        return AgentProviderConfig(
            provider=provider,
            model=model,
            base_url=base_url,
            api_key=api_key,
            enabled=self.enabled,
            allow_real_memo_data=self.allow_real_memo_data,
            config_version=self.config_version,
            source=self.source,
        )


def _validate_base_url(provider: str, value: str, source: str) -> None:
    try:
        parsed = urlparse(value)
        port = parsed.port
    except ValueError as error:
        raise AgentProviderConfigError("invalid Agent provider base URL") from error
    if (
        not parsed.scheme
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or (parsed.path not in {"", "/", "/v1"})
    ):
        raise AgentProviderConfigError("invalid Agent provider base URL")
    if provider in {"openai", "deepseek"} and parsed.scheme != "https":
        raise AgentProviderConfigError("remote Agent providers require HTTPS")
    if source == "stored":
        approved_hosts = {
            "openai": "api.openai.com",
            "deepseek": "api.deepseek.com",
        }
        if provider in approved_hosts and parsed.hostname != approved_hosts[provider]:
            raise AgentProviderConfigError("Agent provider host is not approved")
    if provider == "ollama":
        if parsed.scheme != "http" or parsed.hostname not in {"localhost", "127.0.0.1", "::1", "ollama"}:
            raise AgentProviderConfigError("Ollama must use an approved local endpoint")
        if port not in {None, 11434}:
            raise AgentProviderConfigError("Ollama must use its local service port")


def masked_api_key(api_key: str | None) -> str:
    if not api_key:
        return ""
    suffix = api_key[-4:] if len(api_key) >= 4 else api_key
    return f"••••{suffix}"
