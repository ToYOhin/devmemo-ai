package sqlite

import (
	"context"
	"crypto/sha256"
	"database/sql"
	"encoding/json"
	"fmt"
	"regexp"
	"strings"
	"time"

	"github.com/google/uuid"
	"github.com/pkg/errors"

	"github.com/usememos/memos/internal/base"
	"github.com/usememos/memos/store"
)

var memoLifecycleErrorCodePattern = regexp.MustCompile(`^[a-z0-9_]{1,64}$`)
var memoLifecycleGenerationPattern = regexp.MustCompile(`^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$`)

type memoLifecycleSnapshot struct {
	UID       string
	Content   string
	RowStatus store.RowStatus
}

type memoLifecycleScanner interface {
	Scan(...any) error
}

var _ store.MemoLifecycleOutboxStore = (*DB)(nil)

func (d *DB) CreateMemoWithLifecycleEvent(
	ctx context.Context,
	create *store.Memo,
	request *store.MemoLifecycleEventRequest,
) (*store.Memo, *store.MemoLifecycleOutboxEvent, error) {
	if create == nil || !base.UIDMatcher.MatchString(create.UID) {
		return nil, nil, errors.New("invalid memo create")
	}
	if err := request.ValidateFor(store.MemoLifecycleEventIndex); err != nil {
		return nil, nil, err
	}
	if strings.TrimSpace(create.Content) == "" {
		return nil, nil, errors.New("indexed memo content must not be blank")
	}

	tx, err := d.db.BeginTx(ctx, nil)
	if err != nil {
		return nil, nil, errors.Wrap(err, "failed to begin memo lifecycle transaction")
	}
	defer func() { _ = tx.Rollback() }()

	created := *create
	if _, err := createMemo(ctx, tx, &created); err != nil {
		return nil, nil, errors.Wrap(err, "failed to create memo in lifecycle transaction")
	}
	event, err := enqueueMemoLifecycleEvent(
		ctx,
		tx,
		memoLifecycleSnapshot{UID: created.UID, Content: created.Content, RowStatus: created.RowStatus},
		store.MemoLifecycleEventIndex,
		request,
	)
	if err != nil {
		return nil, nil, errors.Wrap(err, "failed to enqueue memo index event")
	}
	if store.GetMemoLifecycleOutboxFailpoint(ctx) {
		return nil, nil, store.ErrMemoLifecycleOutboxFailpoint
	}
	if err := tx.Commit(); err != nil {
		return nil, nil, errors.Wrap(err, "failed to commit memo lifecycle transaction")
	}
	return &created, event, nil
}

func (d *DB) UpdateMemoWithLifecycleEvent(
	ctx context.Context,
	update *store.UpdateMemo,
	request *store.MemoLifecycleEventRequest,
) (*store.MemoLifecycleOutboxEvent, error) {
	if update == nil {
		return nil, errors.New("memo update is required")
	}
	tx, err := d.db.BeginTx(ctx, nil)
	if err != nil {
		return nil, errors.Wrap(err, "failed to begin memo lifecycle transaction")
	}
	defer func() { _ = tx.Rollback() }()

	if err := updateMemo(ctx, tx, update); err != nil {
		return nil, errors.Wrap(err, "failed to update memo in lifecycle transaction")
	}
	snapshot, err := getMemoLifecycleSnapshot(ctx, tx, update.ID)
	if err != nil {
		return nil, errors.Wrap(err, "failed to read updated memo lifecycle snapshot")
	}
	var isComment bool
	if err := tx.QueryRowContext(ctx, `
		SELECT EXISTS (
			SELECT 1 FROM memo_relation WHERE memo_id = ? AND type = 'COMMENT'
		)
	`, update.ID).Scan(&isComment); err != nil {
		return nil, errors.Wrap(err, "failed to read updated memo lifecycle relation")
	}
	eventType, err := classifyUpdatedMemoLifecycleEvent(snapshot, isComment, request)
	if err != nil {
		return nil, err
	}
	event, err := enqueueMemoLifecycleEvent(ctx, tx, snapshot, eventType, request)
	if err != nil {
		return nil, errors.Wrap(err, "failed to enqueue memo update event")
	}
	if store.GetMemoLifecycleOutboxFailpoint(ctx) {
		return nil, store.ErrMemoLifecycleOutboxFailpoint
	}
	if err := tx.Commit(); err != nil {
		return nil, errors.Wrap(err, "failed to commit memo lifecycle transaction")
	}
	return event, nil
}

func (d *DB) DeleteMemoWithLifecycleEvent(
	ctx context.Context,
	delete *store.DeleteMemo,
	request *store.MemoLifecycleEventRequest,
) (*store.MemoLifecycleOutboxEvent, error) {
	if delete == nil {
		return nil, errors.New("memo delete is required")
	}
	if err := request.ValidateFor(store.MemoLifecycleEventDelete); err != nil {
		return nil, err
	}
	if request.Reason != "deleted" {
		return nil, errors.New("physical memo delete requires deleted reason")
	}

	tx, err := d.db.BeginTx(ctx, nil)
	if err != nil {
		return nil, errors.Wrap(err, "failed to begin memo lifecycle transaction")
	}
	defer func() { _ = tx.Rollback() }()

	snapshot, err := getMemoLifecycleSnapshot(ctx, tx, delete.ID)
	if err != nil {
		return nil, errors.Wrap(err, "failed to read deleted memo lifecycle identity")
	}
	event, err := enqueueMemoLifecycleEvent(
		ctx, tx, snapshot, store.MemoLifecycleEventDelete, request,
	)
	if err != nil {
		return nil, errors.Wrap(err, "failed to enqueue memo delete tombstone")
	}
	if err := deleteMemo(ctx, tx, delete); err != nil {
		return nil, errors.Wrap(err, "failed to delete memo in lifecycle transaction")
	}
	if store.GetMemoLifecycleOutboxFailpoint(ctx) {
		return nil, store.ErrMemoLifecycleOutboxFailpoint
	}
	if err := tx.Commit(); err != nil {
		return nil, errors.Wrap(err, "failed to commit memo lifecycle transaction")
	}
	return event, nil
}

func enqueueMemoLifecycleEvent(
	ctx context.Context,
	tx *sql.Tx,
	snapshot memoLifecycleSnapshot,
	eventType store.MemoLifecycleEventType,
	request *store.MemoLifecycleEventRequest,
) (*store.MemoLifecycleOutboxEvent, error) {
	if err := request.ValidateFor(eventType); err != nil {
		return nil, err
	}

	var sourceSequence int64
	if err := tx.QueryRowContext(ctx, `
		SELECT COALESCE(MAX(source_sequence), 0) + 1
		FROM memo_index_outbox
		WHERE memo_uid = ? AND index_version = ?
	`, snapshot.UID, store.MemoIndexVersion).Scan(&sourceSequence); err != nil {
		return nil, errors.Wrap(err, "failed to allocate memo lifecycle source sequence")
	}

	operation := store.MemoLifecycleOperationUpsert
	var document, documentHash *string
	if eventType == store.MemoLifecycleEventDelete {
		operation = store.MemoLifecycleOperationDelete
	} else {
		if strings.TrimSpace(snapshot.Content) == "" {
			return nil, errors.New("memo lifecycle upsert document must not be blank")
		}
		hash := fmt.Sprintf("%x", sha256.Sum256([]byte(snapshot.Content)))
		document = &snapshot.Content
		documentHash = &hash
	}

	row := tx.QueryRowContext(ctx, `
		INSERT INTO memo_index_outbox (
			event_id,
			memo_uid,
			source_sequence,
			event_type,
			index_version,
			operation,
			reason,
			occurred_at,
			document,
			document_hash
		) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
		RETURNING
			id,
			event_id,
			memo_uid,
			source_sequence,
			event_type,
			index_version,
			operation,
			reason,
			occurred_at,
			document,
			document_hash,
			status,
			attempts,
			last_error_code,
			created_ts,
			updated_ts
	`,
		request.EventID,
		snapshot.UID,
		sourceSequence,
		eventType,
		store.MemoIndexVersion,
		operation,
		request.Reason,
		request.OccurredAt.Format(time.RFC3339Nano),
		document,
		documentHash,
	)
	return scanMemoLifecycleOutboxEvent(row)
}

func getMemoLifecycleSnapshot(
	ctx context.Context, tx *sql.Tx, memoID int32,
) (memoLifecycleSnapshot, error) {
	var snapshot memoLifecycleSnapshot
	if err := tx.QueryRowContext(ctx, `
		SELECT uid, content, row_status
		FROM memo
		WHERE id = ?
	`, memoID).Scan(&snapshot.UID, &snapshot.Content, &snapshot.RowStatus); err != nil {
		return memoLifecycleSnapshot{}, err
	}
	return snapshot, nil
}

func scanMemoLifecycleOutboxEvent(
	scanner memoLifecycleScanner,
) (*store.MemoLifecycleOutboxEvent, error) {
	var event store.MemoLifecycleOutboxEvent
	var occurredAt string
	var document, documentHash, lastErrorCode sql.NullString
	if err := scanner.Scan(
		&event.ID,
		&event.EventID,
		&event.MemoUID,
		&event.SourceSequence,
		&event.EventType,
		&event.IndexVersion,
		&event.Operation,
		&event.Reason,
		&occurredAt,
		&document,
		&documentHash,
		&event.Status,
		&event.Attempts,
		&lastErrorCode,
		&event.CreatedTs,
		&event.UpdatedTs,
	); err != nil {
		return nil, err
	}

	parsedOccurredAt, err := time.Parse(time.RFC3339Nano, occurredAt)
	if err != nil {
		return nil, errors.Wrap(err, "failed to parse memo lifecycle occurred_at")
	}
	event.OccurredAt = parsedOccurredAt
	event.Document = nullableStringPointer(document)
	event.DocumentHash = nullableStringPointer(documentHash)
	event.LastErrorCode = nullableStringPointer(lastErrorCode)
	return &event, nil
}

func nullableStringPointer(value sql.NullString) *string {
	if !value.Valid {
		return nil
	}
	return &value.String
}

func classifyUpdatedMemoLifecycleEvent(
	snapshot memoLifecycleSnapshot,
	isComment bool,
	request *store.MemoLifecycleEventRequest,
) (store.MemoLifecycleEventType, error) {
	if isComment {
		if err := request.ValidateFor(store.MemoLifecycleEventDelete); err != nil {
			return "", err
		}
		if request.Reason != "became_comment" {
			return "", errors.New("comment memo requires became_comment lifecycle reason")
		}
		return store.MemoLifecycleEventDelete, nil
	}
	if snapshot.RowStatus != store.Normal {
		if err := request.ValidateFor(store.MemoLifecycleEventDelete); err != nil {
			return "", err
		}
		if request.Reason != "archived" {
			return "", errors.New("archived memo requires archived lifecycle reason")
		}
		return store.MemoLifecycleEventDelete, nil
	}
	if strings.TrimSpace(snapshot.Content) == "" {
		if err := request.ValidateFor(store.MemoLifecycleEventDelete); err != nil {
			return "", err
		}
		if request.Reason != "blank_content" {
			return "", errors.New("blank memo requires blank_content lifecycle reason")
		}
		return store.MemoLifecycleEventDelete, nil
	}
	if err := request.ValidateFor(store.MemoLifecycleEventReindex); err != nil {
		return "", err
	}
	return store.MemoLifecycleEventReindex, nil
}

func (d *DB) ListMemoLifecycleOutboxEvents(
	ctx context.Context, memoUID string,
) ([]*store.MemoLifecycleOutboxEvent, error) {
	memoUID = strings.TrimSpace(memoUID)
	if memoUID == "" {
		return nil, errors.New("memo lifecycle memo_uid is required")
	}
	rows, err := d.db.QueryContext(ctx, `
		SELECT
			id,
			event_id,
			memo_uid,
			source_sequence,
			event_type,
			index_version,
			operation,
			reason,
			occurred_at,
			document,
			document_hash,
			status,
			attempts,
			last_error_code,
			created_ts,
			updated_ts
		FROM memo_index_outbox
		WHERE memo_uid = ?
		ORDER BY source_sequence ASC
	`, memoUID)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	events := []*store.MemoLifecycleOutboxEvent{}
	for rows.Next() {
		event, err := scanMemoLifecycleOutboxEvent(rows)
		if err != nil {
			return nil, err
		}
		events = append(events, event)
	}
	if err := rows.Err(); err != nil {
		return nil, err
	}
	return events, nil
}

func (d *DB) PrepareMemoLifecycleRebuild(
	ctx context.Context,
	generation string,
	occurredAt time.Time,
) (*store.MemoLifecycleRebuildManifest, error) {
	if !memoLifecycleGenerationPattern.MatchString(generation) || occurredAt.IsZero() {
		return nil, errors.New("memo lifecycle rebuild request is invalid")
	}
	tx, err := d.db.BeginTx(ctx, nil)
	if err != nil {
		return nil, errors.Wrap(err, "failed to begin memo lifecycle rebuild")
	}
	defer func() { _ = tx.Rollback() }()

	type rebuildEvent struct {
		snapshot  memoLifecycleSnapshot
		eventType store.MemoLifecycleEventType
		reason    string
	}
	events := []rebuildEvent{}
	manifestEntries := [][2]string{}
	rows, err := tx.QueryContext(ctx, `
		SELECT memo.uid, memo.content, memo.row_status
		FROM memo
		WHERE memo.row_status = 'NORMAL'
		  AND length(trim(memo.content)) > 0
		  AND NOT EXISTS (
			SELECT 1 FROM memo_relation
			WHERE memo_relation.memo_id = memo.id
			  AND memo_relation.type = 'COMMENT'
		  )
		ORDER BY memo.uid
	`)
	if err != nil {
		return nil, errors.Wrap(err, "failed to read memo lifecycle rebuild source")
	}
	for rows.Next() {
		var snapshot memoLifecycleSnapshot
		if err := rows.Scan(&snapshot.UID, &snapshot.Content, &snapshot.RowStatus); err != nil {
			_ = rows.Close()
			return nil, err
		}
		documentHash := fmt.Sprintf("%x", sha256.Sum256([]byte(snapshot.Content)))
		manifestEntries = append(manifestEntries, [2]string{snapshot.UID, documentHash})
		events = append(events, rebuildEvent{snapshot, store.MemoLifecycleEventReindex, "repair"})
	}
	if err := rows.Close(); err != nil {
		return nil, err
	}
	if err := rows.Err(); err != nil {
		return nil, err
	}

	deleteRows, err := tx.QueryContext(ctx, `
		SELECT source.memo_uid, COALESCE(memo.content, ''), COALESCE(memo.row_status, 'ARCHIVED'),
			CASE
				WHEN memo.id IS NULL THEN 'deleted'
				WHEN memo.row_status != 'NORMAL' THEN 'archived'
				WHEN length(trim(memo.content)) = 0 THEN 'blank_content'
				ELSE 'became_comment'
			END
		FROM (SELECT DISTINCT memo_uid FROM memo_index_outbox) AS source
		LEFT JOIN memo ON memo.uid = source.memo_uid
		WHERE memo.id IS NULL
		   OR memo.row_status != 'NORMAL'
		   OR length(trim(memo.content)) = 0
		   OR EXISTS (
			SELECT 1 FROM memo_relation
			WHERE memo_relation.memo_id = memo.id
			  AND memo_relation.type = 'COMMENT'
		   )
		ORDER BY source.memo_uid
	`)
	if err != nil {
		return nil, errors.Wrap(err, "failed to read memo lifecycle tombstones")
	}
	for deleteRows.Next() {
		var event rebuildEvent
		event.eventType = store.MemoLifecycleEventDelete
		if err := deleteRows.Scan(
			&event.snapshot.UID,
			&event.snapshot.Content,
			&event.snapshot.RowStatus,
			&event.reason,
		); err != nil {
			_ = deleteRows.Close()
			return nil, err
		}
		events = append(events, event)
	}
	if err := deleteRows.Close(); err != nil {
		return nil, err
	}
	if err := deleteRows.Err(); err != nil {
		return nil, err
	}

	for _, event := range events {
		_, err := enqueueMemoLifecycleEvent(
			ctx,
			tx,
			event.snapshot,
			event.eventType,
			&store.MemoLifecycleEventRequest{
				EventID:    "rebuild-" + uuid.NewString(),
				Reason:     event.reason,
				OccurredAt: occurredAt,
			},
		)
		if err != nil {
			return nil, errors.Wrap(err, "failed to enqueue memo lifecycle rebuild")
		}
	}
	manifestBody, err := json.Marshal(manifestEntries)
	if err != nil {
		return nil, errors.Wrap(err, "failed to encode memo lifecycle manifest")
	}
	if err := tx.Commit(); err != nil {
		return nil, errors.Wrap(err, "failed to commit memo lifecycle rebuild")
	}
	return &store.MemoLifecycleRebuildManifest{
		Generation:     generation,
		EligibleCount:  len(manifestEntries),
		ManifestDigest: fmt.Sprintf("%x", sha256.Sum256(manifestBody)),
	}, nil
}

func (d *DB) ListPendingMemoLifecycleOutboxEvents(
	ctx context.Context, limit int,
) ([]*store.MemoLifecycleOutboxEvent, error) {
	if limit < 1 || limit > 100 {
		return nil, errors.New("memo lifecycle pending limit is invalid")
	}
	rows, err := d.db.QueryContext(ctx, `
		SELECT id, event_id, memo_uid, source_sequence, event_type,
			index_version, operation, reason, occurred_at, document,
			document_hash, status, attempts, last_error_code, created_ts, updated_ts
		FROM memo_index_outbox
		WHERE status = 'PENDING'
		ORDER BY id
		LIMIT ?
	`, limit)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	events := []*store.MemoLifecycleOutboxEvent{}
	for rows.Next() {
		event, err := scanMemoLifecycleOutboxEvent(rows)
		if err != nil {
			return nil, err
		}
		events = append(events, event)
	}
	return events, rows.Err()
}

func (d *DB) AcknowledgeMemoLifecycleOutboxEvent(
	ctx context.Context, eventID string,
) (*store.MemoLifecycleOutboxEvent, error) {
	eventID = strings.TrimSpace(eventID)
	if eventID == "" || len(eventID) > 128 {
		return nil, errors.New("memo lifecycle event_id is invalid")
	}
	tx, err := d.db.BeginTx(ctx, nil)
	if err != nil {
		return nil, err
	}
	defer func() { _ = tx.Rollback() }()
	var memoUID string
	var sourceSequence int64
	if err := tx.QueryRowContext(ctx, `
		SELECT memo_uid, source_sequence FROM memo_index_outbox WHERE event_id = ?
	`, eventID).Scan(&memoUID, &sourceSequence); err != nil {
		return nil, err
	}
	if _, err := tx.ExecContext(ctx, `
		UPDATE memo_index_outbox
		SET status = 'ACKNOWLEDGED', last_error_code = NULL,
			updated_ts = strftime('%s', 'now')
		WHERE memo_uid = ? AND source_sequence <= ?
		  AND status IN ('PENDING', 'EXHAUSTED')
	`, memoUID, sourceSequence); err != nil {
		return nil, err
	}
	if err := tx.Commit(); err != nil {
		return nil, err
	}
	return d.getMemoLifecycleOutboxEvent(ctx, eventID)
}

func (d *DB) ReadMemoLifecycleBacklog(
	ctx context.Context,
) (*store.MemoLifecycleBacklog, error) {
	var backlog store.MemoLifecycleBacklog
	err := d.db.QueryRowContext(ctx, `
		SELECT
			COALESCE(SUM(CASE WHEN status = 'PENDING' THEN 1 ELSE 0 END), 0),
			COALESCE(SUM(CASE WHEN status = 'PENDING' AND attempts > 0 THEN 1 ELSE 0 END), 0),
			COALESCE(SUM(CASE WHEN status = 'EXHAUSTED' THEN 1 ELSE 0 END), 0)
		FROM memo_index_outbox
	`).Scan(&backlog.Pending, &backlog.Failed, &backlog.Exhausted)
	if err != nil {
		return nil, err
	}
	return &backlog, nil
}

func (d *DB) RecordMemoLifecycleDeliveryFailure(
	ctx context.Context,
	eventID string,
	errorCode string,
) (*store.MemoLifecycleOutboxEvent, error) {
	eventID = strings.TrimSpace(eventID)
	if eventID == "" || len(eventID) > 128 {
		return nil, errors.New("memo lifecycle event_id is invalid")
	}
	if !memoLifecycleErrorCodePattern.MatchString(errorCode) {
		return nil, errors.New("memo lifecycle error code is invalid")
	}

	row := d.db.QueryRowContext(ctx, `
		UPDATE memo_index_outbox
		SET
			attempts = attempts + 1,
			status = CASE
				WHEN attempts + 1 >= ? THEN 'EXHAUSTED'
				ELSE 'PENDING'
			END,
			last_error_code = ?,
			updated_ts = strftime('%s', 'now')
		WHERE event_id = ? AND status = 'PENDING' AND attempts < ?
		RETURNING
			id,
			event_id,
			memo_uid,
			source_sequence,
			event_type,
			index_version,
			operation,
			reason,
			occurred_at,
			document,
			document_hash,
			status,
			attempts,
			last_error_code,
			created_ts,
			updated_ts
	`,
		store.MaxMemoLifecycleDeliveryAttempts,
		errorCode,
		eventID,
		store.MaxMemoLifecycleDeliveryAttempts,
	)
	event, err := scanMemoLifecycleOutboxEvent(row)
	if err == nil {
		return event, nil
	}
	if !errors.Is(err, sql.ErrNoRows) {
		return nil, err
	}

	event, err = d.getMemoLifecycleOutboxEvent(ctx, eventID)
	if err != nil {
		return nil, err
	}
	if event.Status == store.MemoLifecycleOutboxExhausted {
		return event, store.ErrMemoLifecycleDeliveryExhausted
	}
	return event, errors.New("memo lifecycle event is not pending")
}

func (d *DB) getMemoLifecycleOutboxEvent(
	ctx context.Context, eventID string,
) (*store.MemoLifecycleOutboxEvent, error) {
	row := d.db.QueryRowContext(ctx, `
		SELECT
			id,
			event_id,
			memo_uid,
			source_sequence,
			event_type,
			index_version,
			operation,
			reason,
			occurred_at,
			document,
			document_hash,
			status,
			attempts,
			last_error_code,
			created_ts,
			updated_ts
		FROM memo_index_outbox
		WHERE event_id = ?
	`, eventID)
	return scanMemoLifecycleOutboxEvent(row)
}
