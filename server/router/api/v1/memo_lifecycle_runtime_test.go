package v1

import (
	"context"
	"errors"
	"testing"
	"time"

	"github.com/stretchr/testify/require"

	"github.com/usememos/memos/internal/aiagent"
	"github.com/usememos/memos/store"
)

type fakeMemoLifecycleOutbox struct {
	store.MemoLifecycleOutboxStore
	manifest      *store.MemoLifecycleRebuildManifest
	events        []*store.MemoLifecycleOutboxEvent
	acknowledged  []string
	failureCodes  []string
	prepareCalled int
}

func (outbox *fakeMemoLifecycleOutbox) PrepareMemoLifecycleRebuild(
	context.Context, string, time.Time,
) (*store.MemoLifecycleRebuildManifest, error) {
	outbox.prepareCalled++
	return outbox.manifest, nil
}

func (outbox *fakeMemoLifecycleOutbox) ListPendingMemoLifecycleOutboxEvents(
	context.Context, int,
) ([]*store.MemoLifecycleOutboxEvent, error) {
	pending := []*store.MemoLifecycleOutboxEvent{}
	for _, event := range outbox.events {
		if event.Status == store.MemoLifecycleOutboxPending {
			pending = append(pending, event)
		}
	}
	return pending, nil
}

func (outbox *fakeMemoLifecycleOutbox) AcknowledgeMemoLifecycleOutboxEvent(
	_ context.Context, eventID string,
) (*store.MemoLifecycleOutboxEvent, error) {
	for _, event := range outbox.events {
		if event.EventID == eventID {
			event.Status = store.MemoLifecycleOutboxAcknowledged
			outbox.acknowledged = append(outbox.acknowledged, eventID)
			return event, nil
		}
	}
	return nil, errors.New("missing synthetic event")
}

func (outbox *fakeMemoLifecycleOutbox) RecordMemoLifecycleDeliveryFailure(
	_ context.Context, eventID string, errorCode string,
) (*store.MemoLifecycleOutboxEvent, error) {
	outbox.failureCodes = append(outbox.failureCodes, errorCode)
	for _, event := range outbox.events {
		if event.EventID == eventID {
			event.Attempts++
			return event, nil
		}
	}
	return nil, errors.New("missing synthetic event")
}

func (outbox *fakeMemoLifecycleOutbox) ReadMemoLifecycleBacklog(
	context.Context,
) (*store.MemoLifecycleBacklog, error) {
	backlog := &store.MemoLifecycleBacklog{}
	for _, event := range outbox.events {
		if event.Status == store.MemoLifecycleOutboxPending {
			backlog.Pending++
			if event.Attempts > 0 {
				backlog.Failed++
			}
		}
	}
	return backlog, nil
}

type fakeMemoLifecycleClient struct {
	delivered  []aiagent.LifecycleEventRequest
	activation *aiagent.LifecycleActivationRequest
	deliverErr error
}

func (client *fakeMemoLifecycleClient) Deliver(
	_ context.Context, event aiagent.LifecycleEventRequest,
) (aiagent.LifecycleAcknowledgement, error) {
	client.delivered = append(client.delivered, event)
	if client.deliverErr != nil {
		return aiagent.LifecycleAcknowledgement{}, client.deliverErr
	}
	return aiagent.LifecycleAcknowledgement{
		EventID: event.EventID, MemoUID: event.MemoUID,
		SourceSequence: event.SourceSequence, IndexVersion: event.IndexVersion,
		Status: "applied", Operation: event.Operation,
	}, nil
}

func (client *fakeMemoLifecycleClient) Activate(
	_ context.Context, activation aiagent.LifecycleActivationRequest,
) error {
	client.activation = &activation
	return nil
}

func syntheticMemoLifecycleOutboxEvent() *store.MemoLifecycleOutboxEvent {
	document := "synthetic runtime document"
	documentHash := "b3ebd3f7a25c86fcda8a6a9d89a62456d96ea8b5d80dfc69c12ef3ab48ea8592"
	return &store.MemoLifecycleOutboxEvent{
		EventID: "event-runtime-1", MemoUID: "memo-runtime", SourceSequence: 1,
		EventType: store.MemoLifecycleEventIndex, IndexVersion: store.MemoIndexVersion,
		Operation: store.MemoLifecycleOperationUpsert, Reason: "created",
		OccurredAt: time.Date(2026, time.August, 3, 0, 0, 0, 0, time.UTC),
		Document:   &document, DocumentHash: &documentHash,
		Status: store.MemoLifecycleOutboxPending,
	}
}

func TestMemoLifecycleSourceRuntimeDrainsBeforeGenerationActivation(t *testing.T) {
	event := syntheticMemoLifecycleOutboxEvent()
	outbox := &fakeMemoLifecycleOutbox{
		manifest: &store.MemoLifecycleRebuildManifest{
			Generation: "generation-r5", EligibleCount: 1,
			ManifestDigest: "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
		},
		events: []*store.MemoLifecycleOutboxEvent{event},
	}
	client := &fakeMemoLifecycleClient{}
	runtime := newMemoLifecycleSourceRuntime(outbox, client)

	err := runtime.prepareAndActivate(
		context.Background(), "generation-r5", time.Now().UTC(),
	)

	require.NoError(t, err)
	require.Equal(t, []string{"event-runtime-1"}, outbox.acknowledged)
	require.Len(t, client.delivered, 1)
	require.Equal(t, event.EventID, client.delivered[0].EventID)
	require.NotNil(t, client.activation)
	require.Equal(t, "generation-r5", client.activation.Generation)
}

func TestMemoLifecycleSourceRuntimeRecordsSafeFailureAndBlocksActivation(t *testing.T) {
	outbox := &fakeMemoLifecycleOutbox{
		manifest: &store.MemoLifecycleRebuildManifest{Generation: "generation-r5"},
		events:   []*store.MemoLifecycleOutboxEvent{syntheticMemoLifecycleOutboxEvent()},
	}
	client := &fakeMemoLifecycleClient{deliverErr: errors.New("raw synthetic detail")}
	runtime := newMemoLifecycleSourceRuntime(outbox, client)

	err := runtime.prepareAndActivate(
		context.Background(), "generation-r5", time.Now().UTC(),
	)

	require.ErrorIs(t, err, errMemoLifecycleRuntimeUnavailable)
	require.Equal(t, []string{"transport_unavailable"}, outbox.failureCodes)
	require.Nil(t, client.activation)
}
