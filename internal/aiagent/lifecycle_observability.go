package aiagent

import (
	"errors"
	"sync"
)

const (
	AgentObservabilityVersion             = "agent-observability-v1"
	MaxLifecycleObservationBufferCapacity = 4096
)

var ErrLifecycleObservationInvalid = errors.New("lifecycle observation is invalid")

type LifecycleObservation struct {
	Version   string
	Kind      string
	Component string
	Operation string
	Outcome   string
	Metric    string
	Unit      string
	Value     int
}

func NewLifecycleDispatchEvent(outcome string) (LifecycleObservation, error) {
	sample := LifecycleObservation{
		Version:   AgentObservabilityVersion,
		Kind:      "event",
		Component: "lifecycle",
		Operation: "outbox_dispatch",
		Outcome:   outcome,
	}
	if err := sample.Validate(); err != nil {
		return LifecycleObservation{}, err
	}
	return sample, nil
}

func NewLifecycleCounterMetric(metric string) (LifecycleObservation, error) {
	sample := LifecycleObservation{
		Version:   AgentObservabilityVersion,
		Kind:      "metric",
		Component: "lifecycle",
		Operation: "outbox_dispatch",
		Metric:    metric,
		Unit:      "count",
		Value:     1,
	}
	if err := sample.Validate(); err != nil {
		return LifecycleObservation{}, err
	}
	return sample, nil
}

func (sample LifecycleObservation) Validate() error {
	if sample.Version != AgentObservabilityVersion ||
		sample.Component != "lifecycle" ||
		sample.Operation != "outbox_dispatch" {
		return ErrLifecycleObservationInvalid
	}
	switch sample.Kind {
	case "event":
		if sample.Outcome != "success" &&
			sample.Outcome != "pending" &&
			sample.Outcome != "failed" {
			return ErrLifecycleObservationInvalid
		}
		if sample.Metric != "" || sample.Unit != "" || sample.Value != 0 {
			return ErrLifecycleObservationInvalid
		}
	case "metric":
		if sample.Metric != "retry_count" && sample.Metric != "quarantine_count" {
			return ErrLifecycleObservationInvalid
		}
		if sample.Unit != "count" || sample.Value != 1 || sample.Outcome != "" {
			return ErrLifecycleObservationInvalid
		}
	default:
		return ErrLifecycleObservationInvalid
	}
	return nil
}

type LifecycleObservationRecorder interface {
	RecordLifecycleObservation(LifecycleObservation) error
}

type BoundedLifecycleObservationRecorder struct {
	mu       sync.Mutex
	capacity int
	samples  []LifecycleObservation
}

func NewBoundedLifecycleObservationRecorder(
	capacity int,
) (*BoundedLifecycleObservationRecorder, error) {
	if capacity < 1 || capacity > MaxLifecycleObservationBufferCapacity {
		return nil, ErrLifecycleObservationInvalid
	}
	return &BoundedLifecycleObservationRecorder{
		capacity: capacity,
		samples:  make([]LifecycleObservation, 0, capacity),
	}, nil
}

func (recorder *BoundedLifecycleObservationRecorder) RecordLifecycleObservation(
	sample LifecycleObservation,
) error {
	if recorder == nil || sample.Validate() != nil {
		return ErrLifecycleObservationInvalid
	}
	recorder.mu.Lock()
	defer recorder.mu.Unlock()
	if len(recorder.samples) == recorder.capacity {
		copy(recorder.samples, recorder.samples[1:])
		recorder.samples = recorder.samples[:recorder.capacity-1]
	}
	recorder.samples = append(recorder.samples, sample)
	return nil
}

func (recorder *BoundedLifecycleObservationRecorder) Snapshot() []LifecycleObservation {
	if recorder == nil {
		return nil
	}
	recorder.mu.Lock()
	defer recorder.mu.Unlock()
	snapshot := make([]LifecycleObservation, len(recorder.samples))
	copy(snapshot, recorder.samples)
	return snapshot
}
