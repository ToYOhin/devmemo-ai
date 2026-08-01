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
from app.domain.grounded_answer import (
    GroundedAnswerContractError,
    GroundedAnswerFailureCode,
    map_grounded_answer_failure,
    parse_provider_grounded_answer,
    validate_grounded_answer,
)
from app.services.agent_delegation import (
    INTERNAL_ANSWER_PATH,
    AgentDelegationHeaders,
    DelegatedAnswerRequest,
    verify_delegated_request,
)
from app.services.retrieval_service import RetrievalService


class AgentProviderError(RuntimeError):
    """Raised when the configured answer provider cannot complete safely."""

    def __init__(self, error_code: GroundedAnswerFailureCode) -> None:
        self.error_code = error_code
        super().__init__("Agent provider unavailable")


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

        answer, answer_citations = await self._answer(
            request.question,
            retrieved.context,
            citations,
            retrieved.protected_context_fragments,
        )
        return AgentAnswerResult(
            answer=answer,
            citations=answer_citations,
            visibility=visibility,
            provider=_provider_name(self._provider),
            retrieved_count=len(answer_citations),
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
        protected_context_fragments: tuple[str, ...],
    ) -> tuple[str, tuple[AgentCitation, ...]]:
        fallback = f"Found {len(citations)} authorized Memo source(s) relevant to the question [1]."
        if _provider_name(self._provider) == "deterministic":
            return fallback, citations

        prompt = (
            "Answer using only the authorized evidence below. Return exactly one JSON "
            "object with fields version, answer, and citation_refs. Set version to "
            '"grounded-answer-result-v1" and cite only the provided evidence-* '
            "references. Do not include any other fields.\n"
            f"Question: {question}\n"
            f"Evidence:\n{context}"
        )
        evidence_by_reference = {
            f"evidence-{index}": citation
            for index, citation in enumerate(citations, start=1)
        }
        try:
            provider_result = await self._provider.generate(prompt)
            if not isinstance(provider_result.text, str):
                raise GroundedAnswerContractError
            parsed = parse_provider_grounded_answer(
                provider_result.text.encode("utf-8")
            )
            validated = validate_grounded_answer(
                parsed,
                evidence_by_reference,
                protected_context_fragments=protected_context_fragments,
            )
        except Exception as error:
            failure = map_grounded_answer_failure(error)
            raise AgentProviderError(failure.error_code) from error
        return validated.answer, validated.citations


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
