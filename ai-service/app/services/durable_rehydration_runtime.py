"""Default-disabled ownership for the durable rehydration orchestration path."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from app.adapters.agent_lifecycle_ledger import SQLiteMemoLifecycleLedger
from app.adapters.durable_vector_candidate_repository import (
    AuthorizedVectorSearch,
    DurableVectorCandidateRepository,
    LifecycleSnapshotReader,
)
from app.services.durable_rehydration_orchestrator import (
    DurableRehydrationOrchestrator,
    EvidenceRehydrationClient,
)
from app.services.embedding_service import EmbeddingService
from app.settings import AiSettings


class DurableRehydrationRuntimeError(RuntimeError):
    """Reject an unsafe durable runtime selection without exposing state."""

    def __init__(self) -> None:
        super().__init__("durable rehydration runtime is unavailable")


def build_durable_rehydration_orchestrator(
    settings: AiSettings,
    embedding_service: EmbeddingService,
    client: EvidenceRehydrationClient | None,
    *,
    database: str | Path,
    ledger_factory: Callable[[str | Path], LifecycleSnapshotReader] = (
        SQLiteMemoLifecycleLedger
    ),
) -> DurableRehydrationOrchestrator | None:
    """Select durable retrieval only under the existing strict opt-in."""

    if not settings.agent_rehydration_enabled:
        return None
    store = embedding_service.store
    if (
        client is None
        or settings.vector_store != "qdrant"
        or settings.index_mode != "memo"
        or not isinstance(store, AuthorizedVectorSearch)
    ):
        raise DurableRehydrationRuntimeError
    try:
        ledger = ledger_factory(database)
        repository = DurableVectorCandidateRepository(
            embedding_service.provider,
            store,
            ledger,
        )
        return DurableRehydrationOrchestrator(repository, client)
    except DurableRehydrationRuntimeError:
        raise
    except Exception:
        raise DurableRehydrationRuntimeError from None
