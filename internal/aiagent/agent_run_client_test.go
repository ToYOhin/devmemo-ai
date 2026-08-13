package aiagent

import (
	"context"
	"io"
	"net/http"
	"strings"
	"testing"
	"time"

	"github.com/stretchr/testify/require"
)

func TestAgentRunClientSignsContentFreeCreateRequest(t *testing.T) {
	config := Config{Enabled: true, InternalURL: "http://ai-service:8000", Secret: "test-agent-secret"}
	client, err := NewClient(config)
	require.NoError(t, err)
	now := time.Date(2026, time.August, 13, 8, 0, 0, 0, time.UTC)
	client.now = func() time.Time { return now }
	client.doer = testHTTPDoer(func(request *http.Request) (*http.Response, error) {
		require.Equal(t, InternalAgentRunCreatePath, request.URL.Path)
		body, readErr := io.ReadAll(request.Body)
		require.NoError(t, readErr)
		require.NotContains(t, string(body), "private task")
		require.NoError(t, VerifyRequest(request.Method, request.URL.Path, body, SignedHeaders{
			Signature: request.Header.Get(SignatureHeader),
			Timestamp: request.Header.Get(TimestampHeader),
		}, now, time.Minute, config.Secret))
		return jsonResponse(http.StatusOK, validAgentRunJSON()), nil
	})

	result, err := client.CreateRun(context.Background(), validDelegatedAgentRunCreateRequest())

	require.NoError(t, err)
	require.Equal(t, "queued", result.Status)
}

func TestAgentRunClientRejectsUncontractedResponse(t *testing.T) {
	client, err := NewClient(Config{Enabled: true, InternalURL: "http://ai-service:8000", Secret: "test-agent-secret"})
	require.NoError(t, err)
	client.doer = testHTTPDoer(func(*http.Request) (*http.Response, error) {
		return jsonResponse(http.StatusOK, strings.Replace(validAgentRunJSON(), `"source_count":1`, `"source_count":1,"task":"leak"`, 1)), nil
	})

	_, err = client.CreateRun(context.Background(), validDelegatedAgentRunCreateRequest())

	require.ErrorIs(t, err, ErrInvalidResponse)
}

func TestAgentRunClientSignsCreatorBoundStatusRequest(t *testing.T) {
	config := Config{Enabled: true, InternalURL: "http://ai-service:8000", Secret: "test-agent-secret"}
	client, err := NewClient(config)
	require.NoError(t, err)
	now := time.Date(2026, time.August, 13, 8, 0, 0, 0, time.UTC)
	client.now = func() time.Time { return now }
	client.doer = testHTTPDoer(func(request *http.Request) (*http.Response, error) {
		require.Equal(t, InternalAgentRunStatusPath, request.URL.Path)
		body, readErr := io.ReadAll(request.Body)
		require.NoError(t, readErr)
		require.JSONEq(t, `{"subject_id":"user-1","run_id":"run-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"}`, string(body))
		require.NoError(t, VerifyRequest(request.Method, request.URL.Path, body, SignedHeaders{
			Signature: request.Header.Get(SignatureHeader),
			Timestamp: request.Header.Get(TimestampHeader),
		}, now, time.Minute, config.Secret))
		return jsonResponse(http.StatusOK, validAgentRunJSON()), nil
	})

	_, err = client.GetRun(context.Background(), AgentRunStatusRequest{
		SubjectID: "user-1",
		RunID:     "run-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
	})

	require.NoError(t, err)
}

func TestAgentRunClientMapsAIServiceStatus(t *testing.T) {
	for _, test := range []struct {
		name       string
		statusCode int
		want       error
	}{
		{name: "not found", statusCode: http.StatusNotFound, want: ErrNotFound},
		{name: "unavailable", statusCode: http.StatusServiceUnavailable, want: ErrUnavailable},
	} {
		t.Run(test.name, func(t *testing.T) {
			client, err := NewClient(Config{Enabled: true, InternalURL: "http://ai-service:8000", Secret: "test-agent-secret"})
			require.NoError(t, err)
			client.doer = testHTTPDoer(func(*http.Request) (*http.Response, error) {
				return jsonResponse(test.statusCode, `{}`), nil
			})

			_, err = client.GetRun(context.Background(), AgentRunStatusRequest{
				SubjectID: "user-1",
				RunID:     "run-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
			})

			require.ErrorIs(t, err, test.want)
		})
	}
}

func validDelegatedAgentRunCreateRequest() DelegatedAgentRunCreateRequest {
	return DelegatedAgentRunCreateRequest{
		SubjectID:     "user-1",
		ScopeRef:      "scope-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
		RequestKey:    "request-bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
		RequestDigest: strings.Repeat("c", 64),
		SourceSnapshot: []AgentRunSourceRevision{{
			SourceID: "memo-72756e2d61",
			Revision: "rev-1700000000",
		}},
	}
}

func validAgentRunJSON() string {
	return `{"run_id":"run-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa","status":"queued","created_at":"2026-08-13T08:00:00Z","updated_at":"2026-08-13T08:00:00Z","last_event_seq":0,"source_count":1,"terminal_reason":null}`
}
