package aiagent

import (
	"encoding/json"
	"os"
	"path/filepath"
	"strconv"
	"testing"
	"time"

	"github.com/stretchr/testify/require"
)

func TestLifecycleTransportMatchesCrossLanguageFixture(t *testing.T) {
	fixtureBytes, err := os.ReadFile(filepath.Join("..", "..", "contracts", "memo-lifecycle-transport-v1.json"))
	require.NoError(t, err)
	var fixture struct {
		Method    string `json:"method"`
		Path      string `json:"path"`
		Timestamp string `json:"timestamp"`
		Nonce     string `json:"nonce"`
		Secret    string `json:"secret"`
		RawBody   string `json:"raw_body"`
		Signature string `json:"signature"`
	}
	require.NoError(t, json.Unmarshal(fixtureBytes, &fixture))
	require.Equal(t, "POST", fixture.Method)
	require.Equal(t, InternalLifecyclePath, fixture.Path)

	seconds, err := strconv.ParseInt(fixture.Timestamp, 10, 64)
	require.NoError(t, err)
	headers, err := SignLifecycleRequest(
		[]byte(fixture.RawBody),
		time.Unix(seconds, 0),
		fixture.Nonce,
		fixture.Secret,
	)
	require.NoError(t, err)
	require.Equal(t, fixture.Signature, headers.Signature)
	require.Equal(t, fixture.Timestamp, headers.Timestamp)
	require.Equal(t, fixture.Nonce, headers.Nonce)
}

func TestLifecycleSignatureIsSeparatedFromAnswerDelegation(t *testing.T) {
	body := []byte(`{"event_id":"synthetic"}`)
	at := time.Date(2026, time.August, 1, 12, 0, 0, 0, time.UTC)
	lifecycleHeaders, err := SignLifecycleRequest(body, at, "lifecycle-nonce-0001", "test-secret")
	require.NoError(t, err)
	answerHeaders, err := SignRequest("POST", InternalAnswerPath, body, at, "test-secret")
	require.NoError(t, err)

	require.NotEqual(t, answerHeaders.Signature, lifecycleHeaders.Signature)
	require.NotEqual(t, SignatureHeader, LifecycleSignatureHeader)
	require.NotEqual(t, TimestampHeader, LifecycleTimestampHeader)
}

func TestLifecycleSignerRejectsInvalidInputs(t *testing.T) {
	_, err := SignLifecycleRequest([]byte("{}"), time.Now(), "short", "test-secret")
	require.Error(t, err)
	_, err = SignLifecycleRequest([]byte("{}"), time.Now(), "lifecycle-nonce-0001", " ")
	require.Error(t, err)
}

func TestLifecycleAcknowledgementParserAcceptsOnlyContentFreeProjection(t *testing.T) {
	body := []byte(`{"event_id":"event-index-1","memo_uid":"memo-1","source_sequence":1,"index_version":"memo-v1","status":"applied","operation":"upsert"}`)
	acknowledgement, err := ParseLifecycleAcknowledgement(body)
	require.NoError(t, err)
	require.Equal(t, "event-index-1", acknowledgement.EventID)
	require.Nil(t, acknowledgement.ErrorCode)

	errorCode := "vector_store_unavailable"
	failedBody := []byte(`{"event_id":"event-index-1","memo_uid":"memo-1","source_sequence":1,"index_version":"memo-v1","status":"failed","operation":"upsert","error_code":"vector_store_unavailable"}`)
	failed, err := ParseLifecycleAcknowledgement(failedBody)
	require.NoError(t, err)
	require.Equal(t, &errorCode, failed.ErrorCode)
}

func TestLifecycleAcknowledgementParserRejectsUnsafeMissingAndDuplicateFields(t *testing.T) {
	tests := [][]byte{
		[]byte(`{"event_id":"event-index-1","memo_uid":"memo-1","source_sequence":1,"index_version":"memo-v1","status":"applied","operation":"upsert","document":"raw"}`),
		[]byte(`{"event_id":"event-index-1","source_sequence":1,"index_version":"memo-v1","status":"applied","operation":"upsert"}`),
		[]byte(`{"event_id":"event-index-1","event_id":"duplicate","memo_uid":"memo-1","source_sequence":1,"index_version":"memo-v1","status":"applied","operation":"upsert"}`),
		[]byte(`{"event_id":"event-index-1","memo_uid":"memo-1","source_sequence":1,"index_version":"memo-v1","status":"failed","operation":"upsert","error_code":"raw detail: memo"}`),
	}

	for _, body := range tests {
		_, err := ParseLifecycleAcknowledgement(body)
		require.EqualError(t, err, "invalid lifecycle acknowledgement")
	}
}
