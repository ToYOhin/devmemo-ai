package store

import (
	"context"
	"errors"
	"strings"
	"time"
)

const (
	MemoIndexVersion                    = "memo-v1"
	MaxMemoLifecycleDeliveryAttempts    = 3
	MemoLifecycleErrorCodeMaximumLength = 64
)

type MemoLifecycleEventType string

const (
	MemoLifecycleEventIndex   MemoLifecycleEventType = "memo.index.requested.v1"
	MemoLifecycleEventReindex MemoLifecycleEventType = "memo.reindex.requested.v1"
	MemoLifecycleEventDelete  MemoLifecycleEventType = "memo.delete.requested.v1"
)

type MemoLifecycleOperation string

const (
	MemoLifecycleOperationUpsert MemoLifecycleOperation = "upsert"
	MemoLifecycleOperationDelete MemoLifecycleOperation = "delete"
)

type MemoLifecycleOutboxStatus string

const (
	MemoLifecycleOutboxPending      MemoLifecycleOutboxStatus = "PENDING"
	MemoLifecycleOutboxAcknowledged MemoLifecycleOutboxStatus = "ACKNOWLEDGED"
	MemoLifecycleOutboxExhausted    MemoLifecycleOutboxStatus = "EXHAUSTED"
)

var (
	ErrMemoLifecycleDeliveryExhausted = errors.New("memo lifecycle delivery attempts exhausted")
	ErrMemoLifecycleOutboxFailpoint   = errors.New("memo lifecycle outbox failpoint before commit")
)

// MemoLifecycleEventRequest contains only Memos-owned event metadata.
// The adapter derives memo UID, source sequence, event type, operation, and document.
type MemoLifecycleEventRequest struct {
	EventID    string
	Reason     string
	OccurredAt time.Time
}

func (request *MemoLifecycleEventRequest) ValidateFor(eventType MemoLifecycleEventType) error {
	if request == nil {
		return errors.New("memo lifecycle event request is required")
	}
	request.EventID = strings.TrimSpace(request.EventID)
	if request.EventID == "" || len(request.EventID) > 128 {
		return errors.New("memo lifecycle event_id is invalid")
	}
	if request.OccurredAt.IsZero() {
		return errors.New("memo lifecycle occurred_at is required")
	}
	if !memoLifecycleReasonAllowed(eventType, request.Reason) {
		return errors.New("memo lifecycle reason is invalid for event type")
	}
	return nil
}

type MemoLifecycleOutboxEvent struct {
	ID             int64
	EventID        string
	MemoUID        string
	SourceSequence int64
	EventType      MemoLifecycleEventType
	IndexVersion   string
	Operation      MemoLifecycleOperation
	Reason         string
	OccurredAt     time.Time
	Document       *string
	DocumentHash   *string
	Status         MemoLifecycleOutboxStatus
	Attempts       int
	LastErrorCode  *string
	CreatedTs      int64
	UpdatedTs      int64
}

type MemoLifecycleRebuildManifest struct {
	Generation     string
	EligibleCount  int
	ManifestDigest string
}

type MemoLifecycleBacklog struct {
	Pending   int
	Failed    int
	Exhausted int
}

// MemoLifecycleOutboxStore is an explicit adapter boundary, not part of Driver.
// No existing Memo CRUD path calls these methods in A4-I2.
type MemoLifecycleOutboxStore interface {
	CreateMemoWithLifecycleEvent(context.Context, *Memo, *MemoLifecycleEventRequest) (*Memo, *MemoLifecycleOutboxEvent, error)
	UpdateMemoWithLifecycleEvent(context.Context, *UpdateMemo, *MemoLifecycleEventRequest) (*MemoLifecycleOutboxEvent, error)
	DeleteMemoWithLifecycleEvent(context.Context, *DeleteMemo, *MemoLifecycleEventRequest) (*MemoLifecycleOutboxEvent, error)
	ListMemoLifecycleOutboxEvents(context.Context, string) ([]*MemoLifecycleOutboxEvent, error)
	PrepareMemoLifecycleRebuild(context.Context, string, time.Time) (*MemoLifecycleRebuildManifest, error)
	ListPendingMemoLifecycleOutboxEvents(context.Context, int) ([]*MemoLifecycleOutboxEvent, error)
	AcknowledgeMemoLifecycleOutboxEvent(context.Context, string) (*MemoLifecycleOutboxEvent, error)
	ReadMemoLifecycleBacklog(context.Context) (*MemoLifecycleBacklog, error)
	RecordMemoLifecycleDeliveryFailure(context.Context, string, string) (*MemoLifecycleOutboxEvent, error)
}

type memoLifecycleOutboxFailpointKey struct{}

// WithMemoLifecycleOutboxFailpoint forces an atomic mutation to fail before commit.
func WithMemoLifecycleOutboxFailpoint(ctx context.Context) context.Context {
	return context.WithValue(ctx, memoLifecycleOutboxFailpointKey{}, true)
}

func GetMemoLifecycleOutboxFailpoint(ctx context.Context) bool {
	failpoint, ok := ctx.Value(memoLifecycleOutboxFailpointKey{}).(bool)
	return ok && failpoint
}

func memoLifecycleReasonAllowed(eventType MemoLifecycleEventType, reason string) bool {
	switch eventType {
	case MemoLifecycleEventIndex:
		return reason == "created"
	case MemoLifecycleEventReindex:
		return reason == "content_changed" || reason == "indexed_metadata_changed" ||
			reason == "restored" || reason == "repair"
	case MemoLifecycleEventDelete:
		return reason == "deleted" || reason == "archived" ||
			reason == "became_comment" || reason == "blank_content"
	default:
		return false
	}
}
