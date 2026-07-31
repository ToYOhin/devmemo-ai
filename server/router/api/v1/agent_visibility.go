package v1

import (
	"context"
	"fmt"

	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"

	"github.com/usememos/memos/store"
)

// resolveAgentVisibleMemoUIDs returns only the normal, complete Memos that the
// authenticated caller may read. The result is an internal capability for the
// AI Service, never a browser-supplied authorization claim.
func (s *APIV1Service) resolveAgentVisibleMemoUIDs(ctx context.Context) ([]string, error) {
	currentUser, err := s.fetchCurrentUser(ctx)
	if err != nil {
		return nil, status.Errorf(codes.Internal, "failed to get user")
	}
	if currentUser == nil {
		return nil, status.Errorf(codes.Unauthenticated, "user not authenticated")
	}

	state := store.Normal
	find := &store.FindMemo{
		ExcludeContent:  true,
		ExcludeComments: true,
		RowStatus:       &state,
	}
	applyMemoListVisibility(find, currentUser)
	memos, err := s.Store.ListMemos(ctx, find)
	if err != nil {
		return nil, status.Errorf(codes.Internal, "failed to list visible memos")
	}

	uids := make([]string, 0, len(memos))
	for _, memo := range memos {
		uids = append(uids, memo.UID)
	}
	return uids, nil
}

// applyMemoListVisibility is the shared ListMemos visibility policy. It keeps
// the Agent capability scope aligned with the public Memos read path.
func applyMemoListVisibility(find *store.FindMemo, currentUser *store.User) {
	if currentUser == nil {
		find.VisibilityList = []store.Visibility{store.Public}
		return
	}
	if find.CreatorID == nil {
		filter := fmt.Sprintf(`creator_id == %d || visibility in ["PUBLIC", "PROTECTED"]`, currentUser.ID)
		find.Filters = append(find.Filters, filter)
		return
	}
	if *find.CreatorID != currentUser.ID {
		find.VisibilityList = []store.Visibility{store.Public, store.Protected}
	}
}
