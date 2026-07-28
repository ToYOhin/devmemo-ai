"""Optional Qdrant adapter behind the provider-neutral VectorStore contract."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any
from uuid import NAMESPACE_URL, uuid5

from app.domain.embeddings import (
    VectorDimensionError,
    VectorRecord,
    VectorSearchResult,
    VectorStoreHealth,
)


class QdrantUnavailableError(RuntimeError):
    """Raised when the optional qdrant-client package is not installed."""


class QdrantAdapterError(RuntimeError):
    """Raised when Qdrant cannot create or use the configured collection."""


class QdrantVectorStore:
    """Adapt qdrant-client without exposing its SDK types to the domain."""

    def __init__(self, client: Any, models: Any, dimension: int, collection_name: str) -> None:
        if dimension <= 0:
            raise ValueError("vector dimension must be positive")
        if not collection_name.strip():
            raise ValueError("Qdrant collection name must not be empty")
        self.client = client
        self.models = models
        self.dimension = dimension
        self.collection_name = collection_name
        self._ensure_collection()

    @classmethod
    def from_url(
        cls,
        url: str,
        dimension: int,
        collection_name: str,
        api_key: str | None = None,
    ) -> QdrantVectorStore:
        try:
            from qdrant_client import QdrantClient, models
        except ImportError as error:
            raise QdrantUnavailableError(
                "qdrant-client is not installed; install requirements-qdrant.txt "
                "before selecting AI_VECTOR_STORE=qdrant"
            ) from error

        client_kwargs: dict[str, object] = {"url": url}
        if api_key:
            client_kwargs["api_key"] = api_key
        try:
            client = QdrantClient(**client_kwargs)
            return cls(client, models, dimension, collection_name)
        except Exception as error:
            raise QdrantAdapterError(f"failed to connect to Qdrant at {url}") from error

    def upsert(self, record: VectorRecord) -> None:
        self._validate_vector(record.vector)
        point = self.models.PointStruct(
            id=str(_point_id(record.embedding_id)),
            vector=list(record.vector),
            payload={
                "embedding_id": record.embedding_id,
                "memo_id": record.memo_id,
                "metadata": dict(record.metadata),
            },
        )
        self.client.upsert(
            collection_name=self.collection_name,
            points=[point],
            wait=True,
        )

    def search(self, query: Sequence[float], limit: int = 5) -> list[VectorSearchResult]:
        self._validate_vector(query)
        if limit <= 0:
            raise ValueError("search limit must be positive")
        response = self.client.query_points(
            collection_name=self.collection_name,
            query=list(query),
            limit=limit,
            with_payload=True,
        )
        points = getattr(response, "points", response)
        return [_to_search_result(point) for point in points]

    def delete(self, embedding_id: str) -> bool:
        if not embedding_id:
            raise ValueError("embedding_id must not be empty")
        self.client.delete(
            collection_name=self.collection_name,
            points_selector=self.models.PointIdsList(points=[str(_point_id(embedding_id))]),
            wait=True,
        )
        return True

    def health(self) -> VectorStoreHealth:
        """Return a safe status snapshot without exposing Qdrant SDK types."""

        try:
            collection = self.client.get_collection(collection_name=self.collection_name)
            raw_status = getattr(collection, "status", "green")
            status = str(getattr(raw_status, "value", raw_status)).lower()
            point_count = getattr(collection, "points_count", None)
            if not isinstance(point_count, int):
                point_count = None
            return VectorStoreHealth(
                provider="qdrant",
                available=True,
                dimension=self.dimension,
                status=status,
                collection=self.collection_name,
                point_count=point_count,
            )
        except Exception as error:
            return VectorStoreHealth(
                provider="qdrant",
                available=False,
                dimension=self.dimension,
                status="unavailable",
                collection=self.collection_name,
                detail=f"Qdrant health check failed: {error}",
            )

    def _ensure_collection(self) -> None:
        try:
            if self.client.collection_exists(collection_name=self.collection_name):
                return
            self.client.create_collection(
                collection_name=self.collection_name,
                vectors_config=self.models.VectorParams(
                    size=self.dimension,
                    distance=self.models.Distance.COSINE,
                ),
            )
        except Exception as error:
            raise QdrantAdapterError(
                f"failed to initialize Qdrant collection {self.collection_name}"
            ) from error

    def _validate_vector(self, vector: Sequence[float]) -> None:
        if len(vector) != self.dimension:
            raise VectorDimensionError(
                f"expected vector dimension {self.dimension}, got {len(vector)}"
            )


def _point_id(embedding_id: str) -> str:
    return str(uuid5(NAMESPACE_URL, f"devmemo-ai:{embedding_id}"))


def _to_search_result(point: Any) -> VectorSearchResult:
    payload = dict(getattr(point, "payload", {}) or {})
    metadata = payload.get("metadata", {})
    if not isinstance(metadata, dict):
        metadata = {}
    return VectorSearchResult(
        embedding_id=str(payload.get("embedding_id", getattr(point, "id", ""))),
        memo_id=str(payload.get("memo_id", "")),
        score=float(getattr(point, "score", 0.0)),
        metadata=metadata,
    )
