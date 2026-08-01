package aiagent

import (
	"bytes"
	"crypto/hmac"
	"crypto/sha256"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"regexp"
	"strconv"
	"strings"
	"time"
)

const (
	// InternalLifecyclePath is reserved for Memos-owned memo-v1 lifecycle events.
	InternalLifecyclePath = "/internal/ai/memo-lifecycle/events"

	LifecycleSignatureHeader = "X-DevMemo-Lifecycle-Signature"
	LifecycleTimestampHeader = "X-DevMemo-Lifecycle-Timestamp"
	LifecycleNonceHeader     = "X-DevMemo-Lifecycle-Nonce"

	lifecycleSignaturePrefix  = "sha256="
	lifecycleSignaturePurpose = "devmemo-memo-lifecycle-transport-v1"
	maxLifecycleRequestBytes  = 204096
	maxLifecycleAckBytes      = 2048
)

var lifecycleNoncePattern = regexp.MustCompile(`^[A-Za-z0-9_-]{16,128}$`)
var lifecycleErrorCodePattern = regexp.MustCompile(`^[a-z0-9_]{1,64}$`)

// LifecycleSignedHeaders bind one event body to the lifecycle-only purpose.
type LifecycleSignedHeaders struct {
	Signature string
	Timestamp string
	Nonce     string
}

// LifecycleAcknowledgement is the content-free response projection accepted by Memos.
type LifecycleAcknowledgement struct {
	EventID        string  `json:"event_id"`
	MemoUID        string  `json:"memo_uid"`
	SourceSequence int64   `json:"source_sequence"`
	IndexVersion   string  `json:"index_version"`
	Status         string  `json:"status"`
	Operation      string  `json:"operation"`
	ErrorCode      *string `json:"error_code,omitempty"`
}

// SignLifecycleRequest signs one raw event body without dispatching it.
func SignLifecycleRequest(body []byte, at time.Time, nonce, secret string) (LifecycleSignedHeaders, error) {
	if strings.TrimSpace(secret) == "" {
		return LifecycleSignedHeaders{}, errors.New("lifecycle signing secret must not be empty")
	}
	if !lifecycleNoncePattern.MatchString(nonce) {
		return LifecycleSignedHeaders{}, errors.New("lifecycle nonce is invalid")
	}
	if len(body) == 0 || len(body) > maxLifecycleRequestBytes {
		return LifecycleSignedHeaders{}, errors.New("lifecycle request body is invalid")
	}

	timestamp := strconv.FormatInt(at.UTC().Unix(), 10)
	mac := hmac.New(sha256.New, []byte(secret))
	_, _ = mac.Write(canonicalLifecycleRequest("POST", InternalLifecyclePath, timestamp, nonce, body))
	return LifecycleSignedHeaders{
		Signature: lifecycleSignaturePrefix + fmt.Sprintf("%x", mac.Sum(nil)),
		Timestamp: timestamp,
		Nonce:     nonce,
	}, nil
}

// ParseLifecycleAcknowledgement rejects any response outside the A4-I1 projection.
func ParseLifecycleAcknowledgement(body []byte) (LifecycleAcknowledgement, error) {
	if len(body) == 0 || len(body) > maxLifecycleAckBytes {
		return LifecycleAcknowledgement{}, errors.New("invalid lifecycle acknowledgement")
	}
	fields, err := decodeLifecycleObject(body)
	if err != nil {
		return LifecycleAcknowledgement{}, errors.New("invalid lifecycle acknowledgement")
	}
	required := []string{
		"event_id",
		"memo_uid",
		"source_sequence",
		"index_version",
		"status",
		"operation",
	}
	for _, field := range required {
		if _, ok := fields[field]; !ok {
			return LifecycleAcknowledgement{}, errors.New("invalid lifecycle acknowledgement")
		}
	}
	for field := range fields {
		if field != "error_code" && !containsLifecycleField(required, field) {
			return LifecycleAcknowledgement{}, errors.New("invalid lifecycle acknowledgement")
		}
	}

	var acknowledgement LifecycleAcknowledgement
	if err := json.Unmarshal(body, &acknowledgement); err != nil {
		return LifecycleAcknowledgement{}, errors.New("invalid lifecycle acknowledgement")
	}
	if err := acknowledgement.validate(); err != nil {
		return LifecycleAcknowledgement{}, errors.New("invalid lifecycle acknowledgement")
	}
	return acknowledgement, nil
}

func canonicalLifecycleRequest(method, path, timestamp, nonce string, body []byte) []byte {
	bodyDigest := sha256.Sum256(body)
	return []byte(strings.Join([]string{
		lifecycleSignaturePurpose,
		strings.ToUpper(strings.TrimSpace(method)),
		path,
		timestamp,
		nonce,
		fmt.Sprintf("%x", bodyDigest),
	}, "\n"))
}

func (a LifecycleAcknowledgement) validate() error {
	if strings.TrimSpace(a.EventID) == "" || len(a.EventID) > 128 {
		return errors.New("invalid event ID")
	}
	if strings.TrimSpace(a.MemoUID) == "" || len(a.MemoUID) > 128 {
		return errors.New("invalid Memo UID")
	}
	if a.SourceSequence < 1 || a.IndexVersion != "memo-v1" {
		return errors.New("invalid lifecycle target")
	}
	if a.Status != "applied" && a.Status != "duplicate" && a.Status != "stale" && a.Status != "failed" {
		return errors.New("invalid lifecycle status")
	}
	if a.Operation != "upsert" && a.Operation != "delete" {
		return errors.New("invalid lifecycle operation")
	}
	if a.Status == "failed" {
		if a.ErrorCode == nil || !lifecycleErrorCodePattern.MatchString(*a.ErrorCode) {
			return errors.New("invalid lifecycle error code")
		}
	} else if a.ErrorCode != nil {
		return errors.New("unexpected lifecycle error code")
	}
	return nil
}

func decodeLifecycleObject(body []byte) (map[string]json.RawMessage, error) {
	decoder := json.NewDecoder(bytes.NewReader(body))
	opening, err := decoder.Token()
	if err != nil || opening != json.Delim('{') {
		return nil, errors.New("invalid JSON object")
	}
	fields := map[string]json.RawMessage{}
	for decoder.More() {
		keyToken, err := decoder.Token()
		if err != nil {
			return nil, err
		}
		key, ok := keyToken.(string)
		if !ok {
			return nil, errors.New("invalid JSON field")
		}
		if _, duplicate := fields[key]; duplicate {
			return nil, errors.New("duplicate JSON field")
		}
		var value json.RawMessage
		if err := decoder.Decode(&value); err != nil {
			return nil, err
		}
		fields[key] = value
	}
	closing, err := decoder.Token()
	if err != nil || closing != json.Delim('}') {
		return nil, errors.New("invalid JSON object")
	}
	if _, err := decoder.Token(); !errors.Is(err, io.EOF) {
		return nil, errors.New("unexpected JSON data")
	}
	return fields, nil
}

func containsLifecycleField(fields []string, candidate string) bool {
	for _, field := range fields {
		if field == candidate {
			return true
		}
	}
	return false
}
