package aiagent

import (
	"encoding/json"
	"testing"
	"time"

	"github.com/stretchr/testify/require"
)

func TestDelegatedAnswerRequestIsBoundedAndContentFree(t *testing.T) {
	request := DelegatedAnswerRequest{
		Question:        "Why did the Docker port mapping fail?",
		Limit:           3,
		VisibleMemoUIDs: []string{"memo-a", "memo-b"},
	}

	require.NoError(t, request.Validate())
	payload, err := json.Marshal(request)
	require.NoError(t, err)
	require.NotContains(t, string(payload), "\"content\"")
	require.NotContains(t, string(payload), "user_id")
}

func TestDelegatedAnswerRequestRejectsInvalidScope(t *testing.T) {
	tests := []DelegatedAnswerRequest{
		{Question: " ", Limit: 1},
		{Question: "question", Limit: 11},
		{Question: "question", Limit: 1, VisibleMemoUIDs: []string{""}},
		{Question: "question", Limit: 1, VisibleMemoUIDs: []string{"memo-a", "memo-a"}},
	}

	for _, request := range tests {
		require.Error(t, request.Validate())
	}
}

func TestSignedDelegationBindsMethodPathBodyAndTimestamp(t *testing.T) {
	now := time.Date(2026, time.July, 31, 12, 0, 0, 0, time.UTC)
	body := []byte(`{"question":"Docker port mapping","limit":3,"visible_memo_uids":["memo-a"]}`)
	headers, err := SignRequest("POST", InternalAnswerPath, body, now, "test-agent-secret")
	require.NoError(t, err)

	require.NoError(t, VerifyRequest("POST", InternalAnswerPath, body, headers, now.Add(30*time.Second), time.Minute, "test-agent-secret"))
	require.Error(t, VerifyRequest("GET", InternalAnswerPath, body, headers, now, time.Minute, "test-agent-secret"))
	require.Error(t, VerifyRequest("POST", "/other", body, headers, now, time.Minute, "test-agent-secret"))
	require.Error(t, VerifyRequest("POST", InternalAnswerPath, append(body, ' '), headers, now, time.Minute, "test-agent-secret"))
	require.Error(t, VerifyRequest("POST", InternalAnswerPath, body, headers, now.Add(2*time.Minute), time.Minute, "test-agent-secret"))
}
