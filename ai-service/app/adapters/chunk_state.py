"""AI-owned persistence adapter for the optional chunk index lifecycle."""

from __future__ import annotations

from app.services.chunk_lifecycle import (
    ChunkIndexState,
    ChunkIndexStateStats,
    ChunkIndexStateStore,
)
from database import (
    delete_chunk_index_state,
    get_chunk_index_state,
    get_chunk_index_state_stats,
    save_chunk_index_state,
)


class InMemoryChunkIndexStateStore(ChunkIndexStateStore):
    """Small state store used by provider-neutral lifecycle tests."""

    def __init__(self) -> None:
        self._states: dict[str, ChunkIndexState] = {}

    def get(self, memo_id: str) -> ChunkIndexState | None:
        return self._states.get(str(memo_id))

    def save(self, memo_id: str, index_version: str, chunk_ids: tuple[str, ...]) -> None:
        self._states[str(memo_id)] = ChunkIndexState(
            memo_id=str(memo_id),
            index_version=index_version,
            chunk_ids=tuple(chunk_ids),
        )

    def delete(self, memo_id: str) -> bool:
        return self._states.pop(str(memo_id), None) is not None

    @property
    def backend_name(self) -> str:
        return "memory"

    def stats(self) -> ChunkIndexStateStats:
        return ChunkIndexStateStats(
            tracked_memos=len(self._states),
            tracked_chunks=sum(len(state.chunk_ids) for state in self._states.values()),
            status="ready",
        )


class SqliteChunkIndexStateStore(ChunkIndexStateStore):
    """Persist chunk IDs in the AI Service SQLite database only."""

    def get(self, memo_id: str) -> ChunkIndexState | None:
        row = get_chunk_index_state(memo_id)
        if row is None:
            return None
        return ChunkIndexState(
            memo_id=row["memo_id"],
            index_version=row["index_version"],
            chunk_ids=tuple(row["chunk_ids"]),
        )

    def save(self, memo_id: str, index_version: str, chunk_ids: tuple[str, ...]) -> None:
        save_chunk_index_state(memo_id, index_version, chunk_ids)

    def delete(self, memo_id: str) -> bool:
        return delete_chunk_index_state(memo_id)

    @property
    def backend_name(self) -> str:
        return "sqlite"

    def stats(self) -> ChunkIndexStateStats:
        try:
            row = get_chunk_index_state_stats()
        except Exception as error:
            return ChunkIndexStateStats(
                tracked_memos=0,
                tracked_chunks=0,
                status="unavailable",
                detail=str(error)[:240],
            )
        return ChunkIndexStateStats(
            tracked_memos=row["tracked_memos"],
            tracked_chunks=row["tracked_chunks"],
            status="ready",
        )
