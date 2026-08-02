"""Content-free durable candidate adapter over vectors and the A4 ledger."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Protocol

from app.adapters.agent_lifecycle_ledger import LifecycleSnapshotAuthority
from app.domain.agent_lifecycle import (
    MEMO_INDEX_VERSION,
    MemoLifecycleState,
    is_retrieval_eligible,
)
from app.domain.durable_authorized_retrieval import (
    AuthorizedRetrievalQuery,
    DerivedCandidateSnapshot,
    DerivedMemoCandidate,
)
from app.domain.embeddings import EmbeddingProvider, VectorSearchResult


_GENERATION_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")
_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")


class DurableCandidateRepositoryError(RuntimeError):
    """Map malformed or inconsistent derived state without exposing its values."""

    def __init__(self) -> None:
        super().__init__("durable candidate repository is unavailable")


class AuthorizedVectorSearch(Protocol):
    dimension: int

    def search_visible_memos(
        self,
        query: Sequence[float],
        visible_memo_ids: frozenset[str],
        limit: int = 5,
        *,
        rebuild_generation: str | None = None,
        index_version: str | None = None,
    ) -> list[VectorSearchResult]:
        ...


class LifecycleSnapshotReader(Protocol):
    def read_snapshot_authority(self) -> LifecycleSnapshotAuthority:
        ...

    def get(self, memo_uid: str, index_version: str) -> MemoLifecycleState | None:
        ...


class DurableVectorCandidateRepository:
    """Join scoped vector ranks with current content-free lifecycle authority."""

    def __init__(
        self,
        provider: EmbeddingProvider,
        store: AuthorizedVectorSearch,
        ledger: LifecycleSnapshotReader,
    ) -> None:
        if provider.dimension != store.dimension:
            raise ValueError("embedding provider and vector store dimensions must match")
        self._provider = provider
        self._store = store
        self._ledger = ledger

    def find_candidates(
        self,
        *,
        question: str,
        authorized_memo_uids: frozenset[str],
        limit: int,
    ) -> DerivedCandidateSnapshot:
        try:
            query = AuthorizedRetrievalQuery(
                question, limit, tuple(sorted(authorized_memo_uids))
            )
            before = self._read_snapshot()
            if before.active_generation is None or not query.authorized_memo_uids:
                return DerivedCandidateSnapshot(
                    before.active_generation, before.snapshot_token, ()
                )
            vector = self._provider.embed(query.question)
            results = self._store.search_visible_memos(
                vector.values,
                query.authorized_uid_set,
                limit=len(query.authorized_memo_uids),
                rebuild_generation=before.active_generation,
                index_version=MEMO_INDEX_VERSION,
            )
            candidates = self._eligible_candidates(query, before, results)
            if self._read_snapshot() != before:
                raise DurableCandidateRepositoryError
            return DerivedCandidateSnapshot(
                before.active_generation, before.snapshot_token, candidates[: query.limit]
            )
        except DurableCandidateRepositoryError:
            raise
        except Exception:
            raise DurableCandidateRepositoryError from None

    def read_current_snapshot_token(self) -> str:
        try:
            return self._read_snapshot().snapshot_token
        except Exception:
            raise DurableCandidateRepositoryError from None

    def _eligible_candidates(
        self,
        query: AuthorizedRetrievalQuery,
        snapshot: LifecycleSnapshotAuthority,
        results: list[VectorSearchResult],
    ) -> tuple[DerivedMemoCandidate, ...]:
        seen_records: set[str] = set()
        seen_memos: set[str] = set()
        candidates: list[DerivedMemoCandidate] = []
        for result in results:
            if not isinstance(result, VectorSearchResult):
                raise DurableCandidateRepositoryError
            if result.embedding_id in seen_records or result.memo_id in seen_memos:
                raise DurableCandidateRepositoryError
            seen_records.add(result.embedding_id)
            seen_memos.add(result.memo_id)
            if result.memo_id not in query.authorized_uid_set:
                raise DurableCandidateRepositoryError
            metadata = _candidate_metadata(result.metadata)
            state = self._ledger.get(result.memo_id, metadata["index_version"])
            if (
                metadata["index_version"] != MEMO_INDEX_VERSION
                or metadata["rebuild_generation"] != snapshot.active_generation
                or state is None
                or state.status != "applied"
                or not is_retrieval_eligible(
                    state,
                    vector_source_sequence=metadata["source_sequence"],
                    vector_document_hash=metadata["document_hash"],
                )
            ):
                continue
            candidates.append(
                DerivedMemoCandidate(
                    result.embedding_id,
                    result.memo_id,
                    result.score,
                    metadata["source_sequence"],
                    metadata["document_hash"],
                    metadata["rebuild_generation"],
                    metadata["index_version"],
                    state,
                )
            )
        return tuple(candidates)

    def _read_snapshot(self) -> LifecycleSnapshotAuthority:
        snapshot = self._ledger.read_snapshot_authority()
        if not isinstance(snapshot, LifecycleSnapshotAuthority):
            raise DurableCandidateRepositoryError
        return snapshot


def _candidate_metadata(metadata: Mapping[str, object]) -> dict[str, object]:
    if "content" in metadata:
        raise DurableCandidateRepositoryError
    source_sequence = metadata.get("source_sequence")
    document_hash = metadata.get("document_hash")
    rebuild_generation = metadata.get("rebuild_generation")
    index_version = metadata.get("index_version")
    if (
        type(source_sequence) is not int
        or source_sequence < 1
        or not isinstance(document_hash, str)
        or not _SHA256_PATTERN.fullmatch(document_hash)
        or not isinstance(rebuild_generation, str)
        or not _GENERATION_PATTERN.fullmatch(rebuild_generation)
        or index_version != MEMO_INDEX_VERSION
    ):
        raise DurableCandidateRepositoryError
    return {
        "source_sequence": source_sequence,
        "document_hash": document_hash,
        "rebuild_generation": rebuild_generation,
        "index_version": index_version,
    }
