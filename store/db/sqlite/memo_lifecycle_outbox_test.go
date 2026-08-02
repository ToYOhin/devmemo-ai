package sqlite_test

import (
	"context"
	"crypto/sha256"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"testing"
	"time"

	"github.com/stretchr/testify/require"

	"github.com/usememos/memos/internal/profile"
	"github.com/usememos/memos/store"
	storesqlite "github.com/usememos/memos/store/db/sqlite"
)

var lifecycleOccurredAt = time.Date(2026, 8, 1, 10, 0, 0, 0, time.FixedZone("UTC+8", 8*60*60))

type memoLifecycleTestStore struct {
	store   *store.Store
	adapter store.MemoLifecycleOutboxStore
}

type memoLifecycleFixtureEvent struct {
	EventID        string `json:"event_id"`
	EventType      string `json:"event_type"`
	MemoUID        string `json:"memo_uid"`
	SourceSequence int64  `json:"source_sequence"`
	IndexVersion   string `json:"index_version"`
	Operation      string `json:"operation"`
	Reason         string `json:"reason"`
	OccurredAt     string `json:"occurred_at"`
	Document       string `json:"document"`
	DocumentHash   string `json:"document_hash"`
}

func newMemoLifecycleTestStore(t *testing.T) *memoLifecycleTestStore {
	t.Helper()
	ctx := context.Background()
	dataDir := t.TempDir()
	testProfile := &profile.Profile{
		Data:   dataDir,
		DSN:    filepath.Join(dataDir, "memos.db"),
		Driver: "sqlite",
	}
	driver, err := storesqlite.NewDB(testProfile)
	require.NoError(t, err)

	stores := store.New(driver, testProfile)
	t.Cleanup(func() { require.NoError(t, stores.Close()) })
	require.NoError(t, stores.Migrate(ctx))
	adapter, ok := driver.(store.MemoLifecycleOutboxStore)
	require.True(t, ok, "SQLite must expose only the explicit lifecycle outbox adapter")
	return &memoLifecycleTestStore{store: stores, adapter: adapter}
}

func lifecycleRequest(eventID, reason string) *store.MemoLifecycleEventRequest {
	return &store.MemoLifecycleEventRequest{
		EventID:    eventID,
		Reason:     reason,
		OccurredAt: lifecycleOccurredAt,
	}
}

func createLifecycleMemo(
	t *testing.T,
	ctx context.Context,
	testStore *memoLifecycleTestStore,
	uid string,
	eventID string,
) *store.Memo {
	t.Helper()
	memo, _, err := testStore.adapter.CreateMemoWithLifecycleEvent(
		ctx,
		&store.Memo{UID: uid, CreatorID: 1, Content: "initial", Visibility: store.Private},
		lifecycleRequest(eventID, "created"),
	)
	require.NoError(t, err)
	return memo
}

func findMemo(t *testing.T, ctx context.Context, stores *store.Store, uid string) *store.Memo {
	t.Helper()
	memo, err := stores.GetMemo(ctx, &store.FindMemo{UID: &uid})
	require.NoError(t, err)
	return memo
}

func TestMemoLifecycleOutboxCommitsSourceMutationsAndSequencedEventsTogether(t *testing.T) {
	ctx := context.Background()
	testStore := newMemoLifecycleTestStore(t)

	created, indexed, err := testStore.adapter.CreateMemoWithLifecycleEvent(
		ctx,
		&store.Memo{
			UID:        "a4-i2-commit",
			CreatorID:  1,
			Content:    "initial",
			Visibility: store.Private,
		},
		lifecycleRequest("event-commit-1", "created"),
	)
	require.NoError(t, err)
	require.Equal(t, int64(1), indexed.SourceSequence)
	require.Equal(t, store.MemoLifecycleEventIndex, indexed.EventType)
	require.Equal(t, store.MemoLifecycleOperationUpsert, indexed.Operation)
	require.Equal(t, "initial", *indexed.Document)
	require.Equal(t, fmt.Sprintf("%x", sha256.Sum256([]byte("initial"))), *indexed.DocumentHash)

	updatedContent := "updated"
	reindexed, err := testStore.adapter.UpdateMemoWithLifecycleEvent(
		ctx,
		&store.UpdateMemo{ID: created.ID, Content: &updatedContent},
		lifecycleRequest("event-commit-2", "content_changed"),
	)
	require.NoError(t, err)
	require.Equal(t, int64(2), reindexed.SourceSequence)
	require.Equal(t, store.MemoLifecycleEventReindex, reindexed.EventType)
	require.Equal(t, updatedContent, findMemo(t, ctx, testStore.store, created.UID).Content)

	archivedStatus := store.Archived
	archived, err := testStore.adapter.UpdateMemoWithLifecycleEvent(
		ctx,
		&store.UpdateMemo{ID: created.ID, RowStatus: &archivedStatus},
		lifecycleRequest("event-commit-3", "archived"),
	)
	require.NoError(t, err)
	require.Equal(t, int64(3), archived.SourceSequence)
	require.Equal(t, store.MemoLifecycleEventDelete, archived.EventType)
	require.Nil(t, archived.Document)
	require.Nil(t, archived.DocumentHash)
	require.Equal(t, store.Archived, findMemo(t, ctx, testStore.store, created.UID).RowStatus)

	deleted, err := testStore.adapter.DeleteMemoWithLifecycleEvent(
		ctx,
		&store.DeleteMemo{ID: created.ID},
		lifecycleRequest("event-commit-4", "deleted"),
	)
	require.NoError(t, err)
	require.Equal(t, int64(4), deleted.SourceSequence)
	require.Equal(t, store.MemoLifecycleEventDelete, deleted.EventType)
	require.Nil(t, deleted.Document)
	require.Nil(t, deleted.DocumentHash)
	require.Nil(t, findMemo(t, ctx, testStore.store, created.UID))

	events, err := testStore.adapter.ListMemoLifecycleOutboxEvents(ctx, created.UID)
	require.NoError(t, err)
	require.Len(t, events, 4)
	require.Equal(t, []int64{1, 2, 3, 4}, []int64{
		events[0].SourceSequence,
		events[1].SourceSequence,
		events[2].SourceSequence,
		events[3].SourceSequence,
	})
}

func TestMemoLifecycleOutboxMatchesSharedIndexEventFixture(t *testing.T) {
	fixtureBytes, err := os.ReadFile(filepath.Join(
		"..", "..", "..", "contracts", "memo-lifecycle-v1.json",
	))
	require.NoError(t, err)
	var fixture struct {
		Events []memoLifecycleFixtureEvent `json:"events"`
	}
	require.NoError(t, json.Unmarshal(fixtureBytes, &fixture))
	require.NotEmpty(t, fixture.Events)
	expected := fixture.Events[0]
	occurredAt, err := time.Parse(time.RFC3339, expected.OccurredAt)
	require.NoError(t, err)

	ctx := context.Background()
	testStore := newMemoLifecycleTestStore(t)
	_, event, err := testStore.adapter.CreateMemoWithLifecycleEvent(
		ctx,
		&store.Memo{
			UID:        expected.MemoUID,
			CreatorID:  1,
			Content:    expected.Document,
			Visibility: store.Private,
		},
		&store.MemoLifecycleEventRequest{
			EventID:    expected.EventID,
			Reason:     expected.Reason,
			OccurredAt: occurredAt,
		},
	)
	require.NoError(t, err)
	require.Equal(t, expected.EventType, string(event.EventType))
	require.Equal(t, expected.SourceSequence, event.SourceSequence)
	require.Equal(t, expected.IndexVersion, event.IndexVersion)
	require.Equal(t, expected.Operation, string(event.Operation))
	require.Equal(t, expected.DocumentHash, *event.DocumentHash)
}

func TestMemoLifecycleOutboxIncrementalMigrationUsesTemporarySQLite(t *testing.T) {
	ctx := context.Background()
	dataDir := t.TempDir()
	testProfile := &profile.Profile{
		Data:   dataDir,
		DSN:    filepath.Join(dataDir, "pre-a4.db"),
		Driver: "sqlite",
	}
	driver, err := storesqlite.NewDB(testProfile)
	require.NoError(t, err)
	stores := store.New(driver, testProfile)
	t.Cleanup(func() { require.NoError(t, stores.Close()) })

	_, err = driver.GetDB().ExecContext(ctx, `
		CREATE TABLE memo (id INTEGER PRIMARY KEY);
		CREATE TABLE system_setting (
			name TEXT NOT NULL,
			value TEXT NOT NULL,
			description TEXT NOT NULL DEFAULT '',
			UNIQUE(name)
		);
		INSERT INTO system_setting (name, value, description)
		VALUES ('BASIC', '{"schemaVersion":"0.28.1"}', '');
	`)
	require.NoError(t, err)

	require.NoError(t, stores.Migrate(ctx))
	var exists bool
	require.NoError(t, driver.GetDB().QueryRowContext(ctx, `
		SELECT EXISTS(
			SELECT 1 FROM sqlite_master
			WHERE type = 'table' AND name = 'memo_index_outbox'
		)
	`).Scan(&exists))
	require.True(t, exists)
	schemaVersion, err := stores.GetCurrentSchemaVersion()
	require.NoError(t, err)
	require.Equal(t, "0.29.1", schemaVersion)
}

func TestMemoLifecycleOutboxRollsBackSourceAndEventBeforeCommit(t *testing.T) {
	ctx := context.Background()
	testStore := newMemoLifecycleTestStore(t)
	failingCtx := store.WithMemoLifecycleOutboxFailpoint(ctx)

	_, _, err := testStore.adapter.CreateMemoWithLifecycleEvent(
		failingCtx,
		&store.Memo{
			UID:        "a4-i2-create-rollback",
			CreatorID:  1,
			Content:    "not committed",
			Visibility: store.Private,
		},
		lifecycleRequest("event-create-rollback", "created"),
	)
	require.ErrorIs(t, err, store.ErrMemoLifecycleOutboxFailpoint)
	require.Nil(t, findMemo(t, ctx, testStore.store, "a4-i2-create-rollback"))
	events, err := testStore.adapter.ListMemoLifecycleOutboxEvents(ctx, "a4-i2-create-rollback")
	require.NoError(t, err)
	require.Empty(t, events)

	updatedMemo := createLifecycleMemo(
		t, ctx, testStore, "a4-i2-update-rollback", "event-update-base",
	)
	updatedContent := "not committed"
	_, err = testStore.adapter.UpdateMemoWithLifecycleEvent(
		failingCtx,
		&store.UpdateMemo{ID: updatedMemo.ID, Content: &updatedContent},
		lifecycleRequest("event-update-rollback", "content_changed"),
	)
	require.ErrorIs(t, err, store.ErrMemoLifecycleOutboxFailpoint)
	require.Equal(t, "initial", findMemo(t, ctx, testStore.store, updatedMemo.UID).Content)
	events, err = testStore.adapter.ListMemoLifecycleOutboxEvents(ctx, updatedMemo.UID)
	require.NoError(t, err)
	require.Len(t, events, 1)

	deletedMemo := createLifecycleMemo(
		t, ctx, testStore, "a4-i2-delete-rollback", "event-delete-base",
	)
	_, err = testStore.adapter.DeleteMemoWithLifecycleEvent(
		failingCtx,
		&store.DeleteMemo{ID: deletedMemo.ID},
		lifecycleRequest("event-delete-rollback", "deleted"),
	)
	require.ErrorIs(t, err, store.ErrMemoLifecycleOutboxFailpoint)
	require.NotNil(t, findMemo(t, ctx, testStore.store, deletedMemo.UID))
	events, err = testStore.adapter.ListMemoLifecycleOutboxEvents(ctx, deletedMemo.UID)
	require.NoError(t, err)
	require.Len(t, events, 1)
}

func TestMemoLifecycleOutboxConstraintFailureRollsBackSourceUpdate(t *testing.T) {
	ctx := context.Background()
	testStore := newMemoLifecycleTestStore(t)
	memo := createLifecycleMemo(t, ctx, testStore, "a4-i2-constraint", "event-reused")

	updatedContent := "must roll back"
	_, err := testStore.adapter.UpdateMemoWithLifecycleEvent(
		ctx,
		&store.UpdateMemo{ID: memo.ID, Content: &updatedContent},
		lifecycleRequest("event-reused", "content_changed"),
	)
	require.Error(t, err)
	require.Equal(t, "initial", findMemo(t, ctx, testStore.store, memo.UID).Content)
	events, listErr := testStore.adapter.ListMemoLifecycleOutboxEvents(ctx, memo.UID)
	require.NoError(t, listErr)
	require.Len(t, events, 1)
}

func TestMemoLifecycleOutboxRefusesDeleteWithoutValidTombstone(t *testing.T) {
	ctx := context.Background()
	testStore := newMemoLifecycleTestStore(t)
	memo := createLifecycleMemo(t, ctx, testStore, "a4-i2-tombstone", "event-tombstone-base")

	_, err := testStore.adapter.DeleteMemoWithLifecycleEvent(
		ctx,
		&store.DeleteMemo{ID: memo.ID},
		nil,
	)
	require.Error(t, err)
	require.NotNil(t, findMemo(t, ctx, testStore.store, memo.UID))
	events, listErr := testStore.adapter.ListMemoLifecycleOutboxEvents(ctx, memo.UID)
	require.NoError(t, listErr)
	require.Len(t, events, 1)
}

func TestMemoLifecycleOutboxBoundsExplicitDeliveryFailures(t *testing.T) {
	ctx := context.Background()
	testStore := newMemoLifecycleTestStore(t)
	memo := createLifecycleMemo(t, ctx, testStore, "a4-i2-retry", "event-retry")

	for attempt := 1; attempt <= store.MaxMemoLifecycleDeliveryAttempts; attempt++ {
		event, err := testStore.adapter.RecordMemoLifecycleDeliveryFailure(
			ctx, "event-retry", "transport_unavailable",
		)
		require.NoError(t, err)
		require.Equal(t, attempt, event.Attempts)
		require.Equal(t, "transport_unavailable", *event.LastErrorCode)
		if attempt < store.MaxMemoLifecycleDeliveryAttempts {
			require.Equal(t, store.MemoLifecycleOutboxPending, event.Status)
		} else {
			require.Equal(t, store.MemoLifecycleOutboxExhausted, event.Status)
		}
	}

	event, err := testStore.adapter.RecordMemoLifecycleDeliveryFailure(
		ctx, "event-retry", "transport_unavailable",
	)
	require.ErrorIs(t, err, store.ErrMemoLifecycleDeliveryExhausted)
	require.Equal(t, store.MaxMemoLifecycleDeliveryAttempts, event.Attempts)

	_, err = testStore.adapter.RecordMemoLifecycleDeliveryFailure(
		ctx, "event-retry", "raw error: memo content",
	)
	require.Error(t, err)
	events, listErr := testStore.adapter.ListMemoLifecycleOutboxEvents(ctx, memo.UID)
	require.NoError(t, listErr)
	require.Len(t, events, 1)
	require.Equal(t, store.MaxMemoLifecycleDeliveryAttempts, events[0].Attempts)
}

func TestMemoLifecycleRebuildPreparesOnlyEligibleCompleteMemos(t *testing.T) {
	ctx := context.Background()
	testStore := newMemoLifecycleTestStore(t)
	parent, err := testStore.store.CreateMemo(ctx, &store.Memo{
		UID: "r5-rebuild-parent", CreatorID: 1, Content: "parent document", Visibility: store.Private,
	})
	require.NoError(t, err)
	comment, err := testStore.store.CreateMemo(ctx, &store.Memo{
		UID: "r5-rebuild-comment", CreatorID: 1, Content: "comment document", Visibility: store.Private,
	})
	require.NoError(t, err)
	_, err = testStore.store.UpsertMemoRelation(ctx, &store.MemoRelation{
		MemoID: comment.ID, RelatedMemoID: parent.ID, Type: store.MemoRelationComment,
	})
	require.NoError(t, err)
	_, err = testStore.store.CreateMemo(ctx, &store.Memo{
		UID: "r5-rebuild-blank", CreatorID: 1, Content: "   ", Visibility: store.Private,
	})
	require.NoError(t, err)

	manifest, err := testStore.adapter.PrepareMemoLifecycleRebuild(
		ctx, "generation-r5", lifecycleOccurredAt,
	)
	require.NoError(t, err)
	pending, err := testStore.adapter.ListPendingMemoLifecycleOutboxEvents(ctx, 100)
	require.NoError(t, err)

	documentHash := fmt.Sprintf("%x", sha256.Sum256([]byte("parent document")))
	manifestBody, err := json.Marshal([][2]string{{"r5-rebuild-parent", documentHash}})
	require.NoError(t, err)
	require.Equal(t, "generation-r5", manifest.Generation)
	require.Equal(t, 1, manifest.EligibleCount)
	require.Equal(
		t, fmt.Sprintf("%x", sha256.Sum256(manifestBody)), manifest.ManifestDigest,
	)
	require.Len(t, pending, 1)
	require.Equal(t, "r5-rebuild-parent", pending[0].MemoUID)
	require.Equal(t, store.MemoLifecycleEventReindex, pending[0].EventType)
	require.Equal(t, "repair", pending[0].Reason)
}

func TestMemoLifecycleRebuildSupersedesKnownDeletedMemoWithTombstone(t *testing.T) {
	ctx := context.Background()
	testStore := newMemoLifecycleTestStore(t)
	memo := createLifecycleMemo(
		t, ctx, testStore, "r5-rebuild-deleted", "event-before-delete",
	)
	require.NoError(t, testStore.store.DeleteMemo(ctx, &store.DeleteMemo{ID: memo.ID}))

	manifest, err := testStore.adapter.PrepareMemoLifecycleRebuild(
		ctx, "generation-r5", lifecycleOccurredAt,
	)
	require.NoError(t, err)
	pending, err := testStore.adapter.ListPendingMemoLifecycleOutboxEvents(ctx, 100)
	require.NoError(t, err)

	require.Zero(t, manifest.EligibleCount)
	require.Len(t, pending, 2)
	require.Equal(t, int64(2), pending[1].SourceSequence)
	require.Equal(t, store.MemoLifecycleOperationDelete, pending[1].Operation)
	require.Equal(t, "deleted", pending[1].Reason)
}

func TestMemoLifecycleAcknowledgementSupersedesOlderExhaustedEvent(t *testing.T) {
	ctx := context.Background()
	testStore := newMemoLifecycleTestStore(t)
	createLifecycleMemo(t, ctx, testStore, "r5-rebuild-repair", "event-exhausted")
	for range store.MaxMemoLifecycleDeliveryAttempts {
		_, err := testStore.adapter.RecordMemoLifecycleDeliveryFailure(
			ctx, "event-exhausted", "transport_unavailable",
		)
		require.NoError(t, err)
	}
	_, err := testStore.adapter.PrepareMemoLifecycleRebuild(
		ctx, "generation-r5", lifecycleOccurredAt,
	)
	require.NoError(t, err)
	pending, err := testStore.adapter.ListPendingMemoLifecycleOutboxEvents(ctx, 100)
	require.NoError(t, err)
	require.Len(t, pending, 1)

	acknowledged, err := testStore.adapter.AcknowledgeMemoLifecycleOutboxEvent(
		ctx, pending[0].EventID,
	)
	require.NoError(t, err)
	backlog, err := testStore.adapter.ReadMemoLifecycleBacklog(ctx)
	require.NoError(t, err)
	events, err := testStore.adapter.ListMemoLifecycleOutboxEvents(
		ctx, "r5-rebuild-repair",
	)
	require.NoError(t, err)

	require.Equal(t, store.MemoLifecycleOutboxAcknowledged, acknowledged.Status)
	require.Equal(t, &store.MemoLifecycleBacklog{}, backlog)
	require.Len(t, events, 2)
	require.Equal(t, store.MemoLifecycleOutboxAcknowledged, events[0].Status)
	require.Equal(t, store.MemoLifecycleOutboxAcknowledged, events[1].Status)
}
