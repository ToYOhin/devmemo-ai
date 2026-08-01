"""Whole-Memo retrieval orchestration independent from FastAPI and SDKs."""

from __future__ import annotations

from app.adapters.vector_store import InMemoryVectorStore
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
        return self._retrieve(question, limit)

    def retrieve_authorized(
        self,
        question: str,
        limit: int,
        visible_memo_ids: frozenset[str],
    ) -> RetrievalResult:
        """Retrieve only caller-authorized complete Memos before assembling context."""

        return self._retrieve(question, limit, visible_memo_ids=visible_memo_ids)

    def _retrieve(
        self,
        question: str,
        limit: int,
        visible_memo_ids: frozenset[str] | None = None,
    ) -> RetrievalResult:
        normalized_question = question.strip()
        if not normalized_question:
            raise RetrievalInputError("question must not be empty")
        if limit < 1 or limit > self.MAX_LIMIT:
            raise RetrievalInputError(f"retrieval limit must be between 1 and {self.MAX_LIMIT}")
        if visible_memo_ids is not None and not visible_memo_ids:
            return RetrievalResult(context="", citations=())

        try:
            query = self.embedding_service.provider.embed(normalized_question)
            if visible_memo_ids is None:
                results = self.embedding_service.store.search(query.values, limit=limit)
            else:
                store = self.embedding_service.store
                if not isinstance(store, InMemoryVectorStore):
                    raise RetrievalUnavailableError(
                        "authorized Agent retrieval requires the memory vector store"
                    )
                results = store.search_visible_memos(query.values, visible_memo_ids, limit=limit)
                results = [
                    result
                    for result in results
                    if result.metadata.get("index_version") == "memo-v1"
                ]
        except RetrievalInputError:
            raise
        except RetrievalUnavailableError:
            raise
        except Exception as error:
            raise RetrievalUnavailableError("knowledge-base retrieval unavailable") from error

        citations: list[Citation] = []
        context_blocks: list[str] = []
        protected_context_fragments: list[str] = []
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
            if visible_memo_ids is None:
                context_blocks.append(
                    _format_context_block(
                        index, result.memo_id, result.score, metadata, content
                    )
                )
            else:
                context_blocks.append(_format_agent_context_block(index, content))
                if content:
                    protected_context_fragments.append(content)

        return RetrievalResult(
            context="\n\n".join(context_blocks),
            citations=tuple(citations),
            protected_context_fragments=tuple(protected_context_fragments),
        )


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


def _format_agent_context_block(index: int, content: str) -> str:
    return f"[evidence-{index}]\n{content or '(memo content unavailable)'}"
