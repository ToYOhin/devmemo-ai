"""Strict low-cardinality contracts for dormant Agent observability."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from typing import Literal, Mapping, cast


AGENT_OBSERVABILITY_VERSION = "agent-observability-v1"
MAX_OBSERVABILITY_PAYLOAD_BYTES = 4_096

ObservabilityComponent = Literal[
    "agent",
    "retrieval",
    "provider",
    "lifecycle",
    "rebuild",
    "reconciliation",
]
ObservabilityOperation = Literal[
    "answer",
    "search_memos",
    "provider_call",
    "outbox_dispatch",
    "rebuild",
    "reconcile",
]
ObservabilityOutcome = Literal[
    "success",
    "no_context",
    "refused",
    "unavailable",
    "invalid",
    "pending",
    "failed",
    "synced",
    "degraded",
]
ObservabilityMetricName = Literal[
    "request_count",
    "tool_latency_ms",
    "provider_latency_ms",
    "outbox_lag_seconds",
    "retry_count",
    "quarantine_count",
    "rebuild_state",
    "reconciliation_state",
]
ObservabilityUnit = Literal["count", "milliseconds", "seconds", "state"]
ObservabilityState = Literal[
    "pending",
    "active",
    "complete",
    "failed",
    "synced",
    "degraded",
]

_EVENT_FIELDS = frozenset(
    {"version", "kind", "component", "operation", "outcome"}
)
_NUMERIC_METRIC_FIELDS = frozenset(
    {"version", "kind", "component", "operation", "metric", "unit", "value"}
)
_STATE_METRIC_FIELDS = frozenset(
    {"version", "kind", "component", "operation", "metric", "unit", "state"}
)
_EVENT_RULES: dict[
    ObservabilityOperation,
    tuple[ObservabilityComponent, frozenset[ObservabilityOutcome]],
] = {
    "answer": (
        "agent",
        frozenset({"success", "no_context", "refused", "unavailable", "invalid"}),
    ),
    "search_memos": (
        "retrieval",
        frozenset({"success", "no_context", "unavailable", "invalid"}),
    ),
    "provider_call": (
        "provider",
        frozenset({"success", "unavailable", "invalid"}),
    ),
    "outbox_dispatch": (
        "lifecycle",
        frozenset({"success", "pending", "failed"}),
    ),
    "rebuild": ("rebuild", frozenset({"success", "pending", "failed"})),
    "reconcile": ("reconciliation", frozenset({"synced", "degraded"})),
}
_NUMERIC_METRIC_RULES: dict[
    ObservabilityMetricName,
    tuple[
        ObservabilityComponent,
        ObservabilityOperation,
        ObservabilityUnit,
        float,
        bool,
    ],
] = {
    "request_count": ("agent", "answer", "count", 1_000_000.0, True),
    "tool_latency_ms": (
        "retrieval",
        "search_memos",
        "milliseconds",
        600_000.0,
        False,
    ),
    "provider_latency_ms": (
        "provider",
        "provider_call",
        "milliseconds",
        600_000.0,
        False,
    ),
    "outbox_lag_seconds": (
        "lifecycle",
        "outbox_dispatch",
        "seconds",
        604_800.0,
        False,
    ),
    "retry_count": (
        "lifecycle",
        "outbox_dispatch",
        "count",
        1_000_000.0,
        True,
    ),
    "quarantine_count": (
        "lifecycle",
        "outbox_dispatch",
        "count",
        1_000_000.0,
        True,
    ),
}
_STATE_METRIC_RULES: dict[
    ObservabilityMetricName,
    tuple[
        ObservabilityComponent,
        ObservabilityOperation,
        frozenset[ObservabilityState],
    ],
] = {
    "rebuild_state": (
        "rebuild",
        "rebuild",
        frozenset({"pending", "active", "complete", "failed"}),
    ),
    "reconciliation_state": (
        "reconciliation",
        "reconcile",
        frozenset({"synced", "degraded"}),
    ),
}


class AgentObservabilityContractError(ValueError):
    """Fail closed without retaining rejected observability input."""

    def __init__(self) -> None:
        super().__init__("invalid agent observability contract")


@dataclass(frozen=True)
class AgentObservabilityEvent:
    """One low-cardinality operation outcome without identity or content."""

    component: ObservabilityComponent
    operation: ObservabilityOperation
    outcome: ObservabilityOutcome
    kind: Literal["event"] = "event"
    version: Literal["agent-observability-v1"] = AGENT_OBSERVABILITY_VERSION

    def __post_init__(self) -> None:
        if self.version != AGENT_OBSERVABILITY_VERSION or self.kind != "event":
            raise AgentObservabilityContractError
        if not isinstance(self.operation, str) or self.operation not in _EVENT_RULES:
            raise AgentObservabilityContractError
        expected_component, outcomes = _EVENT_RULES[self.operation]
        if (
            not isinstance(self.component, str)
            or not isinstance(self.outcome, str)
            or self.component != expected_component
            or self.outcome not in outcomes
        ):
            raise AgentObservabilityContractError

    @classmethod
    def from_dict(cls, payload: Mapping[str, object]) -> AgentObservabilityEvent:
        if set(payload) != _EVENT_FIELDS:
            raise AgentObservabilityContractError
        return cls(
            version=cast(
                Literal["agent-observability-v1"], payload["version"]
            ),
            kind=cast(Literal["event"], payload["kind"]),
            component=cast(ObservabilityComponent, payload["component"]),
            operation=cast(ObservabilityOperation, payload["operation"]),
            outcome=cast(ObservabilityOutcome, payload["outcome"]),
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "version": self.version,
            "kind": self.kind,
            "component": self.component,
            "operation": self.operation,
            "outcome": self.outcome,
        }


@dataclass(frozen=True)
class AgentObservabilityMetric:
    """One bounded numeric or state metric with no arbitrary dimensions."""

    component: ObservabilityComponent
    operation: ObservabilityOperation
    metric: ObservabilityMetricName
    unit: ObservabilityUnit
    value: float | int | None = None
    state: ObservabilityState | None = None
    kind: Literal["metric"] = "metric"
    version: Literal["agent-observability-v1"] = AGENT_OBSERVABILITY_VERSION

    def __post_init__(self) -> None:
        if self.version != AGENT_OBSERVABILITY_VERSION or self.kind != "metric":
            raise AgentObservabilityContractError
        if not isinstance(self.metric, str):
            raise AgentObservabilityContractError
        if self.metric in _NUMERIC_METRIC_RULES:
            self._validate_numeric()
        elif self.metric in _STATE_METRIC_RULES:
            self._validate_state()
        else:
            raise AgentObservabilityContractError

    def _validate_numeric(self) -> None:
        component, operation, unit, maximum, integer_only = _NUMERIC_METRIC_RULES[
            self.metric
        ]
        if (
            self.component != component
            or self.operation != operation
            or self.unit != unit
            or self.state is not None
            or not isinstance(self.value, (int, float))
            or isinstance(self.value, bool)
            or not math.isfinite(self.value)
            or not 0 <= self.value <= maximum
            or (integer_only and not isinstance(self.value, int))
        ):
            raise AgentObservabilityContractError

    def _validate_state(self) -> None:
        component, operation, states = _STATE_METRIC_RULES[self.metric]
        if (
            self.component != component
            or self.operation != operation
            or self.unit != "state"
            or self.value is not None
            or not isinstance(self.state, str)
            or self.state not in states
        ):
            raise AgentObservabilityContractError

    @classmethod
    def from_dict(cls, payload: Mapping[str, object]) -> AgentObservabilityMetric:
        metric = payload.get("metric")
        if not isinstance(metric, str):
            raise AgentObservabilityContractError
        if metric in _NUMERIC_METRIC_RULES:
            if set(payload) != _NUMERIC_METRIC_FIELDS:
                raise AgentObservabilityContractError
            value = payload["value"]
            state = None
        elif metric in _STATE_METRIC_RULES:
            if set(payload) != _STATE_METRIC_FIELDS:
                raise AgentObservabilityContractError
            value = None
            state = payload["state"]
        else:
            raise AgentObservabilityContractError
        return cls(
            version=cast(
                Literal["agent-observability-v1"], payload["version"]
            ),
            kind=cast(Literal["metric"], payload["kind"]),
            component=cast(ObservabilityComponent, payload["component"]),
            operation=cast(ObservabilityOperation, payload["operation"]),
            metric=cast(ObservabilityMetricName, metric),
            unit=cast(ObservabilityUnit, payload["unit"]),
            value=cast(float | int | None, value),
            state=cast(ObservabilityState | None, state),
        )

    def to_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "version": self.version,
            "kind": self.kind,
            "component": self.component,
            "operation": self.operation,
            "metric": self.metric,
            "unit": self.unit,
        }
        if self.value is not None:
            payload["value"] = self.value
        else:
            payload["state"] = self.state
        return payload


AgentObservabilitySample = AgentObservabilityEvent | AgentObservabilityMetric


def parse_observability_sample(body: bytes) -> AgentObservabilitySample:
    """Parse one exact event or metric and reject duplicate fields."""

    try:
        if (
            not isinstance(body, bytes)
            or not 0 < len(body) <= MAX_OBSERVABILITY_PAYLOAD_BYTES
        ):
            raise AgentObservabilityContractError
        payload = json.loads(body, object_pairs_hook=_reject_duplicate_fields)
        if not isinstance(payload, dict):
            raise AgentObservabilityContractError
        kind = payload.get("kind")
        if kind == "event":
            return AgentObservabilityEvent.from_dict(payload)
        if kind == "metric":
            return AgentObservabilityMetric.from_dict(payload)
        raise AgentObservabilityContractError
    except AgentObservabilityContractError:
        raise
    except (TypeError, ValueError, UnicodeDecodeError) as error:
        raise AgentObservabilityContractError from error


def _reject_duplicate_fields(pairs: list[tuple[str, object]]) -> dict[str, object]:
    payload: dict[str, object] = {}
    for key, value in pairs:
        if key in payload:
            raise AgentObservabilityContractError
        payload[key] = value
    return payload
