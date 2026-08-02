package v1

import (
	"context"
	"crypto/hmac"
	"crypto/sha256"
	"encoding/json"
	"errors"
	"fmt"
	"strings"
	"sync"
	"testing"
	"time"

	"github.com/stretchr/testify/require"

	"github.com/usememos/memos/internal/aiagent"
	"github.com/usememos/memos/server/auth"
)

const r5I9Secret = "synthetic-r5-i9-secret"

type fakeR5I9Reader struct {
	mu             sync.Mutex
	calls          int
	binding        aiagent.EvidenceAuthorityContextBinding
	authorityToken string
	err            error
	mutateSnapshot func(*aiagent.EvidenceCurrentAuthoritySnapshot)
	mutateRequest  func(*aiagent.EvidenceRehydrationRequest)
	lastRequest    aiagent.EvidenceRehydrationRequest
	lastBinding    aiagent.EvidenceAuthorityContextBinding
}

func (reader *fakeR5I9Reader) configure(
	binding aiagent.EvidenceAuthorityContextBinding,
	authorityToken string,
) {
	reader.mu.Lock()
	defer reader.mu.Unlock()
	reader.binding = binding
	reader.authorityToken = authorityToken
}

func (reader *fakeR5I9Reader) ReadCurrentAuthority(
	request aiagent.EvidenceRehydrationRequest,
	binding aiagent.EvidenceAuthorityContextBinding,
) (aiagent.EvidenceCurrentAuthoritySnapshot, error) {
	reader.mu.Lock()
	defer reader.mu.Unlock()
	reader.calls++
	if reader.mutateRequest != nil {
		reader.mutateRequest(&request)
	}
	reader.lastRequest = request
	reader.lastBinding = binding
	if reader.err != nil {
		return aiagent.EvidenceCurrentAuthoritySnapshot{}, reader.err
	}
	snapshot := aiagent.EvidenceCurrentAuthoritySnapshot{
		MemosAuthorityRef:         reader.binding.MemosAuthorityRef,
		AuthenticatedContextToken: reader.binding.AuthenticatedContextToken,
		SnapshotRevision:          "r5-i9-snapshot-revision-0001",
		AuthorityToken:            reader.authorityToken,
		Documents:                 make([]aiagent.EvidenceCurrentAuthorityDocument, 0, len(request.Selections)),
	}
	for _, selection := range request.Selections {
		document := r5I9Document(selection.MemoUID)
		snapshot.Documents = append(snapshot.Documents, aiagent.EvidenceCurrentAuthorityDocument{
			MemoUID:          selection.MemoUID,
			Document:         document,
			SourceSequence:   selection.SourceSequence,
			DocumentHash:     r5I9DocumentHash(document),
			IndexVersion:     selection.IndexVersion,
			Visibility:       aiagent.EvidenceAuthorityVisibilityCurrent,
			MemoType:         aiagent.EvidenceAuthorityMemoTypeComplete,
			RowState:         aiagent.EvidenceAuthorityRowStateNormal,
			LifecycleState:   aiagent.EvidenceAuthorityLifecycleCurrent,
			SnapshotRevision: snapshot.SnapshotRevision,
			AuthorityToken:   snapshot.AuthorityToken,
		})
	}
	if reader.mutateSnapshot != nil {
		reader.mutateSnapshot(&snapshot)
	}
	return snapshot, nil
}

type fakeR5I9ReaderFactory struct {
	mu             sync.Mutex
	calls          int
	callerID       int32
	binding        aiagent.EvidenceAuthorityContextBinding
	authorityToken string
	reader         *fakeR5I9Reader
	err            error
}

func (factory *fakeR5I9ReaderFactory) newReader(
	ctx context.Context,
	binding aiagent.EvidenceAuthorityContextBinding,
	authorityToken string,
) (aiagent.EvidenceCurrentAuthorityReader, error) {
	factory.mu.Lock()
	defer factory.mu.Unlock()
	factory.calls++
	factory.callerID = auth.GetUserID(ctx)
	factory.binding = binding
	factory.authorityToken = authorityToken
	if factory.err != nil || factory.reader == nil {
		return nil, factory.err
	}
	factory.reader.configure(binding, authorityToken)
	return factory.reader, nil
}

type r5I9Harness struct {
	clock         *fakeEvidenceAuthorityCapabilityClock
	scope         *fakeEvidenceAuthorityCapabilityScopeSource
	registry      *evidenceAuthorityCapabilityRegistry
	replay        *evidenceRehydrationRequestReplayStore
	reader        *fakeR5I9Reader
	readerFactory *fakeR5I9ReaderFactory
	composition   *evidenceRehydrationComposition
}

func newR5I9Harness(t *testing.T, authorizedUIDs ...string) *r5I9Harness {
	t.Helper()
	clock := &fakeEvidenceAuthorityCapabilityClock{now: r5I8Now}
	scope := r5I8Scope(17, authorizedUIDs...)
	registry := newR5I8Registry(
		t,
		8,
		30*time.Second,
		clock,
		&fakeEvidenceAuthorityCapabilityTokenSource{},
		scope,
	)
	replay, err := newEvidenceRehydrationRequestReplayStore(8)
	require.NoError(t, err)
	reader := &fakeR5I9Reader{}
	readerFactory := &fakeR5I9ReaderFactory{reader: reader}
	composition, err := newEvidenceRehydrationComposition(
		r5I9Secret,
		60*time.Second,
		clock,
		replay,
		registry,
		readerFactory.newReader,
	)
	require.NoError(t, err)
	return &r5I9Harness{
		clock:         clock,
		scope:         scope,
		registry:      registry,
		replay:        replay,
		reader:        reader,
		readerFactory: readerFactory,
		composition:   composition,
	}
}

func (harness *r5I9Harness) issuePreparedRequest(
	t *testing.T,
	nonce string,
	requestedUIDs ...string,
) (aiagent.EvidenceRehydrationRequest, []byte, aiagent.EvidenceRehydrationRequestHeaders) {
	t.Helper()
	grant, err := harness.registry.issue(r5I8AuthenticatedContext(17))
	require.NoError(t, err)
	request := r5I9Request(grant.memosAuthorityRef, requestedUIDs...)
	body, headers := r5I9PrepareRequest(t, request, nonce, harness.clock.now, r5I9Secret)
	return request, body, headers
}

func r5I9Request(authorityRef string, uids ...string) aiagent.EvidenceRehydrationRequest {
	request := aiagent.EvidenceRehydrationRequest{
		Version:           "memo-evidence-rehydration-v1",
		SnapshotToken:     "r5-i9-derived-snapshot-token-000001",
		MemosAuthorityRef: authorityRef,
		Selections:        make([]aiagent.EvidenceRehydrationSelection, 0, len(uids)),
	}
	for index, uid := range uids {
		document := r5I9Document(uid)
		request.Selections = append(request.Selections, aiagent.EvidenceRehydrationSelection{
			SelectionRef:   fmt.Sprintf("rehydration-%d", index+1),
			MemoUID:        uid,
			SourceSequence: int64(index + 11),
			DocumentHash:   r5I9DocumentHash(document),
			IndexVersion:   "memo-v1",
		})
	}
	return request
}

func r5I9Document(uid string) string {
	return "# Synthetic R5-I9\n\nCurrent Memos authority for " + uid + "."
}

func r5I9DocumentHash(document string) string {
	digest := sha256.Sum256([]byte(document))
	return fmt.Sprintf("%x", digest)
}

func r5I9PrepareRequest(
	t *testing.T,
	request aiagent.EvidenceRehydrationRequest,
	nonce string,
	at time.Time,
	secret string,
) ([]byte, aiagent.EvidenceRehydrationRequestHeaders) {
	t.Helper()
	body, err := json.Marshal(request)
	require.NoError(t, err)
	timestamp := strconvFormatUnix(at)
	digest := sha256.Sum256(body)
	canonical := strings.Join([]string{
		"devmemo-agent-evidence-rehydration-v1",
		"memo-evidence-rehydration-transport-v1",
		"POST",
		aiagent.InternalEvidenceRehydrationPath,
		timestamp,
		nonce,
		fmt.Sprintf("%x", digest),
	}, "\n")
	mac := hmac.New(sha256.New, []byte(secret))
	_, _ = mac.Write([]byte(canonical))
	return body, aiagent.EvidenceRehydrationRequestHeaders{
		Signature: "sha256=" + fmt.Sprintf("%x", mac.Sum(nil)),
		Timestamp: timestamp,
		Nonce:     nonce,
		Version:   "memo-evidence-rehydration-transport-v1",
	}
}

func strconvFormatUnix(at time.Time) string {
	return fmt.Sprintf("%d", at.UTC().Unix())
}

func assertR5I9SignedResult(
	t *testing.T,
	result evidenceRehydrationCompositionResult,
	request aiagent.EvidenceRehydrationRequest,
	requestNonce string,
	at time.Time,
	statusCode int,
) {
	t.Helper()
	require.Equal(t, statusCode, result.statusCode)
	expected, err := aiagent.SignEvidenceRehydrationResponse(
		result.body,
		statusCode,
		at,
		requestNonce,
		request,
		r5I9Secret,
	)
	require.NoError(t, err)
	require.Equal(t, expected, result.headers)
	parsed, err := aiagent.ParseEvidenceRehydrationResponse(result.body, statusCode, request)
	require.NoError(t, err)
	if statusCode == 503 {
		require.True(t, parsed.IsFailure)
		require.Equal(t, evidenceRehydrationCompositionFailureBody, string(result.body))
	}
}

func assertR5I9Unavailable(t *testing.T, err error) {
	t.Helper()
	require.EqualError(t, err, "authorized retrieval unavailable")
	for _, forbidden := range []string{
		"memo", "caller", "identity", "visibility", "scope", "authority", "token",
		"secret", "SQL", "endpoint", "private", "signature", "nonce",
	} {
		require.NotContains(t, err.Error(), forbidden)
	}
}

func TestEvidenceRehydrationCompositionBuildsExactSignedSuccess(t *testing.T) {
	harness := newR5I9Harness(t, "memo-visible-one", "memo-visible-two", "memo-visible-three")
	request, body, headers := harness.issuePreparedRequest(
		t,
		"r5-i9-success-nonce-0001",
		"memo-visible-two",
		"memo-visible-one",
	)
	entry, ok := harness.registry.byRef[request.MemosAuthorityRef]
	require.True(t, ok)
	require.True(t, validEvidenceAuthorityCapabilityRequest(request, entry.authorizedMemoUIDs))
	require.True(t, validEvidenceRehydrationCompositionResolution(
		request,
		evidenceAuthorityCapabilityResolution{
			callerID:           entry.callerID,
			authorizedMemoUIDs: append([]string(nil), entry.authorizedMemoUIDs...),
			binding: aiagent.EvidenceAuthorityContextBinding{
				MemosAuthorityRef:         entry.memosAuthorityRef,
				AuthenticatedContextToken: entry.authenticatedContextToken,
			},
			authorityToken: entry.authorityToken,
		},
	))

	result, err := harness.composition.handle(
		"POST",
		aiagent.InternalEvidenceRehydrationPath,
		body,
		headers,
	)
	require.NoError(t, err)
	assertR5I9SignedResult(t, result, request, headers.Nonce, harness.clock.now, 200)
	require.Equal(t, 1, harness.readerFactory.calls)
	require.Equal(t, int32(17), harness.readerFactory.callerID)
	require.Equal(t, 1, harness.reader.calls)
	require.Equal(t, request, harness.reader.lastRequest)
	require.Equal(t, harness.readerFactory.binding, harness.reader.lastBinding)

	parsed, err := aiagent.ParseEvidenceRehydrationResponse(result.body, 200, request)
	require.NoError(t, err)
	require.Equal(t, request.Selections[0].SelectionRef, parsed.Response.Documents[0].SelectionRef)
	require.Equal(t, request.Selections[1].SelectionRef, parsed.Response.Documents[1].SelectionRef)
	for _, forbidden := range []string{
		"memo_uid", "memos_authority_ref", "authenticated_context", "caller", "visibility", "scope",
	} {
		require.NotContains(t, string(result.body), forbidden)
	}
}

func TestEvidenceRehydrationCompositionVerifiesBeforeReplayOrAuthority(t *testing.T) {
	harness := newR5I9Harness(t, "memo-visible-one")
	request, body, headers := harness.issuePreparedRequest(t, "r5-i9-verify-nonce-0001", "memo-visible-one")
	tampered := headers
	tampered.Signature = "sha256=" + strings.Repeat("0", 64)

	result, err := harness.composition.handle(
		"POST",
		aiagent.InternalEvidenceRehydrationPath,
		body,
		tampered,
	)
	require.Equal(t, evidenceRehydrationCompositionResult{}, result)
	assertR5I9Unavailable(t, err)
	require.Empty(t, harness.replay.expiresAt)
	require.Zero(t, harness.readerFactory.calls)
	require.Zero(t, harness.reader.calls)

	result, err = harness.composition.handle(
		"POST",
		aiagent.InternalEvidenceRehydrationPath,
		body,
		headers,
	)
	require.NoError(t, err)
	assertR5I9SignedResult(t, result, request, headers.Nonce, harness.clock.now, 200)
}

func TestEvidenceRehydrationCompositionReplayDoesNotConsumeCapability(t *testing.T) {
	harness := newR5I9Harness(t, "memo-visible-one")
	firstRequest, firstBody, firstHeaders := harness.issuePreparedRequest(
		t,
		"r5-i9-replay-nonce-0001",
		"memo-visible-one",
	)
	first, err := harness.composition.handle(
		"POST",
		aiagent.InternalEvidenceRehydrationPath,
		firstBody,
		firstHeaders,
	)
	require.NoError(t, err)
	assertR5I9SignedResult(t, first, firstRequest, firstHeaders.Nonce, harness.clock.now, 200)

	secondRequest, secondBody, secondHeaders := harness.issuePreparedRequest(
		t,
		firstHeaders.Nonce,
		"memo-visible-one",
	)
	second, err := harness.composition.handle(
		"POST",
		aiagent.InternalEvidenceRehydrationPath,
		secondBody,
		secondHeaders,
	)
	require.NoError(t, err)
	assertR5I9SignedResult(t, second, secondRequest, secondHeaders.Nonce, harness.clock.now, 503)
	require.Equal(t, 1, harness.readerFactory.calls)

	freshBody, freshHeaders := r5I9PrepareRequest(
		t,
		secondRequest,
		"r5-i9-replay-nonce-0002",
		harness.clock.now,
		r5I9Secret,
	)
	third, err := harness.composition.handle(
		"POST",
		aiagent.InternalEvidenceRehydrationPath,
		freshBody,
		freshHeaders,
	)
	require.NoError(t, err)
	assertR5I9SignedResult(t, third, secondRequest, freshHeaders.Nonce, harness.clock.now, 200)
	require.Equal(t, 2, harness.readerFactory.calls)
}

func TestEvidenceRehydrationCompositionCapabilityIsSingleUseAcrossNonces(t *testing.T) {
	harness := newR5I9Harness(t, "memo-visible-one")
	request, firstBody, firstHeaders := harness.issuePreparedRequest(
		t,
		"r5-i9-capability-nonce-0001",
		"memo-visible-one",
	)
	first, err := harness.composition.handle(
		"POST",
		aiagent.InternalEvidenceRehydrationPath,
		firstBody,
		firstHeaders,
	)
	require.NoError(t, err)
	assertR5I9SignedResult(t, first, request, firstHeaders.Nonce, harness.clock.now, 200)

	secondBody, secondHeaders := r5I9PrepareRequest(
		t,
		request,
		"r5-i9-capability-nonce-0002",
		harness.clock.now,
		r5I9Secret,
	)
	second, err := harness.composition.handle(
		"POST",
		aiagent.InternalEvidenceRehydrationPath,
		secondBody,
		secondHeaders,
	)
	require.NoError(t, err)
	assertR5I9SignedResult(t, second, request, secondHeaders.Nonce, harness.clock.now, 503)
	require.Equal(t, 1, harness.readerFactory.calls)
	require.Equal(t, 1, harness.reader.calls)
}

func TestEvidenceRehydrationCompositionRejectsOutOfScopeBeforeReader(t *testing.T) {
	harness := newR5I9Harness(t, "memo-visible-one")
	grant, err := harness.registry.issue(r5I8AuthenticatedContext(17))
	require.NoError(t, err)
	outOfScope := r5I9Request(grant.memosAuthorityRef, "memo-not-authorized")
	body, headers := r5I9PrepareRequest(
		t,
		outOfScope,
		"r5-i9-scope-nonce-0001",
		harness.clock.now,
		r5I9Secret,
	)

	result, err := harness.composition.handle(
		"POST",
		aiagent.InternalEvidenceRehydrationPath,
		body,
		headers,
	)
	require.NoError(t, err)
	assertR5I9SignedResult(t, result, outOfScope, headers.Nonce, harness.clock.now, 503)
	require.Zero(t, harness.readerFactory.calls)

	allowed := r5I9Request(grant.memosAuthorityRef, "memo-visible-one")
	body, headers = r5I9PrepareRequest(
		t,
		allowed,
		"r5-i9-scope-nonce-0002",
		harness.clock.now,
		r5I9Secret,
	)
	result, err = harness.composition.handle(
		"POST",
		aiagent.InternalEvidenceRehydrationPath,
		body,
		headers,
	)
	require.NoError(t, err)
	assertR5I9SignedResult(t, result, allowed, headers.Nonce, harness.clock.now, 200)
}

func TestEvidenceRehydrationCompositionRejectsBindingAndTokenMismatch(t *testing.T) {
	tests := []struct {
		name   string
		mutate func(*aiagent.EvidenceCurrentAuthoritySnapshot)
	}{
		{
			name: "authenticated context binding",
			mutate: func(snapshot *aiagent.EvidenceCurrentAuthoritySnapshot) {
				snapshot.AuthenticatedContextToken = "mismatched-authenticated-context-0001"
			},
		},
		{
			name: "authority token",
			mutate: func(snapshot *aiagent.EvidenceCurrentAuthoritySnapshot) {
				snapshot.AuthorityToken = "mismatched-authority-token-0001"
			},
		},
	}
	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			harness := newR5I9Harness(t, "memo-visible-one")
			harness.reader.mutateSnapshot = test.mutate
			request, body, headers := harness.issuePreparedRequest(
				t,
				"r5-i9-mismatch-nonce-0001",
				"memo-visible-one",
			)
			result, err := harness.composition.handle(
				"POST",
				aiagent.InternalEvidenceRehydrationPath,
				body,
				headers,
			)
			require.NoError(t, err)
			assertR5I9SignedResult(t, result, request, headers.Nonce, harness.clock.now, 503)
			require.Equal(t, 1, harness.readerFactory.calls)
			require.Equal(t, 1, harness.reader.calls)
		})
	}
}

func TestEvidenceRehydrationCompositionCallsReaderAtMostOnceOnFailure(t *testing.T) {
	tests := []struct {
		name    string
		prepare func(*r5I9Harness)
	}{
		{
			name: "factory failure",
			prepare: func(harness *r5I9Harness) {
				harness.readerFactory.err = errors.New("private factory database detail")
			},
		},
		{
			name: "reader failure",
			prepare: func(harness *r5I9Harness) {
				harness.reader.err = errors.New("private reader SQL detail")
			},
		},
	}
	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			harness := newR5I9Harness(t, "memo-visible-one")
			test.prepare(harness)
			request, body, headers := harness.issuePreparedRequest(
				t,
				"r5-i9-reader-failure-0001",
				"memo-visible-one",
			)
			result, err := harness.composition.handle(
				"POST",
				aiagent.InternalEvidenceRehydrationPath,
				body,
				headers,
			)
			require.NoError(t, err)
			assertR5I9SignedResult(t, result, request, headers.Nonce, harness.clock.now, 503)
			require.Equal(t, 1, harness.readerFactory.calls)
			if test.name == "factory failure" {
				require.Zero(t, harness.reader.calls)
			} else {
				require.Equal(t, 1, harness.reader.calls)
			}
		})
	}
}

func TestEvidenceRehydrationCompositionConcurrentDuplicateEntersReaderOnce(t *testing.T) {
	harness := newR5I9Harness(t, "memo-visible-one")
	request, body, headers := harness.issuePreparedRequest(
		t,
		"r5-i9-concurrent-nonce-0001",
		"memo-visible-one",
	)
	results := make(chan evidenceRehydrationCompositionResult, 2)
	errors := make(chan error, 2)
	var wait sync.WaitGroup
	for range 2 {
		wait.Add(1)
		go func() {
			defer wait.Done()
			result, err := harness.composition.handle(
				"POST",
				aiagent.InternalEvidenceRehydrationPath,
				body,
				headers,
			)
			results <- result
			errors <- err
		}()
	}
	wait.Wait()
	close(results)
	close(errors)
	for err := range errors {
		require.NoError(t, err)
	}
	statuses := make([]int, 0, 2)
	for result := range results {
		statuses = append(statuses, result.statusCode)
		assertR5I9SignedResult(t, result, request, headers.Nonce, harness.clock.now, result.statusCode)
	}
	require.ElementsMatch(t, []int{200, 503}, statuses)
	require.Equal(t, 1, harness.readerFactory.calls)
	require.Equal(t, 1, harness.reader.calls)
}

func TestEvidenceRehydrationCompositionProcessLocalStoresResetIndependently(t *testing.T) {
	harness := newR5I9Harness(t, "memo-visible-one")
	firstRequest, firstBody, firstHeaders := harness.issuePreparedRequest(
		t,
		"r5-i9-restart-nonce-0001",
		"memo-visible-one",
	)
	first, err := harness.composition.handle(
		"POST",
		aiagent.InternalEvidenceRehydrationPath,
		firstBody,
		firstHeaders,
	)
	require.NoError(t, err)
	assertR5I9SignedResult(t, first, firstRequest, firstHeaders.Nonce, harness.clock.now, 200)

	secondRequest, secondBody, secondHeaders := harness.issuePreparedRequest(
		t,
		firstHeaders.Nonce,
		"memo-visible-one",
	)
	newReplay, err := newEvidenceRehydrationRequestReplayStore(8)
	require.NoError(t, err)
	newReplayComposition, err := newEvidenceRehydrationComposition(
		r5I9Secret,
		60*time.Second,
		harness.clock,
		newReplay,
		harness.registry,
		harness.readerFactory.newReader,
	)
	require.NoError(t, err)
	second, err := newReplayComposition.handle(
		"POST",
		aiagent.InternalEvidenceRehydrationPath,
		secondBody,
		secondHeaders,
	)
	require.NoError(t, err)
	assertR5I9SignedResult(t, second, secondRequest, secondHeaders.Nonce, harness.clock.now, 200)

	oldCapabilityRequest, oldCapabilityBody, oldCapabilityHeaders := harness.issuePreparedRequest(
		t,
		"r5-i9-restart-nonce-0002",
		"memo-visible-one",
	)
	newRegistry := newR5I8Registry(
		t,
		8,
		30*time.Second,
		harness.clock,
		&fakeEvidenceAuthorityCapabilityTokenSource{values: []string{"new-registry-entropy-000000000001"}},
		harness.scope,
	)
	thirdReplay, err := newEvidenceRehydrationRequestReplayStore(8)
	require.NoError(t, err)
	newRegistryComposition, err := newEvidenceRehydrationComposition(
		r5I9Secret,
		60*time.Second,
		harness.clock,
		thirdReplay,
		newRegistry,
		harness.readerFactory.newReader,
	)
	require.NoError(t, err)
	third, err := newRegistryComposition.handle(
		"POST",
		aiagent.InternalEvidenceRehydrationPath,
		oldCapabilityBody,
		oldCapabilityHeaders,
	)
	require.NoError(t, err)
	assertR5I9SignedResult(
		t,
		third,
		oldCapabilityRequest,
		oldCapabilityHeaders.Nonce,
		harness.clock.now,
		503,
	)
	require.Equal(t, 2, harness.readerFactory.calls)
}

func TestEvidenceRehydrationCompositionFixesTimeoutAndConstructorBounds(t *testing.T) {
	require.Equal(t, 5*time.Second, evidenceRehydrationFutureClientTimeout)
	require.False(t, evidenceRehydrationAutoRetry)

	harness := newR5I9Harness(t, "memo-visible-one")
	invalidReplayCapacities := []int{0, -1, maxEvidenceRehydrationRequestReplayCapacity + 1}
	for _, capacity := range invalidReplayCapacities {
		store, err := newEvidenceRehydrationRequestReplayStore(capacity)
		require.Nil(t, store)
		assertR5I9Unavailable(t, err)
	}

	tests := []struct {
		name     string
		secret   string
		maxAge   time.Duration
		clock    evidenceAuthorityCapabilityClock
		replay   *evidenceRehydrationRequestReplayStore
		registry *evidenceAuthorityCapabilityRegistry
		factory  evidenceRehydrationCurrentAuthorityReaderFactory
	}{
		{name: "blank secret", secret: " ", maxAge: time.Second, clock: harness.clock, replay: harness.replay, registry: harness.registry, factory: harness.readerFactory.newReader},
		{name: "zero max age", secret: r5I9Secret, maxAge: 0, clock: harness.clock, replay: harness.replay, registry: harness.registry, factory: harness.readerFactory.newReader},
		{name: "excess max age", secret: r5I9Secret, maxAge: 61 * time.Second, clock: harness.clock, replay: harness.replay, registry: harness.registry, factory: harness.readerFactory.newReader},
		{name: "fractional max age", secret: r5I9Secret, maxAge: time.Second + time.Millisecond, clock: harness.clock, replay: harness.replay, registry: harness.registry, factory: harness.readerFactory.newReader},
		{name: "nil clock", secret: r5I9Secret, maxAge: time.Second, replay: harness.replay, registry: harness.registry, factory: harness.readerFactory.newReader},
		{name: "nil replay", secret: r5I9Secret, maxAge: time.Second, clock: harness.clock, registry: harness.registry, factory: harness.readerFactory.newReader},
		{name: "nil registry", secret: r5I9Secret, maxAge: time.Second, clock: harness.clock, replay: harness.replay, factory: harness.readerFactory.newReader},
		{name: "nil factory", secret: r5I9Secret, maxAge: time.Second, clock: harness.clock, replay: harness.replay, registry: harness.registry},
	}
	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			composition, err := newEvidenceRehydrationComposition(
				test.secret,
				test.maxAge,
				test.clock,
				test.replay,
				test.registry,
				test.factory,
			)
			require.Nil(t, composition)
			assertR5I9Unavailable(t, err)
		})
	}
}

func TestEvidenceRehydrationCompositionClockFailureIsContentFree(t *testing.T) {
	harness := newR5I9Harness(t, "memo-visible-one")
	_, body, headers := harness.issuePreparedRequest(
		t,
		"r5-i9-clock-failure-0001",
		"memo-visible-one",
	)
	harness.clock.err = errors.New("private clock endpoint detail")

	result, err := harness.composition.handle(
		"POST",
		aiagent.InternalEvidenceRehydrationPath,
		body,
		headers,
	)
	require.Equal(t, evidenceRehydrationCompositionResult{}, result)
	assertR5I9Unavailable(t, err)
	require.Empty(t, harness.replay.expiresAt)
	require.Zero(t, harness.readerFactory.calls)
}
