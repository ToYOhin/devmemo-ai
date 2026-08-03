import json

import pytest

from app.adapters.agent_observability import (
    MAX_OBSERVABILITY_BUFFER_CAPACITY,
    AgentObservabilityAdapterError,
    BoundedInMemoryObservabilityAdapter,
)
from app.domain.agent_observability import (
    AGENT_OBSERVABILITY_VERSION,
    MAX_OBSERVABILITY_PAYLOAD_BYTES,
    AgentObservabilityContractError,
    AgentObservabilityEvent,
    AgentObservabilityMetric,
    parse_observability_sample,
)
from app.services.agent_observability_runtime import (
    record_answer_observation,
    record_provider_observation,
    record_retrieval_observation,
    start_provider_observation,
    start_retrieval_observation,
)


def _event_payload(**overrides):
    payload = {
        "version": AGENT_OBSERVABILITY_VERSION,
        "kind": "event",
        "component": "agent",
        "operation": "answer",
        "outcome": "success",
    }
    payload.update(overrides)
    return payload


def _metric_payload(**overrides):
    payload = {
        "version": AGENT_OBSERVABILITY_VERSION,
        "kind": "metric",
        "component": "retrieval",
        "operation": "search_memos",
        "metric": "tool_latency_ms",
        "unit": "milliseconds",
        "value": 12.5,
    }
    payload.update(overrides)
    return payload


def _event(outcome="success"):
    return AgentObservabilityEvent(
        component="agent",
        operation="answer",
        outcome=outcome,
    )


def _metric(value=12.5):
    return AgentObservabilityMetric(
        component="retrieval",
        operation="search_memos",
        metric="tool_latency_ms",
        unit="milliseconds",
        value=value,
    )


def test_event_round_trips_exact_low_cardinality_projection():
    payload = _event_payload()

    event = parse_observability_sample(json.dumps(payload).encode())

    assert isinstance(event, AgentObservabilityEvent)
    assert event.to_dict() == payload


@pytest.mark.parametrize(
    "payload",
    [
        _event_payload(version="agent-observability-v2"),
        _event_payload(kind="span"),
        _event_payload(component="provider"),
        _event_payload(operation="unknown"),
        _event_payload(outcome="raw-error"),
        _event_payload(outcome=[]),
        _event_payload(label="variable"),
        _event_payload(request_id="request-123"),
        _event_payload(metadata={"user_id": "user-1"}),
    ],
)
def test_event_rejects_unknown_combinations_and_arbitrary_dimensions(payload):
    with pytest.raises(AgentObservabilityContractError):
        AgentObservabilityEvent.from_dict(payload)


@pytest.mark.parametrize(
    "payload",
    [
        _metric_payload(),
        _metric_payload(
            component="provider",
            operation="provider_call",
            metric="provider_latency_ms",
        ),
        _metric_payload(
            component="lifecycle",
            operation="outbox_dispatch",
            metric="outbox_lag_seconds",
            unit="seconds",
            value=3.0,
        ),
        _metric_payload(
            component="lifecycle",
            operation="outbox_dispatch",
            metric="retry_count",
            unit="count",
            value=2,
        ),
        _metric_payload(
            component="lifecycle",
            operation="outbox_dispatch",
            metric="quarantine_count",
            unit="count",
            value=0,
        ),
        _metric_payload(
            component="agent",
            operation="answer",
            metric="request_count",
            unit="count",
            value=1,
        ),
    ],
)
def test_numeric_metrics_round_trip_fixed_semantics(payload):
    metric = parse_observability_sample(json.dumps(payload).encode())

    assert isinstance(metric, AgentObservabilityMetric)
    assert metric.to_dict() == payload


@pytest.mark.parametrize(
    "payload",
    [
        {
            "version": AGENT_OBSERVABILITY_VERSION,
            "kind": "metric",
            "component": "rebuild",
            "operation": "rebuild",
            "metric": "rebuild_state",
            "unit": "state",
            "state": "active",
        },
        {
            "version": AGENT_OBSERVABILITY_VERSION,
            "kind": "metric",
            "component": "reconciliation",
            "operation": "reconcile",
            "metric": "reconciliation_state",
            "unit": "state",
            "state": "synced",
        },
    ],
)
def test_state_metrics_expose_only_fixed_state_without_generation_id(payload):
    metric = parse_observability_sample(json.dumps(payload).encode())

    assert isinstance(metric, AgentObservabilityMetric)
    assert metric.to_dict() == payload


@pytest.mark.parametrize(
    "payload",
    [
        _metric_payload(value=-1),
        _metric_payload(value=True),
        _metric_payload(value=600_001),
        _metric_payload(unit="seconds"),
        _metric_payload(component="agent"),
        _metric_payload(operation="answer"),
        _metric_payload(metric="unknown"),
        _metric_payload(label="variable"),
        _metric_payload(user_id="user-1"),
        _metric_payload(generation_id="generation-1"),
        _metric_payload(state="active"),
        {
            "version": AGENT_OBSERVABILITY_VERSION,
            "kind": "metric",
            "component": "rebuild",
            "operation": "rebuild",
            "metric": "rebuild_state",
            "unit": "state",
            "state": "generation-123",
        },
        _metric_payload(
            component="rebuild",
            operation="rebuild",
            metric="rebuild_state",
            unit="state",
            value=None,
            state="generation-123",
        ),
        _metric_payload(
            component="lifecycle",
            operation="outbox_dispatch",
            metric="retry_count",
            unit="count",
            value=1.5,
        ),
    ],
)
def test_metric_rejects_unbounded_values_dimensions_and_state(payload):
    with pytest.raises(AgentObservabilityContractError):
        AgentObservabilityMetric.from_dict(payload)


def test_parser_rejects_duplicate_malformed_and_non_object_payloads():
    duplicate = json.dumps(_event_payload()).replace(
        '"outcome": "success"',
        '"outcome": "success", "outcome": "failed"',
    )

    for body in (duplicate.encode(), b"[]", b"{not-json", b""):
        with pytest.raises(AgentObservabilityContractError):
            parse_observability_sample(body)


def test_parser_rejects_oversized_payload_before_json_parsing():
    body = b"{" + b" " * MAX_OBSERVABILITY_PAYLOAD_BYTES

    with pytest.raises(AgentObservabilityContractError):
        parse_observability_sample(body)


def test_bounded_adapter_preserves_fifo_order_and_sample_types():
    adapter = BoundedInMemoryObservabilityAdapter(capacity=3)
    event = _event()
    metric = _metric()

    adapter.record(event)
    adapter.record(metric)

    assert adapter.capacity == 3
    assert len(adapter) == 2
    assert adapter.snapshot() == (event, metric)


def test_bounded_adapter_evicts_oldest_sample_on_overflow():
    adapter = BoundedInMemoryObservabilityAdapter(capacity=2)
    oldest = _event("success")
    middle = _event("no_context")
    newest = _metric(4.0)

    adapter.record(oldest)
    adapter.record(middle)
    adapter.record(newest)

    assert adapter.snapshot() == (middle, newest)


def test_bounded_adapter_snapshot_is_immutable_copy():
    adapter = BoundedInMemoryObservabilityAdapter(capacity=2)
    first = _event()
    adapter.record(first)

    snapshot = adapter.snapshot()
    adapter.record(_metric())

    assert isinstance(snapshot, tuple)
    assert snapshot == (first,)
    assert len(adapter.snapshot()) == 2


@pytest.mark.parametrize(
    "capacity",
    [0, -1, True, 1.5, MAX_OBSERVABILITY_BUFFER_CAPACITY + 1],
)
def test_bounded_adapter_rejects_invalid_capacity(capacity):
    with pytest.raises(AgentObservabilityAdapterError):
        BoundedInMemoryObservabilityAdapter(capacity=capacity)


@pytest.mark.parametrize("sample", [None, {}, "event", object()])
def test_bounded_adapter_rejects_unvalidated_samples(sample):
    adapter = BoundedInMemoryObservabilityAdapter(capacity=1)

    with pytest.raises(AgentObservabilityAdapterError):
        adapter.record(sample)

    assert adapter.snapshot() == ()


@pytest.mark.parametrize(
    "outcome",
    ["success", "no_context", "refused", "invalid", "unavailable"],
)
def test_answer_observation_records_only_fixed_count_and_outcome(outcome):
    adapter = BoundedInMemoryObservabilityAdapter(capacity=2)

    record_answer_observation(adapter, outcome)

    metric, event = adapter.snapshot()
    assert metric.to_dict() == {
        "version": AGENT_OBSERVABILITY_VERSION,
        "kind": "metric",
        "component": "agent",
        "operation": "answer",
        "metric": "request_count",
        "unit": "count",
        "value": 1,
    }
    assert event.to_dict() == {
        "version": AGENT_OBSERVABILITY_VERSION,
        "kind": "event",
        "component": "agent",
        "operation": "answer",
        "outcome": outcome,
    }


def test_answer_observation_is_noop_without_recorder_or_allowed_outcome():
    adapter = BoundedInMemoryObservabilityAdapter(capacity=2)

    record_answer_observation(None, "success")
    record_answer_observation(adapter, "degraded")

    assert adapter.snapshot() == ()


def test_answer_observation_attempts_both_samples_when_recorder_raises():
    class RaisingRecorder:
        calls = 0

        def record(self, _sample):
            self.calls += 1
            raise RuntimeError("raw synthetic recorder failure")

    recorder = RaisingRecorder()

    record_answer_observation(recorder, "unavailable")

    assert recorder.calls == 2


@pytest.mark.parametrize(
    "outcome",
    ["success", "no_context", "invalid", "unavailable"],
)
def test_retrieval_observation_records_only_fixed_latency_and_outcome(outcome):
    adapter = BoundedInMemoryObservabilityAdapter(capacity=2)
    readings = iter([10.0, 10.025])
    clock = lambda: next(readings)

    started_at = start_retrieval_observation(clock)
    record_retrieval_observation(adapter, clock, started_at, outcome)

    metric, event = adapter.snapshot()
    assert metric.to_dict() == {
        "version": AGENT_OBSERVABILITY_VERSION,
        "kind": "metric",
        "component": "retrieval",
        "operation": "search_memos",
        "metric": "tool_latency_ms",
        "unit": "milliseconds",
        "value": pytest.approx(25.0),
    }
    assert event.to_dict() == {
        "version": AGENT_OBSERVABILITY_VERSION,
        "kind": "event",
        "component": "retrieval",
        "operation": "search_memos",
        "outcome": outcome,
    }


def test_retrieval_observation_is_noop_without_dependencies_or_allowed_outcome():
    adapter = BoundedInMemoryObservabilityAdapter(capacity=4)
    clock = lambda: 10.0

    record_retrieval_observation(None, clock, 9.0, "success")
    record_retrieval_observation(adapter, None, 9.0, "success")
    record_retrieval_observation(adapter, clock, 9.0, "refused")

    assert adapter.snapshot() == ()


@pytest.mark.parametrize("value", [True, "10", float("nan"), float("inf")])
def test_retrieval_observation_discards_invalid_start_clock_value(value):
    assert start_retrieval_observation(lambda: value) is None


def test_retrieval_observation_discards_raising_start_clock():
    def clock():
        raise RuntimeError("raw synthetic clock failure")

    assert start_retrieval_observation(clock) is None


@pytest.mark.parametrize(
    "readings",
    [
        [10.0, True],
        [10.0, "11"],
        [10.0, float("nan")],
        [10.0, float("inf")],
        [10.0, 9.0],
        [10.0, 610.001],
    ],
)
def test_retrieval_observation_discards_invalid_elapsed_time(readings):
    adapter = BoundedInMemoryObservabilityAdapter(capacity=2)
    values = iter(readings)
    clock = lambda: next(values)

    started_at = start_retrieval_observation(clock)
    record_retrieval_observation(adapter, clock, started_at, "success")

    assert adapter.snapshot() == ()


def test_retrieval_observation_discards_raising_stop_clock():
    adapter = BoundedInMemoryObservabilityAdapter(capacity=2)
    calls = 0

    def clock():
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError("raw synthetic clock failure")
        return 10.0

    started_at = start_retrieval_observation(clock)
    record_retrieval_observation(adapter, clock, started_at, "success")

    assert adapter.snapshot() == ()


def test_retrieval_observation_attempts_both_samples_when_recorder_raises():
    class RaisingRecorder:
        calls = 0

        def record(self, _sample):
            self.calls += 1
            raise RuntimeError("raw synthetic recorder failure")

    recorder = RaisingRecorder()
    readings = iter([10.0, 10.025])
    clock = lambda: next(readings)

    started_at = start_retrieval_observation(clock)
    record_retrieval_observation(recorder, clock, started_at, "unavailable")

    assert recorder.calls == 2


@pytest.mark.parametrize("outcome", ["success", "invalid", "unavailable"])
def test_provider_observation_records_only_fixed_latency_and_outcome(outcome):
    adapter = BoundedInMemoryObservabilityAdapter(capacity=2)
    readings = iter([20.0, 20.04])
    clock = lambda: next(readings)

    started_at = start_provider_observation(clock)
    record_provider_observation(adapter, clock, started_at, outcome)

    metric, event = adapter.snapshot()
    assert metric.to_dict() == {
        "version": AGENT_OBSERVABILITY_VERSION,
        "kind": "metric",
        "component": "provider",
        "operation": "provider_call",
        "metric": "provider_latency_ms",
        "unit": "milliseconds",
        "value": pytest.approx(40.0),
    }
    assert event.to_dict() == {
        "version": AGENT_OBSERVABILITY_VERSION,
        "kind": "event",
        "component": "provider",
        "operation": "provider_call",
        "outcome": outcome,
    }


def test_provider_observation_is_noop_without_dependencies_or_allowed_outcome():
    adapter = BoundedInMemoryObservabilityAdapter(capacity=4)
    clock = lambda: 20.0

    record_provider_observation(None, clock, 19.0, "success")
    record_provider_observation(adapter, None, 19.0, "success")
    record_provider_observation(adapter, clock, 19.0, "no_context")

    assert adapter.snapshot() == ()


@pytest.mark.parametrize("value", [True, "20", float("nan"), float("inf")])
def test_provider_observation_discards_invalid_start_clock_value(value):
    assert start_provider_observation(lambda: value) is None


@pytest.mark.parametrize(
    "readings",
    [
        [20.0, True],
        [20.0, "21"],
        [20.0, float("nan")],
        [20.0, float("inf")],
        [20.0, 19.0],
        [20.0, 621.0],
    ],
)
def test_provider_observation_discards_invalid_elapsed_time(readings):
    adapter = BoundedInMemoryObservabilityAdapter(capacity=2)
    values = iter(readings)
    clock = lambda: next(values)

    started_at = start_provider_observation(clock)
    record_provider_observation(adapter, clock, started_at, "success")

    assert adapter.snapshot() == ()


def test_provider_observation_discards_raising_clock():
    adapter = BoundedInMemoryObservabilityAdapter(capacity=2)
    calls = 0

    def clock():
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError("raw synthetic clock failure")
        return 20.0

    started_at = start_provider_observation(clock)
    record_provider_observation(adapter, clock, started_at, "success")

    assert adapter.snapshot() == ()


def test_provider_observation_attempts_both_samples_when_recorder_raises():
    class RaisingRecorder:
        calls = 0

        def record(self, _sample):
            self.calls += 1
            raise RuntimeError("raw synthetic recorder failure")

    recorder = RaisingRecorder()
    readings = iter([20.0, 20.04])
    clock = lambda: next(readings)

    started_at = start_provider_observation(clock)
    record_provider_observation(recorder, clock, started_at, "unavailable")

    assert recorder.calls == 2
