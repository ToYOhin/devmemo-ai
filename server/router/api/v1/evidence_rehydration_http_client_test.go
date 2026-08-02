package v1

import (
	"bytes"
	"context"
	"errors"
	"io"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	"github.com/stretchr/testify/require"

	"github.com/usememos/memos/internal/aiagent"
)

type r5I10RoundTripFunc func(*http.Request) (*http.Response, error)

func (function r5I10RoundTripFunc) RoundTrip(request *http.Request) (*http.Response, error) {
	return function(request)
}

type r5I10TrackingReadCloser struct {
	io.Reader
	closed   bool
	closeErr error
}

func (body *r5I10TrackingReadCloser) Close() error {
	body.closed = true
	return body.closeErr
}

func TestEvidenceRehydrationHTTPClientSendsAndVerifiesExactExchange(t *testing.T) {
	for _, signedFailure := range []bool{false, true} {
		t.Run(map[bool]string{false: "success", true: "signed failure"}[signedFailure], func(t *testing.T) {
			harness := newR5I9Harness(t, "memo-r5-i10-client")
			if signedFailure {
				harness.reader.err = errors.New("synthetic reader failure")
			}
			_, body, headers := harness.issuePreparedRequest(t, "r5-i10-client-nonce-0001", "memo-r5-i10-client")
			calls := 0
			transport := r5I10RoundTripFunc(func(request *http.Request) (*http.Response, error) {
				calls++
				require.Equal(t, http.MethodPost, request.Method)
				require.Equal(t, "single-host.invalid", request.URL.Host)
				require.Equal(t, aiagent.InternalEvidenceRehydrationPath, request.URL.Path)
				require.Empty(t, request.URL.RawQuery)
				require.ElementsMatch(t, []string{
					"Content-Type",
					"X-Devmemo-Rehydration-Signature",
					"X-Devmemo-Rehydration-Timestamp",
					"X-Devmemo-Rehydration-Nonce",
					"X-Devmemo-Rehydration-Version",
				}, r5I10HeaderNames(request.Header))
				response := httptest.NewRecorder()
				mustR5I10HTTPHandler(t, harness.composition).ServeHTTP(response, request)
				return response.Result(), nil
			})
			client := mustR5I10HTTPClient(t, harness.clock, transport)

			result, err := client.rehydrate(context.Background(), body, headers)

			require.NoError(t, err)
			require.Equal(t, 1, calls)
			require.Equal(t, evidenceRehydrationFutureClientTimeout, client.httpClient.Timeout)
			require.Equal(t, signedFailure, result.IsFailure)
			if signedFailure {
				require.Nil(t, result.Response)
			} else {
				require.NotNil(t, result.Response)
			}
		})
	}
}

func TestEvidenceRehydrationHTTPClientDoesNotRetryAndFixesTimeout(t *testing.T) {
	harness := newR5I9Harness(t, "memo-r5-i10-no-retry")
	_, body, headers := harness.issuePreparedRequest(t, "r5-i10-no-retry-nonce-01", "memo-r5-i10-no-retry")
	calls := 0
	var deadlineRemaining time.Duration
	transport := r5I10RoundTripFunc(func(request *http.Request) (*http.Response, error) {
		calls++
		deadline, ok := request.Context().Deadline()
		require.True(t, ok)
		deadlineRemaining = time.Until(deadline)
		return nil, errors.New("synthetic transport failure")
	})
	client := mustR5I10HTTPClient(t, harness.clock, transport)

	_, err := client.rehydrate(context.Background(), body, headers)

	require.EqualError(t, err, "authorized retrieval unavailable")
	require.Equal(t, 1, calls)
	require.False(t, evidenceRehydrationAutoRetry)
	require.Greater(t, deadlineRemaining, 4*time.Second)
	require.LessOrEqual(t, deadlineRemaining, evidenceRehydrationFutureClientTimeout)
}

func TestEvidenceRehydrationHTTPClientRejectsBeforeParsingAndClosesBody(t *testing.T) {
	harness := newR5I9Harness(t, "memo-r5-i10-verify")
	requestValue, body, headers := harness.issuePreparedRequest(t, "r5-i10-verify-nonce-0001", "memo-r5-i10-verify")
	malformed := []byte(`{"raw_memo":"must-not-parse"}`)
	signedHeaders, err := aiagent.SignEvidenceRehydrationResponse(
		[]byte(evidenceRehydrationCompositionFailureBody),
		http.StatusServiceUnavailable,
		harness.clock.now,
		headers.Nonce,
		requestValue,
		r5I9Secret,
	)
	require.NoError(t, err)
	trackedBody := &r5I10TrackingReadCloser{Reader: bytes.NewReader(malformed)}
	transport := r5I10RoundTripFunc(func(*http.Request) (*http.Response, error) {
		return &http.Response{
			StatusCode:    http.StatusServiceUnavailable,
			ContentLength: int64(len(malformed)),
			Header:        r5I10ResponseHeaders(signedHeaders),
			Body:          trackedBody,
		}, nil
	})
	client := mustR5I10HTTPClient(t, harness.clock, transport)

	_, err = client.rehydrate(context.Background(), body, headers)

	require.EqualError(t, err, "authorized retrieval unavailable")
	require.True(t, trackedBody.closed)
}

func TestEvidenceRehydrationHTTPClientRejectsUnsafeResponseHeaders(t *testing.T) {
	tests := []struct {
		name   string
		mutate func(http.Header)
	}{
		{name: "cacheable", mutate: func(headers http.Header) { headers.Set("Cache-Control", "public, max-age=60") }},
		{name: "duplicate signature", mutate: func(headers http.Header) {
			headers.Add(aiagent.EvidenceRehydrationResponseSignatureHeader, "sha256="+strings.Repeat("0", 64))
		}},
		{name: "identity header", mutate: func(headers http.Header) { headers.Set("X-Memo-UID", "private-memo") }},
		{name: "debug header", mutate: func(headers http.Header) { headers.Set("X-Debug", "secret") }},
	}
	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			harness := newR5I9Harness(t, "memo-r5-i10-headers")
			requestValue, body, requestHeaders := harness.issuePreparedRequest(t, "r5-i10-headers-nonce-001", "memo-r5-i10-headers")
			responseBody := []byte(evidenceRehydrationCompositionFailureBody)
			responseHeaders, err := aiagent.SignEvidenceRehydrationResponse(
				responseBody,
				http.StatusServiceUnavailable,
				harness.clock.now,
				requestHeaders.Nonce,
				requestValue,
				r5I9Secret,
			)
			require.NoError(t, err)
			headers := r5I10ResponseHeaders(responseHeaders)
			test.mutate(headers)
			trackedBody := &r5I10TrackingReadCloser{Reader: bytes.NewReader(responseBody)}
			client := mustR5I10HTTPClient(t, harness.clock, r5I10RoundTripFunc(func(*http.Request) (*http.Response, error) {
				return &http.Response{
					StatusCode:    http.StatusServiceUnavailable,
					ContentLength: int64(len(responseBody)),
					Header:        headers,
					Body:          trackedBody,
				}, nil
			}))

			_, err = client.rehydrate(context.Background(), body, requestHeaders)

			require.EqualError(t, err, "authorized retrieval unavailable")
			require.True(t, trackedBody.closed)
		})
	}
}

func TestEvidenceRehydrationHTTPClientBoundsAndClosesResponses(t *testing.T) {
	tests := []struct {
		name          string
		responseBody  func() []byte
		contentLength int64
		closeErr      error
	}{
		{
			name:          "close failure",
			responseBody:  func() []byte { return []byte(evidenceRehydrationCompositionFailureBody) },
			contentLength: int64(len(evidenceRehydrationCompositionFailureBody)),
			closeErr:      errors.New("synthetic close failure"),
		},
		{
			name:          "unknown-length oversized response",
			responseBody:  func() []byte { return bytes.Repeat([]byte("x"), maxEvidenceRehydrationHTTPResponseBytes+1) },
			contentLength: -1,
		},
	}
	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			harness := newR5I9Harness(t, "memo-r5-i10-bounded")
			requestValue, body, requestHeaders := harness.issuePreparedRequest(t, "r5-i10-bounded-nonce-01", "memo-r5-i10-bounded")
			responseHeaders, err := aiagent.SignEvidenceRehydrationResponse(
				[]byte(evidenceRehydrationCompositionFailureBody),
				http.StatusServiceUnavailable,
				harness.clock.now,
				requestHeaders.Nonce,
				requestValue,
				r5I9Secret,
			)
			require.NoError(t, err)
			responseBody := test.responseBody()
			trackedBody := &r5I10TrackingReadCloser{
				Reader:   bytes.NewReader(responseBody),
				closeErr: test.closeErr,
			}
			client := mustR5I10HTTPClient(t, harness.clock, r5I10RoundTripFunc(func(*http.Request) (*http.Response, error) {
				return &http.Response{
					StatusCode:    http.StatusServiceUnavailable,
					ContentLength: test.contentLength,
					Header:        r5I10ResponseHeaders(responseHeaders),
					Body:          trackedBody,
				}, nil
			}))

			_, err = client.rehydrate(context.Background(), body, requestHeaders)

			require.EqualError(t, err, "authorized retrieval unavailable")
			require.True(t, trackedBody.closed)
		})
	}
}

func TestEvidenceRehydrationHTTPClientFailsClosedOnCancellation(t *testing.T) {
	harness := newR5I9Harness(t, "memo-r5-i10-cancel")
	_, body, headers := harness.issuePreparedRequest(t, "r5-i10-cancel-nonce-0001", "memo-r5-i10-cancel")
	calls := 0
	client := mustR5I10HTTPClient(t, harness.clock, r5I10RoundTripFunc(func(*http.Request) (*http.Response, error) {
		calls++
		return nil, errors.New("must not be called")
	}))
	ctx, cancel := context.WithCancel(context.Background())
	cancel()

	_, err := client.rehydrate(ctx, body, headers)

	require.EqualError(t, err, "authorized retrieval unavailable")
	require.Zero(t, calls)
}

func mustR5I10HTTPClient(
	t *testing.T,
	clock evidenceAuthorityCapabilityClock,
	transport http.RoundTripper,
) *evidenceRehydrationHTTPClient {
	t.Helper()
	client, err := newEvidenceRehydrationHTTPClient("http://single-host.invalid", r5I9Secret, clock, transport)
	require.NoError(t, err)
	return client
}

func r5I10ResponseHeaders(headers aiagent.EvidenceRehydrationResponseHeaders) http.Header {
	result := make(http.Header)
	result.Set("Content-Type", evidenceRehydrationHTTPContentType)
	result.Set("Cache-Control", evidenceRehydrationHTTPNoStore)
	result.Set(aiagent.EvidenceRehydrationResponseSignatureHeader, headers.Signature)
	result.Set(aiagent.EvidenceRehydrationResponseTimestampHeader, headers.Timestamp)
	result.Set(aiagent.EvidenceRehydrationResponseNonceHeader, headers.RequestNonce)
	result.Set(aiagent.EvidenceRehydrationResponseVersionHeader, headers.Version)
	return result
}
