package v1

import (
	"context"
	"errors"
	"fmt"
	"reflect"
	"strings"
	"sync"
	"testing"
	"time"

	"github.com/stretchr/testify/require"

	"github.com/usememos/memos/internal/aiagent"
	"github.com/usememos/memos/server/auth"
)

var r5I8Now = time.Date(2026, 8, 2, 16, 0, 0, 0, time.FixedZone("UTC+8", 8*60*60))

type fakeEvidenceAuthorityCapabilityClock struct {
	mu  sync.Mutex
	now time.Time
	err error
}

func (clock *fakeEvidenceAuthorityCapabilityClock) Now() (time.Time, error) {
	clock.mu.Lock()
	defer clock.mu.Unlock()
	return clock.now, clock.err
}

func (clock *fakeEvidenceAuthorityCapabilityClock) advance(duration time.Duration) {
	clock.mu.Lock()
	defer clock.mu.Unlock()
	clock.now = clock.now.Add(duration)
}

type fakeEvidenceAuthorityCapabilityTokenSource struct {
	mu       sync.Mutex
	values   []string
	failCall int
	calls    int
}

func (source *fakeEvidenceAuthorityCapabilityTokenSource) Token() (string, error) {
	source.mu.Lock()
	defer source.mu.Unlock()
	source.calls++
	if source.failCall == source.calls {
		return "", errors.New("private token source secret")
	}
	if len(source.values) >= source.calls {
		return source.values[source.calls-1], nil
	}
	return fmt.Sprintf("synthetic-token-%032d", source.calls), nil
}

type fakeEvidenceAuthorityCapabilityScopeSource struct {
	mu       sync.Mutex
	scope    evidenceAuthorityCapabilityScope
	err      error
	calls    int
	callerID int32
}

func (source *fakeEvidenceAuthorityCapabilityScopeSource) ReadCurrentAuthorizedCompleteMemoScope(
	_ context.Context,
	callerID int32,
) (evidenceAuthorityCapabilityScope, error) {
	source.mu.Lock()
	defer source.mu.Unlock()
	source.calls++
	source.callerID = callerID
	result := source.scope
	result.authorizedMemoUIDs = append([]string(nil), source.scope.authorizedMemoUIDs...)
	return result, source.err
}

func newR5I8Registry(
	t *testing.T,
	capacity int,
	ttl time.Duration,
	clock *fakeEvidenceAuthorityCapabilityClock,
	tokens *fakeEvidenceAuthorityCapabilityTokenSource,
	scope *fakeEvidenceAuthorityCapabilityScopeSource,
) *evidenceAuthorityCapabilityRegistry {
	t.Helper()
	registry, err := newEvidenceAuthorityCapabilityRegistry(capacity, ttl, clock, tokens, scope)
	require.NoError(t, err)
	return registry
}

func r5I8AuthenticatedContext(callerID int32) context.Context {
	return context.WithValue(context.Background(), auth.UserIDContextKey, callerID)
}

func r5I8Scope(callerID int32, uids ...string) *fakeEvidenceAuthorityCapabilityScopeSource {
	return &fakeEvidenceAuthorityCapabilityScopeSource{
		scope: evidenceAuthorityCapabilityScope{
			callerID:           callerID,
			callerIsCurrent:    true,
			authorizedMemoUIDs: append([]string(nil), uids...),
		},
	}
}

func r5I8Request(ref string, uids ...string) aiagent.EvidenceRehydrationRequest {
	selections := make([]aiagent.EvidenceRehydrationSelection, 0, len(uids))
	for index, uid := range uids {
		selections = append(selections, aiagent.EvidenceRehydrationSelection{
			SelectionRef:   fmt.Sprintf("rehydration-%d", index+1),
			MemoUID:        uid,
			SourceSequence: int64(index + 1),
			DocumentHash:   strings.Repeat(fmt.Sprintf("%x", (index+1)%16), 64),
			IndexVersion:   "memo-v1",
		})
	}
	return aiagent.EvidenceRehydrationRequest{
		Version:           "memo-evidence-rehydration-v1",
		SnapshotToken:     "snapshot-capability-synthetic-0001",
		MemosAuthorityRef: ref,
		Selections:        selections,
	}
}

func assertR5I8Unavailable(t *testing.T, err error) {
	t.Helper()
	require.EqualError(t, err, "authorized retrieval unavailable")
	for _, forbidden := range []string{
		"memo", "caller", "identity", "visibility", "scope", "authority", "token",
		"secret", "SQL", "endpoint", "private",
	} {
		require.NotContains(t, err.Error(), forbidden)
	}
}

func TestEvidenceAuthorityCapabilityIssuesAndConsumesExactPrivateBinding(t *testing.T) {
	clock := &fakeEvidenceAuthorityCapabilityClock{now: r5I8Now}
	tokens := &fakeEvidenceAuthorityCapabilityTokenSource{}
	scope := r5I8Scope(17, "memo-visible-one", "memo-visible-two", "memo-visible-three")
	registry := newR5I8Registry(t, 4, 30*time.Second, clock, tokens, scope)

	grant, err := registry.issue(r5I8AuthenticatedContext(17))
	require.NoError(t, err)
	require.Equal(t, 1, scope.calls)
	require.Equal(t, int32(17), scope.callerID)
	require.True(t, evidenceAuthorityCapabilityOpaquePattern.MatchString(grant.memosAuthorityRef))

	resolution, err := registry.consume(r5I8Request(
		grant.memosAuthorityRef,
		"memo-visible-two",
		"memo-visible-one",
	))
	require.NoError(t, err)
	restoredContext, err := resolution.authenticatedContext(context.Background())
	require.NoError(t, err)
	require.Equal(t, int32(17), auth.GetUserID(restoredContext))
	require.Equal(t, []string{"memo-visible-one", "memo-visible-two", "memo-visible-three"}, resolution.authorizedMemoUIDs)
	require.Equal(t, grant.memosAuthorityRef, resolution.binding.MemosAuthorityRef)
	require.True(t, evidenceAuthorityCapabilityOpaquePattern.MatchString(resolution.binding.AuthenticatedContextToken))
	require.True(t, evidenceAuthorityCapabilityOpaquePattern.MatchString(resolution.authorityToken))
	require.NotEqual(t, grant.memosAuthorityRef, resolution.binding.AuthenticatedContextToken)
	require.NotEqual(t, grant.memosAuthorityRef, resolution.authorityToken)
	require.NotEqual(t, resolution.binding.AuthenticatedContextToken, resolution.authorityToken)

	second, err := registry.consume(r5I8Request(grant.memosAuthorityRef, "memo-visible-one"))
	require.Equal(t, evidenceAuthorityCapabilityResolution{}, second)
	assertR5I8Unavailable(t, err)
}

func TestEvidenceAuthorityCapabilityHasNoCallerControlledIssueFieldsOrProjection(t *testing.T) {
	issueType := reflect.TypeOf((*evidenceAuthorityCapabilityRegistry).issue)
	require.Equal(t, 2, issueType.NumIn())
	require.Equal(t, reflect.TypeOf((*context.Context)(nil)).Elem(), issueType.In(1))

	grantType := reflect.TypeOf(evidenceAuthorityCapabilityGrant{})
	require.Equal(t, 1, grantType.NumField())
	require.Equal(t, "memosAuthorityRef", grantType.Field(0).Name)
	require.False(t, grantType.Field(0).IsExported())

	bindingType := reflect.TypeOf(aiagent.EvidenceAuthorityContextBinding{})
	require.Equal(t, 2, bindingType.NumField())
	require.Equal(t, "MemosAuthorityRef", bindingType.Field(0).Name)
	require.Equal(t, "AuthenticatedContextToken", bindingType.Field(1).Name)
}

func TestEvidenceAuthorityCapabilityRequiresCurrentMemosAuthenticatedCaller(t *testing.T) {
	tests := []struct {
		name    string
		ctx     context.Context
		prepare func(*fakeEvidenceAuthorityCapabilityScopeSource)
	}{
		{name: "missing auth context", ctx: context.Background()},
		{name: "wrong auth context type", ctx: context.WithValue(context.Background(), auth.UserIDContextKey, "17")},
		{name: "invalid negative caller", ctx: r5I8AuthenticatedContext(-1)},
		{name: "unknown caller", ctx: r5I8AuthenticatedContext(17), prepare: func(scope *fakeEvidenceAuthorityCapabilityScopeSource) {
			scope.scope.callerIsCurrent = false
		}},
		{name: "archived caller", ctx: r5I8AuthenticatedContext(17), prepare: func(scope *fakeEvidenceAuthorityCapabilityScopeSource) {
			scope.scope.callerIsCurrent = false
		}},
		{name: "caller binding mismatch", ctx: r5I8AuthenticatedContext(17), prepare: func(scope *fakeEvidenceAuthorityCapabilityScopeSource) {
			scope.scope.callerID = 18
		}},
		{name: "Memos authority failure", ctx: r5I8AuthenticatedContext(17), prepare: func(scope *fakeEvidenceAuthorityCapabilityScopeSource) {
			scope.err = errors.New("caller identity visibility database detail")
		}},
	}

	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			scope := r5I8Scope(17, "memo-visible")
			if test.prepare != nil {
				test.prepare(scope)
			}
			registry := newR5I8Registry(
				t, 2, 30*time.Second,
				&fakeEvidenceAuthorityCapabilityClock{now: r5I8Now},
				&fakeEvidenceAuthorityCapabilityTokenSource{},
				scope,
			)
			grant, err := registry.issue(test.ctx)
			require.Equal(t, evidenceAuthorityCapabilityGrant{}, grant)
			assertR5I8Unavailable(t, err)
		})
	}
}

func TestEvidenceAuthorityCapabilityRequiresBoundedExactMemosScope(t *testing.T) {
	overLimit := make([]string, maxEvidenceAuthorityCapabilityUIDs+1)
	for index := range overLimit {
		overLimit[index] = fmt.Sprintf("memo-%d", index)
	}
	tests := []struct {
		name string
		uids []string
	}{
		{name: "nil", uids: nil},
		{name: "empty", uids: []string{}},
		{name: "malformed", uids: []string{"memo_bad"}},
		{name: "duplicate", uids: []string{"memo-one", "memo-one"}},
		{name: "over limit", uids: overLimit},
	}
	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			registry := newR5I8Registry(
				t, 2, 30*time.Second,
				&fakeEvidenceAuthorityCapabilityClock{now: r5I8Now},
				&fakeEvidenceAuthorityCapabilityTokenSource{},
				r5I8Scope(17, test.uids...),
			)
			grant, err := registry.issue(r5I8AuthenticatedContext(17))
			require.Equal(t, evidenceAuthorityCapabilityGrant{}, grant)
			assertR5I8Unavailable(t, err)
		})
	}
}

func TestEvidenceAuthorityCapabilityAcceptsExactR5I1ScopeLimit(t *testing.T) {
	uids := make([]string, maxEvidenceAuthorityCapabilityUIDs)
	for index := range uids {
		uids[index] = fmt.Sprintf("memo-%d", index)
	}
	registry := newR5I8Registry(
		t, 1, maxEvidenceAuthorityCapabilityTTL,
		&fakeEvidenceAuthorityCapabilityClock{now: r5I8Now},
		&fakeEvidenceAuthorityCapabilityTokenSource{},
		r5I8Scope(17, uids...),
	)
	grant, err := registry.issue(r5I8AuthenticatedContext(17))
	require.NoError(t, err)
	resolution, err := registry.consume(r5I8Request(grant.memosAuthorityRef, uids[len(uids)-1]))
	require.NoError(t, err)
	require.Len(t, resolution.authorizedMemoUIDs, maxEvidenceAuthorityCapabilityUIDs)
}

func TestEvidenceAuthorityCapabilityConsumeRequiresBoundedAuthorizedSubset(t *testing.T) {
	tests := []struct {
		name   string
		mutate func(aiagent.EvidenceRehydrationRequest) aiagent.EvidenceRehydrationRequest
	}{
		{name: "missing selection", mutate: func(request aiagent.EvidenceRehydrationRequest) aiagent.EvidenceRehydrationRequest {
			request.Selections = nil
			return request
		}},
		{name: "unknown extra uid", mutate: func(request aiagent.EvidenceRehydrationRequest) aiagent.EvidenceRehydrationRequest {
			request.Selections[0].MemoUID = "memo-unknown"
			return request
		}},
		{name: "missing uid", mutate: func(request aiagent.EvidenceRehydrationRequest) aiagent.EvidenceRehydrationRequest {
			request.Selections[0].MemoUID = ""
			return request
		}},
		{name: "duplicate uid", mutate: func(request aiagent.EvidenceRehydrationRequest) aiagent.EvidenceRehydrationRequest {
			request.Selections = append(request.Selections, request.Selections[0])
			request.Selections[1].SelectionRef = "rehydration-2"
			return request
		}},
		{name: "duplicate selection ref", mutate: func(request aiagent.EvidenceRehydrationRequest) aiagent.EvidenceRehydrationRequest {
			request.Selections = append(request.Selections, request.Selections[0])
			request.Selections[1].MemoUID = "memo-visible-two"
			return request
		}},
		{name: "authority ref mismatch", mutate: func(request aiagent.EvidenceRehydrationRequest) aiagent.EvidenceRehydrationRequest {
			request.MemosAuthorityRef = "unknown-authority-reference-000001"
			return request
		}},
		{name: "over selection limit", mutate: func(request aiagent.EvidenceRehydrationRequest) aiagent.EvidenceRehydrationRequest {
			request.Selections = nil
			for index := 0; index < maxEvidenceAuthorityCapabilityItems+1; index++ {
				selection := r5I8Request(request.MemosAuthorityRef, fmt.Sprintf("memo-visible-%d", index)).Selections[0]
				selection.SelectionRef = fmt.Sprintf("rehydration-%d", index+1)
				request.Selections = append(request.Selections, selection)
			}
			return request
		}},
	}

	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			scope := r5I8Scope(17, "memo-visible-one", "memo-visible-two")
			registry := newR5I8Registry(
				t, 2, 30*time.Second,
				&fakeEvidenceAuthorityCapabilityClock{now: r5I8Now},
				&fakeEvidenceAuthorityCapabilityTokenSource{},
				scope,
			)
			grant, err := registry.issue(r5I8AuthenticatedContext(17))
			require.NoError(t, err)
			request := test.mutate(r5I8Request(grant.memosAuthorityRef, "memo-visible-one"))
			resolution, err := registry.consume(request)
			require.Equal(t, evidenceAuthorityCapabilityResolution{}, resolution)
			assertR5I8Unavailable(t, err)

			// A failed validation returns no partial binding and does not make a
			// later exact request resolve to a broader scope.
			resolution, err = registry.consume(r5I8Request(grant.memosAuthorityRef, "memo-visible-one"))
			require.NoError(t, err)
			require.Equal(t, []string{"memo-visible-one", "memo-visible-two"}, resolution.authorizedMemoUIDs)
		})
	}
}

func TestEvidenceAuthorityCapabilityExpiryCapacityAndReuseAreFailClosed(t *testing.T) {
	clock := &fakeEvidenceAuthorityCapabilityClock{now: r5I8Now}
	registry := newR5I8Registry(
		t, 1, 10*time.Second, clock,
		&fakeEvidenceAuthorityCapabilityTokenSource{},
		r5I8Scope(17, "memo-visible"),
	)
	first, err := registry.issue(r5I8AuthenticatedContext(17))
	require.NoError(t, err)

	_, err = registry.issue(r5I8AuthenticatedContext(17))
	assertR5I8Unavailable(t, err)
	clock.advance(10 * time.Second)
	resolution, err := registry.consume(r5I8Request(first.memosAuthorityRef, "memo-visible"))
	require.Equal(t, evidenceAuthorityCapabilityResolution{}, resolution)
	assertR5I8Unavailable(t, err)

	replacement, err := registry.issue(r5I8AuthenticatedContext(17))
	require.NoError(t, err)
	require.NotEqual(t, first.memosAuthorityRef, replacement.memosAuthorityRef)
	resolution, err = registry.consume(r5I8Request(first.memosAuthorityRef, "memo-visible"))
	require.Equal(t, evidenceAuthorityCapabilityResolution{}, resolution)
	assertR5I8Unavailable(t, err)
	_, err = registry.consume(r5I8Request(replacement.memosAuthorityRef, "memo-visible"))
	require.NoError(t, err)
}

func TestEvidenceAuthorityCapabilityMapsClockAndTokenFailures(t *testing.T) {
	scope := r5I8Scope(17, "memo-visible")
	_, err := newEvidenceAuthorityCapabilityRegistry(
		1, 30*time.Second,
		&fakeEvidenceAuthorityCapabilityClock{now: r5I8Now},
		&fakeEvidenceAuthorityCapabilityTokenSource{failCall: 1},
		scope,
	)
	assertR5I8Unavailable(t, err)

	for _, test := range []struct {
		name   string
		tokens *fakeEvidenceAuthorityCapabilityTokenSource
	}{
		{name: "generation failure", tokens: &fakeEvidenceAuthorityCapabilityTokenSource{failCall: 3}},
		{name: "malformed token", tokens: &fakeEvidenceAuthorityCapabilityTokenSource{values: []string{
			"synthetic-registry-entropy-00000001", "short",
		}}},
		{name: "token collision", tokens: &fakeEvidenceAuthorityCapabilityTokenSource{values: []string{
			"synthetic-registry-entropy-00000001",
			"synthetic-colliding-entropy-00000001",
			"synthetic-colliding-entropy-00000001",
		}}},
	} {
		t.Run(test.name, func(t *testing.T) {
			registry := newR5I8Registry(
				t, 1, 30*time.Second,
				&fakeEvidenceAuthorityCapabilityClock{now: r5I8Now},
				test.tokens,
				scope,
			)
			grant, err := registry.issue(r5I8AuthenticatedContext(17))
			require.Equal(t, evidenceAuthorityCapabilityGrant{}, grant)
			assertR5I8Unavailable(t, err)
		})
	}

	clock := &fakeEvidenceAuthorityCapabilityClock{now: r5I8Now}
	registry := newR5I8Registry(t, 1, 30*time.Second, clock, &fakeEvidenceAuthorityCapabilityTokenSource{}, scope)
	clock.err = errors.New("private clock failure")
	_, err = registry.issue(r5I8AuthenticatedContext(17))
	assertR5I8Unavailable(t, err)

	clock.err = nil
	grant, err := registry.issue(r5I8AuthenticatedContext(17))
	require.NoError(t, err)
	clock.err = errors.New("private clock failure")
	resolution, err := registry.consume(r5I8Request(grant.memosAuthorityRef, "memo-visible"))
	require.Equal(t, evidenceAuthorityCapabilityResolution{}, resolution)
	assertR5I8Unavailable(t, err)
}

func TestEvidenceAuthorityCapabilityRejectsInvalidRegistryBounds(t *testing.T) {
	clock := &fakeEvidenceAuthorityCapabilityClock{now: r5I8Now}
	tokens := &fakeEvidenceAuthorityCapabilityTokenSource{}
	scope := r5I8Scope(17, "memo-visible")
	for _, test := range []struct {
		name     string
		capacity int
		ttl      time.Duration
	}{
		{name: "zero capacity", capacity: 0, ttl: time.Second},
		{name: "excess capacity", capacity: maxEvidenceAuthorityCapabilityCapacity + 1, ttl: time.Second},
		{name: "zero ttl", capacity: 1, ttl: 0},
		{name: "excess ttl", capacity: 1, ttl: maxEvidenceAuthorityCapabilityTTL + time.Nanosecond},
	} {
		t.Run(test.name, func(t *testing.T) {
			registry, err := newEvidenceAuthorityCapabilityRegistry(test.capacity, test.ttl, clock, tokens, scope)
			require.Nil(t, registry)
			assertR5I8Unavailable(t, err)
		})
	}
}

func TestEvidenceAuthorityCapabilityRejectsUnknownOrInternalTokenMismatch(t *testing.T) {
	registry := newR5I8Registry(
		t, 2, 30*time.Second,
		&fakeEvidenceAuthorityCapabilityClock{now: r5I8Now},
		&fakeEvidenceAuthorityCapabilityTokenSource{},
		r5I8Scope(17, "memo-visible"),
	)
	unknown, err := registry.consume(r5I8Request("unknown-authority-reference-000001", "memo-visible"))
	require.Equal(t, evidenceAuthorityCapabilityResolution{}, unknown)
	assertR5I8Unavailable(t, err)

	for _, tokenIndex := range []string{"authenticated context", "authority"} {
		t.Run(tokenIndex, func(t *testing.T) {
			registry := newR5I8Registry(
				t, 2, 30*time.Second,
				&fakeEvidenceAuthorityCapabilityClock{now: r5I8Now},
				&fakeEvidenceAuthorityCapabilityTokenSource{},
				r5I8Scope(17, "memo-visible"),
			)
			grant, err := registry.issue(r5I8AuthenticatedContext(17))
			require.NoError(t, err)
			entry := registry.byRef[grant.memosAuthorityRef]
			if tokenIndex == "authenticated context" {
				registry.contextToRef[entry.authenticatedContextToken] = "mismatched-authority-reference-0001"
			} else {
				registry.authorityToRef[entry.authorityToken] = "mismatched-authority-reference-0001"
			}
			resolution, err := registry.consume(r5I8Request(grant.memosAuthorityRef, "memo-visible"))
			require.Equal(t, evidenceAuthorityCapabilityResolution{}, resolution)
			assertR5I8Unavailable(t, err)
			_, found := registry.byRef[grant.memosAuthorityRef]
			require.False(t, found)
		})
	}
}

func TestEvidenceAuthorityCapabilityConsumeIsAtomicAndAtMostOnce(t *testing.T) {
	registry := newR5I8Registry(
		t, 2, 30*time.Second,
		&fakeEvidenceAuthorityCapabilityClock{now: r5I8Now},
		&fakeEvidenceAuthorityCapabilityTokenSource{},
		r5I8Scope(17, "memo-visible"),
	)
	grant, err := registry.issue(r5I8AuthenticatedContext(17))
	require.NoError(t, err)
	request := r5I8Request(grant.memosAuthorityRef, "memo-visible")

	const attempts = 24
	start := make(chan struct{})
	results := make(chan error, attempts)
	for index := 0; index < attempts; index++ {
		go func() {
			<-start
			_, err := registry.consume(request)
			results <- err
		}()
	}
	close(start)
	successes := 0
	for index := 0; index < attempts; index++ {
		if err := <-results; err == nil {
			successes++
		} else {
			assertR5I8Unavailable(t, err)
		}
	}
	require.Equal(t, 1, successes)
}

func TestEvidenceAuthorityCapabilityNewRegistryInvalidatesOldReference(t *testing.T) {
	first := newR5I8Registry(
		t, 2, 30*time.Second,
		&fakeEvidenceAuthorityCapabilityClock{now: r5I8Now},
		&fakeEvidenceAuthorityCapabilityTokenSource{},
		r5I8Scope(17, "memo-visible"),
	)
	grant, err := first.issue(r5I8AuthenticatedContext(17))
	require.NoError(t, err)

	restarted := newR5I8Registry(
		t, 2, 30*time.Second,
		&fakeEvidenceAuthorityCapabilityClock{now: r5I8Now},
		&fakeEvidenceAuthorityCapabilityTokenSource{values: []string{"different-registry-entropy-00000000001"}},
		r5I8Scope(17, "memo-visible"),
	)
	resolution, err := restarted.consume(r5I8Request(grant.memosAuthorityRef, "memo-visible"))
	require.Equal(t, evidenceAuthorityCapabilityResolution{}, resolution)
	assertR5I8Unavailable(t, err)
}

func TestCryptoEvidenceAuthorityCapabilityTokenSourceReturnsOpaqueIndependentValues(t *testing.T) {
	source := cryptoEvidenceAuthorityCapabilityTokenSource{}
	first, err := source.Token()
	require.NoError(t, err)
	second, err := source.Token()
	require.NoError(t, err)
	require.True(t, evidenceAuthorityCapabilityOpaquePattern.MatchString(first))
	require.True(t, evidenceAuthorityCapabilityOpaquePattern.MatchString(second))
	require.NotEqual(t, first, second)
}
