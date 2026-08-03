package aiagent

import (
	"testing"

	"github.com/stretchr/testify/require"
)

func TestLifecycleObservationConstructorsAreFixed(t *testing.T) {
	event, err := NewLifecycleDispatchEvent("pending")
	require.NoError(t, err)
	require.Equal(t, LifecycleObservation{
		Version:   AgentObservabilityVersion,
		Kind:      "event",
		Component: "lifecycle",
		Operation: "outbox_dispatch",
		Outcome:   "pending",
	}, event)

	metric, err := NewLifecycleCounterMetric("retry_count")
	require.NoError(t, err)
	require.Equal(t, LifecycleObservation{
		Version:   AgentObservabilityVersion,
		Kind:      "metric",
		Component: "lifecycle",
		Operation: "outbox_dispatch",
		Metric:    "retry_count",
		Unit:      "count",
		Value:     1,
	}, metric)
}

func TestLifecycleObservationRejectsUnknownOrContentBearingShape(t *testing.T) {
	_, err := NewLifecycleDispatchEvent("unavailable")
	require.ErrorIs(t, err, ErrLifecycleObservationInvalid)
	_, err = NewLifecycleCounterMetric("request_count")
	require.ErrorIs(t, err, ErrLifecycleObservationInvalid)

	forged := LifecycleObservation{
		Version:   AgentObservabilityVersion,
		Kind:      "event",
		Component: "lifecycle",
		Operation: "outbox_dispatch",
		Outcome:   "success",
		Metric:    "memo-content",
	}
	require.ErrorIs(t, forged.Validate(), ErrLifecycleObservationInvalid)
}

func TestBoundedLifecycleObservationRecorderEvictsOldestAndCopiesSnapshot(t *testing.T) {
	recorder, err := NewBoundedLifecycleObservationRecorder(2)
	require.NoError(t, err)
	first, err := NewLifecycleDispatchEvent("pending")
	require.NoError(t, err)
	second, err := NewLifecycleCounterMetric("retry_count")
	require.NoError(t, err)
	third, err := NewLifecycleDispatchEvent("success")
	require.NoError(t, err)

	require.NoError(t, recorder.RecordLifecycleObservation(first))
	require.NoError(t, recorder.RecordLifecycleObservation(second))
	require.NoError(t, recorder.RecordLifecycleObservation(third))

	snapshot := recorder.Snapshot()
	require.Equal(t, []LifecycleObservation{second, third}, snapshot)
	snapshot[0] = first
	require.Equal(t, []LifecycleObservation{second, third}, recorder.Snapshot())
}

func TestBoundedLifecycleObservationRecorderRejectsInvalidInputs(t *testing.T) {
	for _, capacity := range []int{0, -1, MaxLifecycleObservationBufferCapacity + 1} {
		_, err := NewBoundedLifecycleObservationRecorder(capacity)
		require.ErrorIs(t, err, ErrLifecycleObservationInvalid)
	}

	recorder, err := NewBoundedLifecycleObservationRecorder(1)
	require.NoError(t, err)
	require.ErrorIs(
		t,
		recorder.RecordLifecycleObservation(LifecycleObservation{}),
		ErrLifecycleObservationInvalid,
	)
	var nilRecorder *BoundedLifecycleObservationRecorder
	require.ErrorIs(
		t,
		nilRecorder.RecordLifecycleObservation(LifecycleObservation{}),
		ErrLifecycleObservationInvalid,
	)
	require.Nil(t, nilRecorder.Snapshot())
}
