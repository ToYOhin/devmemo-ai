import asyncio
from contextlib import asynccontextmanager

import pytest
from fastapi import FastAPI

from app.adapters.embedding import DeterministicEmbeddingProvider
from app.adapters.vector_store import InMemoryVectorStore
from app.services.durable_rehydration_orchestrator import (
    DurableRehydrationOrchestrator,
)
from app.services.durable_rehydration_runtime import (
    DurableRehydrationRuntimeError,
    build_durable_rehydration_orchestrator,
)
from app.services.embedding_service import EmbeddingService
from app.settings import AiSettings


class FakeClient:
    async def rehydrate(self, request):
        raise AssertionError("runtime construction must not call rehydration")


def _embedding_service() -> EmbeddingService:
    provider = DeterministicEmbeddingProvider()
    return EmbeddingService(provider, InMemoryVectorStore(provider.dimension))


def _enabled_settings(**overrides: object) -> AiSettings:
    values: dict[str, object] = {
        "agent_enabled": True,
        "agent_internal_secret": "synthetic-delegation-secret",
        "agent_rehydration_enabled": True,
        "agent_rehydration_secret_current": "synthetic-rehydration-secret",
        "agent_rehydration_memos_url": "http://memos.invalid",
        "vector_store": "qdrant",
        "index_mode": "memo",
    }
    values.update(overrides)
    return AiSettings(**values)


def test_disabled_runtime_constructs_no_ledger_or_orchestrator(tmp_path):
    calls = 0

    def ledger_factory(path):
        nonlocal calls
        calls += 1
        raise AssertionError("disabled runtime must not construct a ledger")

    result = build_durable_rehydration_orchestrator(
        AiSettings(),
        _embedding_service(),
        None,
        database=tmp_path / "disabled.db",
        ledger_factory=ledger_factory,
    )

    assert result is None
    assert calls == 0


def test_enabled_runtime_owns_real_candidate_repository_without_io(tmp_path):
    paths = []

    class FakeLedger:
        pass

    def ledger_factory(path):
        paths.append(path)
        return FakeLedger()

    result = build_durable_rehydration_orchestrator(
        _enabled_settings(),
        _embedding_service(),
        FakeClient(),
        database=tmp_path / "derived.db",
        ledger_factory=ledger_factory,
    )

    assert isinstance(result, DurableRehydrationOrchestrator)
    assert paths == [tmp_path / "derived.db"]


@pytest.mark.parametrize(
    "overrides",
    [{"vector_store": "memory"}, {"index_mode": "chunk"}],
)
def test_enabled_runtime_rejects_non_durable_or_non_memo_selection(
    tmp_path, overrides
):
    with pytest.raises(DurableRehydrationRuntimeError):
        build_durable_rehydration_orchestrator(
            _enabled_settings(**overrides),
            _embedding_service(),
            FakeClient(),
            database=tmp_path / "invalid.db",
        )


def test_main_lifespan_owns_and_clears_durable_runtime_state(monkeypatch):
    import main

    client = FakeClient()
    orchestrator = object()

    @asynccontextmanager
    async def fake_client_lifespan(settings):
        yield client

    def fake_runtime_builder(settings, embedding_service, selected_client, *, database):
        assert selected_client is client
        return orchestrator

    monkeypatch.setattr(main, "evidence_rehydration_client_lifespan", fake_client_lifespan)
    monkeypatch.setattr(main, "build_durable_rehydration_orchestrator", fake_runtime_builder)

    async def scenario() -> None:
        application = FastAPI()
        async with main.lifespan(application):
            assert application.state.evidence_rehydration_client is client
            assert application.state.durable_rehydration_orchestrator is orchestrator
        assert application.state.evidence_rehydration_client is None
        assert application.state.durable_rehydration_orchestrator is None

    asyncio.run(scenario())


def test_main_lifespan_clears_state_when_runtime_construction_fails(monkeypatch):
    import main

    @asynccontextmanager
    async def fake_client_lifespan(settings):
        yield FakeClient()

    def failing_runtime_builder(*args, **kwargs):
        raise DurableRehydrationRuntimeError

    monkeypatch.setattr(main, "evidence_rehydration_client_lifespan", fake_client_lifespan)
    monkeypatch.setattr(main, "build_durable_rehydration_orchestrator", failing_runtime_builder)
    application = FastAPI()

    async def scenario() -> None:
        with pytest.raises(DurableRehydrationRuntimeError):
            async with main.lifespan(application):
                raise AssertionError("failed construction must not enter lifespan")

    asyncio.run(scenario())
    assert application.state.evidence_rehydration_client is None
    assert application.state.durable_rehydration_orchestrator is None
