package v1

import (
	"context"
	"crypto/rand"
	"crypto/sha256"
	"encoding/base64"
	"errors"
	"fmt"
	"math"
	"regexp"
	"strconv"
	"sync"
	"time"

	"github.com/usememos/memos/internal/aiagent"
	"github.com/usememos/memos/internal/base"
	"github.com/usememos/memos/server/auth"
)

const (
	maxEvidenceAuthorityCapabilityUIDs     = 1000
	maxEvidenceAuthorityCapabilityItems    = 10
	maxEvidenceAuthorityCapabilityTTL      = 60 * time.Second
	maxEvidenceAuthorityCapabilityCapacity = 4096
)

var (
	evidenceAuthorityCapabilityOpaquePattern  = regexp.MustCompile(`^[A-Za-z0-9][A-Za-z0-9_-]{31,63}$`)
	evidenceAuthorityCapabilityRefPattern     = regexp.MustCompile(`^rehydration-[1-9][0-9]*$`)
	evidenceAuthorityCapabilityHashPattern    = regexp.MustCompile(`^[0-9a-f]{64}$`)
	errEvidenceAuthorityCapabilityUnavailable = errors.New("authorized retrieval unavailable")
)

type evidenceAuthorityCapabilityClock interface {
	Now() (time.Time, error)
}

type evidenceAuthorityCapabilityTokenSource interface {
	Token() (string, error)
}

type evidenceAuthorityCapabilityScopeSource interface {
	ReadCurrentAuthorizedCompleteMemoScope(
		ctx context.Context,
		authenticatedCallerID int32,
	) (evidenceAuthorityCapabilityScope, error)
}

type evidenceAuthorityCapabilityScope struct {
	callerID           int32
	callerIsCurrent    bool
	authorizedMemoUIDs []string
}

// evidenceAuthorityCapabilityGrant is Memos-private. Only its opaque reference
// is intended to enter a later signed rehydration request.
type evidenceAuthorityCapabilityGrant struct {
	memosAuthorityRef string
}

// evidenceAuthorityCapabilityResolution is Memos-private and has no JSON
// projection. A future separately authorized handler may use it to reconstruct
// a server-owned auth context and the existing two-field R5-I6 binding.
type evidenceAuthorityCapabilityResolution struct {
	callerID           int32
	authorizedMemoUIDs []string
	binding            aiagent.EvidenceAuthorityContextBinding
	authorityToken     string
}

func (value evidenceAuthorityCapabilityResolution) authenticatedContext(parent context.Context) (context.Context, error) {
	if parent == nil || value.callerID == 0 {
		return nil, errEvidenceAuthorityCapabilityUnavailable
	}
	return context.WithValue(parent, auth.UserIDContextKey, value.callerID), nil
}

type evidenceAuthorityCapabilityEntry struct {
	callerID                  int32
	authorizedMemoUIDs        []string
	memosAuthorityRef         string
	authenticatedContextToken string
	authorityToken            string
	expiresAt                 time.Time
}

// evidenceAuthorityCapabilityRegistry is intentionally process-local. It has
// no timer, persistence, HTTP surface, runtime registration, or replay-store
// reuse. Restarting the process discards every capability.
type evidenceAuthorityCapabilityRegistry struct {
	mu              sync.Mutex
	capacity        int
	ttl             time.Duration
	clock           evidenceAuthorityCapabilityClock
	tokenSource     evidenceAuthorityCapabilityTokenSource
	scopeSource     evidenceAuthorityCapabilityScopeSource
	registryEntropy string
	sequence        uint64
	byRef           map[string]evidenceAuthorityCapabilityEntry
	contextToRef    map[string]string
	authorityToRef  map[string]string
}

func newEvidenceAuthorityCapabilityRegistry(
	capacity int,
	ttl time.Duration,
	clock evidenceAuthorityCapabilityClock,
	tokenSource evidenceAuthorityCapabilityTokenSource,
	scopeSource evidenceAuthorityCapabilityScopeSource,
) (*evidenceAuthorityCapabilityRegistry, error) {
	if capacity < 1 || capacity > maxEvidenceAuthorityCapabilityCapacity ||
		ttl <= 0 || ttl > maxEvidenceAuthorityCapabilityTTL ||
		clock == nil || tokenSource == nil || scopeSource == nil {
		return nil, errEvidenceAuthorityCapabilityUnavailable
	}
	registryEntropy, err := tokenSource.Token()
	if err != nil || !evidenceAuthorityCapabilityOpaquePattern.MatchString(registryEntropy) {
		return nil, errEvidenceAuthorityCapabilityUnavailable
	}
	return &evidenceAuthorityCapabilityRegistry{
		capacity:        capacity,
		ttl:             ttl,
		clock:           clock,
		tokenSource:     tokenSource,
		scopeSource:     scopeSource,
		registryEntropy: registryEntropy,
		byRef:           make(map[string]evidenceAuthorityCapabilityEntry, capacity),
		contextToRef:    make(map[string]string, capacity),
		authorityToRef:  make(map[string]string, capacity),
	}, nil
}

func (registry *evidenceAuthorityCapabilityRegistry) issue(
	ctx context.Context,
) (evidenceAuthorityCapabilityGrant, error) {
	if registry == nil || ctx == nil {
		return evidenceAuthorityCapabilityGrant{}, errEvidenceAuthorityCapabilityUnavailable
	}
	callerID := auth.GetUserID(ctx)
	if callerID <= 0 {
		return evidenceAuthorityCapabilityGrant{}, errEvidenceAuthorityCapabilityUnavailable
	}
	scope, err := registry.scopeSource.ReadCurrentAuthorizedCompleteMemoScope(ctx, callerID)
	if err != nil || scope.callerID != callerID || !scope.callerIsCurrent ||
		!validEvidenceAuthorityCapabilityUIDs(scope.authorizedMemoUIDs, maxEvidenceAuthorityCapabilityUIDs) {
		return evidenceAuthorityCapabilityGrant{}, errEvidenceAuthorityCapabilityUnavailable
	}

	registry.mu.Lock()
	defer registry.mu.Unlock()
	now, err := registry.clock.Now()
	if err != nil {
		return evidenceAuthorityCapabilityGrant{}, errEvidenceAuthorityCapabilityUnavailable
	}
	registry.removeExpired(now)
	if len(registry.byRef) >= registry.capacity || registry.sequence == math.MaxUint64 {
		return evidenceAuthorityCapabilityGrant{}, errEvidenceAuthorityCapabilityUnavailable
	}

	entropies := make([]string, 3)
	seenEntropy := make(map[string]struct{}, len(entropies))
	for index := range entropies {
		entropy, err := registry.tokenSource.Token()
		if err != nil || !evidenceAuthorityCapabilityOpaquePattern.MatchString(entropy) {
			return evidenceAuthorityCapabilityGrant{}, errEvidenceAuthorityCapabilityUnavailable
		}
		if _, duplicate := seenEntropy[entropy]; duplicate {
			return evidenceAuthorityCapabilityGrant{}, errEvidenceAuthorityCapabilityUnavailable
		}
		seenEntropy[entropy] = struct{}{}
		entropies[index] = entropy
	}

	nextSequence := registry.sequence + 1
	ref := deriveEvidenceAuthorityCapabilityToken("authority-ref", registry.registryEntropy, entropies[0], nextSequence)
	contextToken := deriveEvidenceAuthorityCapabilityToken("authenticated-context", registry.registryEntropy, entropies[1], nextSequence)
	authorityToken := deriveEvidenceAuthorityCapabilityToken("authority-token", registry.registryEntropy, entropies[2], nextSequence)
	if !validIndependentEvidenceAuthorityCapabilityTokens(ref, contextToken, authorityToken) ||
		registry.tokenInUse(ref) || registry.tokenInUse(contextToken) || registry.tokenInUse(authorityToken) {
		return evidenceAuthorityCapabilityGrant{}, errEvidenceAuthorityCapabilityUnavailable
	}

	entry := evidenceAuthorityCapabilityEntry{
		callerID:                  callerID,
		authorizedMemoUIDs:        append([]string(nil), scope.authorizedMemoUIDs...),
		memosAuthorityRef:         ref,
		authenticatedContextToken: contextToken,
		authorityToken:            authorityToken,
		expiresAt:                 now.Add(registry.ttl),
	}
	registry.byRef[ref] = entry
	registry.contextToRef[contextToken] = ref
	registry.authorityToRef[authorityToken] = ref
	registry.sequence = nextSequence
	return evidenceAuthorityCapabilityGrant{memosAuthorityRef: ref}, nil
}

func (registry *evidenceAuthorityCapabilityRegistry) consume(
	request aiagent.EvidenceRehydrationRequest,
) (evidenceAuthorityCapabilityResolution, error) {
	if registry == nil {
		return evidenceAuthorityCapabilityResolution{}, errEvidenceAuthorityCapabilityUnavailable
	}
	registry.mu.Lock()
	defer registry.mu.Unlock()
	now, err := registry.clock.Now()
	if err != nil {
		return evidenceAuthorityCapabilityResolution{}, errEvidenceAuthorityCapabilityUnavailable
	}
	registry.removeExpired(now)
	entry, ok := registry.byRef[request.MemosAuthorityRef]
	if !ok {
		return evidenceAuthorityCapabilityResolution{}, errEvidenceAuthorityCapabilityUnavailable
	}
	if !registry.validEntry(entry, now) {
		registry.removeEntry(entry)
		return evidenceAuthorityCapabilityResolution{}, errEvidenceAuthorityCapabilityUnavailable
	}
	if !validEvidenceAuthorityCapabilityRequest(request, entry.authorizedMemoUIDs) {
		return evidenceAuthorityCapabilityResolution{}, errEvidenceAuthorityCapabilityUnavailable
	}

	registry.removeEntry(entry)
	return evidenceAuthorityCapabilityResolution{
		callerID:           entry.callerID,
		authorizedMemoUIDs: append([]string(nil), entry.authorizedMemoUIDs...),
		binding: aiagent.EvidenceAuthorityContextBinding{
			MemosAuthorityRef:         entry.memosAuthorityRef,
			AuthenticatedContextToken: entry.authenticatedContextToken,
		},
		authorityToken: entry.authorityToken,
	}, nil
}

func (registry *evidenceAuthorityCapabilityRegistry) validEntry(
	entry evidenceAuthorityCapabilityEntry,
	now time.Time,
) bool {
	return entry.callerID > 0 && now.Before(entry.expiresAt) &&
		validEvidenceAuthorityCapabilityUIDs(entry.authorizedMemoUIDs, maxEvidenceAuthorityCapabilityUIDs) &&
		validIndependentEvidenceAuthorityCapabilityTokens(
			entry.memosAuthorityRef,
			entry.authenticatedContextToken,
			entry.authorityToken,
		) && registry.contextToRef[entry.authenticatedContextToken] == entry.memosAuthorityRef &&
		registry.authorityToRef[entry.authorityToken] == entry.memosAuthorityRef
}

func (registry *evidenceAuthorityCapabilityRegistry) tokenInUse(token string) bool {
	if _, found := registry.byRef[token]; found {
		return true
	}
	if _, found := registry.contextToRef[token]; found {
		return true
	}
	_, found := registry.authorityToRef[token]
	return found
}

func (registry *evidenceAuthorityCapabilityRegistry) removeExpired(now time.Time) {
	for _, entry := range registry.byRef {
		if !now.Before(entry.expiresAt) {
			registry.removeEntry(entry)
		}
	}
}

func (registry *evidenceAuthorityCapabilityRegistry) removeEntry(entry evidenceAuthorityCapabilityEntry) {
	delete(registry.byRef, entry.memosAuthorityRef)
	delete(registry.contextToRef, entry.authenticatedContextToken)
	delete(registry.authorityToRef, entry.authorityToken)
}

func validEvidenceAuthorityCapabilityRequest(
	request aiagent.EvidenceRehydrationRequest,
	authorizedMemoUIDs []string,
) bool {
	if request.Version != "memo-evidence-rehydration-v1" ||
		!evidenceAuthorityCapabilityOpaquePattern.MatchString(request.SnapshotToken) ||
		!evidenceAuthorityCapabilityOpaquePattern.MatchString(request.MemosAuthorityRef) ||
		len(request.Selections) < 1 || len(request.Selections) > maxEvidenceAuthorityCapabilityItems {
		return false
	}
	authorized := make(map[string]struct{}, len(authorizedMemoUIDs))
	for _, uid := range authorizedMemoUIDs {
		authorized[uid] = struct{}{}
	}
	seenRefs := make(map[string]struct{}, len(request.Selections))
	seenUIDs := make(map[string]struct{}, len(request.Selections))
	for _, selection := range request.Selections {
		if !evidenceAuthorityCapabilityRefPattern.MatchString(selection.SelectionRef) ||
			!base.UIDMatcher.MatchString(selection.MemoUID) || selection.SourceSequence < 1 ||
			!evidenceAuthorityCapabilityHashPattern.MatchString(selection.DocumentHash) ||
			selection.IndexVersion != "memo-v1" {
			return false
		}
		if _, allowed := authorized[selection.MemoUID]; !allowed {
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

func validEvidenceAuthorityCapabilityUIDs(uids []string, limit int) bool {
	if len(uids) < 1 || len(uids) > limit {
		return false
	}
	seen := make(map[string]struct{}, len(uids))
	for _, uid := range uids {
		if !base.UIDMatcher.MatchString(uid) {
			return false
		}
		if _, duplicate := seen[uid]; duplicate {
			return false
		}
		seen[uid] = struct{}{}
	}
	return true
}

func validIndependentEvidenceAuthorityCapabilityTokens(tokens ...string) bool {
	if len(tokens) != 3 {
		return false
	}
	seen := make(map[string]struct{}, len(tokens))
	for _, token := range tokens {
		if !evidenceAuthorityCapabilityOpaquePattern.MatchString(token) {
			return false
		}
		if _, duplicate := seen[token]; duplicate {
			return false
		}
		seen[token] = struct{}{}
	}
	return true
}

func deriveEvidenceAuthorityCapabilityToken(
	purpose string,
	registryEntropy string,
	entropy string,
	sequence uint64,
) string {
	digest := sha256.Sum256([]byte(
		purpose + "\x00" + registryEntropy + "\x00" + strconv.FormatUint(sequence, 10) + "\x00" + entropy,
	))
	return "t" + base64.RawURLEncoding.EncodeToString(digest[:])
}

type cryptoEvidenceAuthorityCapabilityTokenSource struct{}

func (cryptoEvidenceAuthorityCapabilityTokenSource) Token() (string, error) {
	value := make([]byte, 32)
	if _, err := rand.Read(value); err != nil {
		return "", fmt.Errorf("token source unavailable")
	}
	return "t" + base64.RawURLEncoding.EncodeToString(value), nil
}
