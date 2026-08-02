package v1

import (
	"context"
	"log/slog"
	"strings"
	"time"

	"github.com/google/uuid"

	"github.com/usememos/memos/store"
)

type suppressMemoLifecycleKey struct{}

func withSuppressMemoLifecycle(ctx context.Context) context.Context {
	return context.WithValue(ctx, suppressMemoLifecycleKey{}, true)
}

func memoLifecycleSuppressed(ctx context.Context) bool {
	suppressed, ok := ctx.Value(suppressMemoLifecycleKey{}).(bool)
	return ok && suppressed
}

func (s *APIV1Service) createMemoWithLifecycle(
	ctx context.Context, create *store.Memo,
) (*store.Memo, error) {
	runtime := s.memoLifecycleRuntime
	if runtime == nil || memoLifecycleSuppressed(ctx) || strings.TrimSpace(create.Content) == "" {
		return s.Store.CreateMemo(ctx, create)
	}
	memo, event, err := runtime.outbox.CreateMemoWithLifecycleEvent(
		ctx, create, newMemoLifecycleEventRequest("created"),
	)
	if err != nil {
		return nil, err
	}
	runtime.deliverBestEffort(ctx, event)
	return memo, nil
}

func (s *APIV1Service) updateMemoWithLifecycle(
	ctx context.Context, memo *store.Memo, update *store.UpdateMemo,
) error {
	runtime := s.memoLifecycleRuntime
	if runtime == nil {
		return s.Store.UpdateMemo(ctx, update)
	}
	isComment, err := s.memoIsComment(ctx, memo.ID)
	if err != nil {
		return err
	}
	if isComment {
		events, err := runtime.outbox.ListMemoLifecycleOutboxEvents(ctx, memo.UID)
		if err != nil {
			return err
		}
		if len(events) == 0 {
			return s.Store.UpdateMemo(ctx, update)
		}
		event, err := runtime.outbox.UpdateMemoWithLifecycleEvent(
			ctx, update, newMemoLifecycleEventRequest("became_comment"),
		)
		if err != nil {
			return err
		}
		runtime.deliverBestEffort(ctx, event)
		return nil
	}
	event, err := runtime.outbox.UpdateMemoWithLifecycleEvent(
		ctx, update, newMemoLifecycleEventRequest(memoLifecycleUpdateReason(memo, update)),
	)
	if err != nil {
		return err
	}
	runtime.deliverBestEffort(ctx, event)
	return nil
}

func (s *APIV1Service) deleteMemoWithLifecycle(
	ctx context.Context, memo *store.Memo,
) error {
	runtime := s.memoLifecycleRuntime
	if runtime == nil {
		return s.Store.DeleteMemo(ctx, &store.DeleteMemo{ID: memo.ID})
	}
	isComment, err := s.memoIsComment(ctx, memo.ID)
	if err != nil {
		return err
	}
	if isComment {
		return s.Store.DeleteMemo(ctx, &store.DeleteMemo{ID: memo.ID})
	}
	if err := s.cleanupMemoDependencies(ctx, memo.ID); err != nil {
		return err
	}
	event, err := runtime.outbox.DeleteMemoWithLifecycleEvent(
		ctx,
		&store.DeleteMemo{ID: memo.ID},
		newMemoLifecycleEventRequest("deleted"),
	)
	if err != nil {
		return err
	}
	runtime.deliverBestEffort(ctx, event)
	return nil
}

func (s *APIV1Service) memoIsComment(ctx context.Context, memoID int32) (bool, error) {
	commentType := store.MemoRelationComment
	relations, err := s.Store.ListMemoRelations(ctx, &store.FindMemoRelation{
		MemoID: &memoID,
		Type:   &commentType,
	})
	return len(relations) > 0, err
}

func (s *APIV1Service) cleanupMemoDependencies(ctx context.Context, memoID int32) error {
	if err := s.Store.DeleteMemoRelation(
		ctx, &store.DeleteMemoRelation{MemoID: &memoID},
	); err != nil {
		return err
	}
	if err := s.Store.DeleteMemoRelation(
		ctx, &store.DeleteMemoRelation{RelatedMemoID: &memoID},
	); err != nil {
		return err
	}
	attachments, err := s.Store.ListAttachments(ctx, &store.FindAttachment{MemoID: &memoID})
	if err != nil {
		return err
	}
	for _, attachment := range attachments {
		if err := s.Store.DeleteAttachment(ctx, &store.DeleteAttachment{ID: attachment.ID}); err != nil {
			return err
		}
	}
	return nil
}

func memoLifecycleUpdateReason(memo *store.Memo, update *store.UpdateMemo) string {
	resultingStatus := memo.RowStatus
	if update.RowStatus != nil {
		resultingStatus = *update.RowStatus
	}
	resultingContent := memo.Content
	if update.Content != nil {
		resultingContent = *update.Content
	}
	if resultingStatus != store.Normal {
		return "archived"
	}
	if strings.TrimSpace(resultingContent) == "" {
		return "blank_content"
	}
	if memo.RowStatus != store.Normal {
		return "restored"
	}
	if update.Content != nil {
		return "content_changed"
	}
	return "indexed_metadata_changed"
}

func newMemoLifecycleEventRequest(reason string) *store.MemoLifecycleEventRequest {
	return &store.MemoLifecycleEventRequest{
		EventID:    "runtime-" + uuid.NewString(),
		Reason:     reason,
		OccurredAt: time.Now().UTC(),
	}
}

func (runtime *memoLifecycleSourceRuntime) deliverBestEffort(
	ctx context.Context, event *store.MemoLifecycleOutboxEvent,
) {
	if err := runtime.deliver(ctx, event); err != nil {
		slog.Warn("Memo lifecycle delivery deferred", slog.String("event_id", event.EventID))
	}
}
