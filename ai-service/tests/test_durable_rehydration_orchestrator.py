from __future__ import annotations

import asyncio

import pytest

from app.domain.agent_lifecycle import (
    MemoLifecycleEvent,
    accept_lifecycle_event,
    complete_lifecycle_event,
    hash_lifecycle_document,
)
from app.domain.durable_authorized_retrieval import (
    DerivedCandidateSnapshot,
    DerivedMemoCandidate,
)
from app.domain.evidence_rehydration import (
    ContentRehydrationFailure,
    ContentRehydrationRequest,
    ContentRehydrationResponse,
    RehydratedContent,
)
from app.services.agent_delegation import DelegatedAnswerRequest
from app.services.durable_authorized_retrieval import (
    DurableAuthorizedRetrievalUnavailableError,
)
from app.services.durable_rehydration_orchestrator import (
    DurableRehydrationOrchestrator,
)


DOCUMENT = "# Synthetic Memo\n\nCurrent Memos content only."
DOCUMENT_HASH = hash_lifecycle_document(DOCUMENT)
AUTHORITY_REF = "authority-ref-synthetic-0000000001"


def _candidate() -> DerivedMemoCandidate:
    event = MemoLifecycleEvent.from_dict(
        {
            "event_id": "event-memo-visible-3",
            "event_type": "memo.index.requested.v1",
            "memo_uid": "memo-visible",
            "source_sequence": 3,
            "index_version": "memo-v1",
            "operation": "upsert",
            "reason": "created",
            "occurred_at": "2026-08-03T08:00:00+08:00",
            "document": DOCUMENT,
            "document_hash": DOCUMENT_HASH,
        }
    )
    state = complete_lifecycle_event(
        accept_lifecycle_event(None, event).state,
        event,
    )[0]
    return DerivedMemoCandidate(
        record_key="record-visible",
        memo_uid="memo-visible",
        score=0.91,
        source_sequence=3,
        document_hash=DOCUMENT_HASH,
        rebuild_generation="generation-active",
        index_version="memo-v1",
        lifecycle_state=state,
    )


class FakeCandidateRepository:
    def __init__(self, snapshot: DerivedCandidateSnapshot) -> None:
        self.snapshot = snapshot
        self.current_token = snapshot.snapshot_token
        self.find_calls = 0
        self.token_calls = 0

    def find_candidates(self, **_: object) -> DerivedCandidateSnapshot:
        self.find_calls += 1
        return self.snapshot

    def read_current_snapshot_token(self) -> str:
        self.token_calls += 1
        return self.current_token


class FakeRehydrationClient:
    def __init__(self) -> None:
        self.calls = 0
        self.requests: list[ContentRehydrationRequest] = []
        self.result: ContentRehydrationResponse | ContentRehydrationFailure | None = None
        self.error: BaseException | None = None

    async def rehydrate(
        self,
        request: ContentRehydrationRequest,
    ) -> ContentRehydrationResponse | ContentRehydrationFailure:
        self.calls += 1
        self.requests.append(request)
        if self.error is not None:
            raise self.error
        if self.result is not None:
            return self.result
        selection = request.selections[0]
        return ContentRehydrationResponse(
            snapshot_token=request.snapshot_token,
            authority_token="authority-token-synthetic-00000001",
            documents=(
                RehydratedContent(
                    selection_ref=selection.selection_ref,
                    document=DOCUMENT,
                    source_sequence=selection.source_sequence,
                    document_hash=selection.document_hash,
                ),
            ),
        )


def _snapshot(*candidates: DerivedMemoCandidate) -> DerivedCandidateSnapshot:
    return DerivedCandidateSnapshot(
        active_generation="generation-active",
        snapshot_token="snapshot-synthetic-1",
        candidates=candidates or (_candidate(),),
    )


def _delegated(*uids: str, authority_ref: str | None = AUTHORITY_REF) -> DelegatedAnswerRequest:
    return DelegatedAnswerRequest(
        question="Which content is current?",
        limit=3,
        visible_memo_uids=uids or ("memo-visible",),
        memos_authority_ref=authority_ref,
    )


def test_orchestrator_rehydrates_once_and_materializes_request_memory_result():
    async def scenario() -> None:
        repository = FakeCandidateRepository(_snapshot())
        client = FakeRehydrationClient()

        result = await DurableRehydrationOrchestrator(repository, client).retrieve(
            _delegated()
        )

        assert client.calls == 1
        assert repository.find_calls == 1
        assert repository.token_calls == 1
        assert result.evidence[0].document == DOCUMENT
        assert result.evidence[0].citation.memo_uid == "memo-visible"
        assert client.requests[0].memos_authority_ref == AUTHORITY_REF

    asyncio.run(scenario())


def test_orchestrator_skips_client_for_empty_scope_or_no_candidates():
    async def scenario() -> None:
        empty_client = FakeRehydrationClient()
        empty_result = await DurableRehydrationOrchestrator(
            FakeCandidateRepository(_snapshot()), empty_client
        ).retrieve(
            DelegatedAnswerRequest("empty", 3, (), None)
        )
        assert not empty_result.evidence
        assert empty_client.calls == 0

        client = FakeRehydrationClient()
        result = await DurableRehydrationOrchestrator(
            FakeCandidateRepository(_snapshot()), client
        ).retrieve(_delegated("memo-other"))
        assert not result.evidence
        assert client.calls == 0

    asyncio.run(scenario())


@pytest.mark.parametrize("failure", ["missing ref", "client", "snapshot", "partial"])
def test_orchestrator_fails_closed_without_content_fallback(failure: str):
    async def scenario() -> None:
        repository = FakeCandidateRepository(_snapshot())
        client = FakeRehydrationClient()
        delegated = _delegated()
        if failure == "missing ref":
            delegated = _delegated(authority_ref=None)
        elif failure == "client":
            client.result = ContentRehydrationFailure()
        elif failure == "snapshot":
            repository.current_token = "snapshot-changed"
        elif failure == "partial":
            client.result = ContentRehydrationResponse(
                snapshot_token="snapshot-synthetic-1",
                authority_token="authority-token-synthetic-00000001",
                documents=(
                    RehydratedContent(
                        selection_ref="rehydration-9",
                        document=DOCUMENT,
                        source_sequence=3,
                        document_hash=DOCUMENT_HASH,
                    ),
                ),
            )

        with pytest.raises(
            DurableAuthorizedRetrievalUnavailableError,
            match="authorized retrieval unavailable",
        ) as raised:
            await DurableRehydrationOrchestrator(repository, client).retrieve(delegated)
        assert DOCUMENT not in str(raised.value)
        assert client.calls <= 1

    asyncio.run(scenario())
