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
	"unicode/utf8"
)

const (
	// InternalEvidenceRehydrationPath is reserved for Memos-owned content rehydration.
	InternalEvidenceRehydrationPath = "/internal/ai/agent/evidence/rehydrate"

	EvidenceRehydrationSignatureHeader         = "X-DevMemo-Rehydration-Signature"
	EvidenceRehydrationTimestampHeader         = "X-DevMemo-Rehydration-Timestamp"
	EvidenceRehydrationNonceHeader             = "X-DevMemo-Rehydration-Nonce"
	EvidenceRehydrationVersionHeader           = "X-DevMemo-Rehydration-Version"
	EvidenceRehydrationResponseSignatureHeader = "X-DevMemo-Rehydration-Response-Signature"
	EvidenceRehydrationResponseTimestampHeader = "X-DevMemo-Rehydration-Response-Timestamp"
	EvidenceRehydrationResponseNonceHeader     = "X-DevMemo-Rehydration-Response-Nonce"
	EvidenceRehydrationResponseVersionHeader   = "X-DevMemo-Rehydration-Response-Version"

	evidenceRehydrationTransportVersion = "memo-evidence-rehydration-transport-v1"
	evidenceRehydrationContentVersion   = "memo-evidence-rehydration-v1"
	evidenceRehydrationRequestPurpose   = "devmemo-agent-evidence-rehydration-v1"
	evidenceRehydrationResponsePurpose  = "devmemo-agent-evidence-rehydration-response-v1"
	evidenceRehydrationSignaturePrefix  = "sha256="
	maxEvidenceRehydrationRequestBytes  = 32768
	maxEvidenceRehydrationItems         = 10
	maxEvidenceRehydrationDocumentChars = 200000
	maxEvidenceRehydrationResponseBytes = maxEvidenceRehydrationItems*maxEvidenceRehydrationDocumentChars*4 + 65536
	maxEvidenceRehydrationAge           = 60 * time.Second
)

var evidenceRehydrationNoncePattern = regexp.MustCompile(`^[A-Za-z0-9_-]{16,128}$`)
var evidenceRehydrationSignaturePattern = regexp.MustCompile(`^sha256=[0-9a-f]{64}$`)
var evidenceRehydrationTimestampPattern = regexp.MustCompile(`^[0-9]{1,12}$`)
var evidenceRehydrationOpaqueIDPattern = regexp.MustCompile(`^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$`)
var evidenceRehydrationSelectionRefPattern = regexp.MustCompile(`^rehydration-[1-9][0-9]*$`)
var evidenceRehydrationMemoUIDPattern = regexp.MustCompile(`^[A-Za-z0-9](?:[A-Za-z0-9-]{0,34}[A-Za-z0-9])?$`)
var evidenceRehydrationHashPattern = regexp.MustCompile(`^[0-9a-f]{64}$`)

// EvidenceRehydrationRequestHeaders are verified before parsing any request body.
type EvidenceRehydrationRequestHeaders struct {
	Signature string
	Timestamp string
	Nonce     string
	Version   string
}

// EvidenceRehydrationSelection is one already-authorized memo-v1 candidate.
type EvidenceRehydrationSelection struct {
	SelectionRef   string `json:"selection_ref"`
	MemoUID        string `json:"memo_uid"`
	SourceSequence int64  `json:"source_sequence"`
	DocumentHash   string `json:"document_hash"`
	IndexVersion   string `json:"index_version"`
}

// EvidenceRehydrationRequest carries an opaque Memos authority reference.
type EvidenceRehydrationRequest struct {
	Version           string                         `json:"version"`
	SnapshotToken     string                         `json:"snapshot_token"`
	MemosAuthorityRef string                         `json:"memos_authority_ref"`
	Selections        []EvidenceRehydrationSelection `json:"selections"`
}

// EvidenceRehydrationResponseHeaders use a response-only HMAC domain.
type EvidenceRehydrationResponseHeaders struct {
	Signature    string
	Timestamp    string
	RequestNonce string
	Version      string
}

// EvidenceRehydrationDocument omits Memo identity and authority metadata.
type EvidenceRehydrationDocument struct {
	SelectionRef   string `json:"selection_ref"`
	Document       string `json:"document"`
	SourceSequence int64  `json:"source_sequence"`
	DocumentHash   string `json:"document_hash"`
	IndexVersion   string `json:"index_version"`
}

// EvidenceRehydrationResponse is the exact all-or-nothing success projection.
type EvidenceRehydrationResponse struct {
	Version        string                        `json:"version"`
	SnapshotToken  string                        `json:"snapshot_token"`
	AuthorityToken string                        `json:"authority_token"`
	Documents      []EvidenceRehydrationDocument `json:"documents"`
}

// EvidenceRehydrationResult distinguishes exact success from the fixed 503 body.
type EvidenceRehydrationResult struct {
	Response  *EvidenceRehydrationResponse
	IsFailure bool
}

// VerifyEvidenceRehydrationRequest authenticates before exact request parsing.
// Replay protection remains the separately proven process-local Python boundary.
func VerifyEvidenceRehydrationRequest(
	method, path string,
	body []byte,
	headers EvidenceRehydrationRequestHeaders,
	now time.Time,
	maxAge time.Duration,
	secret string,
) (EvidenceRehydrationRequest, error) {
	issuedAt, ok := validEvidenceRehydrationRequestEnvelope(
		method,
		path,
		body,
		headers,
		now,
		maxAge,
		secret,
	)
	if !ok {
		return EvidenceRehydrationRequest{}, evidenceRehydrationUnavailable()
	}
	expected := evidenceRehydrationRequestSignature(
		body,
		strconv.FormatInt(issuedAt, 10),
		headers.Nonce,
		secret,
	)
	if !hmac.Equal([]byte(expected), []byte(headers.Signature)) {
		return EvidenceRehydrationRequest{}, evidenceRehydrationUnavailable()
	}

	request, err := parseEvidenceRehydrationRequest(body)
	if err != nil {
		return EvidenceRehydrationRequest{}, evidenceRehydrationUnavailable()
	}
	return request, nil
}

func validEvidenceRehydrationRequestEnvelope(
	method, path string,
	body []byte,
	headers EvidenceRehydrationRequestHeaders,
	now time.Time,
	maxAge time.Duration,
	secret string,
) (int64, bool) {
	if strings.ToUpper(strings.TrimSpace(method)) != "POST" ||
		path != InternalEvidenceRehydrationPath ||
		headers.Version != evidenceRehydrationTransportVersion ||
		strings.TrimSpace(secret) == "" ||
		!evidenceRehydrationNoncePattern.MatchString(headers.Nonce) ||
		!evidenceRehydrationSignaturePattern.MatchString(headers.Signature) ||
		!evidenceRehydrationTimestampPattern.MatchString(headers.Timestamp) ||
		len(body) == 0 || len(body) > maxEvidenceRehydrationRequestBytes || !utf8.Valid(body) ||
		maxAge <= 0 || maxAge > maxEvidenceRehydrationAge || maxAge%time.Second != 0 {
		return 0, false
	}
	issuedAt, err := strconv.ParseInt(headers.Timestamp, 10, 64)
	if err != nil || issuedAt < 0 || strconv.FormatInt(issuedAt, 10) != headers.Timestamp {
		return 0, false
	}
	nowSeconds := now.UTC().Unix()
	if issuedAt > nowSeconds || nowSeconds-issuedAt > int64(maxAge/time.Second) {
		return 0, false
	}
	return issuedAt, true
}

func evidenceRehydrationRequestSignature(body []byte, timestamp, nonce, secret string) string {
	mac := hmac.New(sha256.New, []byte(secret))
	_, _ = mac.Write(canonicalEvidenceRehydrationRequest(timestamp, nonce, body))
	return evidenceRehydrationSignaturePrefix + fmt.Sprintf("%x", mac.Sum(nil))
}

func canonicalEvidenceRehydrationRequest(timestamp, nonce string, body []byte) []byte {
	bodyDigest := sha256.Sum256(body)
	return []byte(strings.Join([]string{
		evidenceRehydrationRequestPurpose,
		evidenceRehydrationTransportVersion,
		"POST",
		InternalEvidenceRehydrationPath,
		timestamp,
		nonce,
		fmt.Sprintf("%x", bodyDigest),
	}, "\n"))
}

// SignEvidenceRehydrationResponse validates the exact body before signing it.
func SignEvidenceRehydrationResponse(
	body []byte,
	statusCode int,
	at time.Time,
	requestNonce string,
	request EvidenceRehydrationRequest,
	secret string,
) (EvidenceRehydrationResponseHeaders, error) {
	if strings.TrimSpace(secret) == "" ||
		!evidenceRehydrationNoncePattern.MatchString(requestNonce) ||
		!validEvidenceRehydrationRequestValue(request) {
		return EvidenceRehydrationResponseHeaders{}, evidenceRehydrationUnavailable()
	}
	if _, err := ParseEvidenceRehydrationResponse(body, statusCode, request); err != nil {
		return EvidenceRehydrationResponseHeaders{}, evidenceRehydrationUnavailable()
	}
	timestamp := at.UTC().Unix()
	if timestamp < 0 || timestamp > 999999999999 {
		return EvidenceRehydrationResponseHeaders{}, evidenceRehydrationUnavailable()
	}
	timestampText := strconv.FormatInt(timestamp, 10)
	mac := hmac.New(sha256.New, []byte(secret))
	_, _ = mac.Write(canonicalEvidenceRehydrationResponse(
		timestampText,
		requestNonce,
		request.SnapshotToken,
		statusCode,
		body,
	))
	return EvidenceRehydrationResponseHeaders{
		Signature:    evidenceRehydrationSignaturePrefix + fmt.Sprintf("%x", mac.Sum(nil)),
		Timestamp:    timestampText,
		RequestNonce: requestNonce,
		Version:      evidenceRehydrationTransportVersion,
	}, nil
}

// VerifyEvidenceRehydrationResponse authenticates the exact status and body
// before parsing the response payload. Replay remains owned by the AI-side
// R5-I4 response replay store.
func VerifyEvidenceRehydrationResponse(
	body []byte,
	statusCode int,
	headers EvidenceRehydrationResponseHeaders,
	now time.Time,
	maxAge time.Duration,
	expectedRequestNonce string,
	request EvidenceRehydrationRequest,
	secret string,
) (EvidenceRehydrationResult, error) {
	if strings.TrimSpace(secret) == "" || !validEvidenceRehydrationRequestValue(request) ||
		headers.Version != evidenceRehydrationTransportVersion ||
		headers.RequestNonce != expectedRequestNonce ||
		!evidenceRehydrationNoncePattern.MatchString(expectedRequestNonce) ||
		!evidenceRehydrationSignaturePattern.MatchString(headers.Signature) ||
		!evidenceRehydrationTimestampPattern.MatchString(headers.Timestamp) ||
		len(body) == 0 || len(body) > maxEvidenceRehydrationResponseBytes || !utf8.Valid(body) ||
		maxAge <= 0 || maxAge > maxEvidenceRehydrationAge || maxAge%time.Second != 0 {
		return EvidenceRehydrationResult{}, evidenceRehydrationUnavailable()
	}
	issuedAt, err := strconv.ParseInt(headers.Timestamp, 10, 64)
	if err != nil || issuedAt < 0 || strconv.FormatInt(issuedAt, 10) != headers.Timestamp {
		return EvidenceRehydrationResult{}, evidenceRehydrationUnavailable()
	}
	nowSeconds := now.UTC().Unix()
	if issuedAt > nowSeconds || nowSeconds-issuedAt > int64(maxAge/time.Second) {
		return EvidenceRehydrationResult{}, evidenceRehydrationUnavailable()
	}
	mac := hmac.New(sha256.New, []byte(secret))
	_, _ = mac.Write(canonicalEvidenceRehydrationResponse(
		headers.Timestamp,
		headers.RequestNonce,
		request.SnapshotToken,
		statusCode,
		body,
	))
	expectedSignature := evidenceRehydrationSignaturePrefix + fmt.Sprintf("%x", mac.Sum(nil))
	if !hmac.Equal([]byte(expectedSignature), []byte(headers.Signature)) {
		return EvidenceRehydrationResult{}, evidenceRehydrationUnavailable()
	}
	result, err := ParseEvidenceRehydrationResponse(body, statusCode, request)
	if err != nil {
		return EvidenceRehydrationResult{}, evidenceRehydrationUnavailable()
	}
	return result, nil
}

// ParseEvidenceRehydrationResponse accepts only exact success or fixed failure.
func ParseEvidenceRehydrationResponse(
	body []byte,
	statusCode int,
	request EvidenceRehydrationRequest,
) (EvidenceRehydrationResult, error) {
	if len(body) == 0 || len(body) > maxEvidenceRehydrationResponseBytes || !utf8.Valid(body) ||
		!validEvidenceRehydrationRequestValue(request) {
		return EvidenceRehydrationResult{}, evidenceRehydrationUnavailable()
	}
	if statusCode == 503 {
		fields, err := decodeEvidenceRehydrationObject(body)
		if err != nil || !hasExactEvidenceRehydrationFields(fields, "error_code") {
			return EvidenceRehydrationResult{}, evidenceRehydrationUnavailable()
		}
		var errorCode string
		if err := json.Unmarshal(fields["error_code"], &errorCode); err != nil ||
			errorCode != "authorized_retrieval_unavailable" {
			return EvidenceRehydrationResult{}, evidenceRehydrationUnavailable()
		}
		return EvidenceRehydrationResult{IsFailure: true}, nil
	}
	if statusCode != 200 {
		return EvidenceRehydrationResult{}, evidenceRehydrationUnavailable()
	}

	response, err := parseEvidenceRehydrationSuccess(body)
	if err != nil || !responseMatchesEvidenceRehydrationRequest(response, request) {
		return EvidenceRehydrationResult{}, evidenceRehydrationUnavailable()
	}
	return EvidenceRehydrationResult{Response: &response}, nil
}

func canonicalEvidenceRehydrationResponse(
	timestamp, requestNonce, snapshotToken string,
	statusCode int,
	body []byte,
) []byte {
	bodyDigest := sha256.Sum256(body)
	return []byte(strings.Join([]string{
		evidenceRehydrationResponsePurpose,
		evidenceRehydrationTransportVersion,
		"POST",
		InternalEvidenceRehydrationPath,
		timestamp,
		requestNonce,
		snapshotToken,
		strconv.Itoa(statusCode),
		fmt.Sprintf("%x", bodyDigest),
	}, "\n"))
}

func parseEvidenceRehydrationRequest(body []byte) (EvidenceRehydrationRequest, error) {
	fields, err := decodeEvidenceRehydrationObject(body)
	if err != nil || !hasExactEvidenceRehydrationFields(fields,
		"version", "snapshot_token", "memos_authority_ref", "selections",
	) {
		return EvidenceRehydrationRequest{}, errors.New("invalid request")
	}

	var request EvidenceRehydrationRequest
	if err := json.Unmarshal(fields["version"], &request.Version); err != nil ||
		request.Version != evidenceRehydrationContentVersion {
		return EvidenceRehydrationRequest{}, errors.New("invalid request")
	}
	if err := json.Unmarshal(fields["snapshot_token"], &request.SnapshotToken); err != nil ||
		!evidenceRehydrationOpaqueIDPattern.MatchString(request.SnapshotToken) {
		return EvidenceRehydrationRequest{}, errors.New("invalid request")
	}
	if err := json.Unmarshal(fields["memos_authority_ref"], &request.MemosAuthorityRef); err != nil ||
		!evidenceRehydrationOpaqueIDPattern.MatchString(request.MemosAuthorityRef) {
		return EvidenceRehydrationRequest{}, errors.New("invalid request")
	}

	var selections []json.RawMessage
	if err := json.Unmarshal(fields["selections"], &selections); err != nil ||
		len(selections) < 1 || len(selections) > maxEvidenceRehydrationItems {
		return EvidenceRehydrationRequest{}, errors.New("invalid request")
	}
	seenRefs := make(map[string]struct{}, len(selections))
	seenUIDs := make(map[string]struct{}, len(selections))
	request.Selections = make([]EvidenceRehydrationSelection, 0, len(selections))
	for _, rawSelection := range selections {
		selection, err := parseEvidenceRehydrationSelection(rawSelection)
		if err != nil {
			return EvidenceRehydrationRequest{}, errors.New("invalid request")
		}
		if _, duplicate := seenRefs[selection.SelectionRef]; duplicate {
			return EvidenceRehydrationRequest{}, errors.New("invalid request")
		}
		if _, duplicate := seenUIDs[selection.MemoUID]; duplicate {
			return EvidenceRehydrationRequest{}, errors.New("invalid request")
		}
		seenRefs[selection.SelectionRef] = struct{}{}
		seenUIDs[selection.MemoUID] = struct{}{}
		request.Selections = append(request.Selections, selection)
	}
	return request, nil
}

func parseEvidenceRehydrationSelection(body []byte) (EvidenceRehydrationSelection, error) {
	fields, err := decodeEvidenceRehydrationObject(body)
	if err != nil || !hasExactEvidenceRehydrationFields(fields,
		"selection_ref", "memo_uid", "source_sequence", "document_hash", "index_version",
	) {
		return EvidenceRehydrationSelection{}, errors.New("invalid selection")
	}
	var selection EvidenceRehydrationSelection
	if err := json.Unmarshal(body, &selection); err != nil || !validEvidenceRehydrationSelection(selection) {
		return EvidenceRehydrationSelection{}, errors.New("invalid selection")
	}
	return selection, nil
}

func parseEvidenceRehydrationSuccess(body []byte) (EvidenceRehydrationResponse, error) {
	fields, err := decodeEvidenceRehydrationObject(body)
	if err != nil || !hasExactEvidenceRehydrationFields(fields,
		"version", "snapshot_token", "authority_token", "documents",
	) {
		return EvidenceRehydrationResponse{}, errors.New("invalid response")
	}
	var response EvidenceRehydrationResponse
	if err := json.Unmarshal(fields["version"], &response.Version); err != nil ||
		response.Version != evidenceRehydrationContentVersion {
		return EvidenceRehydrationResponse{}, errors.New("invalid response")
	}
	if err := json.Unmarshal(fields["snapshot_token"], &response.SnapshotToken); err != nil ||
		!evidenceRehydrationOpaqueIDPattern.MatchString(response.SnapshotToken) {
		return EvidenceRehydrationResponse{}, errors.New("invalid response")
	}
	if err := json.Unmarshal(fields["authority_token"], &response.AuthorityToken); err != nil ||
		!evidenceRehydrationOpaqueIDPattern.MatchString(response.AuthorityToken) {
		return EvidenceRehydrationResponse{}, errors.New("invalid response")
	}

	var documents []json.RawMessage
	if err := json.Unmarshal(fields["documents"], &documents); err != nil ||
		len(documents) < 1 || len(documents) > maxEvidenceRehydrationItems {
		return EvidenceRehydrationResponse{}, errors.New("invalid response")
	}
	seenRefs := make(map[string]struct{}, len(documents))
	response.Documents = make([]EvidenceRehydrationDocument, 0, len(documents))
	for _, rawDocument := range documents {
		document, err := parseEvidenceRehydrationDocument(rawDocument)
		if err != nil {
			return EvidenceRehydrationResponse{}, errors.New("invalid response")
		}
		if _, duplicate := seenRefs[document.SelectionRef]; duplicate {
			return EvidenceRehydrationResponse{}, errors.New("invalid response")
		}
		seenRefs[document.SelectionRef] = struct{}{}
		response.Documents = append(response.Documents, document)
	}
	return response, nil
}

func parseEvidenceRehydrationDocument(body []byte) (EvidenceRehydrationDocument, error) {
	fields, err := decodeEvidenceRehydrationObject(body)
	if err != nil || !hasExactEvidenceRehydrationFields(fields,
		"selection_ref", "document", "source_sequence", "document_hash", "index_version",
	) {
		return EvidenceRehydrationDocument{}, errors.New("invalid document")
	}
	var document EvidenceRehydrationDocument
	if err := json.Unmarshal(body, &document); err != nil ||
		!evidenceRehydrationSelectionRefPattern.MatchString(document.SelectionRef) ||
		strings.TrimSpace(document.Document) == "" ||
		utf8.RuneCountInString(document.Document) > maxEvidenceRehydrationDocumentChars ||
		document.SourceSequence < 1 ||
		!evidenceRehydrationHashPattern.MatchString(document.DocumentHash) ||
		document.IndexVersion != "memo-v1" {
		return EvidenceRehydrationDocument{}, errors.New("invalid document")
	}
	digest := sha256.Sum256([]byte(document.Document))
	if document.DocumentHash != fmt.Sprintf("%x", digest) {
		return EvidenceRehydrationDocument{}, errors.New("invalid document")
	}
	return document, nil
}

func validEvidenceRehydrationRequestValue(request EvidenceRehydrationRequest) bool {
	if request.Version != evidenceRehydrationContentVersion ||
		!evidenceRehydrationOpaqueIDPattern.MatchString(request.SnapshotToken) ||
		!evidenceRehydrationOpaqueIDPattern.MatchString(request.MemosAuthorityRef) ||
		len(request.Selections) < 1 || len(request.Selections) > maxEvidenceRehydrationItems {
		return false
	}
	seenRefs := make(map[string]struct{}, len(request.Selections))
	seenUIDs := make(map[string]struct{}, len(request.Selections))
	for _, selection := range request.Selections {
		if !validEvidenceRehydrationSelection(selection) {
			return false
		}
		if _, duplicate := seenRefs[selection.SelectionRef]; duplicate {
			return false
		}
		if _, duplicate := seenUIDs[selection.MemoUID]; duplicate {
			return false
		}
		seenRefs[selection.SelectionRef] = struct{}{}
		seenUIDs[selection.MemoUID] = struct{}{}
	}
	return true
}

func validEvidenceRehydrationSelection(selection EvidenceRehydrationSelection) bool {
	return evidenceRehydrationSelectionRefPattern.MatchString(selection.SelectionRef) &&
		evidenceRehydrationMemoUIDPattern.MatchString(selection.MemoUID) &&
		selection.SourceSequence >= 1 &&
		evidenceRehydrationHashPattern.MatchString(selection.DocumentHash) &&
		selection.IndexVersion == "memo-v1"
}

func responseMatchesEvidenceRehydrationRequest(
	response EvidenceRehydrationResponse,
	request EvidenceRehydrationRequest,
) bool {
	if response.SnapshotToken != request.SnapshotToken || len(response.Documents) != len(request.Selections) {
		return false
	}
	byRef := make(map[string]EvidenceRehydrationDocument, len(response.Documents))
	for _, document := range response.Documents {
		byRef[document.SelectionRef] = document
	}
	for _, selection := range request.Selections {
		document, ok := byRef[selection.SelectionRef]
		if !ok || document.SourceSequence != selection.SourceSequence ||
			document.DocumentHash != selection.DocumentHash ||
			document.IndexVersion != selection.IndexVersion {
			return false
		}
	}
	return true
}

func decodeEvidenceRehydrationObject(body []byte) (map[string]json.RawMessage, error) {
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

func hasExactEvidenceRehydrationFields(fields map[string]json.RawMessage, expected ...string) bool {
	if len(fields) != len(expected) {
		return false
	}
	for _, field := range expected {
		if _, ok := fields[field]; !ok {
			return false
		}
	}
	return true
}

func evidenceRehydrationUnavailable() error {
	return errors.New("authorized retrieval unavailable")
}
