package v1

import (
	"bytes"
	"context"
	"errors"
	"io"
	"net/http"
	"net/http/httptest"
	"net/textproto"
	"testing"
	"time"

	"github.com/stretchr/testify/require"

	"github.com/usememos/memos/internal/aiagent"
)

func TestEvidenceRehydrationHTTPHandlerProjectsExactSignedSuccess(t *testing.T) {
	harness := newR5I9Harness(t, "memo-r5-i10-success")
	requestValue, body, headers := harness.issuePreparedRequest(t, "r5-i10-success-nonce-0001", "memo-r5-i10-success")
	handler := mustR5I10HTTPHandler(t, harness.composition)

	response := httptest.NewRecorder()
	handler.ServeHTTP(response, newR5I10HTTPRequest(body, headers))

	require.Equal(t, http.StatusOK, response.Code)
	assertR5I10SignedHTTPResponse(t, response, requestValue, headers.Nonce, harness.clock.now, http.StatusOK)
	require.Equal(t, evidenceRehydrationHTTPContentType, response.Header().Get("Content-Type"))
	require.Equal(t, evidenceRehydrationHTTPNoStore, response.Header().Get("Cache-Control"))
	require.ElementsMatch(t, []string{
		"Cache-Control", "Content-Type",
		textproto.CanonicalMIMEHeaderKey(aiagent.EvidenceRehydrationResponseSignatureHeader),
		textproto.CanonicalMIMEHeaderKey(aiagent.EvidenceRehydrationResponseTimestampHeader),
		textproto.CanonicalMIMEHeaderKey(aiagent.EvidenceRehydrationResponseNonceHeader),
		textproto.CanonicalMIMEHeaderKey(aiagent.EvidenceRehydrationResponseVersionHeader),
	}, r5I10HeaderNames(response.Header()))
}

func TestEvidenceRehydrationHTTPHandlerProjectsExactSignedFailure(t *testing.T) {
	harness := newR5I9Harness(t, "memo-r5-i10-failure")
	harness.reader.err = errors.New("synthetic reader failure")
	requestValue, body, headers := harness.issuePreparedRequest(t, "r5-i10-failure-nonce-001", "memo-r5-i10-failure")
	handler := mustR5I10HTTPHandler(t, harness.composition)

	response := httptest.NewRecorder()
	handler.ServeHTTP(response, newR5I10HTTPRequest(body, headers))

	require.Equal(t, http.StatusServiceUnavailable, response.Code)
	assertR5I10SignedHTTPResponse(t, response, requestValue, headers.Nonce, harness.clock.now, http.StatusServiceUnavailable)
	require.Equal(t, evidenceRehydrationCompositionFailureBody, response.Body.String())
}

func TestEvidenceRehydrationHTTPHandlerRejectsUnverifiedEnvelopesBeforeComposition(t *testing.T) {
	tests := []struct {
		name   string
		mutate func(*http.Request)
	}{
		{name: "method", mutate: func(request *http.Request) { request.Method = http.MethodGet }},
		{name: "path", mutate: func(request *http.Request) { request.URL.Path = "/internal/ai/agent/evidence/wrong" }},
		{name: "query", mutate: func(request *http.Request) { request.URL.RawQuery = "caller=17" }},
		{name: "missing auth header", mutate: func(request *http.Request) { request.Header.Del(aiagent.EvidenceRehydrationSignatureHeader) }},
		{name: "duplicate auth header", mutate: func(request *http.Request) {
			request.Header.Add(aiagent.EvidenceRehydrationNonceHeader, "another-nonce-0001")
		}},
		{name: "invalid content type", mutate: func(request *http.Request) { request.Header.Set("Content-Type", "application/json; charset=utf-8") }},
		{name: "duplicate content type", mutate: func(request *http.Request) { request.Header.Add("Content-Type", evidenceRehydrationHTTPContentType) }},
		{name: "chunked", mutate: func(request *http.Request) {
			request.TransferEncoding = []string{"chunked"}
			request.ContentLength = -1
		}},
		{name: "unknown length", mutate: func(request *http.Request) { request.ContentLength = -1 }},
	}
	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			harness := newR5I9Harness(t, "memo-r5-i10-reject")
			_, body, headers := harness.issuePreparedRequest(t, "r5-i10-reject-nonce-0001", "memo-r5-i10-reject")
			request := newR5I10HTTPRequest(body, headers)
			test.mutate(request)
			response := httptest.NewRecorder()

			mustR5I10HTTPHandler(t, harness.composition).ServeHTTP(response, request)

			assertR5I10UnverifiedResponse(t, response)
			require.Zero(t, harness.readerFactory.calls)
		})
	}
}

func TestEvidenceRehydrationHTTPHandlerRejectsBodyAbuseAndCancellation(t *testing.T) {
	tests := []struct {
		name   string
		mutate func(*http.Request)
	}{
		{name: "empty", mutate: func(request *http.Request) {
			request.Body = io.NopCloser(bytes.NewReader(nil))
			request.ContentLength = 0
		}},
		{name: "oversized", mutate: func(request *http.Request) {
			body := bytes.Repeat([]byte("x"), maxEvidenceRehydrationHTTPRequestBytes+1)
			request.Body = io.NopCloser(bytes.NewReader(body))
			request.ContentLength = maxEvidenceRehydrationHTTPRequestBytes
		}},
		{name: "trailing JSON", mutate: func(request *http.Request) {
			body, err := io.ReadAll(request.Body)
			require.NoError(t, err)
			body = append(body, []byte(` {}`)...)
			request.Body = io.NopCloser(bytes.NewReader(body))
			request.ContentLength = int64(len(body))
		}},
		{name: "canceled context", mutate: func(request *http.Request) {
			ctx, cancel := context.WithCancel(request.Context())
			cancel()
			*request = *request.WithContext(ctx)
		}},
		{name: "body close failure", mutate: func(request *http.Request) {
			body, err := io.ReadAll(request.Body)
			require.NoError(t, err)
			request.Body = &r5I10TrackingReadCloser{
				Reader:   bytes.NewReader(body),
				closeErr: errors.New("synthetic close failure"),
			}
		}},
	}
	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			harness := newR5I9Harness(t, "memo-r5-i10-body")
			_, body, headers := harness.issuePreparedRequest(t, "r5-i10-body-nonce-00001", "memo-r5-i10-body")
			request := newR5I10HTTPRequest(body, headers)
			test.mutate(request)
			response := httptest.NewRecorder()

			mustR5I10HTTPHandler(t, harness.composition).ServeHTTP(response, request)

			assertR5I10UnverifiedResponse(t, response)
			require.Zero(t, harness.readerFactory.calls)
		})
	}
}

func mustR5I10HTTPHandler(t *testing.T, composition *evidenceRehydrationComposition) *evidenceRehydrationHTTPHandler {
	t.Helper()
	handler, err := newEvidenceRehydrationHTTPHandler(composition)
	require.NoError(t, err)
	return handler
}

func newR5I10HTTPRequest(body []byte, headers aiagent.EvidenceRehydrationRequestHeaders) *http.Request {
	request := httptest.NewRequest(http.MethodPost, aiagent.InternalEvidenceRehydrationPath, bytes.NewReader(body))
	request.Header.Set("Content-Type", evidenceRehydrationHTTPContentType)
	request.Header.Set(aiagent.EvidenceRehydrationSignatureHeader, headers.Signature)
	request.Header.Set(aiagent.EvidenceRehydrationTimestampHeader, headers.Timestamp)
	request.Header.Set(aiagent.EvidenceRehydrationNonceHeader, headers.Nonce)
	request.Header.Set(aiagent.EvidenceRehydrationVersionHeader, headers.Version)
	return request
}

func assertR5I10UnverifiedResponse(t *testing.T, response *httptest.ResponseRecorder) {
	t.Helper()
	require.Equal(t, http.StatusNotFound, response.Code)
	require.Empty(t, response.Body.Bytes())
	require.Equal(t, http.Header{"Cache-Control": []string{evidenceRehydrationHTTPNoStore}}, response.Header())
}

func assertR5I10SignedHTTPResponse(
	t *testing.T,
	response *httptest.ResponseRecorder,
	request aiagent.EvidenceRehydrationRequest,
	requestNonce string,
	at time.Time,
	statusCode int,
) {
	t.Helper()
	assertR5I9SignedResult(t, evidenceRehydrationCompositionResult{
		statusCode: response.Code,
		body:       response.Body.Bytes(),
		headers: aiagent.EvidenceRehydrationResponseHeaders{
			Signature:    response.Header().Get(aiagent.EvidenceRehydrationResponseSignatureHeader),
			Timestamp:    response.Header().Get(aiagent.EvidenceRehydrationResponseTimestampHeader),
			RequestNonce: response.Header().Get(aiagent.EvidenceRehydrationResponseNonceHeader),
			Version:      response.Header().Get(aiagent.EvidenceRehydrationResponseVersionHeader),
		},
	}, request, requestNonce, at, statusCode)
}

func r5I10HeaderNames(headers http.Header) []string {
	names := make([]string, 0, len(headers))
	for name := range headers {
		names = append(names, name)
	}
	return names
}
