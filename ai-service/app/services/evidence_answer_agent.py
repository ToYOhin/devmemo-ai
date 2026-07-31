"""Pure, single-tool Evidence Answer Agent execution service."""

from __future__ import annotations

from datetime import datetime

from app.domain.agent import (
    AgentAnswerResult,
    AgentCitation,
    AgentStep,
    AgentTrace,
    EvidenceMetadata,
    MemoVisibilityScope,
    SearchMemosToolCall,
    VisibleMemoEvidence,
)
from app.services.agent_delegation import (
    INTERNAL_ANSWER_PATH,
    AgentDelegationHeaders,
    DelegatedAnswerRequest,
    verify_delegated_request,
)
from app.services.retrieval_service import RetrievalService


class EvidenceAnswerAgent:
    """Execute one authorized whole-Memo search without HTTP or persistence."""

    def __init__(self, retrieval_service: RetrievalService, provider: object) -> None:
        self._retrieval_service = retrieval_service
        self._provider = provider

    async def run_delegated(
        self,
        body: bytes,
        headers: AgentDelegationHeaders,
        secret: str,
        now: datetime,
    ) -> AgentAnswerResult:
        """Verify the Memos capability before any search or context assembly."""

        request = verify_delegated_request(
            "POST",
            INTERNAL_ANSWER_PATH,
            body,
            headers,
            secret,
            now,
        )
        return await self._run(request)

    async def _run(self, request: DelegatedAnswerRequest) -> AgentAnswerResult:
        visibility = MemoVisibilityScope(frozenset(request.visible_memo_uids))
        tool_call = SearchMemosToolCall(
            question=request.question,
            limit=request.limit,
            visibility=visibility,
        )
        retrieved = self._retrieval_service.retrieve_authorized(
            tool_call.question,
            tool_call.limit,
            tool_call.visibility.visible_memo_ids,
        )
        citations = tuple(
            _safe_citation(citation, visibility)
            for citation in retrieved.citations
        )
        search_step = AgentStep(
            1,
            "tool",
            tool_call.name,
            "completed",
            result_count=len(citations),
        )
        if not citations:
            return AgentAnswerResult(
                answer="No visible Memo provides relevant evidence.",
                citations=(),
                visibility=visibility,
                provider=_provider_name(self._provider),
                retrieved_count=0,
                trace=AgentTrace(terminal_state="no_context", steps=(search_step,)),
            )

        answer = await self._answer(request.question, retrieved.context, citations)
        return AgentAnswerResult(
            answer=answer,
            citations=citations,
            visibility=visibility,
            provider=_provider_name(self._provider),
            retrieved_count=len(citations),
            trace=AgentTrace(
                terminal_state="answered",
                steps=(
                    search_step,
                    AgentStep(2, "final", "answer_from_evidence", "completed"),
                ),
            ),
        )

    async def _answer(
        self,
        question: str,
        context: str,
        citations: tuple[AgentCitation, ...],
    ) -> str:
        fallback = f"Found {len(citations)} authorized Memo source(s) relevant to the question [1]."
        if _provider_name(self._provider) == "deterministic":
            return fallback

        prompt = (
            "Answer the question using only the authorized knowledge-base context below. "
            "Cite sources with [1], [2] in context order.\n"
            f"Question: {question}\n"
            f"Context:\n{context}"
        )
        result = await self._provider.generate(prompt)
        answer = result.text.strip()
        if not answer or "[" not in answer or _contains_complete_memo_content(answer, context):
            return fallback
        return answer


def _safe_citation(citation: object, visibility: MemoVisibilityScope) -> AgentCitation:
    metadata = dict(citation.metadata)
    tags = tuple(str(tag) for tag in metadata.get("tags", []) if str(tag).strip())
    evidence = VisibleMemoEvidence(
        memo_id=citation.memo_id,
        embedding_id=citation.embedding_id,
        score=citation.score,
        title=str(metadata.get("title") or ""),
        summary="Authorized complete Memo retrieved as evidence.",
        source_refs=(f"memos/{citation.memo_id}",),
        metadata=EvidenceMetadata(
            memo_type=str(metadata.get("memo_type") or "plain"),
            tags=tags,
            index_version="memo-v1",
        ),
    )
    return evidence.citation_for(visibility)


def _provider_name(provider: object) -> str:
    return str(provider.name)


def _contains_complete_memo_content(answer: str, context: str) -> bool:
    """Reject a provider response that includes an entire internal Memo block."""

    for block in context.split("\n\n"):
        _, separator, content = block.partition("\n")
        if separator and content and content != "(memo content unavailable)" and content in answer:
            return True
    return False
