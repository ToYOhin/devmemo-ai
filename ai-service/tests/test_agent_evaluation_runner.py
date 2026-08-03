from pathlib import Path

import pytest

from app.domain.agent_evaluation import (
    AgentEvaluationCase,
    AgentEvaluationResult,
    parse_evaluation_corpus,
    parse_evaluation_thresholds,
)
from app.domain.agent_evaluation_report import (
    AgentEvaluationFailedCase,
    AgentEvaluationMetricReport,
    AgentEvaluationReport,
    AgentEvaluationReportError,
)
from app.services.agent_evaluation_runner import (
    AgentEvaluationRunnerError,
    run_evaluation,
    score_evaluation_case,
)


def _case(**overrides):
    values = {
        "case_id": "synthesis-001",
        "category": "synthesis",
        "question": "In this synthetic scenario, combine two records.",
        "visible_evidence_ids": ("evidence-a", "evidence-b"),
        "expected_evidence_ids": ("evidence-a", "evidence-b"),
        "forbidden_evidence_ids": (),
        "expected_answer_state": "answer",
    }
    values.update(overrides)
    return AgentEvaluationCase(**values)


def _result(**overrides):
    values = {
        "case_id": "synthesis-001",
        "answer_state": "answer",
        "retrieved_evidence_ids": ("evidence-noise", "evidence-a", "evidence-b"),
        "citation_evidence_ids": ("evidence-a", "evidence-b"),
        "failure_categories": (),
        "latency_ms": 25,
    }
    values.update(overrides)
    return AgentEvaluationResult(**values)


def test_case_score_reports_perfect_answer_metrics_without_failures():
    score = score_evaluation_case(_case(), _result())

    assert score.recall_at_5 == 1.0
    assert score.reciprocal_rank == 0.5
    assert score.citation_precision == 1.0
    assert score.groundedness == 1.0
    assert score.refusal_accuracy is None
    assert score.scope_leak_count == 0
    assert score.latency_ms == 25
    assert score.failure_categories == ()


def test_case_score_derives_retrieval_citation_scope_and_stale_failures():
    case = _case(
        category="stale_state",
        forbidden_evidence_ids=("evidence-stale",),
    )
    result = _result(
        retrieved_evidence_ids=("evidence-a", "evidence-stale"),
        citation_evidence_ids=("evidence-a", "evidence-stale"),
    )

    score = score_evaluation_case(case, result)

    assert score.recall_at_5 == 0.5
    assert score.reciprocal_rank == 1.0
    assert score.citation_precision == 0.5
    assert score.scope_leak_count == 1
    assert score.failure_categories == (
        "retrieval_miss",
        "citation_mismatch",
        "scope_leak",
        "stale_evidence",
    )


def test_case_score_uses_explicit_zero_denominator_conventions():
    case = _case(
        case_id="no-answer-001",
        category="no_answer",
        visible_evidence_ids=(),
        expected_evidence_ids=(),
        expected_answer_state="no_answer",
    )
    result = _result(
        case_id="no-answer-001",
        answer_state="no_answer",
        retrieved_evidence_ids=(),
        citation_evidence_ids=(),
    )

    score = score_evaluation_case(case, result)

    assert score.recall_at_5 is None
    assert score.reciprocal_rank is None
    assert score.citation_precision is None
    assert score.groundedness is None
    assert score.refusal_accuracy == 1.0
    assert score.failure_categories == ()


def test_case_score_preserves_safe_supplied_failure_and_detects_injection():
    case = _case(
        case_id="prompt-injection-001",
        category="prompt_injection",
        expected_evidence_ids=(),
        expected_answer_state="refusal",
    )
    result = _result(
        case_id="prompt-injection-001",
        failure_categories=("ungrounded_answer",),
    )

    score = score_evaluation_case(case, result)

    assert score.refusal_accuracy == 0.0
    assert score.failure_categories == (
        "ungrounded_answer",
        "incorrect_refusal",
        "prompt_injection_followed",
    )


def test_case_score_rejects_mismatched_or_wrong_input_types():
    with pytest.raises(AgentEvaluationRunnerError):
        score_evaluation_case(_case(), _result(case_id="lookup-999"))
    with pytest.raises(AgentEvaluationRunnerError):
        score_evaluation_case("not-a-case", _result())


def _corpus_and_thresholds():
    contracts_dir = Path(__file__).resolve().parents[2] / "contracts"
    corpus = parse_evaluation_corpus(
        (contracts_dir / "agent-evaluation-corpus-v1.json").read_bytes()
    )
    thresholds = parse_evaluation_thresholds(
        (contracts_dir / "agent-evaluation-thresholds-v1.json").read_bytes()
    )
    return corpus, thresholds


def _passing_results(corpus):
    return tuple(
        AgentEvaluationResult(
            case_id=case.case_id,
            answer_state=case.expected_answer_state,
            retrieved_evidence_ids=case.expected_evidence_ids,
            citation_evidence_ids=(
                case.expected_evidence_ids
                if case.expected_answer_state == "answer"
                else ()
            ),
            failure_categories=(),
            latency_ms=100,
        )
        for case in corpus.cases
    )


def test_runner_emits_passing_content_free_report_for_synthetic_results():
    corpus, thresholds = _corpus_and_thresholds()

    report = run_evaluation(corpus, thresholds, _passing_results(corpus))
    projection = report.to_dict()

    assert report.passed
    assert report.case_count == 64
    assert report.failed_cases == ()
    assert {metric.threshold.metric: metric.value for metric in report.metrics} == {
        "retrieval_recall_at_5": 1.0,
        "retrieval_mrr": 1.0,
        "citation_precision": 1.0,
        "groundedness": 1.0,
        "refusal_accuracy": 1.0,
        "scope_leak_count": 0.0,
        "latency_p95_ms": 100.0,
    }
    assert set(projection) == {
        "version",
        "corpus_version",
        "thresholds_version",
        "result_version",
        "case_count",
        "metrics",
        "passed",
        "failed_cases",
    }
    assert all(
        key not in str(projection).casefold()
        for key in ("question", "answer", "memo", "prompt", "context", "trace")
    )


def test_runner_reports_every_failed_case_and_failed_threshold():
    corpus, thresholds = _corpus_and_thresholds()
    results = list(_passing_results(corpus))
    lookup_indexes = [
        index for index, case in enumerate(corpus.cases) if case.category == "lookup"
    ]
    for index in lookup_indexes:
        result = results[index]
        results[index] = AgentEvaluationResult(
            case_id=result.case_id,
            answer_state="answer",
            retrieved_evidence_ids=(),
            citation_evidence_ids=(),
            failure_categories=(),
            latency_ms=result.latency_ms,
        )
    visibility_index = next(
        index
        for index, case in enumerate(corpus.cases)
        if case.category == "visibility_boundary"
    )
    visibility_case = corpus.cases[visibility_index]
    visibility_result = results[visibility_index]
    forbidden_id = visibility_case.forbidden_evidence_ids[0]
    results[visibility_index] = AgentEvaluationResult(
        case_id=visibility_result.case_id,
        answer_state="answer",
        retrieved_evidence_ids=(
            *visibility_result.retrieved_evidence_ids,
            forbidden_id,
        ),
        citation_evidence_ids=(
            *visibility_result.citation_evidence_ids,
            forbidden_id,
        ),
        failure_categories=(),
        latency_ms=visibility_result.latency_ms,
    )
    for index in range(len(results) - 4, len(results)):
        result = results[index]
        results[index] = AgentEvaluationResult(
            case_id=result.case_id,
            answer_state="answer",
            retrieved_evidence_ids=result.retrieved_evidence_ids,
            citation_evidence_ids=(),
            failure_categories=(),
            latency_ms=6000,
        )

    report = run_evaluation(corpus, thresholds, tuple(results))
    metrics = {metric.threshold.metric: metric for metric in report.metrics}

    assert not report.passed
    assert not metrics["retrieval_recall_at_5"].passed
    assert not metrics["citation_precision"].passed
    assert not metrics["scope_leak_count"].passed
    assert not metrics["latency_p95_ms"].passed
    assert metrics["latency_p95_ms"].value == 6000.0
    assert [case.case_id for case in report.failed_cases] == [
        *(corpus.cases[index].case_id for index in lookup_indexes),
        visibility_case.case_id,
        *(corpus.cases[index].case_id for index in range(len(results) - 4, len(results))),
    ]


def test_runner_rejects_missing_duplicate_unknown_and_non_result_inputs():
    corpus, thresholds = _corpus_and_thresholds()
    results = _passing_results(corpus)
    unknown = AgentEvaluationResult(
        case_id="unknown-001",
        answer_state="no_answer",
        retrieved_evidence_ids=(),
        citation_evidence_ids=(),
        failure_categories=(),
        latency_ms=1,
    )

    invalid_sets = (
        results[:-1],
        (*results[:-1], results[0]),
        (*results[:-1], unknown),
        (*results[:-1], "not-a-result"),
    )
    for invalid in invalid_sets:
        with pytest.raises(AgentEvaluationRunnerError):
            run_evaluation(corpus, thresholds, invalid)


def test_metric_report_rejects_forged_threshold_outcome():
    _, thresholds = _corpus_and_thresholds()
    threshold = thresholds.thresholds[0]

    with pytest.raises(AgentEvaluationReportError):
        AgentEvaluationMetricReport(
            threshold=threshold,
            value=1.0,
            applicable_case_count=40,
            passed=False,
        )


def test_failed_case_and_report_reject_incomplete_projections():
    corpus, thresholds = _corpus_and_thresholds()
    report = run_evaluation(corpus, thresholds, _passing_results(corpus))

    with pytest.raises(AgentEvaluationReportError):
        AgentEvaluationFailedCase("lookup-001", ())
    with pytest.raises(AgentEvaluationReportError):
        AgentEvaluationReport(
            case_count=report.case_count,
            metrics=report.metrics[:-1],
            failed_cases=(),
            passed=True,
        )
