"""Pure, single-tool Evidence Answer Agent execution service."""

from __future__ import annotations

from datetime import datetime
from typing import Protocol

from app.domain.agent import (
    AGENT_REFUSAL_ANSWER,
    AgentAnswerResult,
    AgentCitation,
    AgentStep,
    AgentTrace,
    EvidenceMetadata,
    MemoVisibilityScope,
    SearchMemosToolCall,
    VisibleMemoEvidence,
)
from app.domain.durable_authorized_retrieval import (
    AuthorizedRetrievalEvidence,
    AuthorizedRetrievalResult,
)
from app.domain.grounded_answer import (
    GroundedAnswerContractError,
    GroundedAnswerFailureCode,
    map_grounded_answer_failure,
    parse_provider_grounded_answer,
    validate_grounded_answer,
)
from app.domain.retrieval import Citation, RetrievalInputError, RetrievalUnavailableError
from app.services.agent_delegation import (
    INTERNAL_ANSWER_PATH,
    AgentDelegationHeaders,
    DelegatedAnswerRequest,
    verify_delegated_request,
)
from app.services.agent_observability_runtime import (
    AgentObservabilityRecorder,
    MonotonicClock,
    ProviderObservabilityOutcome,
    RetrievalObservabilityOutcome,
    record_provider_observation,
    record_retrieval_observation,
    start_provider_observation,
    start_retrieval_observation,
)
from app.services.agent_refusal_policy import should_refuse_agent_question
from app.services.retrieval_service import RetrievalService


class AgentProviderError(RuntimeError):
    """Raised when the configured answer provider cannot complete safely."""

    def __init__(self, error_code: GroundedAnswerFailureCode) -> None:
        self.error_code = error_code
        super().__init__("Agent provider unavailable")


class DurableAgentRetrieval(Protocol):
    async def retrieve(
        self, request: DelegatedAnswerRequest
    ) -> AuthorizedRetrievalResult:
        ...


class AgentProviderResult(Protocol):
    @property
    def text(self) -> str:
        ...


class AgentProvider(Protocol):
    name: str

    async def generate(self, prompt: str) -> AgentProviderResult:
        ...


class EvidenceAnswerAgent:
    """Execute one authorized whole-Memo search without HTTP or persistence."""

    def __init__(
        self,
        retrieval_service: RetrievalService,
        provider: AgentProvider,
        durable_retrieval: DurableAgentRetrieval | None = None,
        *,
        observability_recorder: AgentObservabilityRecorder | None = None,
        monotonic_clock: MonotonicClock | None = None,
    ) -> None:
        self._retrieval_service = retrieval_service
        self._provider = provider
        self._durable_retrieval = durable_retrieval
        self._observability_recorder = observability_recorder
        self._monotonic_clock = monotonic_clock

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
        if should_refuse_agent_question(request.question):
            return AgentAnswerResult(
                answer=AGENT_REFUSAL_ANSWER,
                citations=(),
                visibility=visibility,
                provider="policy",
                retrieved_count=0,
                trace=AgentTrace(
                    terminal_state="refused",
                    steps=(
                        AgentStep(
                            1,
                            "final",
                            "refuse_unsafe_request",
                            "completed",
                        ),
                    ),
                ),
            )
        tool_call = SearchMemosToolCall(
            question=request.question,
            limit=request.limit,
            visibility=visibility,
        )
        started_at = start_retrieval_observation(self._monotonic_clock)
        retrieval_outcome: RetrievalObservabilityOutcome = "unavailable"
        try:
            if self._durable_retrieval is None:
                retrieved = self._retrieval_service.retrieve_authorized(
                    tool_call.question,
                    tool_call.limit,
                    tool_call.visibility.visible_memo_ids,
                )
                citations = tuple(
                    _safe_citation(citation, visibility)
                    for citation in retrieved.citations
                )
                context = retrieved.context
                protected_context_fragments = retrieved.protected_context_fragments
            else:
                try:
                    durable = await self._durable_retrieval.retrieve(request)
                    if not isinstance(durable, AuthorizedRetrievalResult):
                        raise TypeError
                    citations = tuple(
                        _safe_durable_citation(evidence, visibility)
                        for evidence in durable.evidence
                    )
                    context = durable.context
                    protected_context_fragments = durable.protected_context_fragments
                except Exception as error:
                    raise RetrievalUnavailableError(
                        "Agent retrieval unavailable"
                    ) from error
            retrieval_outcome = "success" if citations else "no_context"
        except RetrievalInputError:
            retrieval_outcome = "invalid"
            raise
        finally:
            record_retrieval_observation(
                self._observability_recorder,
                self._monotonic_clock,
                started_at,
                retrieval_outcome,
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
            context,
            citations,
            protected_context_fragments,
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
            "references. Do not include any other fields. Output JSON only, without "
            "Markdown fences, prefixes, suffixes, or explanation. Example: "
            '{"version":"grounded-answer-result-v1","answer":"Concise grounded '
            'answer.","citation_refs":["evidence-1"]}\n'
            f"Question: {question}\n"
            f"Evidence:\n{context}"
        )
        evidence_by_reference = {
            f"evidence-{index}": citation
            for index, citation in enumerate(citations, start=1)
        }
        try:
            provider_started_at = start_provider_observation(self._monotonic_clock)
            provider_outcome: ProviderObservabilityOutcome = "unavailable"
            try:
                provider_result = await self._provider.generate(prompt)
                if not isinstance(provider_result.text, str):
                    provider_outcome = "invalid"
                    raise GroundedAnswerContractError
                provider_outcome = "success"
            finally:
                record_provider_observation(
                    self._observability_recorder,
                    self._monotonic_clock,
                    provider_started_at,
                    provider_outcome,
                )
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


def _safe_citation(citation: Citation, visibility: MemoVisibilityScope) -> AgentCitation:
    metadata = dict(citation.metadata)
    raw_tags = metadata.get("tags")
    tags = (
        tuple(str(tag) for tag in raw_tags if str(tag).strip())
        if isinstance(raw_tags, (list, tuple))
        else ()
    )
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


def _safe_durable_citation(
    evidence: AuthorizedRetrievalEvidence,
    visibility: MemoVisibilityScope,
) -> AgentCitation:
    citation = evidence.citation
    safe = VisibleMemoEvidence(
        memo_id=citation.memo_uid,
        embedding_id=(
            f"{citation.index_version}-{citation.memo_uid}-{citation.source_sequence}"
        ),
        score=0.0,
        title="",
        summary="Authorized current Memo retrieved as durable evidence.",
        source_refs=(f"memos/{citation.memo_uid}",),
        metadata=EvidenceMetadata(index_version=citation.index_version),
    )
    return safe.citation_for(visibility)


def _provider_name(provider: AgentProvider) -> str:
    return str(provider.name)
