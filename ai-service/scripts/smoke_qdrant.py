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
from app.domain.embeddings import VectorRecord


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
        first = provider.embed("FastAPI Docker port mapping").values
        second = provider.embed("Go SQLite migration").values
        store.upsert(
            VectorRecord(
                "smoke-1",
                "memo-1",
                first,
                {"title": "Docker ports", "provider": provider.name},
            )
        )
        store.upsert(
            VectorRecord(
                "smoke-2",
                "memo-2",
                second,
                {"title": "Go SQLite", "provider": provider.name},
            )
        )
        before_delete = store.search(first, limit=2)
        if not before_delete or before_delete[0].embedding_id != "smoke-1":
            raise RuntimeError("Qdrant search did not return the nearest smoke point")
        if not store.delete("smoke-1"):
            raise RuntimeError("Qdrant delete did not acknowledge the smoke point")
        after_delete = store.search(first, limit=2)
        if any(result.embedding_id == "smoke-1" for result in after_delete):
            raise RuntimeError("Qdrant delete left the smoke point searchable")

        print("QDRANT_SMOKE_OK")
        print(f"provider={provider.name}")
        print(f"dimension={provider.dimension}")
        print(f"collection={collection}")
        print(f"before_delete={[result.embedding_id for result in before_delete]}")
        print(f"after_delete={[result.embedding_id for result in after_delete]}")
    finally:
        store.client.delete_collection(collection_name=collection)


if __name__ == "__main__":
    main()
