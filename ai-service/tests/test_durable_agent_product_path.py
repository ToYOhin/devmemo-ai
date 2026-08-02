from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone

from app.adapters.agent_lifecycle_ledger import SQLiteMemoLifecycleLedger
from app.adapters.durable_vector_candidate_repository import (
    DurableVectorCandidateRepository,
)
from app.adapters.embedding import DeterministicEmbeddingProvider
from app.adapters.vector_store import InMemoryVectorStore
from app.domain.agent_lifecycle import MemoLifecycleEvent, hash_lifecycle_document
from app.domain.embeddings import VectorRecord
from app.domain.evidence_rehydration import (
    ContentRehydrationRequest,
    ContentRehydrationResponse,
    RehydratedContent,
)
from app.services.agent_delegation import (
    INTERNAL_ANSWER_PATH,
    sign_delegated_request,
)
from app.services.durable_rehydration_orchestrator import (
    DurableRehydrationOrchestrator,
)
from app.services.evidence_answer_agent import EvidenceAnswerAgent
from llm import DeterministicProvider


DOCUMENT = "# Disposable Memo\n\nDocker port mapping is declared in Compose."
DOCUMENT_HASH = hash_lifecycle_document(DOCUMENT)
AUTHORITY_REF = "rehydration-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"


class FailingLegacyRetrieval:
    def retrieve_authorized(self, *args, **kwargs):
        raise AssertionError("durable product path must not call memory retrieval")


class FakeRehydrationClient:
    def __init__(self) -> None:
        self.calls = 0

    async def rehydrate(
        self, request: ContentRehydrationRequest
    ) -> ContentRehydrationResponse:
        self.calls += 1
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


def _keys(value: object) -> set[str]:
    if isinstance(value, dict):
        return set(value).union(*(_keys(item) for item in value.values()))
    if isinstance(value, list):
        return set().union(*(_keys(item) for item in value))
    return set()


def test_disposable_single_host_durable_agent_product_path(tmp_path):
    provider = DeterministicEmbeddingProvider()
    store = InMemoryVectorStore(provider.dimension)
    ledger = SQLiteMemoLifecycleLedger(tmp_path / "derived.db")
    ledger.select_active_generation("generation-active")
    event = MemoLifecycleEvent.from_dict(
        {
            "event_id": "event-visible-1",
            "event_type": "memo.index.requested.v1",
            "memo_uid": "memo-visible",
            "source_sequence": 1,
            "index_version": "memo-v1",
            "operation": "upsert",
            "reason": "created",
            "occurred_at": "2026-08-03T12:00:00+08:00",
            "document": DOCUMENT,
            "document_hash": DOCUMENT_HASH,
        }
    )
    ledger.reserve(event)
    ledger.complete(event)
    store.upsert(
        VectorRecord(
            "record-visible",
            "memo-visible",
            provider.embed("Docker ports").values,
            {
                "source_sequence": 1,
                "document_hash": DOCUMENT_HASH,
                "rebuild_generation": "generation-active",
                "index_version": "memo-v1",
            },
        )
    )
    client = FakeRehydrationClient()
    orchestrator = DurableRehydrationOrchestrator(
        DurableVectorCandidateRepository(provider, store, ledger), client
    )
    agent = EvidenceAnswerAgent(
        FailingLegacyRetrieval(), DeterministicProvider(), orchestrator
    )
    timestamp = 1785758400
    body = json.dumps(
        {
            "question": "Docker ports",
            "limit": 3,
            "visible_memo_uids": ["memo-visible"],
            "memos_authority_ref": AUTHORITY_REF,
        },
        separators=(",", ":"),
    ).encode("utf-8")
    headers = sign_delegated_request(
        "POST", INTERNAL_ANSWER_PATH, body, timestamp, "synthetic-agent-secret"
    )

    result = asyncio.run(
        agent.run_delegated(
            body,
            headers,
            "synthetic-agent-secret",
            datetime.fromtimestamp(timestamp + 30, timezone.utc),
        )
    )
    payload = result.to_dict()

    assert client.calls == 1
    assert result.trace.terminal_state == "answered"
    assert result.trace.steps[0].name == "search_memos"
    assert payload["citations"][0]["memo_id"] == "memo-visible"
    assert payload["citations"][0]["metadata"]["index_version"] == "memo-v1"
    assert "content" not in _keys(payload)
