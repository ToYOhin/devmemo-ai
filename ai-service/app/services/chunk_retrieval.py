"""Provider-neutral internal retrieval contract for Memo chunks."""

from __future__ import annotations

from app.domain.memo_chunking import CHUNK_INDEX_MODE, CHUNK_INDEX_VERSION
from app.domain.retrieval import (
    ChunkCitation,
    ChunkRetrievalResult,
    Citation,
    RetrievalUnavailableError,
)
from app.services.retrieval_service import RetrievalService


class ChunkRetrievalService:
    """Validate chunk metadata after shared query embedding and vector search."""

    def __init__(self, retrieval_service: RetrievalService) -> None:
        self.retrieval_service = retrieval_service

    def retrieve(self, question: str, limit: int = 5) -> ChunkRetrievalResult:
        result = self.retrieval_service.retrieve(question, limit=limit)
        citations = tuple(self._to_chunk_citation(citation) for citation in result.citations)
        return ChunkRetrievalResult(context=result.context, citations=citations)

    @staticmethod
    def _to_chunk_citation(citation: Citation) -> ChunkCitation:
        metadata = dict(citation.metadata)
        if metadata.get("source_type") != "memo_chunk":
            raise RetrievalUnavailableError("chunk retrieval metadata source_type is invalid")
        if metadata.get("index_mode") != CHUNK_INDEX_MODE:
            raise RetrievalUnavailableError("chunk retrieval metadata index_mode is invalid")
        if metadata.get("index_version") != CHUNK_INDEX_VERSION:
            raise RetrievalUnavailableError("chunk retrieval metadata index_version is invalid")

        chunk_id = metadata.get("chunk_id")
        if not isinstance(chunk_id, str) or chunk_id != citation.embedding_id:
            raise RetrievalUnavailableError("chunk retrieval metadata chunk_id is invalid")
        if citation.memo_id != metadata.get("memo_id"):
            raise RetrievalUnavailableError("chunk retrieval metadata memo_id is invalid")

        chunk_index = metadata.get("chunk_index")
        if isinstance(chunk_index, bool) or not isinstance(chunk_index, int) or chunk_index < 0:
            raise RetrievalUnavailableError("chunk retrieval metadata chunk_index is invalid")

        return ChunkCitation(
            memo_id=citation.memo_id,
            chunk_id=chunk_id,
            chunk_index=chunk_index,
            index_version=CHUNK_INDEX_VERSION,
            score=citation.score,
            metadata=metadata,
        )
