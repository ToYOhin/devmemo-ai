from datetime import datetime, timezone
from pathlib import Path

from app.adapters.agent_lifecycle_ledger import SQLiteMemoLifecycleLedger
from app.adapters.embedding import DeterministicEmbeddingProvider
from app.domain.agent_lifecycle import MemoLifecycleEvent, hash_lifecycle_document
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
    LifecycleTransportHeaders,
    prepare_lifecycle_request,
)
from test_agent_lifecycle_runtime import FakeLifecycleStore


NOW_SECONDS = 1_785_710_400
NOW = datetime.fromtimestamp(NOW_SECONDS + 30, timezone.utc)
SECRET = "synthetic-lifecycle-runtime-secret"


def _adapter(tmp_path: Path) -> MemoLifecycleHTTPAdapter:
    provider = DeterministicEmbeddingProvider()
    store = FakeLifecycleStore(provider.dimension)
    runtime = MemoLifecycleRuntime(
        SQLiteMemoLifecycleLedger(tmp_path / "ledger.db"),
        QdrantLifecycleVectorWriter(provider, store, "generation-next"),
    )
    return MemoLifecycleHTTPAdapter(runtime, SECRET)


def _event() -> MemoLifecycleEvent:
    document = "authenticated lifecycle document"
    return MemoLifecycleEvent.from_dict(
        {
            "event_id": "event-runtime-1",
            "event_type": "memo.index.requested.v1",
            "memo_uid": "memo-runtime",
            "source_sequence": 1,
            "index_version": "memo-v1",
            "operation": "upsert",
            "reason": "created",
            "occurred_at": "2026-08-03T00:00:00+00:00",
            "document": document,
            "document_hash": hash_lifecycle_document(document),
        }
    )


def test_http_adapter_applies_event_then_activates_exact_manifest(tmp_path: Path):
    adapter = _adapter(tmp_path)
    event = _event()
    prepared = prepare_lifecycle_request(
        event, NOW_SECONDS, "lifecycle-event-nonce-0001", SECRET
    )

    event_response = adapter.handle_event(
        method="POST",
        path=INTERNAL_LIFECYCLE_PATH,
        body=prepared.body,
        headers=prepared.headers,
        now=NOW,
    )
    activation = prepare_lifecycle_activation_request(
        LifecycleActivationRequest(
            "generation-next",
            1,
            _manifest_digest([("memo-runtime", event.document_hash or "")]),
        ),
        NOW_SECONDS,
        "lifecycle-activate-nonce-0001",
        SECRET,
    )
    activation_response = adapter.handle_activation(
        method="POST",
        path=INTERNAL_LIFECYCLE_ACTIVATION_PATH,
        body=activation.body,
        headers=activation.headers,
        now=NOW,
    )

    assert event_response.status_code == 200
    assert event_response.content_type == "application/json"
    assert activation_response.status_code == 204
    assert adapter.runtime.ledger.read_snapshot_authority().active_generation == (
        "generation-next"
    )


def test_http_adapter_maps_unverified_input_to_bodyless_404(tmp_path: Path):
    adapter = _adapter(tmp_path)
    prepared = prepare_lifecycle_request(
        _event(), NOW_SECONDS, "lifecycle-event-nonce-0002", SECRET
    )
    tampered = LifecycleTransportHeaders(
        "sha256=" + "0" * 64,
        prepared.headers.timestamp,
        prepared.headers.nonce,
    )

    response = adapter.handle_event(
        method="POST",
        path=INTERNAL_LIFECYCLE_PATH,
        body=prepared.body,
        headers=tampered,
        now=NOW,
    )

    assert response.status_code == 404
    assert response.body == b""
    assert adapter.runtime.ledger.get("memo-runtime") is None


def test_http_adapter_rejects_wrong_method_before_processing(tmp_path: Path):
    adapter = _adapter(tmp_path)
    prepared = prepare_lifecycle_request(
        _event(), NOW_SECONDS, "lifecycle-event-nonce-0004", SECRET
    )

    response = adapter.handle_event(
        method="GET",
        path=INTERNAL_LIFECYCLE_PATH,
        body=prepared.body,
        headers=prepared.headers,
        now=NOW,
    )

    assert response.status_code == 404
    assert adapter.runtime.ledger.get("memo-runtime") is None


def test_http_adapter_maps_verified_manifest_mismatch_to_bodyless_503(
    tmp_path: Path,
):
    adapter = _adapter(tmp_path)
    prepared = prepare_lifecycle_activation_request(
        LifecycleActivationRequest("generation-next", 0, "0" * 64),
        NOW_SECONDS,
        "lifecycle-activate-nonce-0002",
        SECRET,
    )

    response = adapter.handle_activation(
        method="POST",
        path=INTERNAL_LIFECYCLE_ACTIVATION_PATH,
        body=prepared.body,
        headers=prepared.headers,
        now=NOW,
    )

    assert response.status_code == 503
    assert response.body == b""


def test_activation_nonce_is_single_use(tmp_path: Path):
    adapter = _adapter(tmp_path)
    empty_manifest = _manifest_digest([])
    prepared = prepare_lifecycle_activation_request(
        LifecycleActivationRequest("generation-next", 0, empty_manifest),
        NOW_SECONDS,
        "lifecycle-activate-nonce-0003",
        SECRET,
    )
    arguments = {
        "method": "POST",
        "path": INTERNAL_LIFECYCLE_ACTIVATION_PATH,
        "body": prepared.body,
        "headers": prepared.headers,
        "now": NOW,
    }

    assert adapter.handle_activation(**arguments).status_code == 204
    assert adapter.handle_activation(**arguments).status_code == 404
