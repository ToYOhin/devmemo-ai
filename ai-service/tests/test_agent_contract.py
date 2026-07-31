import pytest

from app.domain.agent import (
    AGENT_VERSION,
    AgentAnswerRequest,
    AgentAnswerResult,
    AgentCitation,
    AgentContractError,
    AgentStep,
    AgentTrace,
    EvidenceMetadata,
    MemoVisibilityScope,
    SearchMemosToolCall,
    VisibleMemoEvidence,
)


def _evidence() -> VisibleMemoEvidence:
    return VisibleMemoEvidence(
        memo_id="memo-42",
        embedding_id="memo-42-vector",
        score=0.9,
        title="Docker ports",
        summary="The Compose port mapping was corrected.",
        source_refs=("memo.name", "memo.content.summary"),
        metadata=EvidenceMetadata(memo_type="plain", tags=("docker",)),
    )


def _keys(value: object) -> set[str]:
    if isinstance(value, dict):
        return set(value).union(*(_keys(item) for item in value.values()))
    if isinstance(value, list):
        return set().union(*(_keys(item) for item in value))
    return set()


def test_agent_contract_serializes_only_safe_complete_memo_evidence():
    scope = MemoVisibilityScope(frozenset({"memo-42"}))
    citation = _evidence().citation_for(scope)
    result = AgentAnswerResult(
        answer="The Compose port mapping was corrected [1].",
        citations=(citation,),
        visibility=scope,
        provider="deterministic",
        retrieved_count=1,
        trace=AgentTrace(
            terminal_state="answered",
            steps=(
                AgentStep(1, "tool", "search_memos", "completed", result_count=1),
                AgentStep(2, "final", "answer_from_evidence", "completed"),
            ),
        ),
    )

    payload = result.to_dict()

    assert payload["agent_version"] == AGENT_VERSION
    assert payload["citations"] == [
        {
            "memo_id": "memo-42",
            "embedding_id": "memo-42-vector",
            "score": 0.9,
            "title": "Docker ports",
            "summary": "The Compose port mapping was corrected.",
            "source_refs": ["memo.name", "memo.content.summary"],
            "metadata": {
                "memo_type": "plain",
                "tags": ["docker"],
                "index_version": "memo-v1",
            },
        }
    ]
    assert "content" not in _keys(payload)
    assert payload["trace"] == {
        "terminal_state": "answered",
        "steps": [
            {
                "index": 1,
                "kind": "tool",
                "name": "search_memos",
                "status": "completed",
                "result_count": 1,
            },
            {
                "index": 2,
                "kind": "final",
                "name": "answer_from_evidence",
                "status": "completed",
            },
        ],
    }


def test_agent_contract_rejects_invisible_or_chunk_evidence():
    with pytest.raises(AgentContractError, match="not visible"):
        _evidence().citation_for(MemoVisibilityScope(frozenset({"memo-elsewhere"})))

    with pytest.raises(AgentContractError, match="complete-Memo memo-v1"):
        EvidenceMetadata(index_version="memo-chunk-v1")  # type: ignore[arg-type]

    with pytest.raises(AgentContractError, match="controlled EvidenceMetadata"):
        AgentCitation(  # type: ignore[arg-type]
            memo_id="memo-42",
            embedding_id="memo-42-vector",
            score=0.9,
            title="Docker ports",
            summary="Safe summary",
            source_refs=(),
            metadata={"content": "raw Memo"},
        )

    with pytest.raises(AgentContractError, match="visible to the caller"):
        AgentAnswerResult(
            answer="Answer [1]",
            citations=(
                AgentCitation(
                    memo_id="memo-42",
                    embedding_id="memo-42-vector",
                    score=0.9,
                    title="Docker ports",
                    summary="Safe summary",
                    source_refs=(),
                    metadata=EvidenceMetadata(),
                ),
            ),
            visibility=MemoVisibilityScope(frozenset({"memo-elsewhere"})),
            provider="deterministic",
            retrieved_count=1,
            trace=AgentTrace(
                terminal_state="answered",
                steps=(
                    AgentStep(1, "tool", "search_memos", "completed", result_count=1),
                    AgentStep(2, "final", "answer_from_evidence", "completed"),
                ),
            ),
        )


def test_agent_contract_allows_only_one_read_only_search_tool():
    request = AgentAnswerRequest(question=" Docker ports ", limit=3)
    call = SearchMemosToolCall(
        question=request.question,
        limit=request.limit,
        visibility=MemoVisibilityScope(frozenset({"memo-42"})),
    )

    assert call.name == "search_memos"
    assert call.question == "Docker ports"

    with pytest.raises(AgentContractError, match="only permitted Agent tool"):
        SearchMemosToolCall(
            question="Docker ports",
            limit=3,
            visibility=MemoVisibilityScope(frozenset({"memo-42"})),
            name="write_memo",  # type: ignore[arg-type]
        )

    with pytest.raises(AgentContractError, match="retrieval limit"):
        AgentAnswerRequest(question="Docker ports", limit=11)


def test_no_context_trace_has_one_search_and_no_provider_finalization():
    result = AgentAnswerResult(
        answer="No visible Memo provides relevant evidence.",
        citations=(),
        visibility=MemoVisibilityScope(frozenset()),
        provider="deterministic",
        retrieved_count=0,
        trace=AgentTrace(
            terminal_state="no_context",
            steps=(AgentStep(1, "tool", "search_memos", "completed", result_count=0),),
        ),
    )

    assert result.to_dict()["trace"]["terminal_state"] == "no_context"


def test_trace_rejects_additional_or_non_search_tools():
    with pytest.raises(AgentContractError, match="only permitted Agent tool"):
        AgentStep(1, "tool", "fetch_url", "completed")

    with pytest.raises(AgentContractError, match="exactly one search_memos"):
        AgentTrace(
            terminal_state="no_context",
            steps=(
                AgentStep(1, "tool", "search_memos", "completed", result_count=0),
                AgentStep(2, "tool", "search_memos", "completed", result_count=0),
            ),
        )
