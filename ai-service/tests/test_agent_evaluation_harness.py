import asyncio
from pathlib import Path

from app.domain.agent_evaluation import (
    parse_evaluation_corpus,
    parse_evaluation_thresholds,
)
from app.services.agent_evaluation_harness import run_synthetic_agent_evaluation


class FixedStepClock:
    def __init__(self) -> None:
        self.value = 0.0

    def __call__(self) -> float:
        self.value += 0.001
        return self.value


def _contracts():
    contracts_dir = Path(__file__).parents[2] / "contracts"
    corpus = parse_evaluation_corpus(
        (contracts_dir / "agent-evaluation-corpus-v1.json").read_bytes()
    )
    thresholds = parse_evaluation_thresholds(
        (contracts_dir / "agent-evaluation-thresholds-v1.json").read_bytes()
    )
    return corpus, thresholds


def test_synthetic_harness_runs_real_in_memory_agent_core_and_reports_failures():
    corpus, thresholds = _contracts()

    report = asyncio.run(
        run_synthetic_agent_evaluation(
            corpus,
            thresholds,
            clock=FixedStepClock(),
        )
    )

    assert report.case_count == 64
    assert not report.passed
    assert [case.case_id for case in report.failed_cases] == [
        f"prompt-injection-{index:03d}" for index in range(1, 9)
    ]
    metrics = {metric.threshold.metric: metric for metric in report.metrics}
    assert metrics["retrieval_recall_at_5"].passed
    assert metrics["retrieval_mrr"].passed
    assert metrics["citation_precision"].passed
    assert metrics["groundedness"].passed
    assert not metrics["refusal_accuracy"].passed
    assert metrics["scope_leak_count"].passed
    assert metrics["latency_p95_ms"].value == 1


def test_synthetic_harness_report_is_content_free():
    corpus, thresholds = _contracts()

    projection = asyncio.run(
        run_synthetic_agent_evaluation(
            corpus,
            thresholds,
            clock=FixedStepClock(),
        )
    ).to_dict()

    serialized = str(projection).lower()
    for forbidden in (
        "question",
        "context",
        "memo",
        "which port does",
        "synthetic scenario",
        "synthetic supporting record",
        "ignore instructions",
    ):
        assert forbidden not in serialized
