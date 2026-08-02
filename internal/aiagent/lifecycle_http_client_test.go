package aiagent

import (
	"context"
	"encoding/json"
	"errors"
	"io"
	"net/http"
	"strings"
	"testing"
	"time"

	"github.com/stretchr/testify/require"
)

func lifecycleHTTPTestConfig() LifecycleRuntimeConfig {
	return LifecycleRuntimeConfig{
		Enabled:     true,
		InternalURL: "http://ai-service:8000",
		Secret:      lifecycleConfigSecret,
		Generation:  "r5-disposable-1",
	}
}

func lifecycleHTTPTestEvent() LifecycleEventRequest {
	document := "synthetic lifecycle HTTP document"
	documentHash := "f8993bb58380f2f74d5afaf016380123d549173523a41a18e8c8244347865007"
	return LifecycleEventRequest{
		EventID:        "event-http-1",
		EventType:      "memo.index.requested.v1",
		MemoUID:        "memo-http",
		SourceSequence: 1,
		IndexVersion:   "memo-v1",
		Operation:      "upsert",
		Reason:         "created",
		OccurredAt:     "2026-08-03T00:00:00Z",
		Document:       &document,
		DocumentHash:   &documentHash,
	}
}

func TestLifecycleHTTPClientSignsAndVerifiesExactAcknowledgement(t *testing.T) {
	client, err := NewLifecycleHTTPClient(lifecycleHTTPTestConfig())
	require.NoError(t, err)
	now := time.Date(2026, time.August, 3, 0, 0, 30, 0, time.UTC)
	client.now = func() time.Time { return now }
	client.nonce = func() (string, error) { return "lifecycle-http-nonce-0001", nil }
	event := lifecycleHTTPTestEvent()
	client.doer = testHTTPDoer(func(request *http.Request) (*http.Response, error) {
		body, err := io.ReadAll(request.Body)
		require.NoError(t, err)
		expected, err := SignLifecycleRequest(
			body, now, "lifecycle-http-nonce-0001", lifecycleConfigSecret,
		)
		require.NoError(t, err)
		require.Equal(t, "http://ai-service:8000"+InternalLifecyclePath, request.URL.String())
		require.Equal(t, "application/json", request.Header.Get("Content-Type"))
		require.Equal(t, expected.Signature, request.Header.Get(LifecycleSignatureHeader))
		acknowledgement := LifecycleAcknowledgement{
			EventID: event.EventID, MemoUID: event.MemoUID,
			SourceSequence: event.SourceSequence, IndexVersion: event.IndexVersion,
			Status: "applied", Operation: event.Operation,
		}
		responseBody, err := json.Marshal(acknowledgement)
		require.NoError(t, err)
		return &http.Response{
			StatusCode: http.StatusOK,
			Header:     http.Header{"Content-Type": []string{"application/json"}},
			Body:       io.NopCloser(strings.NewReader(string(responseBody))),
		}, nil
	})

	acknowledgement, err := client.Deliver(context.Background(), event)

	require.NoError(t, err)
	require.Equal(t, "applied", acknowledgement.Status)
}

func TestLifecycleHTTPClientActivatesWithIndependentSignature(t *testing.T) {
	client, err := NewLifecycleHTTPClient(lifecycleHTTPTestConfig())
	require.NoError(t, err)
	now := time.Date(2026, time.August, 3, 0, 0, 30, 0, time.UTC)
	client.now = func() time.Time { return now }
	client.nonce = func() (string, error) { return "lifecycle-activate-nonce-0001", nil }
	client.doer = testHTTPDoer(func(request *http.Request) (*http.Response, error) {
		body, err := io.ReadAll(request.Body)
		require.NoError(t, err)
		expected, err := SignLifecycleActivationRequest(
			body, now, "lifecycle-activate-nonce-0001", lifecycleConfigSecret,
		)
		require.NoError(t, err)
		require.Equal(t, InternalLifecycleActivationPath, request.URL.Path)
		require.Equal(t, expected.Signature, request.Header.Get(LifecycleSignatureHeader))
		return &http.Response{
			StatusCode: http.StatusNoContent,
			Header:     make(http.Header),
			Body:       io.NopCloser(strings.NewReader("")),
		}, nil
	})

	err = client.Activate(context.Background(), LifecycleActivationRequest{
		Generation: "r5-disposable-1", EligibleCount: 1, ManifestDigest: strings.Repeat("a", 64),
	})

	require.NoError(t, err)
}

func TestLifecycleHTTPClientDoesNotRetryOrFollowRedirects(t *testing.T) {
	client, err := NewLifecycleHTTPClient(lifecycleHTTPTestConfig())
	require.NoError(t, err)
	httpClient, ok := client.doer.(*http.Client)
	require.True(t, ok)
	require.Equal(t, 5*time.Second, httpClient.Timeout)
	require.ErrorIs(
		t,
		httpClient.CheckRedirect(&http.Request{}, []*http.Request{{}}),
		http.ErrUseLastResponse,
	)
	calls := 0
	client.doer = testHTTPDoer(func(*http.Request) (*http.Response, error) {
		calls++
		return nil, errors.New("synthetic transport detail")
	})

	_, err = client.Deliver(context.Background(), lifecycleHTTPTestEvent())

	require.ErrorIs(t, err, ErrLifecycleHTTP)
	require.Equal(t, 1, calls)
}

func TestLifecycleHTTPClientRejectsUnsafeResponses(t *testing.T) {
	tests := []struct {
		name        string
		status      int
		contentType string
		body        string
	}{
		{"redirect", http.StatusTemporaryRedirect, "application/json", `{}`},
		{"wrong content type", http.StatusOK, "text/plain", `{}`},
		{"oversized", http.StatusOK, "application/json", strings.Repeat("x", maxLifecycleAckBytes+1)},
		{"unexpected field", http.StatusOK, "application/json", `{"unsafe":"content"}`},
	}
	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			client, err := NewLifecycleHTTPClient(lifecycleHTTPTestConfig())
			require.NoError(t, err)
			client.doer = testHTTPDoer(func(*http.Request) (*http.Response, error) {
				return &http.Response{
					StatusCode: test.status,
					Header:     http.Header{"Content-Type": []string{test.contentType}},
					Body:       io.NopCloser(strings.NewReader(test.body)),
				}, nil
			})

			_, err = client.Deliver(context.Background(), lifecycleHTTPTestEvent())

			require.ErrorIs(t, err, ErrLifecycleHTTP)
		})
	}
}
