"""Strict internal contract for Agent provider administration."""

from __future__ import annotations

from dataclasses import asdict
import json

from app.domain.agent_provider import (
    AGENT_PROVIDER_CONFIG_VERSION,
    AgentProviderConfig,
    AgentProviderConfigError,
)
from app.services.agent_provider_registry import AgentProviderRegistry


INTERNAL_AGENT_PROVIDER_PATH = "/internal/ai/agent/provider"
INTERNAL_AGENT_PROVIDER_TEST_PATH = "/internal/ai/agent/provider/test"


class AgentProviderAPIError(ValueError):
    """Raised for invalid provider-admin requests without echoing sensitive input."""


class AgentProviderAPI:
    def __init__(self, registry: AgentProviderRegistry) -> None:
        self._registry = registry

    def get(self) -> dict[str, object]:
        return asdict(self._registry.view())

    def update(self, body: bytes) -> dict[str, object]:
        try:
            payload = json.loads(body)
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise AgentProviderAPIError("invalid Agent provider request") from error
        required = {
            "version",
            "provider",
            "model",
            "base_url",
            "enabled",
            "allow_real_memo_data",
        }
        if (
            not isinstance(payload, dict)
            or not required.issubset(payload)
            or not set(payload).issubset(required | {"api_key"})
        ):
            raise AgentProviderAPIError("invalid Agent provider request")
        if payload["version"] != AGENT_PROVIDER_CONFIG_VERSION:
            raise AgentProviderAPIError("invalid Agent provider request")
        api_key = payload.get("api_key")
        if api_key is not None and not isinstance(api_key, str):
            raise AgentProviderAPIError("invalid Agent provider request")
        try:
            config = AgentProviderConfig(
                provider=_required_string(payload, "provider"),
                model=_required_string(payload, "model", allow_empty=True),
                base_url=_required_string(payload, "base_url", allow_empty=True),
                api_key=api_key or None,
                enabled=_required_bool(payload, "enabled"),
                allow_real_memo_data=_required_bool(payload, "allow_real_memo_data"),
            )
            preserve_api_key = not bool(api_key) and config.provider.strip().lower() != "deterministic"
            view = self._registry.update(config, preserve_api_key=preserve_api_key)
        except AgentProviderConfigError as error:
            raise AgentProviderAPIError(str(error)) from error
        return asdict(view)

    async def test(self, body: bytes) -> dict[str, object]:
        try:
            payload = json.loads(body or b"{}")
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise AgentProviderAPIError("invalid Agent provider test request") from error
        if payload != {"version": AGENT_PROVIDER_CONFIG_VERSION}:
            raise AgentProviderAPIError("invalid Agent provider test request")
        return asdict(await self._registry.test_connection())


def _required_string(payload: dict[str, object], key: str, *, allow_empty: bool = False) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or (not allow_empty and not value.strip()):
        raise AgentProviderAPIError("invalid Agent provider request")
    return value


def _required_bool(payload: dict[str, object], key: str) -> bool:
    value = payload.get(key)
    if type(value) is not bool:
        raise AgentProviderAPIError("invalid Agent provider request")
    return value
