package v1

import (
	"context"
	"crypto/sha256"
	"encoding/json"
	"fmt"
	"path/filepath"
	"testing"
	"time"

	"github.com/stretchr/testify/require"

	"github.com/usememos/memos/internal/aiagent"
	"github.com/usememos/memos/internal/profile"
	"github.com/usememos/memos/server/auth"
	"github.com/usememos/memos/store"
	storesqlite "github.com/usememos/memos/store/db/sqlite"
)

var r5I7OccurredAt = time.Date(2026, 8, 2, 11, 0, 0, 0, time.FixedZone("UTC+8", 8*60*60))

type r5I7Harness struct {
	ctx       context.Context
	store     *store.Store
	driver    *storesqlite.DB
	lifecycle store.MemoLifecycleOutboxStore
	service   *APIV1Service
	caller    *store.User
	other     *store.User
	binding   aiagent.EvidenceAuthorityContextBinding
}

type r5I7Memo struct {
	memo      *store.Memo
	selection aiagent.EvidenceRehydrationSelection
}

func newR5I7Harness(t *testing.T) *r5I7Harness {
	t.Helper()
	ctx := context.Background()
	dataDir := t.TempDir()
	testProfile := &profile.Profile{
		Data:   dataDir,
		DSN:    filepath.Join(dataDir, "memos.db"),
		Driver: "sqlite",
	}
	driverValue, err := storesqlite.NewDB(testProfile)
	require.NoError(t, err)
	driver, ok := driverValue.(*storesqlite.DB)
	require.True(t, ok)
	testStore := store.New(driverValue, testProfile)
	t.Cleanup(func() { _ = testStore.Close() })
	require.NoError(t, testStore.Migrate(ctx))
	lifecycle, ok := driverValue.(store.MemoLifecycleOutboxStore)
	require.True(t, ok)
	caller := createR5I7User(ctx, t, testStore, "r5-i7-caller")
	other := createR5I7User(ctx, t, testStore, "r5-i7-other")
	return &r5I7Harness{
		ctx:       context.WithValue(ctx, auth.UserIDContextKey, caller.ID),
		store:     testStore,
		driver:    driver,
		lifecycle: lifecycle,
		service:   &APIV1Service{Store: testStore, Profile: testProfile},
		caller:    caller,
		other:     other,
		binding: aiagent.EvidenceAuthorityContextBinding{
			MemosAuthorityRef:         "authority-ref-r5-i7",
			AuthenticatedContextToken: "authenticated-context-r5-i7",
		},
	}
}

func createR5I7User(ctx context.Context, t *testing.T, testStore *store.Store, username string) *store.User {
	t.Helper()
	user, err := testStore.CreateUser(ctx, &store.User{
		Username: username,
		Role:     store.RoleUser,
		Email:    username + "@example.test",
	})
	require.NoError(t, err)
	return user
}

func (h *r5I7Harness) createMemo(
	t *testing.T,
	uid string,
	creatorID int32,
	visibility store.Visibility,
	content string,
) r5I7Memo {
	t.Helper()
	memo, event, err := h.lifecycle.CreateMemoWithLifecycleEvent(
		h.ctx,
		&store.Memo{
			UID:        uid,
			CreatorID:  creatorID,
			Content:    content,
			Visibility: visibility,
		},
		r5I7LifecycleRequest{uid: uid}.request("created"),
	)
	require.NoError(t, err)
	require.NotNil(t, event.DocumentHash)
	return r5I7Memo{
		memo: memo,
		selection: aiagent.EvidenceRehydrationSelection{
			SelectionRef:   "rehydration-1",
			MemoUID:        uid,
			SourceSequence: event.SourceSequence,
			DocumentHash:   *event.DocumentHash,
			IndexVersion:   store.MemoIndexVersion,
		},
	}
}

type r5I7LifecycleRequest struct {
	uid string
}

func (value r5I7LifecycleRequest) request(reason string) *store.MemoLifecycleEventRequest {
	return &store.MemoLifecycleEventRequest{
		EventID:    fmt.Sprintf("event-%s-%s", value.uid, reason),
		Reason:     reason,
		OccurredAt: r5I7OccurredAt,
	}
}

func (h *r5I7Harness) request(selections ...aiagent.EvidenceRehydrationSelection) aiagent.EvidenceRehydrationRequest {
	for index := range selections {
		selections[index].SelectionRef = fmt.Sprintf("rehydration-%d", index+1)
	}
	return aiagent.EvidenceRehydrationRequest{
		Version:           "memo-evidence-rehydration-v1",
		SnapshotToken:     "snapshot-r5-i7",
		MemosAuthorityRef: h.binding.MemosAuthorityRef,
		Selections:        selections,
	}
}

func (h *r5I7Harness) reader(t *testing.T) *sqliteEvidenceCurrentAuthorityReader {
	t.Helper()
	reader, err := newSQLiteEvidenceCurrentAuthorityReader(
		h.ctx,
		h.service,
		h.binding,
		"authority-token-r5-i7",
	)
	require.NoError(t, err)
	return reader
}

func assertR5I7Unavailable(t *testing.T, response aiagent.EvidenceRehydrationResponse, err error) {
	t.Helper()
	require.Equal(t, aiagent.EvidenceRehydrationResponse{}, response)
	require.Empty(t, response.Documents)
	require.EqualError(t, err, "authorized retrieval unavailable")
}

func TestSQLiteEvidenceAuthorityReaderMatchesMemosVisibilityAndRequestOrder(t *testing.T) {
	h := newR5I7Harness(t)
	callerPrivate := h.createMemo(t, "r5-i7-caller-private", h.caller.ID, store.Private, "owned private body")
	otherPublic := h.createMemo(t, "r5-i7-other-public", h.other.ID, store.Public, "other public body")
	otherProtected := h.createMemo(t, "r5-i7-other-protected", h.other.ID, store.Protected, "other protected body")
	h.createMemo(t, "r5-i7-other-private", h.other.ID, store.Private, "forbidden private body marker")

	visibleUIDs, err := h.service.resolveAgentVisibleMemoUIDs(h.ctx)
	require.NoError(t, err)
	require.ElementsMatch(t, []string{
		callerPrivate.memo.UID,
		otherPublic.memo.UID,
		otherProtected.memo.UID,
	}, visibleUIDs)

	request := h.request(otherProtected.selection, callerPrivate.selection, otherPublic.selection)
	response, err := aiagent.BuildEvidenceRehydrationResponse(request, h.binding, h.reader(t))
	require.NoError(t, err)
	require.Equal(t, "authority-token-r5-i7", response.AuthorityToken)
	require.Equal(t, []string{
		"other protected body",
		"owned private body",
		"other public body",
	}, []string{
		response.Documents[0].Document,
		response.Documents[1].Document,
		response.Documents[2].Document,
	})

	body, err := json.Marshal(response)
	require.NoError(t, err)
	for _, forbidden := range []string{
		"forbidden private body marker", "memo_uid", "caller", "owner", "visibility",
		"memos_authority_ref", "authenticated-context", "snapshot-revision", "citation", "store",
	} {
		require.NotContains(t, string(body), forbidden)
	}
}

func TestSQLiteEvidenceAuthorityReaderRejectsUnauthorizedMemoWithoutPartialBody(t *testing.T) {
	h := newR5I7Harness(t)
	allowed := h.createMemo(t, "r5-i7-visible", h.caller.ID, store.Private, "allowed body")
	forbidden := h.createMemo(t, "r5-i7-hidden", h.other.ID, store.Private, "secret hidden body")

	response, err := aiagent.BuildEvidenceRehydrationResponse(
		h.request(allowed.selection, forbidden.selection),
		h.binding,
		h.reader(t),
	)
	assertR5I7Unavailable(t, response, err)
	require.NotContains(t, err.Error(), "allowed body")
	require.NotContains(t, err.Error(), "secret hidden body")
}

func TestSQLiteEvidenceAuthorityReaderRejectsIneligibleCurrentStoreState(t *testing.T) {
	tests := []struct {
		name   string
		mutate func(*testing.T, *r5I7Harness, r5I7Memo)
	}{
		{
			name: "caller archived",
			mutate: func(t *testing.T, h *r5I7Harness, _ r5I7Memo) {
				archived := store.Archived
				_, err := h.store.UpdateUser(h.ctx, &store.UpdateUser{ID: h.caller.ID, RowStatus: &archived})
				require.NoError(t, err)
			},
		},
		{
			name: "visibility lost",
			mutate: func(t *testing.T, h *r5I7Harness, memo r5I7Memo) {
				private := store.Private
				require.NoError(t, h.store.UpdateMemo(h.ctx, &store.UpdateMemo{ID: memo.memo.ID, Visibility: &private}))
			},
		},
		{
			name: "comment",
			mutate: func(t *testing.T, h *r5I7Harness, memo r5I7Memo) {
				parent := h.createMemo(t, "r5-i7-parent", h.other.ID, store.Public, "parent body")
				_, err := h.store.UpsertMemoRelation(h.ctx, &store.MemoRelation{
					MemoID: memo.memo.ID, RelatedMemoID: parent.memo.ID, Type: store.MemoRelationComment,
				})
				require.NoError(t, err)
			},
		},
		{
			name: "archived memo",
			mutate: func(t *testing.T, h *r5I7Harness, memo r5I7Memo) {
				archived := store.Archived
				require.NoError(t, h.store.UpdateMemo(h.ctx, &store.UpdateMemo{ID: memo.memo.ID, RowStatus: &archived}))
			},
		},
		{
			name: "blank memo",
			mutate: func(t *testing.T, h *r5I7Harness, memo r5I7Memo) {
				blank := "   "
				require.NoError(t, h.store.UpdateMemo(h.ctx, &store.UpdateMemo{ID: memo.memo.ID, Content: &blank}))
			},
		},
		{
			name: "missing source state",
			mutate: func(t *testing.T, h *r5I7Harness, memo r5I7Memo) {
				_, err := h.driver.GetDB().ExecContext(h.ctx, "DELETE FROM memo_index_outbox WHERE memo_uid = ?", memo.memo.UID)
				require.NoError(t, err)
			},
		},
		{
			name: "latest tombstone",
			mutate: func(t *testing.T, h *r5I7Harness, memo r5I7Memo) {
				_, err := h.driver.GetDB().ExecContext(h.ctx, `
					INSERT INTO memo_index_outbox (
						event_id, memo_uid, source_sequence, event_type, index_version,
						operation, reason, occurred_at, document, document_hash
					) VALUES (?, ?, 2, ?, ?, ?, 'deleted', ?, NULL, NULL)
				`, "event-r5-i7-tombstone", memo.memo.UID, store.MemoLifecycleEventDelete,
					store.MemoIndexVersion, store.MemoLifecycleOperationDelete, r5I7OccurredAt.Format(time.RFC3339Nano))
				require.NoError(t, err)
			},
		},
	}

	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			h := newR5I7Harness(t)
			creatorID := h.caller.ID
			visibility := store.Private
			if test.name == "visibility lost" || test.name == "comment" {
				creatorID = h.other.ID
				visibility = store.Public
			}
			memo := h.createMemo(t, "r5-i7-state", creatorID, visibility, "current body")
			test.mutate(t, h, memo)

			response, err := aiagent.BuildEvidenceRehydrationResponse(
				h.request(memo.selection), h.binding, h.reader(t),
			)
			assertR5I7Unavailable(t, response, err)
		})
	}
}

func TestSQLiteEvidenceAuthorityReaderRejectsSourceSequenceHashAndVersionMismatch(t *testing.T) {
	tests := []struct {
		name   string
		mutate func(*testing.T, *r5I7Harness, *r5I7Memo)
	}{
		{
			name: "request sequence stale",
			mutate: func(_ *testing.T, _ *r5I7Harness, memo *r5I7Memo) {
				memo.selection.SourceSequence++
			},
		},
		{
			name: "request hash stale",
			mutate: func(_ *testing.T, _ *r5I7Harness, memo *r5I7Memo) {
				memo.selection.DocumentHash = fmt.Sprintf("%064d", 0)
			},
		},
		{
			name: "source hash inconsistent",
			mutate: func(t *testing.T, h *r5I7Harness, memo *r5I7Memo) {
				_, err := h.driver.GetDB().ExecContext(h.ctx,
					"UPDATE memo_index_outbox SET document_hash = ? WHERE memo_uid = ?",
					fmt.Sprintf("%064d", 0), memo.memo.UID)
				require.NoError(t, err)
			},
		},
		{
			name: "source version unknown",
			mutate: func(t *testing.T, h *r5I7Harness, memo *r5I7Memo) {
				connection, err := h.driver.GetDB().Conn(h.ctx)
				require.NoError(t, err)
				defer connection.Close()
				_, err = connection.ExecContext(h.ctx, "PRAGMA ignore_check_constraints = ON")
				require.NoError(t, err)
				_, err = connection.ExecContext(h.ctx,
					"UPDATE memo_index_outbox SET index_version = 'memo-chunk-v1' WHERE memo_uid = ?",
					memo.memo.UID)
				require.NoError(t, err)
				_, err = connection.ExecContext(h.ctx, "PRAGMA ignore_check_constraints = OFF")
				require.NoError(t, err)
			},
		},
	}

	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			h := newR5I7Harness(t)
			memo := h.createMemo(t, "r5-i7-source", h.caller.ID, store.Private, "source body")
			test.mutate(t, h, &memo)

			response, err := aiagent.BuildEvidenceRehydrationResponse(
				h.request(memo.selection), h.binding, h.reader(t),
			)
			assertR5I7Unavailable(t, response, err)
		})
	}
}

func TestSQLiteEvidenceAuthorityReaderRejectsWritesDuringSnapshot(t *testing.T) {
	tests := []struct {
		name   string
		mutate func(*testing.T, *r5I7Harness, r5I7Memo)
	}{
		{
			name: "content update",
			mutate: func(t *testing.T, h *r5I7Harness, memo r5I7Memo) {
				updated := "updated during read"
				_, err := h.lifecycle.UpdateMemoWithLifecycleEvent(
					h.ctx,
					&store.UpdateMemo{ID: memo.memo.ID, Content: &updated},
					r5I7LifecycleRequest{uid: memo.memo.UID}.request("content_changed"),
				)
				require.NoError(t, err)
			},
		},
		{
			name: "delete",
			mutate: func(t *testing.T, h *r5I7Harness, memo r5I7Memo) {
				_, err := h.lifecycle.DeleteMemoWithLifecycleEvent(
					h.ctx,
					&store.DeleteMemo{ID: memo.memo.ID},
					r5I7LifecycleRequest{uid: memo.memo.UID}.request("deleted"),
				)
				require.NoError(t, err)
			},
		},
		{
			name: "visibility change",
			mutate: func(t *testing.T, h *r5I7Harness, memo r5I7Memo) {
				private := store.Private
				require.NoError(t, h.store.UpdateMemo(h.ctx, &store.UpdateMemo{ID: memo.memo.ID, Visibility: &private}))
			},
		},
	}

	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			h := newR5I7Harness(t)
			creatorID := h.caller.ID
			visibility := store.Private
			if test.name == "visibility change" {
				creatorID = h.other.ID
				visibility = store.Public
			}
			memo := h.createMemo(t, "r5-i7-race", creatorID, visibility, "before race")
			reader := h.reader(t)
			reader.testAfterCallerRead = func() error {
				test.mutate(t, h, memo)
				return nil
			}

			response, err := aiagent.BuildEvidenceRehydrationResponse(
				h.request(memo.selection), h.binding, reader,
			)
			assertR5I7Unavailable(t, response, err)
		})
	}
}

func TestSQLiteEvidenceAuthorityReaderRequiresExactUIDSet(t *testing.T) {
	h := newR5I7Harness(t)
	requested := h.createMemo(t, "r5-i7-requested", h.caller.ID, store.Private, "requested body")
	h.createMemo(t, "r5-i7-extra", h.other.ID, store.Public, "extra body")

	unknown := requested.selection
	unknown.MemoUID = "r5-i7-unknown"
	response, err := aiagent.BuildEvidenceRehydrationResponse(
		h.request(requested.selection, unknown), h.binding, h.reader(t),
	)
	assertR5I7Unavailable(t, response, err)

	duplicate := requested.selection
	duplicate.SelectionRef = "rehydration-2"
	response, err = aiagent.BuildEvidenceRehydrationResponse(
		h.request(requested.selection, duplicate), h.binding, h.reader(t),
	)
	assertR5I7Unavailable(t, response, err)

	reader := h.reader(t)
	directRequest := h.request(requested.selection, duplicate)
	_, err = reader.ReadCurrentAuthority(directRequest, h.binding)
	require.EqualError(t, err, "authorized retrieval unavailable")

	malformed := requested.selection
	malformed.MemoUID = "malformed_uid"
	_, err = reader.ReadCurrentAuthority(h.request(malformed), h.binding)
	require.EqualError(t, err, "authorized retrieval unavailable")

	overLimit := make([]aiagent.EvidenceRehydrationSelection, 11)
	for index := range overLimit {
		overLimit[index] = requested.selection
		overLimit[index].MemoUID = fmt.Sprintf("r5-i7-limit-%d", index+1)
	}
	_, err = reader.ReadCurrentAuthority(h.request(overLimit...), h.binding)
	require.EqualError(t, err, "authorized retrieval unavailable")
}

func TestSQLiteEvidenceAuthorityReaderMapsFactorySchemaAndTransactionFailures(t *testing.T) {
	h := newR5I7Harness(t)
	memo := h.createMemo(t, "r5-i7-failure", h.caller.ID, store.Private, "failure body")
	request := h.request(memo.selection)

	_, err := newSQLiteEvidenceCurrentAuthorityReader(context.Background(), h.service, h.binding, "authority-token-r5-i7")
	require.EqualError(t, err, "authorized retrieval unavailable")
	_, err = newSQLiteEvidenceCurrentAuthorityReader(h.ctx, nil, h.binding, "authority-token-r5-i7")
	require.EqualError(t, err, "authorized retrieval unavailable")

	t.Run("schema", func(t *testing.T) {
		h := newR5I7Harness(t)
		memo := h.createMemo(t, "r5-i7-schema", h.caller.ID, store.Private, "schema body")
		reader := h.reader(t)
		_, err := h.driver.GetDB().ExecContext(h.ctx, "DROP TABLE memo_index_outbox")
		require.NoError(t, err)
		response, err := aiagent.BuildEvidenceRehydrationResponse(h.request(memo.selection), h.binding, reader)
		assertR5I7Unavailable(t, response, err)
	})

	t.Run("transaction context", func(t *testing.T) {
		canceled, cancel := context.WithCancel(h.ctx)
		reader, err := newSQLiteEvidenceCurrentAuthorityReader(canceled, h.service, h.binding, "authority-token-r5-i7")
		require.NoError(t, err)
		cancel()
		response, err := aiagent.BuildEvidenceRehydrationResponse(request, h.binding, reader)
		assertR5I7Unavailable(t, response, err)
	})

	t.Run("closed database", func(t *testing.T) {
		h := newR5I7Harness(t)
		memo := h.createMemo(t, "r5-i7-closed", h.caller.ID, store.Private, "closed body")
		reader := h.reader(t)
		require.NoError(t, h.store.Close())
		response, err := aiagent.BuildEvidenceRehydrationResponse(h.request(memo.selection), h.binding, reader)
		assertR5I7Unavailable(t, response, err)
	})

	t.Run("binding", func(t *testing.T) {
		changed := h.binding
		changed.AuthenticatedContextToken = "authenticated-context-other"
		response, err := aiagent.BuildEvidenceRehydrationResponse(request, changed, h.reader(t))
		assertR5I7Unavailable(t, response, err)
	})
}

func TestSQLiteEvidenceAuthorityReaderDoesNotTrustOutboxDocumentHashAlone(t *testing.T) {
	h := newR5I7Harness(t)
	memo := h.createMemo(t, "r5-i7-document", h.caller.ID, store.Private, "current memo authority")
	stale := "stale derived body"
	staleHash := fmt.Sprintf("%x", sha256.Sum256([]byte(stale)))
	_, err := h.driver.GetDB().ExecContext(h.ctx, `
		UPDATE memo_index_outbox
		SET document = ?, document_hash = ?
		WHERE memo_uid = ?
	`, stale, staleHash, memo.memo.UID)
	require.NoError(t, err)

	response, err := aiagent.BuildEvidenceRehydrationResponse(
		h.request(memo.selection), h.binding, h.reader(t),
	)
	assertR5I7Unavailable(t, response, err)
	require.NotContains(t, err.Error(), stale)
}
