package v1

import (
	"context"
	"testing"

	"github.com/stretchr/testify/require"

	"github.com/usememos/memos/server/auth"
	"github.com/usememos/memos/store"
	teststore "github.com/usememos/memos/store/test"
)

func TestResolveAgentVisibleMemoUIDsUsesMemosReadVisibility(t *testing.T) {
	ctx := context.Background()
	testStore := teststore.NewTestingStore(ctx, t)
	t.Cleanup(func() { _ = testStore.Close() })
	service := &APIV1Service{Store: testStore}

	caller := createAgentVisibilityUser(ctx, t, testStore, "agent-caller")
	other := createAgentVisibilityUser(ctx, t, testStore, "agent-other")
	createAgentVisibilityMemo(ctx, t, testStore, "agent-caller-private", caller.ID, store.Private)
	createAgentVisibilityMemo(ctx, t, testStore, "agent-other-public", other.ID, store.Public)
	createAgentVisibilityMemo(ctx, t, testStore, "agent-other-protected", other.ID, store.Protected)
	createAgentVisibilityMemo(ctx, t, testStore, "agent-other-private", other.ID, store.Private)

	userCtx := context.WithValue(ctx, auth.UserIDContextKey, caller.ID)
	uids, err := service.resolveAgentVisibleMemoUIDs(userCtx)

	require.NoError(t, err)
	require.ElementsMatch(t, []string{
		"agent-caller-private",
		"agent-other-public",
		"agent-other-protected",
	}, uids)
}

func TestResolveAgentVisibleMemoUIDsRequiresMemosAuthentication(t *testing.T) {
	ctx := context.Background()
	testStore := teststore.NewTestingStore(ctx, t)
	t.Cleanup(func() { _ = testStore.Close() })
	service := &APIV1Service{Store: testStore}

	_, err := service.resolveAgentVisibleMemoUIDs(ctx)

	require.Error(t, err)
}

func createAgentVisibilityUser(ctx context.Context, t *testing.T, testStore *store.Store, username string) *store.User {
	t.Helper()
	user, err := testStore.CreateUser(ctx, &store.User{
		Username: username,
		Role:     store.RoleUser,
		Email:    username + "@example.com",
	})
	require.NoError(t, err)
	return user
}

func createAgentVisibilityMemo(ctx context.Context, t *testing.T, testStore *store.Store, uid string, creatorID int32, visibility store.Visibility) {
	t.Helper()
	_, err := testStore.CreateMemo(ctx, &store.Memo{
		UID:        uid,
		CreatorID:  creatorID,
		Content:    "test memo content",
		Visibility: visibility,
	})
	require.NoError(t, err)
}
