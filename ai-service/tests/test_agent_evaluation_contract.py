import json
from pathlib import Path

import pytest

from app.domain.agent_evaluation import (
    EVALUATION_CASE_VERSION,
    EVALUATION_RESULT_VERSION,
    AgentEvaluationCase,
    AgentEvaluationContractError,
    AgentEvaluationResult,
    parse_evaluation_case,
    parse_evaluation_result,
)


def _case_payload(**overrides):
    payload = {
        "version": EVALUATION_CASE_VERSION,
        "case_id": "lookup-001",
        "category": "lookup",
        "data_classification": "synthetic",
        "question": "Which synthetic runbook defines the service port?",
        "visible_evidence_ids": ["evidence-runbook"],
        "expected_evidence_ids": ["evidence-runbook"],
        "forbidden_evidence_ids": [],
        "expected_answer_state": "answer",
    }
    payload.update(overrides)
    return payload


def _result_payload(**overrides):
    payload = {
        "version": EVALUATION_RESULT_VERSION,
        "case_id": "lookup-001",
        "answer_state": "answer",
        "retrieved_evidence_ids": ["evidence-runbook"],
        "citation_evidence_ids": ["evidence-runbook"],
        "failure_categories": [],
        "latency_ms": 12,
    }
    payload.update(overrides)
    return payload


def test_evaluation_case_round_trips_strict_synthetic_contract():
    payload = _case_payload()

    case = parse_evaluation_case(json.dumps(payload).encode())

    assert isinstance(case, AgentEvaluationCase)
    assert case.to_dict() == payload


@pytest.mark.parametrize(
    "overrides",
    [
        {"version": "agent-evaluation-case-v2"},
        {"data_classification": "production"},
        {"category": "tool_use"},
        {"category": []},
        {"expected_answer_state": []},
        {"question": " "},
        {"visible_evidence_ids": ["memo-real"]},
        {"visible_evidence_ids": ["evidence-a", "evidence-a"]},
        {"expected_evidence_ids": ["evidence-hidden"]},
        {
            "visible_evidence_ids": ["evidence-a"],
            "expected_evidence_ids": ["evidence-a"],
            "forbidden_evidence_ids": ["evidence-a"],
        },
        {"expected_answer_state": "answer", "expected_evidence_ids": []},
        {
            "expected_answer_state": "no_answer",
            "expected_evidence_ids": ["evidence-runbook"],
        },
    ],
)
def test_evaluation_case_rejects_invalid_scope_and_semantics(overrides):
    with pytest.raises(
        AgentEvaluationContractError, match="invalid agent evaluation contract"
    ):
        AgentEvaluationCase.from_dict(_case_payload(**overrides))


def test_evaluation_case_rejects_missing_unknown_duplicate_and_malformed_fields():
    missing = _case_payload()
    missing.pop("category")
    unknown = _case_payload(extra=True)
    duplicate = json.dumps(_case_payload()).replace(
        '"case_id": "lookup-001",',
        '"case_id": "lookup-001", "case_id": "duplicate",',
    )

    for body in (
        json.dumps(missing).encode(),
        json.dumps(unknown).encode(),
        duplicate.encode(),
        b"[]",
        b"{not-json",
        b"",
    ):
        with pytest.raises(AgentEvaluationContractError):
            parse_evaluation_case(body)


def test_evaluation_case_rejects_non_list_and_non_string_evidence_ids():
    for payload in (
        _case_payload(visible_evidence_ids="evidence-runbook"),
        _case_payload(visible_evidence_ids=[True]),
    ):
        with pytest.raises(AgentEvaluationContractError):
            AgentEvaluationCase.from_dict(payload)


def test_evaluation_result_round_trips_without_answer_or_trace_content():
    payload = _result_payload()

    result = parse_evaluation_result(json.dumps(payload).encode())

    assert isinstance(result, AgentEvaluationResult)
    assert result.to_dict() == payload
    assert "answer" not in result.to_dict()
    assert "trace" not in result.to_dict()


@pytest.mark.parametrize(
    "overrides",
    [
        {"version": "agent-evaluation-result-v2"},
        {"answer_state": "unknown"},
        {"answer_state": []},
        {"citation_evidence_ids": ["evidence-hidden"]},
        {"answer_state": "no_answer", "citation_evidence_ids": ["evidence-runbook"]},
        {"failure_categories": ["scope_leak", "scope_leak"]},
        {"failure_categories": ["raw_provider_error"]},
        {"failure_categories": [[]]},
        {"latency_ms": -1},
        {"latency_ms": True},
        {"latency_ms": 600_001},
        {"answer_state": "error", "failure_categories": []},
    ],
)
def test_evaluation_result_rejects_invalid_or_content_bearing_shapes(overrides):
    with pytest.raises(AgentEvaluationContractError):
        AgentEvaluationResult.from_dict(_result_payload(**overrides))


def test_evaluation_result_rejects_unknown_duplicate_and_malformed_fields():
    unknown = _result_payload(answer="raw output must not enter evaluation results")
    duplicate = json.dumps(_result_payload()).replace(
        '"latency_ms": 12', '"latency_ms": 12, "latency_ms": 13'
    )

    for body in (
        json.dumps(unknown).encode(),
        duplicate.encode(),
        b"[]",
        b"{not-json",
        b"",
    ):
        with pytest.raises(AgentEvaluationContractError):
            parse_evaluation_result(body)


def test_synthetic_seed_cases_cover_every_r6_evaluation_category():
    fixture_path = (
        Path(__file__).resolve().parents[2]
        / "contracts"
        / "agent-evaluation-seed-v1.json"
    )
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))

    assert set(fixture) == {"case_version", "cases"}
    assert fixture["case_version"] == EVALUATION_CASE_VERSION
    cases = tuple(AgentEvaluationCase.from_dict(case) for case in fixture["cases"])

    assert len(cases) == 8
    assert len({case.case_id for case in cases}) == len(cases)
    assert {case.category for case in cases} == {
        "lookup",
        "synthesis",
        "no_answer",
        "conflicting_evidence",
        "visibility_boundary",
        "deletion",
        "stale_state",
        "prompt_injection",
    }
    assert all(case.data_classification == "synthetic" for case in cases)
