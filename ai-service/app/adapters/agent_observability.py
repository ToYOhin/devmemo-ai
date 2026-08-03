from collections import deque

from app.domain.agent_observability import (
    AgentObservabilityEvent,
    AgentObservabilityMetric,
    AgentObservabilitySample,
)


MAX_OBSERVABILITY_BUFFER_CAPACITY = 4096


class AgentObservabilityAdapterError(ValueError):
    """Reject invalid adapter configuration or samples without retaining them."""

    def __init__(self) -> None:
        super().__init__("invalid agent observability adapter")


class BoundedInMemoryObservabilityAdapter:
    """Dormant FIFO buffer with constructor-fixed capacity and immutable snapshots."""

    def __init__(self, capacity: int) -> None:
        if type(capacity) is not int or not 1 <= capacity <= MAX_OBSERVABILITY_BUFFER_CAPACITY:
            raise AgentObservabilityAdapterError
        self._capacity = capacity
        self._samples: deque[AgentObservabilitySample] = deque(maxlen=capacity)

    @property
    def capacity(self) -> int:
        return self._capacity

    def record(self, sample: AgentObservabilitySample) -> None:
        if not isinstance(sample, (AgentObservabilityEvent, AgentObservabilityMetric)):
            raise AgentObservabilityAdapterError
        self._samples.append(sample)

    def snapshot(self) -> tuple[AgentObservabilitySample, ...]:
        return tuple(self._samples)

    def __len__(self) -> int:
        return len(self._samples)
