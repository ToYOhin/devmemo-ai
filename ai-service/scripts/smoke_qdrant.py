"""Run a real Qdrant collection lifecycle smoke test.

This script is intentionally opt-in. It requires a running Qdrant instance and
an optional embedding dependency; the normal Compose path remains deterministic
and in-memory.
"""

from __future__ import annotations

import argparse
import os
from datetime import datetime, timezone

from app.adapters.embedding import DeterministicEmbeddingProvider
from app.adapters.fastembed_embedding import FastEmbedEmbeddingProvider
from app.adapters.qdrant_vector_store import QdrantVectorStore
from app.domain.embeddings import EmbeddingProvider, VectorRecord, VectorStoreHealth
from app.domain.memo_chunking import CHUNK_INDEX_MODE, CHUNK_INDEX_VERSION
from app.services.chunk_retrieval import ChunkRetrievalService
from app.services.embedding_service import EmbeddingService
from app.services.retrieval_service import RetrievalService


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--provider",
        choices=("deterministic", "fastembed"),
        default="fastembed",
        help="embedding provider used for the smoke test (default: fastembed)",
    )
    parser.add_argument(
        "--url",
        default=os.getenv("QDRANT_URL", "http://127.0.0.1:6333"),
        help="Qdrant URL (default: QDRANT_URL or localhost)",
    )
    parser.add_argument(
        "--collection",
        default=None,
        help="collection name; defaults to a timestamped smoke collection",
    )
    parser.add_argument(
        "--mode",
        choices=("memo", "chunk"),
        default="memo",
        help="smoke contract to exercise (default: memo)",
    )
    parser.add_argument(
        "--delete-collection",
        action="store_true",
        help="delete an explicitly supplied collection after the smoke test",
    )
    parser.add_argument(
        "--cache-dir",
        default=os.getenv("AI_FASTEMBED_CACHE_DIR") or None,
        help="FastEmbed cache directory; default: AI_FASTEMBED_CACHE_DIR",
    )
    args = parser.parse_args()

    if args.provider == "fastembed":
        provider = FastEmbedEmbeddingProvider.from_model_name(
            "BAAI/bge-small-en-v1.5",
            dimension=384,
            cache_dir=args.cache_dir,
        )
    else:
        provider = DeterministicEmbeddingProvider()

    generated_collection = args.collection is None
    collection = args.collection or (
        "devmemo_phase3e_smoke_"
        + datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    )
    store = QdrantVectorStore.from_url(
        args.url,
        dimension=provider.dimension,
        collection_name=collection,
    )

    try:
        records = _build_records(provider, args.mode)
        first = records[0].vector
        for record in records:
            store.upsert(record)

        initial_health = store.health()
        _require_available(initial_health, "initial")
        if initial_health.point_count != len(records):
            raise RuntimeError(
                f"Qdrant health reported {initial_health.point_count} points; "
                f"expected {len(records)}"
            )

        before_delete = store.search(first, limit=len(records))
        if not before_delete or before_delete[0].embedding_id != records[0].embedding_id:
            raise RuntimeError("Qdrant search did not return the nearest smoke point")

        reconnected_store = QdrantVectorStore.from_url(
            args.url,
            dimension=provider.dimension,
            collection_name=collection,
        )
        reconnected_health = reconnected_store.health()
        _require_available(reconnected_health, "reconnected")
        if reconnected_health.point_count != len(records):
            raise RuntimeError(
                f"Qdrant reconnect reported {reconnected_health.point_count} points; "
                f"expected {len(records)}"
            )
        persisted = reconnected_store.search(first, limit=len(records))
        if not persisted or persisted[0].embedding_id != records[0].embedding_id:
            raise RuntimeError("Qdrant reconnect did not preserve the smoke point")
        if args.mode == "chunk":
            retrieval = ChunkRetrievalService(
                RetrievalService(EmbeddingService(provider, reconnected_store))
            ).retrieve("FastAPI Docker port mapping", limit=2)
            if not retrieval.citations:
                raise RuntimeError("Qdrant chunk retrieval returned no citations")
            if retrieval.citations[0].chunk_id != records[0].embedding_id:
                raise RuntimeError("Qdrant chunk retrieval returned the wrong chunk")
            if "content" in retrieval.citations[0].metadata:
                raise RuntimeError("Qdrant chunk citation leaked internal content")

        if not reconnected_store.delete(records[0].embedding_id):
            raise RuntimeError("Qdrant delete did not acknowledge the smoke point")
        after_delete = reconnected_store.search(first, limit=len(records))
        if any(result.embedding_id == records[0].embedding_id for result in after_delete):
            raise RuntimeError("Qdrant delete left the smoke point searchable")
        final_health = reconnected_store.health()
        _require_available(final_health, "final")
        if final_health.point_count != len(records) - 1:
            raise RuntimeError(
                f"Qdrant final health reported {final_health.point_count} points; "
                f"expected {len(records) - 1}"
            )

        print("QDRANT_CHUNK_SMOKE_OK" if args.mode == "chunk" else "QDRANT_SMOKE_OK")
        print(f"provider={provider.name}")
        print(f"dimension={provider.dimension}")
        print(f"mode={args.mode}")
        print(f"collection={collection}")
        print(f"initial_point_count={initial_health.point_count}")
        print(f"reconnected_point_count={reconnected_health.point_count}")
        print(f"before_delete={[result.embedding_id for result in before_delete]}")
        print(f"after_delete={[result.embedding_id for result in after_delete]}")
    finally:
        if generated_collection or args.delete_collection:
            store.client.delete_collection(collection_name=collection)


def _build_records(
    provider: EmbeddingProvider,
    mode: str,
) -> tuple[VectorRecord, ...]:
    texts = ("FastAPI Docker port mapping", "Go SQLite migration")
    records: list[VectorRecord] = []
    for index, text in enumerate(texts):
        if mode == "chunk":
            embedding_id = f"memo-chunk-v1:smoke:{index:04d}"
            memo_id = "memo-smoke"
            metadata = {
                "content": text,
                "memo_id": memo_id,
                "chunk_id": embedding_id,
                "chunk_index": index,
                "chunk_count": len(texts),
                "index_mode": CHUNK_INDEX_MODE,
                "index_version": CHUNK_INDEX_VERSION,
                "source_type": "memo_chunk",
                "provider": provider.name,
            }
        else:
            embedding_id = f"smoke-{index + 1}"
            memo_id = f"memo-{index + 1}"
            metadata = {"title": text, "provider": provider.name}
        vector = provider.embed(text).values
        records.append(
            VectorRecord(
                embedding_id,
                memo_id,
                vector,
                metadata,
            )
        )
    return tuple(records)


def _require_available(health: VectorStoreHealth, phase: str) -> None:
    if not health.available:
        raise RuntimeError(f"Qdrant {phase} health is unavailable: {health.detail}")


if __name__ == "__main__":
    main()
