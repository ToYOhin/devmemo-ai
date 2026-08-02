package v1

import (
	"context"
	"errors"
	"time"

	"github.com/usememos/memos/internal/aiagent"
	"github.com/usememos/memos/store"
)

var errMemoLifecycleRuntimeUnavailable = errors.New("memo lifecycle runtime unavailable")

type memoLifecycleDeliveryClient interface {
	Deliver(context.Context, aiagent.LifecycleEventRequest) (aiagent.LifecycleAcknowledgement, error)
	Activate(context.Context, aiagent.LifecycleActivationRequest) error
}

type memoLifecycleSourceRuntime struct {
	outbox store.MemoLifecycleOutboxStore
	client memoLifecycleDeliveryClient
}

func newMemoLifecycleSourceRuntime(
	outbox store.MemoLifecycleOutboxStore,
	client memoLifecycleDeliveryClient,
) *memoLifecycleSourceRuntime {
	return &memoLifecycleSourceRuntime{outbox: outbox, client: client}
}

func (runtime *memoLifecycleSourceRuntime) prepareAndActivate(
	ctx context.Context, generation string, occurredAt time.Time,
) error {
	manifest, err := runtime.outbox.PrepareMemoLifecycleRebuild(
		ctx, generation, occurredAt,
	)
	if err != nil {
		return errMemoLifecycleRuntimeUnavailable
	}
	if err := runtime.drainPending(ctx); err != nil {
		return err
	}
	if err := runtime.client.Activate(ctx, aiagent.LifecycleActivationRequest{
		Generation:     manifest.Generation,
		EligibleCount:  manifest.EligibleCount,
		ManifestDigest: manifest.ManifestDigest,
	}); err != nil {
		return errMemoLifecycleRuntimeUnavailable
	}
	return nil
}

func (runtime *memoLifecycleSourceRuntime) drainPending(ctx context.Context) error {
	for {
		events, err := runtime.outbox.ListPendingMemoLifecycleOutboxEvents(ctx, 100)
		if err != nil {
			return errMemoLifecycleRuntimeUnavailable
		}
		if len(events) == 0 {
			break
		}
		hadFailure := false
		for _, event := range events {
			if err := runtime.deliver(ctx, event); err != nil {
				hadFailure = true
			}
		}
		if hadFailure {
			break
		}
	}
	backlog, err := runtime.outbox.ReadMemoLifecycleBacklog(ctx)
	if err != nil || backlog.Pending != 0 || backlog.Exhausted != 0 {
		return errMemoLifecycleRuntimeUnavailable
	}
	return nil
}

func (runtime *memoLifecycleSourceRuntime) deliver(
	ctx context.Context, event *store.MemoLifecycleOutboxEvent,
) error {
	acknowledgement, err := runtime.client.Deliver(ctx, lifecycleEventRequest(event))
	if err != nil {
		return runtime.recordFailure(ctx, event.EventID, "transport_unavailable")
	}
	if acknowledgement.Status == "failed" {
		errorCode := "lifecycle_processing_failed"
		if acknowledgement.ErrorCode != nil {
			errorCode = *acknowledgement.ErrorCode
		}
		return runtime.recordFailure(ctx, event.EventID, errorCode)
	}
	if _, err := runtime.outbox.AcknowledgeMemoLifecycleOutboxEvent(
		ctx, event.EventID,
	); err != nil {
		return errMemoLifecycleRuntimeUnavailable
	}
	return nil
}

func (runtime *memoLifecycleSourceRuntime) recordFailure(
	ctx context.Context, eventID string, errorCode string,
) error {
	_, err := runtime.outbox.RecordMemoLifecycleDeliveryFailure(ctx, eventID, errorCode)
	if err != nil && !errors.Is(err, store.ErrMemoLifecycleDeliveryExhausted) {
		return errMemoLifecycleRuntimeUnavailable
	}
	return errMemoLifecycleRuntimeUnavailable
}

func lifecycleEventRequest(event *store.MemoLifecycleOutboxEvent) aiagent.LifecycleEventRequest {
	return aiagent.LifecycleEventRequest{
		EventID:        event.EventID,
		EventType:      string(event.EventType),
		MemoUID:        event.MemoUID,
		SourceSequence: event.SourceSequence,
		IndexVersion:   event.IndexVersion,
		Operation:      string(event.Operation),
		Reason:         event.Reason,
		OccurredAt:     event.OccurredAt.Format(time.RFC3339Nano),
		Document:       event.Document,
		DocumentHash:   event.DocumentHash,
	}
}

func (s *APIV1Service) configureMemoLifecycleRuntime(ctx context.Context) error {
	config, err := aiagent.LoadLifecycleRuntimeConfigFromEnv()
	if err != nil {
		return errMemoLifecycleRuntimeUnavailable
	}
	if !config.Enabled {
		s.memoLifecycleRuntime = nil
		return nil
	}
	outbox, ok := s.Store.GetDriver().(store.MemoLifecycleOutboxStore)
	if !ok {
		return errMemoLifecycleRuntimeUnavailable
	}
	client, err := aiagent.NewLifecycleHTTPClient(config)
	if err != nil {
		return errMemoLifecycleRuntimeUnavailable
	}
	runtime := newMemoLifecycleSourceRuntime(outbox, client)
	if err := runtime.prepareAndActivate(ctx, config.Generation, time.Now().UTC()); err != nil {
		return err
	}
	s.memoLifecycleRuntime = runtime
	return nil
}
