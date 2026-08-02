package v1

import (
	"context"
	"crypto/sha256"
	"database/sql"
	"errors"
	"fmt"
	"strconv"
	"strings"

	"github.com/usememos/memos/internal/aiagent"
	"github.com/usememos/memos/internal/base"
	"github.com/usememos/memos/server/auth"
	"github.com/usememos/memos/store"
	storesqlite "github.com/usememos/memos/store/db/sqlite"
)

const maxSQLiteEvidenceAuthorityUIDs = 10

var errSQLiteEvidenceAuthorityUnavailable = errors.New("authorized retrieval unavailable")

// sqliteEvidenceCurrentAuthorityReader is a dormant, single-host adapter for
// the R5-I6 protocol. It is deliberately not registered with an HTTP route or
// runtime factory. The future handler remains responsible for supplying the
// already-issued opaque authority token; this reader does not issue one.
type sqliteEvidenceCurrentAuthorityReader struct {
	ctx                 context.Context
	db                  *sql.DB
	callerID            int32
	visibilityScope     memoReadVisibilityScope
	capturedBinding     aiagent.EvidenceAuthorityContextBinding
	authorityToken      string
	testAfterCallerRead func() error
}

// newSQLiteEvidenceCurrentAuthorityReader derives caller identity only from
// the Memos authentication context. Request JSON, query parameters, derived
// metadata, and the opaque R5 binding cannot provide or override caller ID.
func newSQLiteEvidenceCurrentAuthorityReader(
	ctx context.Context,
	service *APIV1Service,
	binding aiagent.EvidenceAuthorityContextBinding,
	authorityToken string,
) (*sqliteEvidenceCurrentAuthorityReader, error) {
	if ctx == nil || service == nil || service.Store == nil {
		return nil, errSQLiteEvidenceAuthorityUnavailable
	}
	callerID := auth.GetUserID(ctx)
	if callerID == 0 {
		return nil, errSQLiteEvidenceAuthorityUnavailable
	}
	driver, ok := service.Store.GetDriver().(*storesqlite.DB)
	if !ok || driver.GetDB() == nil {
		return nil, errSQLiteEvidenceAuthorityUnavailable
	}
	currentUser := &store.User{ID: callerID}
	return &sqliteEvidenceCurrentAuthorityReader{
		ctx:             ctx,
		db:              driver.GetDB(),
		callerID:        callerID,
		visibilityScope: newMemoReadVisibilityScope(currentUser),
		capturedBinding: binding,
		authorityToken:  authorityToken,
	}, nil
}

func (reader *sqliteEvidenceCurrentAuthorityReader) ReadCurrentAuthority(
	request aiagent.EvidenceRehydrationRequest,
	binding aiagent.EvidenceAuthorityContextBinding,
) (aiagent.EvidenceCurrentAuthoritySnapshot, error) {
	if reader == nil || reader.db == nil || reader.ctx == nil ||
		binding != reader.capturedBinding || request.MemosAuthorityRef != binding.MemosAuthorityRef ||
		auth.GetUserID(reader.ctx) != reader.callerID {
		return aiagent.EvidenceCurrentAuthoritySnapshot{}, errSQLiteEvidenceAuthorityUnavailable
	}
	uids, ok := exactEvidenceAuthorityUIDs(request)
	if !ok {
		return aiagent.EvidenceCurrentAuthoritySnapshot{}, errSQLiteEvidenceAuthorityUnavailable
	}

	connection, err := reader.db.Conn(reader.ctx)
	if err != nil {
		return aiagent.EvidenceCurrentAuthoritySnapshot{}, errSQLiteEvidenceAuthorityUnavailable
	}
	defer connection.Close()

	dataVersionBefore, err := readSQLiteDataVersion(reader.ctx, connection)
	if err != nil {
		return aiagent.EvidenceCurrentAuthoritySnapshot{}, errSQLiteEvidenceAuthorityUnavailable
	}
	tx, err := connection.BeginTx(reader.ctx, &sql.TxOptions{ReadOnly: true})
	if err != nil {
		return aiagent.EvidenceCurrentAuthoritySnapshot{}, errSQLiteEvidenceAuthorityUnavailable
	}
	committed := false
	defer func() {
		if !committed {
			_ = tx.Rollback()
		}
	}()

	if !reader.currentAuthenticatedCallerExists(tx) {
		return aiagent.EvidenceCurrentAuthoritySnapshot{}, errSQLiteEvidenceAuthorityUnavailable
	}
	if reader.testAfterCallerRead != nil {
		if err := reader.testAfterCallerRead(); err != nil {
			return aiagent.EvidenceCurrentAuthoritySnapshot{}, errSQLiteEvidenceAuthorityUnavailable
		}
	}

	documents, err := reader.readCurrentDocuments(tx, uids, dataVersionBefore)
	if err != nil {
		return aiagent.EvidenceCurrentAuthoritySnapshot{}, errSQLiteEvidenceAuthorityUnavailable
	}
	if err := tx.Commit(); err != nil {
		return aiagent.EvidenceCurrentAuthoritySnapshot{}, errSQLiteEvidenceAuthorityUnavailable
	}
	committed = true

	dataVersionAfter, err := readSQLiteDataVersion(reader.ctx, connection)
	if err != nil || dataVersionAfter != dataVersionBefore {
		return aiagent.EvidenceCurrentAuthoritySnapshot{}, errSQLiteEvidenceAuthorityUnavailable
	}

	snapshotRevision := opaqueSQLiteSnapshotRevision(dataVersionBefore, reader.callerID, uids)
	for index := range documents {
		documents[index].SnapshotRevision = snapshotRevision
		documents[index].AuthorityToken = reader.authorityToken
	}
	return aiagent.EvidenceCurrentAuthoritySnapshot{
		MemosAuthorityRef:         binding.MemosAuthorityRef,
		AuthenticatedContextToken: binding.AuthenticatedContextToken,
		SnapshotRevision:          snapshotRevision,
		AuthorityToken:            reader.authorityToken,
		Documents:                 documents,
	}, nil
}

func exactEvidenceAuthorityUIDs(request aiagent.EvidenceRehydrationRequest) ([]string, bool) {
	if len(request.Selections) < 1 || len(request.Selections) > maxSQLiteEvidenceAuthorityUIDs {
		return nil, false
	}
	uids := make([]string, 0, len(request.Selections))
	seen := make(map[string]struct{}, len(request.Selections))
	for _, selection := range request.Selections {
		if !base.UIDMatcher.MatchString(selection.MemoUID) {
			return nil, false
		}
		if _, duplicate := seen[selection.MemoUID]; duplicate {
			return nil, false
		}
		seen[selection.MemoUID] = struct{}{}
		uids = append(uids, selection.MemoUID)
	}
	return uids, true
}

func (reader *sqliteEvidenceCurrentAuthorityReader) currentAuthenticatedCallerExists(tx *sql.Tx) bool {
	var exists bool
	err := tx.QueryRowContext(reader.ctx, `
		SELECT EXISTS(
			SELECT 1
			FROM user
			WHERE id = ? AND row_status = ?
		)
	`, reader.callerID, store.Normal).Scan(&exists)
	return err == nil && exists
}

func (reader *sqliteEvidenceCurrentAuthorityReader) readCurrentDocuments(
	tx *sql.Tx,
	uids []string,
	dataVersion int64,
) ([]aiagent.EvidenceCurrentAuthorityDocument, error) {
	if reader.visibilityScope.currentUserID == nil ||
		len(reader.visibilityScope.nonOwnerVisibilities) != 2 {
		return nil, errSQLiteEvidenceAuthorityUnavailable
	}

	requestedValues := make([]string, 0, len(uids))
	args := make([]any, 0, len(uids)*2+7)
	for index, uid := range uids {
		requestedValues = append(requestedValues, "(?, ?)")
		args = append(args, uid, index)
	}
	args = append(
		args,
		store.Normal,
		store.MemoRelationComment,
		*reader.visibilityScope.currentUserID,
		reader.visibilityScope.nonOwnerVisibilities[0],
		reader.visibilityScope.nonOwnerVisibilities[1],
		store.MemoLifecycleOperationUpsert,
		store.MemoIndexVersion,
	)

	query := `
		WITH requested(uid, ordinal) AS (VALUES ` + strings.Join(requestedValues, ", ") + `),
		latest_event AS (
			SELECT outbox.*
			FROM memo_index_outbox AS outbox
			JOIN requested ON requested.uid = outbox.memo_uid
			JOIN (
				SELECT scoped.memo_uid, MAX(scoped.id) AS latest_id
				FROM memo_index_outbox AS scoped
				JOIN requested AS requested_latest ON requested_latest.uid = scoped.memo_uid
				GROUP BY scoped.memo_uid
			) AS latest ON latest.latest_id = outbox.id
		)
		SELECT
			requested.uid,
			memo.content,
			latest_event.source_sequence,
			latest_event.document_hash,
			latest_event.index_version
		FROM requested
		JOIN memo ON memo.uid = requested.uid
		JOIN latest_event ON latest_event.memo_uid = memo.uid
		WHERE memo.row_status = ?
			AND length(trim(memo.content)) > 0
			AND NOT EXISTS (
				SELECT 1
				FROM memo_relation
				WHERE memo_relation.memo_id = memo.id AND memo_relation.type = ?
			)
			AND (memo.creator_id = ? OR memo.visibility IN (?, ?))
			AND latest_event.operation = ?
			AND latest_event.index_version = ?
			AND latest_event.document = memo.content
		ORDER BY requested.ordinal ASC
	`
	rows, err := tx.QueryContext(reader.ctx, query, args...)
	if err != nil {
		return nil, errSQLiteEvidenceAuthorityUnavailable
	}
	defer rows.Close()

	snapshotRevision := opaqueSQLiteSnapshotRevision(dataVersion, reader.callerID, uids)
	documents := make([]aiagent.EvidenceCurrentAuthorityDocument, 0, len(uids))
	seen := make(map[string]struct{}, len(uids))
	for rows.Next() {
		var document aiagent.EvidenceCurrentAuthorityDocument
		if err := rows.Scan(
			&document.MemoUID,
			&document.Document,
			&document.SourceSequence,
			&document.DocumentHash,
			&document.IndexVersion,
		); err != nil {
			return nil, errSQLiteEvidenceAuthorityUnavailable
		}
		if _, duplicate := seen[document.MemoUID]; duplicate {
			return nil, errSQLiteEvidenceAuthorityUnavailable
		}
		seen[document.MemoUID] = struct{}{}
		document.Visibility = aiagent.EvidenceAuthorityVisibilityCurrent
		document.MemoType = aiagent.EvidenceAuthorityMemoTypeComplete
		document.RowState = aiagent.EvidenceAuthorityRowStateNormal
		document.LifecycleState = aiagent.EvidenceAuthorityLifecycleCurrent
		document.SnapshotRevision = snapshotRevision
		document.AuthorityToken = reader.authorityToken
		documents = append(documents, document)
	}
	if err := rows.Err(); err != nil || len(documents) != len(uids) {
		return nil, errSQLiteEvidenceAuthorityUnavailable
	}
	for _, uid := range uids {
		if _, found := seen[uid]; !found {
			return nil, errSQLiteEvidenceAuthorityUnavailable
		}
	}
	return documents, nil
}

type sqliteDataVersionReader interface {
	QueryRowContext(context.Context, string, ...any) *sql.Row
}

func readSQLiteDataVersion(ctx context.Context, reader sqliteDataVersionReader) (int64, error) {
	var version int64
	if err := reader.QueryRowContext(ctx, "PRAGMA data_version").Scan(&version); err != nil || version < 1 {
		return 0, errSQLiteEvidenceAuthorityUnavailable
	}
	return version, nil
}

func opaqueSQLiteSnapshotRevision(dataVersion int64, callerID int32, uids []string) string {
	digest := sha256.Sum256([]byte(
		"r5-i7-sqlite-snapshot\x00" + strconv.FormatInt(dataVersion, 10) + "\x00" +
			strconv.FormatInt(int64(callerID), 10) + "\x00" + strings.Join(uids, "\x00"),
	))
	return fmt.Sprintf("snapshot-%x", digest[:20])
}
