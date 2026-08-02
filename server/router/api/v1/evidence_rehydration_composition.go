package v1

import (
	"context"
	"encoding/json"
	"errors"
	"regexp"
	"strconv"
	"strings"
	"sync"
	"time"

	"github.com/usememos/memos/internal/aiagent"
)

const (
	maxEvidenceRehydrationRequestReplayCapacity = 4096
	maxEvidenceRehydrationCompositionAge        = 60 * time.Second
	evidenceRehydrationFutureClientTimeout      = 5 * time.Second
	evidenceRehydrationAutoRetry                = false
	evidenceRehydrationCompositionFailureBody   = `{"error_code":"authorized_retrieval_unavailable"}`
)

var (
	evidenceRehydrationCompositionNoncePattern   = regexp.MustCompile(`^[A-Za-z0-9_-]{16,128}$`)
	errEvidenceRehydrationCompositionUnavailable = errors.New("authorized retrieval unavailable")
)

// evidenceRehydrationRequestReplayStore is a dedicated process-local request
// replay boundary. It is intentionally distinct from the authority capability
// registry and has no timer or persistence.
type evidenceRehydrationRequestReplayStore struct {
	mu        sync.Mutex
	capacity  int
	expiresAt map[string]int64
}

func newEvidenceRehydrationRequestReplayStore(capacity int) (*evidenceRehydrationRequestReplayStore, error) {
	if capacity < 1 || capacity > maxEvidenceRehydrationRequestReplayCapacity {
		return nil, errEvidenceRehydrationCompositionUnavailable
	}
	return &evidenceRehydrationRequestReplayStore{
		capacity:  capacity,
		expiresAt: make(map[string]int64, capacity),
	}, nil
}

func (store *evidenceRehydrationRequestReplayStore) consume(
	nonce string,
	nowSeconds int64,
	expiresAt int64,
) error {
	if store == nil || !evidenceRehydrationCompositionNoncePattern.MatchString(nonce) ||
		nowSeconds < 0 || expiresAt < nowSeconds {
		return errEvidenceRehydrationCompositionUnavailable
	}
	store.mu.Lock()
	defer store.mu.Unlock()
	for storedNonce, storedExpiry := range store.expiresAt {
		if storedExpiry < nowSeconds {
			delete(store.expiresAt, storedNonce)
		}
	}
	if _, duplicate := store.expiresAt[nonce]; duplicate || len(store.expiresAt) >= store.capacity {
		return errEvidenceRehydrationCompositionUnavailable
	}
	store.expiresAt[nonce] = expiresAt
	return nil
}

type evidenceRehydrationCurrentAuthorityReaderFactory func(
	ctx context.Context,
	binding aiagent.EvidenceAuthorityContextBinding,
	authorityToken string,
) (aiagent.EvidenceCurrentAuthorityReader, error)

type evidenceRehydrationComposition struct {
	secret             string
	maxAge             time.Duration
	clock              evidenceAuthorityCapabilityClock
	requestReplayStore *evidenceRehydrationRequestReplayStore
	capabilities       *evidenceAuthorityCapabilityRegistry
	readerFactory      evidenceRehydrationCurrentAuthorityReaderFactory
}

type evidenceRehydrationCompositionResult struct {
	statusCode int
	body       []byte
	headers    aiagent.EvidenceRehydrationResponseHeaders
}

func newEvidenceRehydrationComposition(
	secret string,
	maxAge time.Duration,
	clock evidenceAuthorityCapabilityClock,
	requestReplayStore *evidenceRehydrationRequestReplayStore,
	capabilities *evidenceAuthorityCapabilityRegistry,
	readerFactory evidenceRehydrationCurrentAuthorityReaderFactory,
) (*evidenceRehydrationComposition, error) {
	if strings.TrimSpace(secret) == "" || maxAge <= 0 || maxAge > maxEvidenceRehydrationCompositionAge ||
		maxAge%time.Second != 0 || clock == nil || requestReplayStore == nil || capabilities == nil ||
		readerFactory == nil {
		return nil, errEvidenceRehydrationCompositionUnavailable
	}
	return &evidenceRehydrationComposition{
		secret:             secret,
		maxAge:             maxAge,
		clock:              clock,
		requestReplayStore: requestReplayStore,
		capabilities:       capabilities,
		readerFactory:      readerFactory,
	}, nil
}

// handle proves the single-host call order without registering an HTTP route.
// An unverified request receives no response projection because no trusted
// snapshot token exists for the response HMAC domain.
func (composition *evidenceRehydrationComposition) handle(
	method string,
	path string,
	body []byte,
	headers aiagent.EvidenceRehydrationRequestHeaders,
) (evidenceRehydrationCompositionResult, error) {
	return composition.handleContext(context.Background(), method, path, body, headers)
}

func (composition *evidenceRehydrationComposition) handleContext(
	ctx context.Context,
	method string,
	path string,
	body []byte,
	headers aiagent.EvidenceRehydrationRequestHeaders,
) (evidenceRehydrationCompositionResult, error) {
	if composition == nil || ctx == nil || ctx.Err() != nil {
		return evidenceRehydrationCompositionResult{}, errEvidenceRehydrationCompositionUnavailable
	}
	now, err := composition.clock.Now()
	if err != nil {
		return evidenceRehydrationCompositionResult{}, errEvidenceRehydrationCompositionUnavailable
	}
	request, err := aiagent.VerifyEvidenceRehydrationRequest(
		method,
		path,
		body,
		headers,
		now,
		composition.maxAge,
		composition.secret,
	)
	if err != nil {
		return evidenceRehydrationCompositionResult{}, errEvidenceRehydrationCompositionUnavailable
	}

	issuedAt, err := strconv.ParseInt(headers.Timestamp, 10, 64)
	if err != nil || issuedAt > now.UTC().Unix() ||
		composition.requestReplayStore.consume(
			headers.Nonce,
			now.UTC().Unix(),
			issuedAt+int64(composition.maxAge/time.Second),
		) != nil {
		return composition.signedFailure(request, headers.Nonce, now)
	}

	resolution, err := composition.capabilities.consume(request)
	if err != nil || !validEvidenceRehydrationCompositionResolution(request, resolution) {
		return composition.signedFailure(request, headers.Nonce, now)
	}
	authenticatedContext, err := resolution.authenticatedContext(ctx)
	if err != nil {
		return composition.signedFailure(request, headers.Nonce, now)
	}
	reader, err := composition.readerFactory(authenticatedContext, resolution.binding, resolution.authorityToken)
	if err != nil || reader == nil || ctx.Err() != nil {
		return composition.signedFailure(request, headers.Nonce, now)
	}
	response, err := aiagent.BuildEvidenceRehydrationResponse(request, resolution.binding, reader)
	if err != nil || ctx.Err() != nil {
		return composition.signedFailure(request, headers.Nonce, now)
	}
	responseBody, err := json.Marshal(response)
	if err != nil {
		return composition.signedFailure(request, headers.Nonce, now)
	}
	responseHeaders, err := aiagent.SignEvidenceRehydrationResponse(
		responseBody,
		200,
		now,
		headers.Nonce,
		request,
		composition.secret,
	)
	if err != nil {
		return composition.signedFailure(request, headers.Nonce, now)
	}
	return evidenceRehydrationCompositionResult{
		statusCode: 200,
		body:       responseBody,
		headers:    responseHeaders,
	}, nil
}

func (composition *evidenceRehydrationComposition) signedFailure(
	request aiagent.EvidenceRehydrationRequest,
	requestNonce string,
	at time.Time,
) (evidenceRehydrationCompositionResult, error) {
	headers, err := aiagent.SignEvidenceRehydrationResponse(
		[]byte(evidenceRehydrationCompositionFailureBody),
		503,
		at,
		requestNonce,
		request,
		composition.secret,
	)
	if err != nil {
		return evidenceRehydrationCompositionResult{}, errEvidenceRehydrationCompositionUnavailable
	}
	return evidenceRehydrationCompositionResult{
		statusCode: 503,
		body:       []byte(evidenceRehydrationCompositionFailureBody),
		headers:    headers,
	}, nil
}

func validEvidenceRehydrationCompositionResolution(
	request aiagent.EvidenceRehydrationRequest,
	resolution evidenceAuthorityCapabilityResolution,
) bool {
	if resolution.callerID <= 0 ||
		resolution.binding.MemosAuthorityRef != request.MemosAuthorityRef ||
		!validIndependentEvidenceAuthorityCapabilityTokens(
			resolution.binding.MemosAuthorityRef,
			resolution.binding.AuthenticatedContextToken,
			resolution.authorityToken,
		) || !validEvidenceAuthorityCapabilityUIDs(
		resolution.authorizedMemoUIDs,
		maxEvidenceAuthorityCapabilityUIDs,
	) {
		return false
	}
	authorized := make(map[string]struct{}, len(resolution.authorizedMemoUIDs))
	for _, uid := range resolution.authorizedMemoUIDs {
		authorized[uid] = struct{}{}
	}
	for _, selection := range request.Selections {
		if _, ok := authorized[selection.MemoUID]; !ok {
			return false
		}
	}
	return true
}
