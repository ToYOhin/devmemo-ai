"""Unselected orchestration for durable candidates and current Memos content."""

from __future__ import annotations

from typing import Protocol

from app.domain.durable_authorized_retrieval import (
    AuthorizedRetrievalQuery,
    AuthorizedRetrievalResult,
    DerivedCandidateSnapshot,
    project_authorized_result,
    select_eligible_candidates,
)
from app.domain.evidence_rehydration import (
    ContentRehydrationFailure,
    ContentRehydrationRequest,
    ContentRehydrationResponse,
    build_content_rehydration_request,
    materialize_rehydrated_documents,
)
from app.services.agent_delegation import DelegatedAnswerRequest
from app.services.durable_authorized_retrieval import (
    DurableAuthorizedRetrievalUnavailableError,
)


class DurableCandidateRepository(Protocol):
    """Content-free candidate and snapshot-revision boundary."""

    def find_candidates(
        self,
        *,
        question: str,
        authorized_memo_uids: frozenset[str],
        limit: int,
    ) -> DerivedCandidateSnapshot:
        ...

    def read_current_snapshot_token(self) -> str:
        ...


class EvidenceRehydrationClient(Protocol):
    async def rehydrate(
        self,
        request: ContentRehydrationRequest,
    ) -> ContentRehydrationResponse | ContentRehydrationFailure:
        ...


class DurableRehydrationOrchestrator:
    """Materialize one reverified durable result in request memory only."""

    def __init__(
        self,
        repository: DurableCandidateRepository,
        client: EvidenceRehydrationClient,
    ) -> None:
        self._repository = repository
        self._client = client

    async def retrieve(
        self,
        delegated: DelegatedAnswerRequest,
    ) -> AuthorizedRetrievalResult:
        try:
            if not isinstance(delegated, DelegatedAnswerRequest):
                raise TypeError
            query = AuthorizedRetrievalQuery(
                question=delegated.question,
                limit=delegated.limit,
                authorized_memo_uids=delegated.visible_memo_uids,
            )
            if not query.authorized_memo_uids:
                return AuthorizedRetrievalResult(())
            if delegated.memos_authority_ref is None:
                raise DurableAuthorizedRetrievalUnavailableError

            snapshot = self._repository.find_candidates(
                question=query.question,
                authorized_memo_uids=query.authorized_uid_set,
                limit=query.limit,
            )
            if not isinstance(snapshot, DerivedCandidateSnapshot):
                raise TypeError
            candidates = select_eligible_candidates(query, snapshot)
            if not candidates:
                return AuthorizedRetrievalResult(())

            request = build_content_rehydration_request(
                query,
                snapshot,
                candidates,
                memos_authority_ref=delegated.memos_authority_ref,
            )
            response = await self._client.rehydrate(request)
            if not isinstance(response, ContentRehydrationResponse):
                raise DurableAuthorizedRetrievalUnavailableError
            current_snapshot_token = self._repository.read_current_snapshot_token()
            documents = materialize_rehydrated_documents(
                query,
                snapshot,
                candidates,
                request,
                response,
                memos_authority_ref=delegated.memos_authority_ref,
                current_snapshot_token=current_snapshot_token,
            )
            return project_authorized_result(query, candidates, documents)
        except DurableAuthorizedRetrievalUnavailableError:
            raise
        except Exception:
            raise DurableAuthorizedRetrievalUnavailableError from None
