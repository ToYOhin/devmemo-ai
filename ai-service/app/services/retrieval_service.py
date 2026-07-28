"""Whole-Memo retrieval orchestration independent from FastAPI and SDKs."""

from __future__ import annotations

from app.domain.retrieval import (
    Citation,
    RetrievalInputError,
    RetrievalResult,
    RetrievalUnavailableError,
)
from app.services.embedding_service import EmbeddingService


class RetrievalService:
    """Embed a question, search the configured store, and assemble citations."""

    MAX_LIMIT = 10

    def __init__(self, embedding_service: EmbeddingService) -> None:
        self.embedding_service = embedding_service

    def retrieve(self, question: str, limit: int = 5) -> RetrievalResult:
        normalized_question = question.strip()
        if not normalized_question:
            raise RetrievalInputError("question must not be empty")
        if limit < 1 or limit > self.MAX_LIMIT:
            raise RetrievalInputError(f"retrieval limit must be between 1 and {self.MAX_LIMIT}")

        try:
            query = self.embedding_service.provider.embed(normalized_question)
            results = self.embedding_service.store.search(query.values, limit=limit)
        except RetrievalInputError:
            raise
        except Exception as error:
            raise RetrievalUnavailableError("knowledge-base retrieval unavailable") from error

        citations: list[Citation] = []
        context_blocks: list[str] = []
        for index, result in enumerate(results, start=1):
            metadata = dict(result.metadata)
            content = str(metadata.pop("content", "")).strip()
            citations.append(
                Citation(
                    memo_id=result.memo_id,
                    embedding_id=result.embedding_id,
                    score=result.score,
                    metadata=metadata,
                )
            )
            context_blocks.append(
                _format_context_block(index, result.memo_id, result.score, metadata, content)
            )

        return RetrievalResult(context="\n\n".join(context_blocks), citations=tuple(citations))


def _format_context_block(
    index: int,
    memo_id: str,
    score: float,
    metadata: dict[str, object],
    content: str,
) -> str:
    title = str(metadata.get("title") or "")
    header = f"[{index}] memo_id={memo_id} score={score:.6f}"
    if title:
        header += f" title={title}"
    return f"{header}\n{content or '(memo content unavailable)'}"
