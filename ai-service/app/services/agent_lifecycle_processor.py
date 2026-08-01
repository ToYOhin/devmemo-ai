"""Unwired processor for proving memo-v1 lifecycle crash recovery."""

from __future__ import annotations

from typing import Protocol

from app.adapters.agent_lifecycle_ledger import SQLiteMemoLifecycleLedger
from app.domain.agent_lifecycle import LifecycleAcknowledgement, MemoLifecycleEvent


class LifecycleVectorWriter(Protocol):
    """Minimal future vector-mutation boundary; A4-I3 uses only test fakes."""

    def upsert_memo(
        self,
        *,
        memo_uid: str,
        document: str,
        source_sequence: int,
        document_hash: str,
        index_version: str,
    ) -> None:
        ...

    def delete_memo(self, *, memo_uid: str, index_version: str) -> None:
        ...


class MemoLifecycleProcessor:
    """Apply one already-authenticated event through a durable reservation."""

    def __init__(
        self,
        ledger: SQLiteMemoLifecycleLedger,
        vector_writer: LifecycleVectorWriter,
    ) -> None:
        self.ledger = ledger
        self.vector_writer = vector_writer

    def process(self, event: MemoLifecycleEvent) -> LifecycleAcknowledgement:
        transition = self.ledger.reserve(event)
        if transition.acknowledgement is not None:
            return transition.acknowledgement

        try:
            if event.operation == "upsert":
                if event.document is None or event.document_hash is None:
                    raise RuntimeError("validated upsert event is missing document data")
                self.vector_writer.upsert_memo(
                    memo_uid=event.memo_uid,
                    document=event.document,
                    source_sequence=event.source_sequence,
                    document_hash=event.document_hash,
                    index_version=event.index_version,
                )
            else:
                self.vector_writer.delete_memo(
                    memo_uid=event.memo_uid,
                    index_version=event.index_version,
                )
        except Exception:
            _, acknowledgement = self.ledger.fail(
                event, "vector_store_unavailable"
            )
            return acknowledgement

        _, acknowledgement = self.ledger.complete(event)
        return acknowledgement
