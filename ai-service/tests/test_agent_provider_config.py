from __future__ import annotations

import asyncio
from contextlib import closing
from dataclasses import dataclass
import json
from pathlib import Path
import sqlite3

import pytest

from app.adapters.agent_provider_store import AgentProviderStoreError, SQLiteAgentProviderStore
from app.domain.agent_provider import AgentProviderConfig, AgentProviderConfigError, masked_api_key
from app.services.agent_provider_api import AgentProviderAPI, AgentProviderAPIError
from app.services.agent_provider_registry import AgentProviderRegistry, AgentProviderRuntimeError
from app.services.agent_run_report import ReportSource, build_agent_run_report


SECRET = "synthetic-agent-provider-secret-with-enough-entropy"
CONTRACT = Path(__file__).parents[2] / "contracts" / "agent-provider-config-v1.json"


@pytest.fixture
def provider_store_connections(monkeypatch):
    connect = sqlite3.connect
    connections = []

    def tracked_connect(*args, **kwargs):
        connection = connect(*args, **kwargs)
        connections.append(connection)
        return connection

    monkeypatch.setattr("app.adapters.agent_provider_store.sqlite3.connect", tracked_connect)
    yield connections
    for connection in connections:
        connection.close()


def _assert_connections_closed(connections):
    assert connections
    for connection in connections:
        with pytest.raises(sqlite3.ProgrammingError, match="closed database"):
            connection.execute("SELECT 1")


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


def _update_payload(**overrides) -> dict[str, object]:
    values: dict[str, object] = {
        "version": "agent-provider-config-v1",
        "provider": "openai",
        "model": "gpt-4o-mini",
        "base_url": "https://api.openai.com/v1",
        "api_key": "synthetic-secret-value",
        "enabled": True,
        "allow_real_memo_data": False,
    }
    values.update(overrides)
    return values


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
    with closing(sqlite3.connect(database)) as connection, connection:
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


def test_store_closes_connections_after_save_and_load(tmp_path, provider_store_connections):
    database = tmp_path / "agent.db"
    store = SQLiteAgentProviderStore(database, SECRET)

    saved = store.save(_config())
    assert store.load() == saved

    assert len(provider_store_connections) == 3
    _assert_connections_closed(provider_store_connections)
    database.rename(tmp_path / "closed.db")


def test_store_closes_connection_after_read_error(monkeypatch, tmp_path, provider_store_connections):
    store = SQLiteAgentProviderStore(tmp_path / "agent.db", SECRET)

    def fail_schema(_connection):
        raise sqlite3.OperationalError("synthetic schema failure")

    monkeypatch.setattr(store, "_ensure_schema", fail_schema)
    with pytest.raises(AgentProviderStoreError, match="credential store is unavailable"):
        store.load()

    _assert_connections_closed(provider_store_connections)


def test_store_closes_connections_and_preserves_data_after_write_error(tmp_path, provider_store_connections):
    database = tmp_path / "agent.db"
    store = SQLiteAgentProviderStore(database, SECRET)
    saved = store.save(_config())
    with closing(sqlite3.connect(database)) as connection, connection:
        connection.execute(
            "CREATE TRIGGER reject_provider_update AFTER UPDATE ON agent_provider_config "
            "BEGIN SELECT RAISE(ABORT, 'synthetic write failure'); END"
        )

    with pytest.raises(AgentProviderStoreError, match="credential store is unavailable"):
        store.save(_config(api_key="synthetic-replacement-key"))

    assert store.load() == saved
    _assert_connections_closed(provider_store_connections)


def test_store_authenticates_provider_routing_metadata(tmp_path):
    database = tmp_path / "agent.db"
    store = SQLiteAgentProviderStore(database, SECRET)
    store.save(_config())
    with closing(sqlite3.connect(database)) as connection, connection:
        connection.execute(
            "UPDATE agent_provider_config SET base_url = ? WHERE id = 1",
            ("https://attacker.example/v1",),
        )

    with pytest.raises(AgentProviderStoreError):
        store.load()


def test_store_rejects_unavailable_or_missing_credentials(tmp_path):
    with pytest.raises(AgentProviderStoreError, match="credential store is unavailable"):
        SQLiteAgentProviderStore(tmp_path / "agent.db", " ")

    store = SQLiteAgentProviderStore(tmp_path / "agent.db", SECRET)
    assert store.load() is None
    with pytest.raises(AgentProviderConfigError, match="credential is required"):
        store.save(_config(api_key=None), preserve_api_key=True)


@pytest.mark.parametrize("corruption", ["nonce", "provider"])
def test_store_rejects_corrupt_records_without_exposing_credentials(tmp_path, corruption):
    database = tmp_path / "agent.db"
    store = SQLiteAgentProviderStore(database, SECRET)
    if corruption == "nonce":
        store.save(_config())
        statement = "UPDATE agent_provider_config SET api_key_nonce = 'not-bytes' WHERE id = 1"
    else:
        store.save(
            _config(
                provider="deterministic",
                model="",
                base_url="",
                api_key=None,
            )
        )
        statement = "UPDATE agent_provider_config SET provider = 'unsupported' WHERE id = 1"
    with closing(sqlite3.connect(database)) as connection, connection:
        connection.execute(statement)

    with pytest.raises(AgentProviderStoreError) as error:
        store.load()

    assert str(error.value) == "Agent provider credential store is unavailable"
    assert "synthetic-secret-value" not in str(error.value)


def test_store_projects_sqlite_open_failures_to_a_safe_error(tmp_path):
    store = SQLiteAgentProviderStore(tmp_path, SECRET)

    with pytest.raises(AgentProviderStoreError, match="credential store is unavailable"):
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


@pytest.mark.parametrize(
    ("config", "message"),
    [
        (_config(provider="unsupported"), "unsupported Agent provider"),
        (_config(enabled=1), "invalid Agent provider flags"),
        (_config(config_version=-1), "invalid Agent provider config version"),
        (_config(source="file"), "invalid Agent provider config source"),
        (_config(api_key=""), "invalid Agent provider credential"),
        (
            _config(provider="deterministic", model="remote-model", base_url="", api_key=None),
            "does not accept remote settings",
        ),
        (
            _config(
                provider="deterministic",
                model="",
                base_url="",
                api_key=None,
                allow_real_memo_data=True,
            ),
            "does not require external data consent",
        ),
        (_config(api_key=None), "credential is required"),
        (
            _config(provider="ollama", model="llama3.2", base_url="http://localhost:11434"),
            "does not accept an API key",
        ),
        (_config(base_url="https://api.openai.com:not-a-port/v1"), "base URL"),
        (
            _config(
                provider="ollama",
                model="llama3.2",
                base_url="http://localhost:11435",
                api_key=None,
            ),
            "local service port",
        ),
    ],
)
def test_provider_config_rejects_invalid_contract_values(config, message):
    with pytest.raises(AgentProviderConfigError, match=message):
        config.validated()


def test_masked_api_key_handles_empty_and_short_values():
    assert masked_api_key(None) == ""
    assert masked_api_key("") == ""
    assert masked_api_key("abc") == "••••abc"


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


def test_registry_default_timeout_matches_shared_bff_budget(tmp_path):
    budget = json.loads(CONTRACT.read_text(encoding="utf-8"))["timeout_budget"]
    registry = AgentProviderRegistry(tmp_path / "agent.db", SECRET)

    assert registry._timeout_seconds == budget["provider_seconds"] == 20
    assert budget["bff_provider_seconds"] == 25
    assert budget["bff_metadata_seconds"] == 10


@pytest.mark.asyncio
async def test_registry_timeout_reaches_agent_run_fallback(tmp_path):
    registry = AgentProviderRegistry(
        tmp_path / "agent.db",
        SECRET,
        provider_factory=lambda config: _Provider(config.provider, "{}", delay=0.05),
        timeout_seconds=0.01,
    )
    registry.update(_config(allow_real_memo_data=True), preserve_api_key=False)

    report = await build_agent_run_report(
        "project_summary",
        (ReportSource("synthetic-source", "synthetic-revision", "Synthetic test evidence."),),
        registry.dynamic_provider(),
    )

    assert report.provider == "deterministic"
    assert report.fallback_reason == "provider_timeout"
    assert "Synthetic test evidence." in report.markdown
    assert "provider_timeout" in report.markdown


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


@pytest.mark.parametrize("initial_provider", [None, "deterministic", "openai"])
@pytest.mark.parametrize("credential", [{}, {"api_key": None}, {"api_key": ""}])
def test_internal_api_enables_keyless_ollama_without_preserving_credentials(
    monkeypatch, tmp_path, initial_provider, credential
):
    monkeypatch.setenv("AI_PROVIDER", "deterministic")
    registry = AgentProviderRegistry(tmp_path / "agent.db", SECRET)
    if initial_provider is not None:
        initial = _config()
        if initial_provider == "deterministic":
            initial = _config(provider="deterministic", model="", base_url="", api_key=None)
        registry.update(initial, preserve_api_key=False)
    api = AgentProviderAPI(registry)
    payload = _update_payload(provider="ollama", model="llama3.2", base_url="http://localhost:11434")
    payload.pop("api_key")
    payload.update(credential)

    response = api.update(json.dumps(payload).encode())

    assert response["provider"] == "ollama"
    assert response["enabled"] is True
    assert response["api_key_set"] is False
    assert response["api_key_hint"] == ""
    assert response["allow_real_memo_data"] is False
    assert api.get() == response
    assert SQLiteAgentProviderStore(tmp_path / "agent.db", SECRET).load().api_key is None


@pytest.mark.parametrize("provider", ["openai", "deepseek"])
def test_internal_api_still_requires_credentials_for_new_remote_provider(monkeypatch, tmp_path, provider):
    monkeypatch.setenv("AI_PROVIDER", "deterministic")
    api = AgentProviderAPI(AgentProviderRegistry(tmp_path / "agent.db", SECRET))
    payload = _update_payload(provider=provider, base_url=f"https://api.{provider}.com/v1")
    payload.pop("api_key")

    with pytest.raises(AgentProviderAPIError, match="credential is required"):
        api.update(json.dumps(payload).encode())


def test_internal_api_rejects_unknown_or_raw_read_fields(tmp_path):
    api = AgentProviderAPI(AgentProviderRegistry(tmp_path / "agent.db", SECRET))
    with pytest.raises(AgentProviderAPIError):
        api.update(b'{"version":"agent-provider-config-v1","api_key_hint":"leak"}')


@pytest.mark.parametrize("body", [b"{", b"\xff"])
def test_internal_api_projects_malformed_update_requests(tmp_path, body):
    api = AgentProviderAPI(AgentProviderRegistry(tmp_path / "agent.db", SECRET))

    with pytest.raises(AgentProviderAPIError, match="invalid Agent provider request"):
        api.update(body)


@pytest.mark.parametrize(
    "payload",
    [
        [],
        {"version": "agent-provider-config-v1"},
        _update_payload(unexpected=True),
        _update_payload(version="unsupported-version"),
        _update_payload(api_key=123),
        _update_payload(provider=""),
        _update_payload(enabled=1),
        _update_payload(provider="unsupported"),
    ],
)
def test_internal_api_projects_invalid_contract_values(tmp_path, payload):
    api = AgentProviderAPI(AgentProviderRegistry(tmp_path / "agent.db", SECRET))

    with pytest.raises(AgentProviderAPIError, match="invalid|unsupported"):
        api.update(json.dumps(payload).encode())


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "body",
    [
        b"{",
        b"{}",
        b'{"version":"agent-provider-config-v1","unexpected":true}',
    ],
)
async def test_internal_api_projects_invalid_connection_test_requests(tmp_path, body):
    api = AgentProviderAPI(AgentProviderRegistry(tmp_path / "agent.db", SECRET))

    with pytest.raises(AgentProviderAPIError, match="invalid Agent provider test request"):
        await api.test(body)
