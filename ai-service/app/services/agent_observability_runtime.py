from typing import Literal, Protocol

from app.domain.agent_observability import (
    AgentObservabilityEvent,
    AgentObservabilityMetric,
    AgentObservabilitySample,
)


AnswerObservabilityOutcome = Literal[
    "success",
    "no_context",
    "invalid",
    "unavailable",
]
_ANSWER_OUTCOMES = frozenset({"success", "no_context", "invalid", "unavailable"})


class AgentObservabilityRecorder(Protocol):
    def record(self, sample: AgentObservabilitySample) -> None:
        ...


def record_answer_observation(
    recorder: AgentObservabilityRecorder | None,
    outcome: AnswerObservabilityOutcome,
) -> None:
    """Attempt both fixed samples without affecting the observed request."""

    if (
        recorder is None
        or not isinstance(outcome, str)
        or outcome not in _ANSWER_OUTCOMES
    ):
        return
    samples: tuple[AgentObservabilitySample, ...] = (
        AgentObservabilityMetric(
            component="agent",
            operation="answer",
            metric="request_count",
            unit="count",
            value=1,
        ),
        AgentObservabilityEvent(
            component="agent",
            operation="answer",
            outcome=outcome,
        ),
    )
    for sample in samples:
        try:
            recorder.record(sample)
        except Exception:
            continue
