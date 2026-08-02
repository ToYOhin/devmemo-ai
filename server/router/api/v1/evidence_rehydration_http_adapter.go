package v1

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"io"
	"net/http"
	"net/url"
	"strings"

	"github.com/usememos/memos/internal/aiagent"
)

const (
	maxEvidenceRehydrationHTTPRequestBytes  = 32 << 10
	maxEvidenceRehydrationHTTPResponseBytes = 10*200000*4 + 65536
	evidenceRehydrationHTTPContentType      = "application/json"
	evidenceRehydrationHTTPNoStore          = "no-store"
)

type evidenceRehydrationHTTPHandler struct {
	currentComposition  *evidenceRehydrationComposition
	previousComposition *evidenceRehydrationComposition
}

type evidenceRehydrationHTTPClient struct {
	baseURL    string
	secret     string
	clock      evidenceAuthorityCapabilityClock
	httpClient *http.Client
}

func newEvidenceRehydrationHTTPHandler(
	currentComposition *evidenceRehydrationComposition,
	previousComposition ...*evidenceRehydrationComposition,
) (*evidenceRehydrationHTTPHandler, error) {
	if currentComposition == nil || len(previousComposition) > 1 ||
		(len(previousComposition) == 1 && previousComposition[0] == nil) {
		return nil, errEvidenceRehydrationCompositionUnavailable
	}
	handler := &evidenceRehydrationHTTPHandler{currentComposition: currentComposition}
	if len(previousComposition) == 1 {
		handler.previousComposition = previousComposition[0]
	}
	return handler, nil
}

func newEvidenceRehydrationHTTPClient(
	baseURL string,
	secret string,
	clock evidenceAuthorityCapabilityClock,
	transport http.RoundTripper,
) (*evidenceRehydrationHTTPClient, error) {
	parsed, err := url.Parse(baseURL)
	if err != nil || parsed.Opaque != "" || (parsed.Scheme != "http" && parsed.Scheme != "https") ||
		parsed.Host == "" || parsed.User != nil || (parsed.Path != "" && parsed.Path != "/") ||
		parsed.RawPath != "" || parsed.RawQuery != "" || parsed.ForceQuery || parsed.Fragment != "" ||
		strings.TrimSpace(secret) == "" || clock == nil || transport == nil {
		return nil, errEvidenceRehydrationCompositionUnavailable
	}
	return &evidenceRehydrationHTTPClient{
		baseURL: strings.TrimRight(parsed.String(), "/"),
		secret:  secret,
		clock:   clock,
		httpClient: &http.Client{
			Timeout:   evidenceRehydrationFutureClientTimeout,
			Transport: transport,
			CheckRedirect: func(*http.Request, []*http.Request) error {
				return http.ErrUseLastResponse
			},
		},
	}, nil
}

func (client *evidenceRehydrationHTTPClient) rehydrate(
	ctx context.Context,
	body []byte,
	headers aiagent.EvidenceRehydrationRequestHeaders,
) (aiagent.EvidenceRehydrationResult, error) {
	if client == nil || client.httpClient == nil || ctx == nil || ctx.Err() != nil {
		return aiagent.EvidenceRehydrationResult{}, errEvidenceRehydrationCompositionUnavailable
	}
	now, err := client.clock.Now()
	if err != nil {
		return aiagent.EvidenceRehydrationResult{}, errEvidenceRehydrationCompositionUnavailable
	}
	requestValue, err := aiagent.VerifyEvidenceRehydrationRequest(
		http.MethodPost,
		aiagent.InternalEvidenceRehydrationPath,
		body,
		headers,
		now,
		maxEvidenceRehydrationCompositionAge,
		client.secret,
	)
	if err != nil {
		return aiagent.EvidenceRehydrationResult{}, errEvidenceRehydrationCompositionUnavailable
	}
	request, err := http.NewRequestWithContext(
		ctx,
		http.MethodPost,
		client.baseURL+aiagent.InternalEvidenceRehydrationPath,
		bytes.NewReader(body),
	)
	if err != nil {
		return aiagent.EvidenceRehydrationResult{}, errEvidenceRehydrationCompositionUnavailable
	}
	request.Header.Set("Content-Type", evidenceRehydrationHTTPContentType)
	request.Header.Set(aiagent.EvidenceRehydrationSignatureHeader, headers.Signature)
	request.Header.Set(aiagent.EvidenceRehydrationTimestampHeader, headers.Timestamp)
	request.Header.Set(aiagent.EvidenceRehydrationNonceHeader, headers.Nonce)
	request.Header.Set(aiagent.EvidenceRehydrationVersionHeader, headers.Version)

	response, err := client.httpClient.Do(request)
	if err != nil {
		if response != nil && response.Body != nil {
			_ = response.Body.Close()
		}
		return aiagent.EvidenceRehydrationResult{}, errEvidenceRehydrationCompositionUnavailable
	}
	responseBody, err := readEvidenceRehydrationHTTPResponse(response)
	if err != nil || ctx.Err() != nil || !validEvidenceRehydrationHTTPResponseHeaders(response.Header) {
		return aiagent.EvidenceRehydrationResult{}, errEvidenceRehydrationCompositionUnavailable
	}
	verifiedAt, err := client.clock.Now()
	if err != nil {
		return aiagent.EvidenceRehydrationResult{}, errEvidenceRehydrationCompositionUnavailable
	}
	result, err := aiagent.VerifyEvidenceRehydrationResponse(
		responseBody,
		response.StatusCode,
		aiagent.EvidenceRehydrationResponseHeaders{
			Signature:    mustSingleEvidenceRehydrationHTTPHeader(response.Header, aiagent.EvidenceRehydrationResponseSignatureHeader),
			Timestamp:    mustSingleEvidenceRehydrationHTTPHeader(response.Header, aiagent.EvidenceRehydrationResponseTimestampHeader),
			RequestNonce: mustSingleEvidenceRehydrationHTTPHeader(response.Header, aiagent.EvidenceRehydrationResponseNonceHeader),
			Version:      mustSingleEvidenceRehydrationHTTPHeader(response.Header, aiagent.EvidenceRehydrationResponseVersionHeader),
		},
		verifiedAt,
		maxEvidenceRehydrationCompositionAge,
		headers.Nonce,
		requestValue,
		client.secret,
	)
	if err != nil {
		return aiagent.EvidenceRehydrationResult{}, errEvidenceRehydrationCompositionUnavailable
	}
	return result, nil
}

func (handler *evidenceRehydrationHTTPHandler) ServeHTTP(writer http.ResponseWriter, request *http.Request) {
	if handler == nil || handler.currentComposition == nil || !validEvidenceRehydrationHTTPRequest(request) {
		writeUnverifiedEvidenceRehydrationHTTPResponse(writer)
		return
	}

	bodyReader := request.Body
	closed := false
	defer func() {
		if !closed {
			_ = bodyReader.Close()
		}
	}()
	body, err := io.ReadAll(io.LimitReader(bodyReader, maxEvidenceRehydrationHTTPRequestBytes+1))
	if err != nil || len(body) == 0 || len(body) > maxEvidenceRehydrationHTTPRequestBytes ||
		!hasSingleEvidenceRehydrationJSONValue(body) {
		writeUnverifiedEvidenceRehydrationHTTPResponse(writer)
		return
	}
	closeErr := bodyReader.Close()
	closed = true
	if closeErr != nil || request.Context().Err() != nil {
		writeUnverifiedEvidenceRehydrationHTTPResponse(writer)
		return
	}

	requestHeaders := aiagent.EvidenceRehydrationRequestHeaders{
		Signature: mustSingleEvidenceRehydrationHTTPHeader(request.Header, aiagent.EvidenceRehydrationSignatureHeader),
		Timestamp: mustSingleEvidenceRehydrationHTTPHeader(request.Header, aiagent.EvidenceRehydrationTimestampHeader),
		Nonce:     mustSingleEvidenceRehydrationHTTPHeader(request.Header, aiagent.EvidenceRehydrationNonceHeader),
		Version:   mustSingleEvidenceRehydrationHTTPHeader(request.Header, aiagent.EvidenceRehydrationVersionHeader),
	}
	result, err := handler.currentComposition.handleContext(
		request.Context(),
		request.Method,
		request.URL.Path,
		body,
		requestHeaders,
	)
	if err != nil && request.Context().Err() == nil && handler.previousComposition != nil {
		result, err = handler.previousComposition.handleContext(
			request.Context(),
			request.Method,
			request.URL.Path,
			body,
			requestHeaders,
		)
	}
	if err != nil || request.Context().Err() != nil {
		writeUnverifiedEvidenceRehydrationHTTPResponse(writer)
		return
	}
	writeVerifiedEvidenceRehydrationHTTPResponse(writer, result)
}

func validEvidenceRehydrationHTTPRequest(request *http.Request) bool {
	if request == nil || request.URL == nil || request.Body == nil || request.Context().Err() != nil ||
		request.Method != http.MethodPost || request.URL.Path != aiagent.InternalEvidenceRehydrationPath ||
		request.URL.RawPath != "" || request.URL.RawQuery != "" || request.URL.ForceQuery || len(request.TransferEncoding) != 0 ||
		request.ContentLength < 1 || request.ContentLength > maxEvidenceRehydrationHTTPRequestBytes {
		return false
	}
	contentType, ok := singleEvidenceRehydrationHTTPHeader(request.Header, "Content-Type")
	if !ok || contentType != evidenceRehydrationHTTPContentType {
		return false
	}
	for _, name := range []string{
		aiagent.EvidenceRehydrationSignatureHeader,
		aiagent.EvidenceRehydrationTimestampHeader,
		aiagent.EvidenceRehydrationNonceHeader,
		aiagent.EvidenceRehydrationVersionHeader,
	} {
		value, ok := singleEvidenceRehydrationHTTPHeader(request.Header, name)
		if !ok || strings.TrimSpace(value) == "" {
			return false
		}
	}
	return true
}

func readEvidenceRehydrationHTTPResponse(response *http.Response) ([]byte, error) {
	if response == nil || response.Body == nil {
		return nil, errEvidenceRehydrationCompositionUnavailable
	}
	if response.ContentLength > maxEvidenceRehydrationHTTPResponseBytes {
		_ = response.Body.Close()
		return nil, errEvidenceRehydrationCompositionUnavailable
	}
	body, readErr := io.ReadAll(io.LimitReader(response.Body, maxEvidenceRehydrationHTTPResponseBytes+1))
	closeErr := response.Body.Close()
	if readErr != nil || closeErr != nil || len(body) == 0 || len(body) > maxEvidenceRehydrationHTTPResponseBytes {
		return nil, errEvidenceRehydrationCompositionUnavailable
	}
	return body, nil
}

func validEvidenceRehydrationHTTPResponseHeaders(headers http.Header) bool {
	for name, expected := range map[string]string{
		"Content-Type":  evidenceRehydrationHTTPContentType,
		"Cache-Control": evidenceRehydrationHTTPNoStore,
		aiagent.EvidenceRehydrationResponseSignatureHeader: "",
		aiagent.EvidenceRehydrationResponseTimestampHeader: "",
		aiagent.EvidenceRehydrationResponseNonceHeader:     "",
		aiagent.EvidenceRehydrationResponseVersionHeader:   "",
	} {
		value, ok := singleEvidenceRehydrationHTTPHeader(headers, name)
		if !ok || (expected != "" && value != expected) || (expected == "" && strings.TrimSpace(value) == "") {
			return false
		}
	}
	allowed := map[string]struct{}{
		"cache-control":  {},
		"content-type":   {},
		"date":           {},
		"content-length": {},
		strings.ToLower(aiagent.EvidenceRehydrationResponseSignatureHeader): {},
		strings.ToLower(aiagent.EvidenceRehydrationResponseTimestampHeader): {},
		strings.ToLower(aiagent.EvidenceRehydrationResponseNonceHeader):     {},
		strings.ToLower(aiagent.EvidenceRehydrationResponseVersionHeader):   {},
	}
	for name := range headers {
		if _, ok := allowed[strings.ToLower(name)]; !ok {
			return false
		}
	}
	return true
}

func singleEvidenceRehydrationHTTPHeader(headers http.Header, name string) (string, bool) {
	var values []string
	for candidate, candidateValues := range headers {
		if strings.EqualFold(candidate, name) {
			values = append(values, candidateValues...)
		}
	}
	returnValue := ""
	if len(values) == 1 {
		returnValue = values[0]
	}
	return returnValue, len(values) == 1
}

func mustSingleEvidenceRehydrationHTTPHeader(headers http.Header, name string) string {
	value, _ := singleEvidenceRehydrationHTTPHeader(headers, name)
	return value
}

func hasSingleEvidenceRehydrationJSONValue(body []byte) bool {
	decoder := json.NewDecoder(bytes.NewReader(body))
	var value json.RawMessage
	if err := decoder.Decode(&value); err != nil || len(value) == 0 {
		return false
	}
	var trailing json.RawMessage
	return errors.Is(decoder.Decode(&trailing), io.EOF)
}

func writeUnverifiedEvidenceRehydrationHTTPResponse(writer http.ResponseWriter) {
	if writer == nil {
		return
	}
	writer.Header().Set("Cache-Control", evidenceRehydrationHTTPNoStore)
	writer.WriteHeader(http.StatusNotFound)
}

func writeVerifiedEvidenceRehydrationHTTPResponse(
	writer http.ResponseWriter,
	result evidenceRehydrationCompositionResult,
) {
	writer.Header().Set("Cache-Control", evidenceRehydrationHTTPNoStore)
	writer.Header().Set("Content-Type", evidenceRehydrationHTTPContentType)
	writer.Header().Set(aiagent.EvidenceRehydrationResponseSignatureHeader, result.headers.Signature)
	writer.Header().Set(aiagent.EvidenceRehydrationResponseTimestampHeader, result.headers.Timestamp)
	writer.Header().Set(aiagent.EvidenceRehydrationResponseNonceHeader, result.headers.RequestNonce)
	writer.Header().Set(aiagent.EvidenceRehydrationResponseVersionHeader, result.headers.Version)
	writer.WriteHeader(result.statusCode)
	_, _ = writer.Write(result.body)
}
