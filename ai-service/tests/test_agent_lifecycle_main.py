from datetime import datetime, timezone
from pathlib import Path

from fastapi.testclient import TestClient

import main
from app.adapters.agent_lifecycle_ledger import SQLiteMemoLifecycleLedger
from app.adapters.embedding import DeterministicEmbeddingProvider
from app.adapters.vector_store import InMemoryVectorStore
from app.domain.agent_lifecycle import MemoLifecycleEvent, hash_lifecycle_document
from app.domain.embeddings import VectorSearchResult
from app.services.agent_lifecycle_http_adapter import (
    INTERNAL_LIFECYCLE_ACTIVATION_PATH,
    MemoLifecycleHTTPAdapter,
    prepare_lifecycle_activation_request,
)
from app.services.agent_lifecycle_runtime import (
    LifecycleActivationRequest,
    MemoLifecycleRuntime,
    QdrantLifecycleVectorWriter,
    _manifest_digest,
)
from app.services.agent_lifecycle_transport import (
    INTERNAL_LIFECYCLE_PATH,
    prepare_lifecycle_request,
)


SECRET = "synthetic-main-lifecycle-secret"


class MainLifecycleStore(InMemoryVectorStore):
    def delete_memo_versions(self, memo_id: str, index_version: str) -> None:
        for embedding_id, record in list(self._records.items()):
            if record.memo_id == memo_id:
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


def _adapter(tmp_path: Path) -> MemoLifecycleHTTPAdapter:
    provider = DeterministicEmbeddingProvider()
    store = MainLifecycleStore(provider.dimension)
    return MemoLifecycleHTTPAdapter(
        MemoLifecycleRuntime(
            SQLiteMemoLifecycleLedger(tmp_path / "ledger.db"),
            QdrantLifecycleVectorWriter(provider, store, "generation-main"),
        ),
        SECRET,
    )


def _headers(prepared) -> dict[str, str]:
    return {
        "X-DevMemo-Lifecycle-Signature": prepared.headers.signature,
        "X-DevMemo-Lifecycle-Timestamp": prepared.headers.timestamp,
        "X-DevMemo-Lifecycle-Nonce": prepared.headers.nonce,
        "Content-Type": "application/json",
    }


def test_disabled_lifecycle_route_is_bodyless_and_no_store():
    with TestClient(main.app) as client:
        response = client.post(INTERNAL_LIFECYCLE_PATH, content=b"{}")

    assert response.status_code == 404
    assert response.content == b""
    assert response.headers["cache-control"] == "no-store"


def test_enabled_lifecycle_route_rejects_non_exact_http_envelope(tmp_path: Path):
    with TestClient(main.app) as client:
        main.app.state.memo_lifecycle_http_adapter = _adapter(tmp_path)
        response = client.post(
            INTERNAL_LIFECYCLE_PATH + "?unexpected=true",
            content=b"{}",
            headers={"Content-Type": "text/plain"},
        )

    assert response.status_code == 404
    assert response.content == b""


def test_existing_listener_applies_event_and_activates_generation(tmp_path: Path):
    now_seconds = int(datetime.now(timezone.utc).timestamp())
    document = "main route lifecycle document"
    event = MemoLifecycleEvent.from_dict(
        {
            "event_id": "event-main-1",
            "event_type": "memo.index.requested.v1",
            "memo_uid": "memo-main",
            "source_sequence": 1,
            "index_version": "memo-v1",
            "operation": "upsert",
            "reason": "created",
            "occurred_at": "2026-08-03T00:00:00+00:00",
            "document": document,
            "document_hash": hash_lifecycle_document(document),
        }
    )
    prepared_event = prepare_lifecycle_request(
        event, now_seconds, "lifecycle-main-event-0001", SECRET
    )
    prepared_activation = prepare_lifecycle_activation_request(
        LifecycleActivationRequest(
            "generation-main",
            1,
            _manifest_digest(
                [("memo-main", hash_lifecycle_document(document))]
            ),
        ),
        now_seconds,
        "lifecycle-main-activate-0001",
        SECRET,
    )

    with TestClient(main.app) as client:
        adapter = _adapter(tmp_path)
        main.app.state.memo_lifecycle_http_adapter = adapter
        event_response = client.post(
            INTERNAL_LIFECYCLE_PATH,
            content=prepared_event.body,
            headers=_headers(prepared_event),
        )
        activation_response = client.post(
            INTERNAL_LIFECYCLE_ACTIVATION_PATH,
            content=prepared_activation.body,
            headers=_headers(prepared_activation),
        )

    assert event_response.status_code == 200
    assert event_response.headers["cache-control"] == "no-store"
    assert activation_response.status_code == 204
    assert adapter.runtime.ledger.read_snapshot_authority().active_generation == (
        "generation-main"
    )
