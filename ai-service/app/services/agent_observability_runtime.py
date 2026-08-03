import math
from collections.abc import Callable
from typing import Literal, Protocol

from app.domain.agent_observability import (
    AgentObservabilityEvent,
    AgentObservabilityMetric,
    AgentObservabilitySample,
)


AnswerObservabilityOutcome = Literal[
    "success",
    "no_context",
    "refused",
    "invalid",
    "unavailable",
]
_ANSWER_OUTCOMES = frozenset(
    {"success", "no_context", "refused", "invalid", "unavailable"}
)
RetrievalObservabilityOutcome = Literal[
    "success",
    "no_context",
    "invalid",
    "unavailable",
]
ProviderObservabilityOutcome = Literal["success", "invalid", "unavailable"]
MonotonicClock = Callable[[], float]
_RETRIEVAL_OUTCOMES = frozenset(
    {"success", "no_context", "invalid", "unavailable"}
)
_MAX_RETRIEVAL_LATENCY_MS = 600_000.0
_PROVIDER_OUTCOMES = frozenset({"success", "invalid", "unavailable"})
_MAX_PROVIDER_LATENCY_MS = 600_000.0


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


def start_retrieval_observation(clock: MonotonicClock | None) -> float | None:
    """Read a valid monotonic start without affecting retrieval."""

    return _read_monotonic(clock)


def record_retrieval_observation(
    recorder: AgentObservabilityRecorder | None,
    clock: MonotonicClock | None,
    started_at: float | None,
    outcome: RetrievalObservabilityOutcome,
) -> None:
    """Attempt a fixed latency/outcome pair without affecting retrieval."""

    if (
        recorder is None
        or not isinstance(outcome, str)
        or outcome not in _RETRIEVAL_OUTCOMES
        or started_at is None
        or not _is_valid_clock_value(started_at)
    ):
        return
    stopped_at = _read_monotonic(clock)
    if stopped_at is None:
        return
    elapsed_ms = (stopped_at - float(started_at)) * 1000
    if (
        not math.isfinite(elapsed_ms)
        or elapsed_ms < 0
        or elapsed_ms > _MAX_RETRIEVAL_LATENCY_MS
    ):
        return
    try:
        samples: tuple[AgentObservabilitySample, ...] = (
            AgentObservabilityMetric(
                component="retrieval",
                operation="search_memos",
                metric="tool_latency_ms",
                unit="milliseconds",
                value=elapsed_ms,
            ),
            AgentObservabilityEvent(
                component="retrieval",
                operation="search_memos",
                outcome=outcome,
            ),
        )
    except Exception:
        return
    for sample in samples:
        try:
            recorder.record(sample)
        except Exception:
            continue


def start_provider_observation(clock: MonotonicClock | None) -> float | None:
    """Read a valid monotonic start without affecting the Provider call."""

    return _read_monotonic(clock)


def record_provider_observation(
    recorder: AgentObservabilityRecorder | None,
    clock: MonotonicClock | None,
    started_at: float | None,
    outcome: ProviderObservabilityOutcome,
) -> None:
    """Attempt a fixed Provider latency/outcome pair without affecting answer."""

    if (
        recorder is None
        or not isinstance(outcome, str)
        or outcome not in _PROVIDER_OUTCOMES
        or started_at is None
        or not _is_valid_clock_value(started_at)
    ):
        return
    stopped_at = _read_monotonic(clock)
    if stopped_at is None:
        return
    elapsed_ms = (stopped_at - float(started_at)) * 1000
    if (
        not math.isfinite(elapsed_ms)
        or elapsed_ms < 0
        or elapsed_ms > _MAX_PROVIDER_LATENCY_MS
    ):
        return
    try:
        samples: tuple[AgentObservabilitySample, ...] = (
            AgentObservabilityMetric(
                component="provider",
                operation="provider_call",
                metric="provider_latency_ms",
                unit="milliseconds",
                value=elapsed_ms,
            ),
            AgentObservabilityEvent(
                component="provider",
                operation="provider_call",
                outcome=outcome,
            ),
        )
    except Exception:
        return
    for sample in samples:
        try:
            recorder.record(sample)
        except Exception:
            continue


def _read_monotonic(clock: MonotonicClock | None) -> float | None:
    if clock is None:
        return None
    try:
        value = clock()
    except Exception:
        return None
    if not _is_valid_clock_value(value):
        return None
    return float(value)


def _is_valid_clock_value(value: object) -> bool:
    return (
        not isinstance(value, bool)
        and isinstance(value, (int, float))
        and math.isfinite(value)
    )
