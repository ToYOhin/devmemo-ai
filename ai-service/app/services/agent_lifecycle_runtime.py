"""Single-host, default-disabled memo lifecycle runtime building blocks."""

from __future__ import annotations

import hashlib
import hmac
import json
import re
import threading
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

from app.adapters.agent_lifecycle_ledger import (
    LifecycleSnapshotAuthority,
    SQLiteMemoLifecycleLedger,
)
from app.domain.agent_lifecycle import (
    MEMO_INDEX_VERSION,
    LifecycleAcknowledgement,
    MemoLifecycleEvent,
)
from app.domain.embeddings import EmbeddingProvider, VectorRecord, VectorSearchResult
from app.services.agent_lifecycle_processor import MemoLifecycleProcessor


_GENERATION_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")
_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
_LIFECYCLE_METADATA_FIELDS = frozenset(
    {"source_sequence", "document_hash", "rebuild_generation", "index_version"}
)


class LifecycleRuntimeError(RuntimeError):
    def __init__(self) -> None:
        super().__init__("memo lifecycle runtime is unavailable")


class LifecycleVectorStore(Protocol):
    dimension: int

    def upsert(self, record: VectorRecord) -> None:
        ...

    def delete_memo_versions(self, memo_id: str, index_version: str) -> None:
        ...

    def list_lifecycle_records(
        self, rebuild_generation: str, index_version: str
    ) -> list[VectorSearchResult]:
        ...


@dataclass(frozen=True)
class LifecycleActivationRequest:
    generation: str
    eligible_count: int
    manifest_digest: str

    def __post_init__(self) -> None:
        if not _GENERATION_PATTERN.fullmatch(self.generation):
            raise LifecycleRuntimeError
        if type(self.eligible_count) is not int or self.eligible_count < 0:
            raise LifecycleRuntimeError
        if not _SHA256_PATTERN.fullmatch(self.manifest_digest):
            raise LifecycleRuntimeError


class QdrantLifecycleVectorWriter:
    """Write generation-scoped points without persisting Memo content."""

    def __init__(
        self,
        provider: EmbeddingProvider,
        store: LifecycleVectorStore,
        generation: str,
    ) -> None:
        if not _GENERATION_PATTERN.fullmatch(generation):
            raise LifecycleRuntimeError
        if provider.dimension != store.dimension:
            raise LifecycleRuntimeError
        self.provider = provider
        self.store = store
        self.generation = generation

    def upsert_memo(
        self,
        *,
        memo_uid: str,
        document: str,
        source_sequence: int,
        document_hash: str,
        index_version: str,
    ) -> None:
        embedding = self.provider.embed(document)
        digest = hashlib.sha256(
            f"{self.generation}\n{memo_uid}".encode("utf-8")
        ).hexdigest()[:24]
        self.store.upsert(
            VectorRecord(
                embedding_id=f"memo-generation-{digest}",
                memo_id=memo_uid,
                vector=embedding.values,
                metadata={
                    "source_sequence": source_sequence,
                    "document_hash": document_hash,
                    "rebuild_generation": self.generation,
                    "index_version": index_version,
                },
            )
        )

    def delete_memo(self, *, memo_uid: str, index_version: str) -> None:
        self.store.delete_memo_versions(memo_uid, index_version)

    def records(self) -> list[VectorSearchResult]:
        return self.store.list_lifecycle_records(
            self.generation, MEMO_INDEX_VERSION
        )


class MemoLifecycleRuntime:
    """Serialize event mutation and generation activation in one process."""

    def __init__(
        self,
        ledger: SQLiteMemoLifecycleLedger,
        writer: QdrantLifecycleVectorWriter,
    ) -> None:
        self.ledger = ledger
        self.writer = writer
        self.processor = MemoLifecycleProcessor(ledger, writer)
        self._lock = threading.Lock()

    def process(self, event: MemoLifecycleEvent) -> LifecycleAcknowledgement:
        with self._lock:
            return self.processor.process(event)

    def activate(
        self, request: LifecycleActivationRequest
    ) -> LifecycleSnapshotAuthority:
        with self._lock:
            if request.generation != self.writer.generation:
                raise LifecycleRuntimeError
            entries = self._validated_manifest_entries(self.writer.records())
            if len(entries) != request.eligible_count:
                raise LifecycleRuntimeError
            digest = _manifest_digest(entries)
            if not hmac.compare_digest(digest, request.manifest_digest):
                raise LifecycleRuntimeError
            return self.ledger.select_active_generation(request.generation)

    def _validated_manifest_entries(
        self, records: Sequence[VectorSearchResult]
    ) -> list[tuple[str, str]]:
        entries: list[tuple[str, str]] = []
        seen: set[str] = set()
        for record in records:
            metadata = record.metadata
            if set(metadata) != _LIFECYCLE_METADATA_FIELDS:
                raise LifecycleRuntimeError
            source_sequence = metadata.get("source_sequence")
            document_hash = metadata.get("document_hash")
            if (
                not record.memo_id
                or record.memo_id in seen
                or type(source_sequence) is not int
                or source_sequence < 1
                or not isinstance(document_hash, str)
                or not _SHA256_PATTERN.fullmatch(document_hash)
                or metadata.get("rebuild_generation") != self.writer.generation
                or metadata.get("index_version") != MEMO_INDEX_VERSION
                or not self.ledger.retrieval_eligible(
                    record.memo_id,
                    vector_source_sequence=source_sequence,
                    vector_document_hash=document_hash,
                )
            ):
                raise LifecycleRuntimeError
            seen.add(record.memo_id)
            entries.append((record.memo_id, document_hash))
        return entries


def _manifest_digest(entries: Sequence[tuple[str, str]]) -> str:
    body = json.dumps(
        sorted(entries), ensure_ascii=False, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(body).hexdigest()
