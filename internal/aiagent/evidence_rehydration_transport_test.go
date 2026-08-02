package aiagent

import (
	"encoding/json"
	"os"
	"path/filepath"
	"strconv"
	"strings"
	"testing"
	"time"

	"github.com/stretchr/testify/require"
)

type evidenceRehydrationTransportFixture struct {
	Version         string `json:"version"`
	RequestPurpose  string `json:"request_purpose"`
	ResponsePurpose string `json:"response_purpose"`
	Method          string `json:"method"`
	Path            string `json:"path"`
	Secret          string `json:"secret"`
	Request         struct {
		Timestamp string `json:"timestamp"`
		Nonce     string `json:"nonce"`
		RawBody   string `json:"raw_body"`
		Signature string `json:"signature"`
	} `json:"request"`
	Response struct {
		Timestamp     string `json:"timestamp"`
		RequestNonce  string `json:"request_nonce"`
		SnapshotToken string `json:"snapshot_token"`
		Status        int    `json:"status"`
		RawBody       string `json:"raw_body"`
		Signature     string `json:"signature"`
	} `json:"response"`
}

func loadEvidenceRehydrationTransportFixture(t *testing.T) evidenceRehydrationTransportFixture {
	t.Helper()
	fixtureBytes, err := os.ReadFile(filepath.Join("..", "..", "contracts", "memo-evidence-rehydration-transport-v1.json"))
	require.NoError(t, err)
	var fixture evidenceRehydrationTransportFixture
	require.NoError(t, json.Unmarshal(fixtureBytes, &fixture))
	return fixture
}

func fixtureRequestHeaders(fixture evidenceRehydrationTransportFixture) EvidenceRehydrationRequestHeaders {
	return EvidenceRehydrationRequestHeaders{
		Signature: fixture.Request.Signature,
		Timestamp: fixture.Request.Timestamp,
		Nonce:     fixture.Request.Nonce,
		Version:   fixture.Version,
	}
}

func signSyntheticEvidenceRehydrationRequest(body []byte, timestamp, nonce, secret string) EvidenceRehydrationRequestHeaders {
	return EvidenceRehydrationRequestHeaders{
		Signature: evidenceRehydrationRequestSignature(body, timestamp, nonce, secret),
		Timestamp: timestamp,
		Nonce:     nonce,
		Version:   evidenceRehydrationTransportVersion,
	}
}

func TestEvidenceRehydrationRequestMatchesCrossLanguageFixture(t *testing.T) {
	fixture := loadEvidenceRehydrationTransportFixture(t)
	seconds, err := strconv.ParseInt(fixture.Request.Timestamp, 10, 64)
	require.NoError(t, err)
	require.Equal(t, evidenceRehydrationTransportVersion, fixture.Version)
	require.Equal(t, evidenceRehydrationRequestPurpose, fixture.RequestPurpose)
	require.Equal(t, "POST", fixture.Method)
	require.Equal(t, InternalEvidenceRehydrationPath, fixture.Path)

	request, err := VerifyEvidenceRehydrationRequest(
		fixture.Method,
		fixture.Path,
		[]byte(fixture.Request.RawBody),
		fixtureRequestHeaders(fixture),
		time.Unix(seconds+30, 0),
		maxEvidenceRehydrationAge,
		fixture.Secret,
	)
	require.NoError(t, err)
	require.Equal(t, "snapshot-synthetic-1", request.SnapshotToken)
	require.Equal(t, "authority-ref-synthetic-4", request.MemosAuthorityRef)
	require.Len(t, request.Selections, 1)
	require.Equal(t, "memo-visible", request.Selections[0].MemoUID)
	_, err = VerifyEvidenceRehydrationRequest(
		fixture.Method,
		fixture.Path,
		[]byte(fixture.Request.RawBody),
		fixtureRequestHeaders(fixture),
		time.Unix(seconds+60, 0),
		maxEvidenceRehydrationAge,
		fixture.Secret,
	)
	require.NoError(t, err)
}

func TestEvidenceRehydrationRequestRejectsEnvelopeTampering(t *testing.T) {
	fixture := loadEvidenceRehydrationTransportFixture(t)
	seconds, err := strconv.ParseInt(fixture.Request.Timestamp, 10, 64)
	require.NoError(t, err)
	body := []byte(fixture.Request.RawBody)
	headers := fixtureRequestHeaders(fixture)
	now := time.Unix(seconds+30, 0)

	tests := []struct {
		name    string
		method  string
		path    string
		body    []byte
		headers EvidenceRehydrationRequestHeaders
		now     time.Time
		maxAge  time.Duration
		secret  string
	}{
		{name: "method", method: "GET", path: fixture.Path, body: body, headers: headers, now: now, maxAge: time.Minute, secret: fixture.Secret},
		{name: "path", method: fixture.Method, path: "/other", body: body, headers: headers, now: now, maxAge: time.Minute, secret: fixture.Secret},
		{name: "body", method: fixture.Method, path: fixture.Path, body: append(append([]byte{}, body...), ' '), headers: headers, now: now, maxAge: time.Minute, secret: fixture.Secret},
		{name: "secret", method: fixture.Method, path: fixture.Path, body: body, headers: headers, now: now, maxAge: time.Minute, secret: "wrong-secret"},
		{name: "expired", method: fixture.Method, path: fixture.Path, body: body, headers: headers, now: time.Unix(seconds+61, 0), maxAge: time.Minute, secret: fixture.Secret},
		{name: "future", method: fixture.Method, path: fixture.Path, body: body, headers: headers, now: time.Unix(seconds-1, 0), maxAge: time.Minute, secret: fixture.Secret},
		{name: "expanded age", method: fixture.Method, path: fixture.Path, body: body, headers: headers, now: now, maxAge: 61 * time.Second, secret: fixture.Secret},
	}
	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			_, err := VerifyEvidenceRehydrationRequest(test.method, test.path, test.body, test.headers, test.now, test.maxAge, test.secret)
			require.EqualError(t, err, "authorized retrieval unavailable")
		})
	}
}

func TestEvidenceRehydrationRequestRejectsHeaderTampering(t *testing.T) {
	fixture := loadEvidenceRehydrationTransportFixture(t)
	seconds, err := strconv.ParseInt(fixture.Request.Timestamp, 10, 64)
	require.NoError(t, err)
	body := []byte(fixture.Request.RawBody)
	valid := fixtureRequestHeaders(fixture)

	tests := []EvidenceRehydrationRequestHeaders{
		{Signature: "sha256=" + strings.Repeat("0", 64), Timestamp: valid.Timestamp, Nonce: valid.Nonce, Version: valid.Version},
		{Signature: valid.Signature, Timestamp: "0" + valid.Timestamp, Nonce: valid.Nonce, Version: valid.Version},
		{Signature: valid.Signature, Timestamp: valid.Timestamp, Nonce: "short", Version: valid.Version},
		{Signature: valid.Signature, Timestamp: valid.Timestamp, Nonce: valid.Nonce, Version: "other"},
	}
	for _, headers := range tests {
		_, err := VerifyEvidenceRehydrationRequest("POST", fixture.Path, body, headers, time.Unix(seconds+30, 0), time.Minute, fixture.Secret)
		require.EqualError(t, err, "authorized retrieval unavailable")
	}
}

func TestEvidenceRehydrationRequestRejectsSignedUnsafeBodies(t *testing.T) {
	fixture := loadEvidenceRehydrationTransportFixture(t)
	timestamp := fixture.Request.Timestamp
	nonce := fixture.Request.Nonce
	secret := fixture.Secret
	bodies := []string{
		`{"version":"memo-evidence-rehydration-v1","snapshot_token":"snapshot-synthetic-1","memos_authority_ref":"authority-ref-synthetic-4","selections":[],"raw_memo":"secret"}`,
		`{"version":"memo-evidence-rehydration-v1","snapshot_token":"snapshot-synthetic-1","selections":[]}`,
		`{"version":"memo-evidence-rehydration-v1","version":"memo-evidence-rehydration-v1","snapshot_token":"snapshot-synthetic-1","memos_authority_ref":"authority-ref-synthetic-4","selections":[]}`,
		`{"version":"memo-evidence-rehydration-v1","snapshot_token":"snapshot-synthetic-1","memos_authority_ref":"authority-ref-synthetic-4","selections":[]}`,
		`{"version":"memo-evidence-rehydration-v1","snapshot_token":"snapshot-synthetic-1","memos_authority_ref":"authority-ref-synthetic-4","selections":[{"selection_ref":"rehydration-1","selection_ref":"rehydration-2","memo_uid":"memo-visible","source_sequence":3,"document_hash":"b56b98dbaf9a594dfe98537a2bd6658173fcd4866dcf0ea3820d9b4e72f9e8af","index_version":"memo-v1"}]}`,
		`{"version":"memo-evidence-rehydration-v1","snapshot_token":"snapshot-synthetic-1","memos_authority_ref":"authority-ref-synthetic-4","selections":[{"selection_ref":"bad","memo_uid":"memo-visible","source_sequence":3,"document_hash":"b56b98dbaf9a594dfe98537a2bd6658173fcd4866dcf0ea3820d9b4e72f9e8af","index_version":"memo-v1"}]}`,
		`{"version":"memo-evidence-rehydration-v1","snapshot_token":"snapshot-synthetic-1","memos_authority_ref":"authority-ref-synthetic-4","selections":[{"selection_ref":"rehydration-1","memo_uid":"bad_uid","source_sequence":3,"document_hash":"b56b98dbaf9a594dfe98537a2bd6658173fcd4866dcf0ea3820d9b4e72f9e8af","index_version":"memo-v1"}]}`,
		`{"version":"memo-evidence-rehydration-v1","snapshot_token":"snapshot-synthetic-1","memos_authority_ref":"authority-ref-synthetic-4","selections":[{"selection_ref":"rehydration-1","memo_uid":"memo-visible","source_sequence":0,"document_hash":"b56b98dbaf9a594dfe98537a2bd6658173fcd4866dcf0ea3820d9b4e72f9e8af","index_version":"memo-v1"}]}`,
		`{"version":"memo-evidence-rehydration-v1","snapshot_token":"snapshot-synthetic-1","memos_authority_ref":"authority-ref-synthetic-4","selections":[{"selection_ref":"rehydration-1","memo_uid":"memo-visible","source_sequence":3,"document_hash":"B56B98DBAF9A594DFE98537A2BD6658173FCD4866DCF0EA3820D9B4E72F9E8AF","index_version":"memo-v1"}]}`,
		`{"version":"memo-evidence-rehydration-v1","snapshot_token":"snapshot-synthetic-1","memos_authority_ref":"authority-ref-synthetic-4","selections":[{"selection_ref":"rehydration-1","memo_uid":"memo-visible","source_sequence":3,"document_hash":"b56b98dbaf9a594dfe98537a2bd6658173fcd4866dcf0ea3820d9b4e72f9e8af","index_version":"memo-chunk-v1"}]}`,
	}
	seconds, err := strconv.ParseInt(timestamp, 10, 64)
	require.NoError(t, err)
	for _, rawBody := range bodies {
		body := []byte(rawBody)
		headers := signSyntheticEvidenceRehydrationRequest(body, timestamp, nonce, secret)
		_, err := VerifyEvidenceRehydrationRequest("POST", fixture.Path, body, headers, time.Unix(seconds+30, 0), time.Minute, secret)
		require.EqualError(t, err, "authorized retrieval unavailable")
	}
}

func TestEvidenceRehydrationRequestIsBoundedBeforeParsing(t *testing.T) {
	fixture := loadEvidenceRehydrationTransportFixture(t)
	body := []byte(strings.Repeat("x", maxEvidenceRehydrationRequestBytes+1))
	headers := signSyntheticEvidenceRehydrationRequest(body, fixture.Request.Timestamp, fixture.Request.Nonce, fixture.Secret)
	seconds, err := strconv.ParseInt(fixture.Request.Timestamp, 10, 64)
	require.NoError(t, err)

	_, err = VerifyEvidenceRehydrationRequest("POST", fixture.Path, body, headers, time.Unix(seconds, 0), time.Minute, fixture.Secret)
	require.EqualError(t, err, "authorized retrieval unavailable")
}

func TestEvidenceRehydrationRequestRejectsDuplicateAndExcessSelections(t *testing.T) {
	fixture := loadEvidenceRehydrationTransportFixture(t)
	base := EvidenceRehydrationSelection{
		SelectionRef:   "rehydration-1",
		MemoUID:        "memo-visible",
		SourceSequence: 3,
		DocumentHash:   "b56b98dbaf9a594dfe98537a2bd6658173fcd4866dcf0ea3820d9b4e72f9e8af",
		IndexVersion:   "memo-v1",
	}
	duplicateRef := base
	duplicateRef.MemoUID = "memo-other"
	duplicateUID := base
	duplicateUID.SelectionRef = "rehydration-2"
	excess := make([]EvidenceRehydrationSelection, 0, maxEvidenceRehydrationItems+1)
	for index := 1; index <= maxEvidenceRehydrationItems+1; index++ {
		selection := base
		selection.SelectionRef = "rehydration-" + strconv.Itoa(index)
		selection.MemoUID = "memo-" + strconv.Itoa(index)
		excess = append(excess, selection)
	}
	tests := [][]EvidenceRehydrationSelection{
		{base, duplicateRef},
		{base, duplicateUID},
		excess,
	}
	seconds, err := strconv.ParseInt(fixture.Request.Timestamp, 10, 64)
	require.NoError(t, err)
	for _, selections := range tests {
		body, err := json.Marshal(EvidenceRehydrationRequest{
			Version:           evidenceRehydrationContentVersion,
			SnapshotToken:     "snapshot-synthetic-1",
			MemosAuthorityRef: "authority-ref-synthetic-4",
			Selections:        selections,
		})
		require.NoError(t, err)
		headers := signSyntheticEvidenceRehydrationRequest(body, fixture.Request.Timestamp, fixture.Request.Nonce, fixture.Secret)
		_, err = VerifyEvidenceRehydrationRequest("POST", fixture.Path, body, headers, time.Unix(seconds, 0), time.Minute, fixture.Secret)
		require.EqualError(t, err, "authorized retrieval unavailable")
	}
}

func TestEvidenceRehydrationRequestRejectsInvalidUTF8(t *testing.T) {
	fixture := loadEvidenceRehydrationTransportFixture(t)
	body := append([]byte(fixture.Request.RawBody), 0xff)
	headers := signSyntheticEvidenceRehydrationRequest(body, fixture.Request.Timestamp, fixture.Request.Nonce, fixture.Secret)
	seconds, err := strconv.ParseInt(fixture.Request.Timestamp, 10, 64)
	require.NoError(t, err)

	_, err = VerifyEvidenceRehydrationRequest("POST", fixture.Path, body, headers, time.Unix(seconds, 0), time.Minute, fixture.Secret)
	require.EqualError(t, err, "authorized retrieval unavailable")
}

func verifiedFixtureEvidenceRehydrationRequest(
	t *testing.T,
	fixture evidenceRehydrationTransportFixture,
) EvidenceRehydrationRequest {
	t.Helper()
	seconds, err := strconv.ParseInt(fixture.Request.Timestamp, 10, 64)
	require.NoError(t, err)
	request, err := VerifyEvidenceRehydrationRequest(
		fixture.Method,
		fixture.Path,
		[]byte(fixture.Request.RawBody),
		fixtureRequestHeaders(fixture),
		time.Unix(seconds+30, 0),
		time.Minute,
		fixture.Secret,
	)
	require.NoError(t, err)
	return request
}

func TestEvidenceRehydrationResponseMatchesCrossLanguageFixture(t *testing.T) {
	fixture := loadEvidenceRehydrationTransportFixture(t)
	request := verifiedFixtureEvidenceRehydrationRequest(t, fixture)
	seconds, err := strconv.ParseInt(fixture.Response.Timestamp, 10, 64)
	require.NoError(t, err)
	require.Equal(t, evidenceRehydrationResponsePurpose, fixture.ResponsePurpose)

	headers, err := SignEvidenceRehydrationResponse(
		[]byte(fixture.Response.RawBody),
		fixture.Response.Status,
		time.Unix(seconds, 0),
		fixture.Response.RequestNonce,
		request,
		fixture.Secret,
	)
	require.NoError(t, err)
	require.Equal(t, fixture.Response.Signature, headers.Signature)
	require.Equal(t, fixture.Response.Timestamp, headers.Timestamp)
	require.Equal(t, fixture.Response.RequestNonce, headers.RequestNonce)
	require.Equal(t, fixture.Version, headers.Version)

	result, err := ParseEvidenceRehydrationResponse(
		[]byte(fixture.Response.RawBody),
		fixture.Response.Status,
		request,
	)
	require.NoError(t, err)
	require.False(t, result.IsFailure)
	require.NotNil(t, result.Response)
	require.Equal(t, "authority-synthetic-9", result.Response.AuthorityToken)
	require.Len(t, result.Response.Documents, 1)
	require.Equal(t, "rehydration-1", result.Response.Documents[0].SelectionRef)
}

func TestEvidenceRehydrationTransportUsesIndependentSignatureDomains(t *testing.T) {
	fixture := loadEvidenceRehydrationTransportFixture(t)
	request := verifiedFixtureEvidenceRehydrationRequest(t, fixture)
	requestSeconds, err := strconv.ParseInt(fixture.Request.Timestamp, 10, 64)
	require.NoError(t, err)
	requestBody := []byte(fixture.Request.RawBody)
	requestAnswerHeaders, err := SignRequest("POST", InternalAnswerPath, requestBody, time.Unix(requestSeconds, 0), fixture.Secret)
	require.NoError(t, err)
	requestLifecycleHeaders, err := SignLifecycleRequest(requestBody, time.Unix(requestSeconds, 0), fixture.Request.Nonce, fixture.Secret)
	require.NoError(t, err)
	require.NotEqual(t, requestAnswerHeaders.Signature, fixture.Request.Signature)
	require.NotEqual(t, requestLifecycleHeaders.Signature, fixture.Request.Signature)
	require.NotEqual(t, SignatureHeader, EvidenceRehydrationSignatureHeader)
	require.NotEqual(t, LifecycleSignatureHeader, EvidenceRehydrationSignatureHeader)

	seconds, err := strconv.ParseInt(fixture.Response.Timestamp, 10, 64)
	require.NoError(t, err)
	responseBody := []byte(fixture.Response.RawBody)
	responseHeaders, err := SignEvidenceRehydrationResponse(
		responseBody,
		200,
		time.Unix(seconds, 0),
		fixture.Request.Nonce,
		request,
		fixture.Secret,
	)
	require.NoError(t, err)
	answerHeaders, err := SignRequest("POST", InternalAnswerPath, responseBody, time.Unix(seconds, 0), fixture.Secret)
	require.NoError(t, err)
	lifecycleHeaders, err := SignLifecycleRequest(responseBody, time.Unix(seconds, 0), fixture.Request.Nonce, fixture.Secret)
	require.NoError(t, err)

	require.NotEqual(t, fixture.Request.Signature, responseHeaders.Signature)
	require.NotEqual(t, answerHeaders.Signature, responseHeaders.Signature)
	require.NotEqual(t, lifecycleHeaders.Signature, responseHeaders.Signature)
	require.NotEqual(t, EvidenceRehydrationSignatureHeader, EvidenceRehydrationResponseSignatureHeader)
	require.NotEqual(t, LifecycleSignatureHeader, EvidenceRehydrationResponseSignatureHeader)
}

func TestEvidenceRehydrationResponseSignsOnlyFixedFailure(t *testing.T) {
	fixture := loadEvidenceRehydrationTransportFixture(t)
	request := verifiedFixtureEvidenceRehydrationRequest(t, fixture)
	failureBody := []byte(`{"error_code":"authorized_retrieval_unavailable"}`)
	seconds, err := strconv.ParseInt(fixture.Response.Timestamp, 10, 64)
	require.NoError(t, err)

	headers, err := SignEvidenceRehydrationResponse(
		failureBody,
		503,
		time.Unix(seconds, 0),
		fixture.Request.Nonce,
		request,
		fixture.Secret,
	)
	require.NoError(t, err)
	require.True(t, evidenceRehydrationSignaturePattern.MatchString(headers.Signature))
	result, err := ParseEvidenceRehydrationResponse(failureBody, 503, request)
	require.NoError(t, err)
	require.True(t, result.IsFailure)
	require.Nil(t, result.Response)

	unsafeFailure := []byte(`{"error_code":"authorized_retrieval_unavailable","detail":"raw memo"}`)
	_, err = SignEvidenceRehydrationResponse(
		unsafeFailure,
		503,
		time.Unix(seconds, 0),
		fixture.Request.Nonce,
		request,
		fixture.Secret,
	)
	require.EqualError(t, err, "authorized retrieval unavailable")
}

func TestEvidenceRehydrationResponseRejectsUnsafeOrInconsistentBodies(t *testing.T) {
	fixture := loadEvidenceRehydrationTransportFixture(t)
	request := verifiedFixtureEvidenceRehydrationRequest(t, fixture)
	valid := fixture.Response.RawBody
	bodies := []string{
		strings.Replace(valid, `"documents":`, `"memos_authority_ref":"authority-ref-synthetic-4","documents":`, 1),
		strings.Replace(valid, `"authority_token":"authority-synthetic-9",`, "", 1),
		strings.Replace(valid, `"snapshot_token":"snapshot-synthetic-1"`, `"snapshot_token":"snapshot-other"`, 1),
		strings.Replace(valid, `"source_sequence":3`, `"source_sequence":4`, 1),
		strings.Replace(valid, `"index_version":"memo-v1"`, `"index_version":"memo-chunk-v1"`, 1),
		strings.Replace(valid, `"selection_ref":"rehydration-1"`, `"selection_ref":"rehydration-2"`, 1),
		`{"version":"memo-evidence-rehydration-v1","snapshot_token":"snapshot-synthetic-1","authority_token":"authority-synthetic-9","documents":[]}`,
		strings.Replace(valid, `Memos remains the current authority.`, `stale raw memo`, 1),
		strings.Replace(valid, `"selection_ref":"rehydration-1"`, `"selection_ref":"rehydration-1","selection_ref":"rehydration-2"`, 1),
		strings.Replace(valid, `"version":"memo-evidence-rehydration-v1"`, `"version":"memo-evidence-rehydration-v1","version":"memo-evidence-rehydration-v1"`, 1),
	}
	seconds, err := strconv.ParseInt(fixture.Response.Timestamp, 10, 64)
	require.NoError(t, err)
	for _, rawBody := range bodies {
		body := []byte(rawBody)
		_, err := ParseEvidenceRehydrationResponse(body, 200, request)
		require.EqualError(t, err, "authorized retrieval unavailable")
		_, err = SignEvidenceRehydrationResponse(body, 200, time.Unix(seconds, 0), fixture.Request.Nonce, request, fixture.Secret)
		require.EqualError(t, err, "authorized retrieval unavailable")
	}
}

func TestEvidenceRehydrationResponseRejectsDuplicateMaterializedRows(t *testing.T) {
	fixture := loadEvidenceRehydrationTransportFixture(t)
	request := verifiedFixtureEvidenceRehydrationRequest(t, fixture)
	result, err := ParseEvidenceRehydrationResponse([]byte(fixture.Response.RawBody), 200, request)
	require.NoError(t, err)
	require.NotNil(t, result.Response)
	response := *result.Response
	response.Documents = append(response.Documents, response.Documents[0])
	body, err := json.Marshal(response)
	require.NoError(t, err)

	_, err = ParseEvidenceRehydrationResponse(body, 200, request)
	require.EqualError(t, err, "authorized retrieval unavailable")
}

func TestEvidenceRehydrationResponseRejectsStatusBodyAndSignerInputs(t *testing.T) {
	fixture := loadEvidenceRehydrationTransportFixture(t)
	request := verifiedFixtureEvidenceRehydrationRequest(t, fixture)
	successBody := []byte(fixture.Response.RawBody)
	failureBody := []byte(`{"error_code":"authorized_retrieval_unavailable"}`)
	seconds, err := strconv.ParseInt(fixture.Response.Timestamp, 10, 64)
	require.NoError(t, err)
	at := time.Unix(seconds, 0)

	_, err = ParseEvidenceRehydrationResponse(successBody, 503, request)
	require.EqualError(t, err, "authorized retrieval unavailable")
	_, err = ParseEvidenceRehydrationResponse(failureBody, 200, request)
	require.EqualError(t, err, "authorized retrieval unavailable")
	_, err = ParseEvidenceRehydrationResponse(successBody, 206, request)
	require.EqualError(t, err, "authorized retrieval unavailable")
	_, err = SignEvidenceRehydrationResponse(successBody, 200, at, "short", request, fixture.Secret)
	require.EqualError(t, err, "authorized retrieval unavailable")
	_, err = SignEvidenceRehydrationResponse(successBody, 200, at, fixture.Request.Nonce, request, " ")
	require.EqualError(t, err, "authorized retrieval unavailable")
	_, err = SignEvidenceRehydrationResponse(successBody, 200, time.Unix(-1, 0), fixture.Request.Nonce, request, fixture.Secret)
	require.EqualError(t, err, "authorized retrieval unavailable")
}

func TestEvidenceRehydrationResponseIsBoundedBeforeParsing(t *testing.T) {
	fixture := loadEvidenceRehydrationTransportFixture(t)
	request := verifiedFixtureEvidenceRehydrationRequest(t, fixture)
	body := []byte(strings.Repeat("x", maxEvidenceRehydrationResponseBytes+1))

	_, err := ParseEvidenceRehydrationResponse(body, 200, request)
	require.EqualError(t, err, "authorized retrieval unavailable")
}

func TestEvidenceRehydrationResponseRejectsInvalidUTF8(t *testing.T) {
	fixture := loadEvidenceRehydrationTransportFixture(t)
	request := verifiedFixtureEvidenceRehydrationRequest(t, fixture)
	body := append([]byte(fixture.Response.RawBody), 0xff)

	_, err := ParseEvidenceRehydrationResponse(body, 200, request)
	require.EqualError(t, err, "authorized retrieval unavailable")
}

func TestEvidenceRehydrationFailureDoesNotEchoSensitiveInput(t *testing.T) {
	fixture := loadEvidenceRehydrationTransportFixture(t)
	request := verifiedFixtureEvidenceRehydrationRequest(t, fixture)
	unsafe := []byte(`{"document":"private memo","memos_authority_ref":"authority-ref-synthetic-4","secret":"synthetic-rehydration-secret"}`)

	_, err := ParseEvidenceRehydrationResponse(unsafe, 200, request)
	require.EqualError(t, err, "authorized retrieval unavailable")
	for _, forbidden := range []string{"private memo", "authority-ref", "secret", "signature", "digest", "endpoint"} {
		require.NotContains(t, err.Error(), forbidden)
	}
}
