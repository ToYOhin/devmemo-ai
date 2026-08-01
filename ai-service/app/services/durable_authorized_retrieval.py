"""Unwired orchestration for durable, lifecycle-safe authorized retrieval."""

from __future__ import annotations

from typing import Protocol

from app.domain.durable_authorized_retrieval import (
    AuthorizedRetrievalQuery,
    AuthorizedRetrievalResult,
    DerivedCandidateSnapshot,
    DerivedMemoDocument,
    project_authorized_result,
    select_eligible_candidates,
)


class DurableAuthorizedRetrievalRepository(Protocol):
    """Two-stage derived-store boundary; candidate reads contain no document."""

    def find_candidates(
        self,
        *,
        question: str,
        authorized_memo_uids: frozenset[str],
        limit: int,
    ) -> DerivedCandidateSnapshot:
        ...

    def load_documents(
        self,
        *,
        record_keys: tuple[str, ...],
        snapshot_token: str,
    ) -> tuple[DerivedMemoDocument, ...]:
        ...


class DurableAuthorizedRetrievalUnavailableError(RuntimeError):
    """Fixed content-free mapping for repository or derived-state failures."""

    error_code = "authorized_retrieval_unavailable"

    def __init__(self) -> None:
        super().__init__("authorized retrieval unavailable")

    def to_dict(self) -> dict[str, str]:
        return {"error_code": self.error_code}


class DurableAuthorizedRetrievalService:
    """Filter content-free state before requesting complete Memo documents."""

    def __init__(self, repository: DurableAuthorizedRetrievalRepository) -> None:
        self._repository = repository

    def retrieve(self, query: AuthorizedRetrievalQuery) -> AuthorizedRetrievalResult:
        if not isinstance(query, AuthorizedRetrievalQuery):
            raise TypeError("query must use AuthorizedRetrievalQuery")
        if not query.authorized_memo_uids:
            return AuthorizedRetrievalResult(())

        try:
            snapshot = self._repository.find_candidates(
                question=query.question,
                authorized_memo_uids=query.authorized_uid_set,
                limit=query.limit,
            )
            if not isinstance(snapshot, DerivedCandidateSnapshot):
                raise TypeError
            eligible = select_eligible_candidates(query, snapshot)
            if not eligible:
                return AuthorizedRetrievalResult(())
            documents = self._repository.load_documents(
                record_keys=tuple(candidate.record_key for candidate in eligible),
                snapshot_token=snapshot.snapshot_token,
            )
            if not isinstance(documents, tuple):
                raise TypeError
            return project_authorized_result(query, eligible, documents)
        except DurableAuthorizedRetrievalUnavailableError:
            raise
        except Exception:
            raise DurableAuthorizedRetrievalUnavailableError from None
