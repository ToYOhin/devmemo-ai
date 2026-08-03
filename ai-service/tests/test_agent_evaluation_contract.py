import json
from pathlib import Path

import pytest

from app.domain.agent_evaluation import (
    EVALUATION_CASE_VERSION,
    EVALUATION_CORPUS_VERSION,
    EVALUATION_RESULT_VERSION,
    EVALUATION_THRESHOLDS_VERSION,
    AgentEvaluationCorpus,
    AgentEvaluationCase,
    AgentEvaluationContractError,
    AgentEvaluationResult,
    AgentEvaluationThresholds,
    parse_evaluation_case,
    parse_evaluation_corpus,
    parse_evaluation_result,
    parse_evaluation_thresholds,
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


_CATEGORIES = (
    "lookup",
    "synthesis",
    "no_answer",
    "conflicting_evidence",
    "visibility_boundary",
    "deletion",
    "stale_state",
    "prompt_injection",
)


def _corpus_payload(*, cases_per_category=8, **overrides):
    cases = []
    for category in _CATEGORIES:
        for number in range(cases_per_category):
            expected_state = "answer"
            expected_ids = [f"evidence-{category}-{number}"]
            visible_ids = list(expected_ids)
            forbidden_ids = []
            if category in {"no_answer", "deletion"}:
                expected_state = "no_answer"
                expected_ids = []
                visible_ids = []
            if category == "prompt_injection":
                expected_state = "refusal"
                expected_ids = []
            if category in {
                "visibility_boundary",
                "deletion",
                "stale_state",
                "prompt_injection",
            }:
                forbidden_ids = [f"evidence-forbidden-{category}-{number}"]
            cases.append(
                _case_payload(
                    case_id=f"{category}-{number:03d}",
                    category=category,
                    question=f"Synthetic {category} question {number}.",
                    visible_evidence_ids=visible_ids,
                    expected_evidence_ids=expected_ids,
                    forbidden_evidence_ids=forbidden_ids,
                    expected_answer_state=expected_state,
                )
            )
    payload = {
        "version": EVALUATION_CORPUS_VERSION,
        "case_version": EVALUATION_CASE_VERSION,
        "category_counts": {
            category: cases_per_category for category in _CATEGORIES
        },
        "cases": cases,
    }
    payload.update(overrides)
    return payload


def _thresholds_payload(**overrides):
    answer_categories = [
        "lookup",
        "synthesis",
        "conflicting_evidence",
        "visibility_boundary",
        "stale_state",
    ]
    all_categories = list(_CATEGORIES)
    thresholds = [
        ["retrieval_recall_at_5", "ratio", "at_least", 0.9, 0.0, 1.0, answer_categories],
        ["retrieval_mrr", "ratio", "at_least", 0.8, 0.0, 1.0, answer_categories],
        ["citation_precision", "ratio", "at_least", 1.0, 0.0, 1.0, answer_categories],
        ["groundedness", "ratio", "at_least", 0.9, 0.0, 1.0, answer_categories],
        [
            "refusal_accuracy",
            "ratio",
            "at_least",
            0.95,
            0.0,
            1.0,
            ["no_answer", "deletion", "prompt_injection"],
        ],
        ["scope_leak_count", "count", "at_most", 0.0, 0.0, 100.0, all_categories],
        [
            "latency_p95_ms",
            "milliseconds",
            "at_most",
            5000.0,
            0.0,
            600000.0,
            all_categories,
        ],
    ]
    payload = {
        "version": EVALUATION_THRESHOLDS_VERSION,
        "corpus_version": EVALUATION_CORPUS_VERSION,
        "result_version": EVALUATION_RESULT_VERSION,
        "thresholds": [
            {
                "metric": metric,
                "unit": unit,
                "direction": direction,
                "boundary": boundary,
                "range_min": range_min,
                "range_max": range_max,
                "applicable_categories": categories,
            }
            for metric, unit, direction, boundary, range_min, range_max, categories in thresholds
        ],
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


def test_evaluation_corpus_round_trips_exact_stratification():
    payload = _corpus_payload()

    corpus = parse_evaluation_corpus(json.dumps(payload).encode())

    assert isinstance(corpus, AgentEvaluationCorpus)
    assert corpus.to_dict() == payload


@pytest.mark.parametrize(
    "mutate",
    [
        lambda payload: payload.update(version="agent-evaluation-corpus-v2"),
        lambda payload: payload.update(case_version="agent-evaluation-case-v2"),
        lambda payload: payload["cases"].pop(),
        lambda payload: payload["cases"].append(payload["cases"][0]),
        lambda payload: payload["cases"][0].update(question="Not marked data."),
        lambda payload: payload["category_counts"].update(lookup=7),
        lambda payload: payload["category_counts"].pop("lookup"),
        lambda payload: payload["category_counts"].update(lookup=True),
    ],
)
def test_evaluation_corpus_rejects_invalid_size_identity_and_counts(mutate):
    payload = _corpus_payload()
    mutate(payload)

    with pytest.raises(AgentEvaluationContractError):
        AgentEvaluationCorpus.from_dict(payload)


def test_evaluation_corpus_rejects_unknown_duplicate_and_non_object_cases():
    unknown = _corpus_payload(extra=True)
    non_object = _corpus_payload()
    non_object["cases"][0] = "not-an-object"
    duplicate = json.dumps(_corpus_payload()).replace(
        '"version": "agent-evaluation-corpus-v1",',
        '"version": "agent-evaluation-corpus-v1", "version": "duplicate",',
        1,
    )

    for payload in (unknown, non_object):
        with pytest.raises(AgentEvaluationContractError):
            AgentEvaluationCorpus.from_dict(payload)
    with pytest.raises(AgentEvaluationContractError):
        parse_evaluation_corpus(duplicate.encode())


@pytest.mark.parametrize("cases_per_category", [6, 13])
def test_evaluation_corpus_rejects_less_than_50_or_more_than_100_cases(
    cases_per_category,
):
    with pytest.raises(AgentEvaluationContractError):
        AgentEvaluationCorpus.from_dict(
            _corpus_payload(cases_per_category=cases_per_category)
        )


def test_evaluation_thresholds_round_trip_without_observed_values_or_score():
    payload = _thresholds_payload()

    thresholds = parse_evaluation_thresholds(json.dumps(payload).encode())

    assert isinstance(thresholds, AgentEvaluationThresholds)
    assert thresholds.to_dict() == payload
    assert "score" not in thresholds.to_dict()


@pytest.mark.parametrize(
    "mutate",
    [
        lambda payload: payload.update(version="agent-evaluation-thresholds-v2"),
        lambda payload: payload.update(corpus_version="agent-evaluation-corpus-v2"),
        lambda payload: payload.update(result_version="agent-evaluation-result-v2"),
        lambda payload: payload["thresholds"].pop(),
        lambda payload: payload["thresholds"].append(payload["thresholds"][0]),
        lambda payload: payload["thresholds"][0].update(metric="overall_score"),
        lambda payload: payload["thresholds"][0].update(unit="count"),
        lambda payload: payload["thresholds"][0].update(direction="at_most"),
        lambda payload: payload["thresholds"][0].update(boundary=2.0),
        lambda payload: payload["thresholds"][0].update(range_max=100.0),
        lambda payload: payload["thresholds"][0].update(boundary=True),
        lambda payload: payload["thresholds"][0].update(
            applicable_categories=[]
        ),
        lambda payload: payload["thresholds"][0].update(
            applicable_categories=["lookup", "lookup"]
        ),
        lambda payload: payload["thresholds"][0].update(
            applicable_categories=["unknown"]
        ),
        lambda payload: payload["thresholds"].__setitem__(0, "not-an-object"),
    ],
)
def test_evaluation_thresholds_reject_incomplete_or_invalid_metric_gates(mutate):
    payload = _thresholds_payload()
    mutate(payload)

    with pytest.raises(AgentEvaluationContractError):
        AgentEvaluationThresholds.from_dict(payload)


def test_evaluation_thresholds_reject_unknown_and_duplicate_fields():
    unknown = _thresholds_payload(overall_score=0.9)
    duplicate = json.dumps(_thresholds_payload()).replace(
        '"version": "agent-evaluation-thresholds-v1",',
        '"version": "agent-evaluation-thresholds-v1", "version": "duplicate",',
        1,
    )

    with pytest.raises(AgentEvaluationContractError):
        AgentEvaluationThresholds.from_dict(unknown)
    with pytest.raises(AgentEvaluationContractError):
        parse_evaluation_thresholds(duplicate.encode())


def test_r6_corpus_and_threshold_fixtures_are_complete_and_parseable():
    contracts_dir = Path(__file__).resolve().parents[2] / "contracts"

    corpus = parse_evaluation_corpus(
        (contracts_dir / "agent-evaluation-corpus-v1.json").read_bytes()
    )
    thresholds = parse_evaluation_thresholds(
        (contracts_dir / "agent-evaluation-thresholds-v1.json").read_bytes()
    )

    assert len(corpus.cases) == 64
    assert dict(corpus.category_counts) == {
        "lookup": 8,
        "synthesis": 8,
        "no_answer": 8,
        "conflicting_evidence": 8,
        "visibility_boundary": 8,
        "deletion": 8,
        "stale_state": 8,
        "prompt_injection": 8,
    }
    assert {threshold.metric for threshold in thresholds.thresholds} == {
        "retrieval_recall_at_5",
        "retrieval_mrr",
        "citation_precision",
        "groundedness",
        "refusal_accuracy",
        "scope_leak_count",
        "latency_p95_ms",
    }
    assert next(
        threshold.boundary
        for threshold in thresholds.thresholds
        if threshold.metric == "scope_leak_count"
    ) == 0.0
