from __future__ import annotations

from pathlib import Path

import pytest

from app.adapters.agent_lifecycle_ledger import SQLiteMemoLifecycleLedger
from app.adapters.embedding import DeterministicEmbeddingProvider
from app.adapters.vector_store import InMemoryVectorStore
from app.domain.agent_lifecycle import MemoLifecycleEvent, hash_lifecycle_document
from app.domain.embeddings import VectorSearchResult
from app.services.agent_lifecycle_runtime import (
    LifecycleActivationRequest,
    LifecycleRuntimeError,
    MemoLifecycleRuntime,
    QdrantLifecycleVectorWriter,
    _manifest_digest,
)


class FakeLifecycleStore(InMemoryVectorStore):
    def delete_memo_versions(self, memo_id: str, index_version: str) -> None:
        for embedding_id, record in list(self._records.items()):
            if (
                record.memo_id == memo_id
                and record.metadata.get("index_version") == index_version
            ):
                self._records.pop(embedding_id)

    def list_lifecycle_records(
        self, rebuild_generation: str, index_version: str
    ) -> list[VectorSearchResult]:
        return [
            VectorSearchResult(
                record.embedding_id,
                record.memo_id,
                0.0,
                dict(record.metadata),
            )
            for record in self._records.values()
            if record.metadata.get("rebuild_generation") == rebuild_generation
            and record.metadata.get("index_version") == index_version
        ]


def _event(memo_uid: str, sequence: int, document: str) -> MemoLifecycleEvent:
    return MemoLifecycleEvent.from_dict(
        {
            "event_id": f"event-{memo_uid}-{sequence}",
            "event_type": "memo.index.requested.v1",
            "memo_uid": memo_uid,
            "source_sequence": sequence,
            "index_version": "memo-v1",
            "operation": "upsert",
            "reason": "created",
            "occurred_at": "2026-08-03T00:00:00+00:00",
            "document": document,
            "document_hash": hash_lifecycle_document(document),
        }
    )


def _runtime(tmp_path: Path):
    provider = DeterministicEmbeddingProvider()
    store = FakeLifecycleStore(provider.dimension)
    ledger = SQLiteMemoLifecycleLedger(tmp_path / "ledger.db")
    writer = QdrantLifecycleVectorWriter(provider, store, "generation-next")
    return MemoLifecycleRuntime(ledger, writer), store


def test_runtime_activates_only_after_exact_applied_manifest(tmp_path: Path):
    runtime, _ = _runtime(tmp_path)
    documents = {"memo-a": "alpha", "memo-b": "beta"}
    for memo_uid, document in documents.items():
        assert runtime.process(_event(memo_uid, 1, document)).status == "applied"

    authority = runtime.activate(
        LifecycleActivationRequest(
            "generation-next",
            2,
            _manifest_digest(
                [(uid, hash_lifecycle_document(doc)) for uid, doc in documents.items()]
            ),
        )
    )

    assert authority.active_generation == "generation-next"


@pytest.mark.parametrize("count,digest", [(1, "0" * 64), (2, "f" * 64)])
def test_runtime_rejects_incomplete_or_mismatched_manifest(
    tmp_path: Path, count: int, digest: str
):
    runtime, _ = _runtime(tmp_path)
    runtime.process(_event("memo-a", 1, "alpha"))

    with pytest.raises(LifecycleRuntimeError):
        runtime.activate(LifecycleActivationRequest("generation-next", count, digest))

    assert runtime.ledger.read_snapshot_authority().active_generation is None


def test_lifecycle_tombstone_removes_every_generation(tmp_path: Path):
    runtime, store = _runtime(tmp_path)
    runtime.process(_event("memo-a", 1, "alpha"))
    old_writer = QdrantLifecycleVectorWriter(
        runtime.writer.provider, store, "generation-old"
    )
    old_writer.upsert_memo(
        memo_uid="memo-a",
        document="old alpha",
        source_sequence=1,
        document_hash=hash_lifecycle_document("old alpha"),
        index_version="memo-v1",
    )
    delete = MemoLifecycleEvent.from_dict(
        {
            "event_id": "event-memo-a-2",
            "event_type": "memo.delete.requested.v1",
            "memo_uid": "memo-a",
            "source_sequence": 2,
            "index_version": "memo-v1",
            "operation": "delete",
            "reason": "deleted",
            "occurred_at": "2026-08-03T00:01:00+00:00",
        }
    )

    assert runtime.process(delete).status == "applied"
    assert store.search((1.0,) * store.dimension) == []
