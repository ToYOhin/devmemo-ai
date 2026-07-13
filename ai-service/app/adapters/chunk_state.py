"""AI-owned persistence adapter for the optional chunk index lifecycle."""

from __future__ import annotations

from app.services.chunk_lifecycle import ChunkIndexState, ChunkIndexStateStore
from database import (
    delete_chunk_index_state,
    get_chunk_index_state,
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
