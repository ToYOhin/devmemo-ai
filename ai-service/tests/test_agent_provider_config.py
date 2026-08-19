from __future__ import annotations

import asyncio
from dataclasses import dataclass
import json
from pathlib import Path
import sqlite3

import pytest

from app.adapters.agent_provider_store import AgentProviderStoreError, SQLiteAgentProviderStore
from app.domain.agent_provider import AgentProviderConfig, AgentProviderConfigError
from app.services.agent_provider_api import AgentProviderAPI, AgentProviderAPIError
from app.services.agent_provider_registry import AgentProviderRegistry, AgentProviderRuntimeError


SECRET = "synthetic-agent-provider-secret-with-enough-entropy"
CONTRACT = Path(__file__).parents[2] / "contracts" / "agent-provider-config-v1.json"


@dataclass(frozen=True)
class _Result:
    text: str


class _Provider:
    def __init__(self, name: str, result: str, *, delay: float = 0) -> None:
        self.name = name
        self._result = result
        self._delay = delay

    async def generate(self, _prompt: str) -> _Result:
        if self._delay:
            await asyncio.sleep(self._delay)
        return _Result(self._result)


def _config(**overrides) -> AgentProviderConfig:
    values = {
        "provider": "openai",
        "model": "gpt-4o-mini",
        "base_url": "https://api.openai.com/v1",
        "api_key": "synthetic-secret-value",
        "enabled": True,
        "allow_real_memo_data": False,
    }
    values.update(overrides)
    return AgentProviderConfig(**values)


def test_shared_agent_provider_contract_is_masked_and_provider_neutral():
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))

    assert contract["version"] == "agent-provider-config-v1"
    assert contract["browser"]["write_only_fields"] == ["api_key"]
    assert "api_key" not in contract["safe_response_fields"]
    assert contract["providers"] == ["deterministic", "openai", "deepseek", "ollama"]
    assert contract["synthetic_test"]["uses_real_memo_data"] is False


def test_encrypted_store_never_persists_plaintext_key(tmp_path):
    database = tmp_path / "agent.db"
    store = SQLiteAgentProviderStore(database, SECRET)

    saved = store.save(_config())
    loaded = store.load()

    assert saved.config_version == 1
    assert loaded == saved
    with sqlite3.connect(database) as connection:
        row = connection.execute("SELECT api_key_nonce, api_key_ciphertext FROM agent_provider_config").fetchone()
    assert row is not None
    assert row[0] != b"synthetic-secret-value"
    assert b"synthetic-secret-value" not in row[1]
    assert b"synthetic-secret-value" not in database.read_bytes()


def test_store_preserves_write_only_key_and_rejects_wrong_master_secret(tmp_path):
    database = tmp_path / "agent.db"
    store = SQLiteAgentProviderStore(database, SECRET)
    store.save(_config())

    updated = store.save(
        _config(api_key=None, model="gpt-4.1-mini"),
        preserve_api_key=True,
    )

    assert updated.api_key == "synthetic-secret-value"
    assert updated.config_version == 2
    with pytest.raises(AgentProviderStoreError):
        SQLiteAgentProviderStore(database, "different-secret").load()


def test_store_authenticates_provider_routing_metadata(tmp_path):
    database = tmp_path / "agent.db"
    store = SQLiteAgentProviderStore(database, SECRET)
    store.save(_config())
    with sqlite3.connect(database) as connection:
        connection.execute(
            "UPDATE agent_provider_config SET base_url = ? WHERE id = 1",
            ("https://attacker.example/v1",),
        )

    with pytest.raises(AgentProviderStoreError):
        store.load()


@pytest.mark.parametrize(
    ("config", "message"),
    [
        (_config(base_url="http://api.openai.com/v1"), "require HTTPS"),
        (_config(base_url="https://user@example.com/v1"), "base URL"),
        (_config(base_url="https://attacker.example/v1"), "host is not approved"),
        (_config(model="bad model"), "model"),
        (
            _config(provider="ollama", model="llama3.2", base_url="http://10.0.0.2:11434", api_key=None),
            "approved local endpoint",
        ),
    ],
)
def test_provider_config_rejects_unsafe_remote_settings(config, message):
    with pytest.raises(AgentProviderConfigError, match=message):
        config.validated()


@pytest.mark.asyncio
async def test_registry_masks_key_and_runs_only_synthetic_connection_test(tmp_path):
    prompts: list[str] = []

    class RecordingProvider(_Provider):
        async def generate(self, prompt: str) -> _Result:
            prompts.append(prompt)
            return await super().generate(prompt)

    registry = AgentProviderRegistry(
        tmp_path / "agent.db",
        SECRET,
        provider_factory=lambda config: RecordingProvider(
            config.provider,
            '{"version":"agent-provider-test-v1","status":"ok"}',
        ),
    )
    view = registry.update(_config(), preserve_api_key=False)

    result = await registry.test_connection()

    assert view.api_key_set is True
    assert view.api_key_hint == "••••alue"
    assert not hasattr(view, "api_key")
    assert result.status == "ok"
    assert len(prompts) == 1
    assert "synthetic connection test" in prompts[0]
    assert "Memo" not in prompts[0]


def test_registry_requires_explicit_real_memo_consent(tmp_path):
    registry = AgentProviderRegistry(
        tmp_path / "agent.db",
        SECRET,
        provider_factory=lambda config: _Provider(config.provider, "{}"),
    )
    registry.update(_config(allow_real_memo_data=False), preserve_api_key=False)

    with pytest.raises(AgentProviderRuntimeError, match="data use is not enabled"):
        registry.provider_for_agent()


def test_registry_can_migrate_environment_key_on_explicit_save(monkeypatch, tmp_path):
    monkeypatch.setenv("AI_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "synthetic-environment-key")
    monkeypatch.setenv("OPENAI_MODEL", "gpt-4o-mini")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
    registry = AgentProviderRegistry(tmp_path / "agent.db", SECRET)

    view = registry.update(_config(api_key=None), preserve_api_key=True)

    assert view.source == "stored"
    assert view.api_key_set is True
    assert view.api_key_hint == "••••-key"


@pytest.mark.asyncio
async def test_registry_enforces_hard_provider_timeout(tmp_path):
    registry = AgentProviderRegistry(
        tmp_path / "agent.db",
        SECRET,
        provider_factory=lambda config: _Provider(config.provider, "{}", delay=0.05),
        timeout_seconds=0.01,
    )
    registry.update(_config(), preserve_api_key=False)

    with pytest.raises(AgentProviderRuntimeError, match="connection test failed"):
        await registry.test_connection()


def test_internal_api_returns_masked_contract_and_preserves_omitted_key(tmp_path):
    registry = AgentProviderRegistry(tmp_path / "agent.db", SECRET)
    api = AgentProviderAPI(registry)
    body = json.dumps(
        {
            "version": "agent-provider-config-v1",
            "provider": "deepseek",
            "model": "deepseek-chat",
            "base_url": "https://api.deepseek.com",
            "api_key": "synthetic-deepseek-key",
            "enabled": True,
            "allow_real_memo_data": True,
        }
    ).encode()

    response = api.update(body)
    response.pop("api_key_hint")
    assert "api_key" not in response
    assert response == {
        "version": "agent-provider-config-v1",
        "provider": "deepseek",
        "model": "deepseek-chat",
        "base_url": "https://api.deepseek.com",
        "enabled": True,
        "allow_real_memo_data": True,
        "api_key_set": True,
        "config_version": 1,
        "source": "stored",
    }
    update_without_key = json.loads(body)
    del update_without_key["api_key"]
    assert api.update(json.dumps(update_without_key).encode())["config_version"] == 2


def test_internal_api_rejects_unknown_or_raw_read_fields(tmp_path):
    api = AgentProviderAPI(AgentProviderRegistry(tmp_path / "agent.db", SECRET))
    with pytest.raises(AgentProviderAPIError):
        api.update(b'{"version":"agent-provider-config-v1","api_key_hint":"leak"}')
