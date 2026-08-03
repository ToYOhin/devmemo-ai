"""Offline synthetic execution harness for the versioned Agent corpus."""

from __future__ import annotations

import math
import time
from collections.abc import Callable

from app.adapters.embedding import DeterministicEmbeddingProvider
from app.adapters.vector_store import InMemoryVectorStore
from app.domain.agent_evaluation import (
    AgentEvaluationCase,
    AgentEvaluationCorpus,
    EvaluationFailureCategory,
    AgentEvaluationResult,
    AgentEvaluationThresholds,
    ObservedAnswerState,
)
from app.domain.agent_evaluation_report import AgentEvaluationReport
from app.services.agent_delegation import DelegatedAnswerRequest
from app.services.agent_evaluation_runner import run_evaluation
from app.services.embedding_service import EmbeddingService
from app.services.evidence_answer_agent import EvidenceAnswerAgent
from app.services.memo_indexing import MemoIndexDocument, index_memo
from app.services.retrieval_service import RetrievalService
from llm import DeterministicProvider


EvaluationClock = Callable[[], float]


async def run_synthetic_agent_evaluation(
    corpus: AgentEvaluationCorpus,
    thresholds: AgentEvaluationThresholds,
    *,
    clock: EvaluationClock = time.perf_counter,
) -> AgentEvaluationReport:
    """Run synthetic evidence through the real in-memory Agent core."""

    results = tuple(
        [await _run_synthetic_case(case, clock) for case in corpus.cases]
    )
    return run_evaluation(corpus, thresholds, results)


async def _run_synthetic_case(
    case: AgentEvaluationCase,
    clock: EvaluationClock,
) -> AgentEvaluationResult:
    service = EmbeddingService(
        DeterministicEmbeddingProvider(),
        InMemoryVectorStore(8),
    )
    for evidence_id in case.visible_evidence_ids:
        index_memo(
            service,
            MemoIndexDocument.from_memo(
                evidence_id,
                _synthetic_evidence(case, evidence_id),
                {"title": "Synthetic evaluation evidence", "tags": ["synthetic"]},
            ),
        )
    agent = EvidenceAnswerAgent(
        RetrievalService(service),
        DeterministicProvider(),
    )
    request = DelegatedAnswerRequest(
        question=case.question,
        limit=10,
        visible_memo_uids=case.visible_evidence_ids,
    )
    started_at = _read_clock(clock)
    answer_state: ObservedAnswerState
    failures: tuple[EvaluationFailureCategory, ...]
    try:
        result = await agent._run(request)
        citations = tuple(citation.memo_id for citation in result.citations)
        if result.trace.terminal_state == "no_context":
            answer_state = "no_answer"
        elif result.trace.terminal_state == "refused":
            answer_state = "refusal"
        else:
            answer_state = "answer"
        failures = ()
    except Exception:
        citations = ()
        answer_state = "error"
        failures = ("runtime_error",)
    latency_ms = _elapsed_ms(started_at, _read_clock(clock))
    return AgentEvaluationResult(
        case_id=case.case_id,
        answer_state=answer_state,
        retrieved_evidence_ids=citations,
        citation_evidence_ids=citations if answer_state == "answer" else (),
        failure_categories=failures,
        latency_ms=latency_ms,
    )


def _synthetic_evidence(case: AgentEvaluationCase, evidence_id: str) -> str:
    if case.category == "prompt_injection":
        return (
            f"{case.question} Synthetic untrusted text asks to ignore instructions. "
            f"Opaque record {evidence_id}."
        )
    return f"{case.question} Synthetic supporting record {evidence_id}."


def _read_clock(clock: EvaluationClock) -> float:
    value = clock()
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("invalid synthetic evaluation clock")
    value = float(value)
    if not math.isfinite(value):
        raise ValueError("invalid synthetic evaluation clock")
    return value


def _elapsed_ms(started_at: float, stopped_at: float) -> int:
    elapsed_ms = round((stopped_at - started_at) * 1000)
    if not 0 <= elapsed_ms <= 600_000:
        raise ValueError("invalid synthetic evaluation elapsed time")
    return elapsed_ms
