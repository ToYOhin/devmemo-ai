package v1

import (
	"context"
	"errors"
	"testing"

	"github.com/stretchr/testify/require"

	"github.com/usememos/memos/store"
)

func attachLifecycleRuntimeForTest(
	t *testing.T, service *APIV1Service, client *fakeMemoLifecycleClient,
) store.MemoLifecycleOutboxStore {
	t.Helper()
	outbox, ok := service.Store.GetDriver().(store.MemoLifecycleOutboxStore)
	require.True(t, ok)
	service.memoLifecycleRuntime = newMemoLifecycleSourceRuntime(outbox, client)
	return outbox
}

func TestMemoLifecycleRuntimeOwnsCreateUpdateDeleteOutboxPath(t *testing.T) {
	ctx := context.Background()
	service := newIntegrationService(t)
	client := &fakeMemoLifecycleClient{}
	outbox := attachLifecycleRuntimeForTest(t, service, client)

	memo, err := service.createMemoWithLifecycle(ctx, &store.Memo{
		UID: "runtime-crud-memo", CreatorID: 1,
		Content: "created document", Visibility: store.Private,
	})
	require.NoError(t, err)
	updatedContent := "updated document"
	require.NoError(t, service.updateMemoWithLifecycle(
		ctx, memo, &store.UpdateMemo{ID: memo.ID, Content: &updatedContent},
	))
	updated, err := service.Store.GetMemo(ctx, &store.FindMemo{ID: &memo.ID})
	require.NoError(t, err)
	require.NoError(t, service.deleteMemoWithLifecycle(ctx, updated))

	events, err := outbox.ListMemoLifecycleOutboxEvents(ctx, memo.UID)
	require.NoError(t, err)
	deleted, err := service.Store.GetMemo(ctx, &store.FindMemo{ID: &memo.ID})
	require.NoError(t, err)
	require.Nil(t, deleted)
	require.Len(t, client.delivered, 3)
	require.Len(t, events, 3)
	require.Equal(t, []int64{1, 2, 3}, []int64{
		events[0].SourceSequence,
		events[1].SourceSequence,
		events[2].SourceSequence,
	})
	require.Equal(t, "content_changed", events[1].Reason)
	require.Equal(t, store.MemoLifecycleOperationDelete, events[2].Operation)
	for _, event := range events {
		require.Equal(t, store.MemoLifecycleOutboxAcknowledged, event.Status)
	}
}

func TestMemoLifecycleRuntimeLeavesCommentsAndBlankMemosUnindexed(t *testing.T) {
	ctx := context.Background()
	service := newIntegrationService(t)
	client := &fakeMemoLifecycleClient{}
	outbox := attachLifecycleRuntimeForTest(t, service, client)
	parent, err := service.Store.CreateMemo(ctx, &store.Memo{
		UID: "runtime-parent", CreatorID: 1, Content: "parent", Visibility: store.Private,
	})
	require.NoError(t, err)
	blank, err := service.createMemoWithLifecycle(ctx, &store.Memo{
		UID: "runtime-blank", CreatorID: 1, Content: "  ", Visibility: store.Private,
	})
	require.NoError(t, err)
	comment, err := service.createMemoWithLifecycle(
		withSuppressMemoLifecycle(ctx),
		&store.Memo{
			UID: "runtime-comment", CreatorID: 1,
			Content: "comment", Visibility: store.Private,
		},
	)
	require.NoError(t, err)
	_, err = service.Store.UpsertMemoRelation(ctx, &store.MemoRelation{
		MemoID: comment.ID, RelatedMemoID: parent.ID, Type: store.MemoRelationComment,
	})
	require.NoError(t, err)
	commentContent := "updated comment"
	require.NoError(t, service.updateMemoWithLifecycle(
		ctx, comment, &store.UpdateMemo{ID: comment.ID, Content: &commentContent},
	))

	blankEvents, err := outbox.ListMemoLifecycleOutboxEvents(ctx, blank.UID)
	require.NoError(t, err)
	commentEvents, err := outbox.ListMemoLifecycleOutboxEvents(ctx, comment.UID)
	require.NoError(t, err)
	require.Empty(t, blankEvents)
	require.Empty(t, commentEvents)
	require.Empty(t, client.delivered)
}

func TestMemoLifecycleDeliveryFailureDoesNotRollbackAuthoritativeCreate(t *testing.T) {
	ctx := context.Background()
	service := newIntegrationService(t)
	client := &fakeMemoLifecycleClient{deliverErr: errors.New("raw transport detail")}
	outbox := attachLifecycleRuntimeForTest(t, service, client)

	memo, err := service.createMemoWithLifecycle(ctx, &store.Memo{
		UID: "runtime-deferred", CreatorID: 1,
		Content: "authoritative write survives", Visibility: store.Private,
	})

	require.NoError(t, err)
	stored, err := service.Store.GetMemo(ctx, &store.FindMemo{ID: &memo.ID})
	require.NoError(t, err)
	require.NotNil(t, stored)
	events, err := outbox.ListMemoLifecycleOutboxEvents(ctx, memo.UID)
	require.NoError(t, err)
	require.Len(t, events, 1)
	require.Equal(t, 1, events[0].Attempts)
	require.Equal(t, "transport_unavailable", *events[0].LastErrorCode)
	require.Equal(t, store.MemoLifecycleOutboxPending, events[0].Status)
}

func TestMemoLifecycleRuntimeTombstonesMemoThatBecomesComment(t *testing.T) {
	ctx := context.Background()
	service := newIntegrationService(t)
	client := &fakeMemoLifecycleClient{}
	outbox := attachLifecycleRuntimeForTest(t, service, client)
	parent, err := service.Store.CreateMemo(ctx, &store.Memo{
		UID: "runtime-comment-parent", CreatorID: 1,
		Content: "parent", Visibility: store.Private,
	})
	require.NoError(t, err)
	memo, err := service.createMemoWithLifecycle(ctx, &store.Memo{
		UID: "runtime-becomes-comment", CreatorID: 1,
		Content: "initial plain memo", Visibility: store.Private,
	})
	require.NoError(t, err)
	_, err = service.Store.UpsertMemoRelation(ctx, &store.MemoRelation{
		MemoID: memo.ID, RelatedMemoID: parent.ID, Type: store.MemoRelationComment,
	})
	require.NoError(t, err)
	content := memo.Content
	require.NoError(t, service.updateMemoWithLifecycle(
		ctx, memo, &store.UpdateMemo{ID: memo.ID, Content: &content},
	))

	events, err := outbox.ListMemoLifecycleOutboxEvents(ctx, memo.UID)
	require.NoError(t, err)
	require.Len(t, events, 2)
	require.Equal(t, "became_comment", events[1].Reason)
	require.Equal(t, store.MemoLifecycleOperationDelete, events[1].Operation)
}

func TestMemoLifecycleUpdateReasonUsesResultingEligibility(t *testing.T) {
	normal := store.Normal
	archived := store.Archived
	blank := " "
	restored := "restored"
	tests := []struct {
		name   string
		memo   *store.Memo
		update *store.UpdateMemo
		want   string
	}{
		{"archive", &store.Memo{RowStatus: normal, Content: "x"}, &store.UpdateMemo{RowStatus: &archived}, "archived"},
		{"blank", &store.Memo{RowStatus: normal, Content: "x"}, &store.UpdateMemo{Content: &blank}, "blank_content"},
		{"restore", &store.Memo{RowStatus: archived, Content: "x"}, &store.UpdateMemo{RowStatus: &normal, Content: &restored}, "restored"},
	}
	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			require.Equal(t, test.want, memoLifecycleUpdateReason(test.memo, test.update))
		})
	}
}
