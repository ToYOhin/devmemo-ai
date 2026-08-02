package v1

import (
	"context"
	"strings"
	"time"

	"github.com/labstack/echo/v5"

	"github.com/usememos/memos/internal/aiagent"
	"github.com/usememos/memos/server/auth"
)

const evidenceRehydrationRuntimeCapacity = 1024

type evidenceRehydrationSystemClock struct{}

func (evidenceRehydrationSystemClock) Now() (time.Time, error) {
	return time.Now().UTC(), nil
}

type memosEvidenceAuthorityCapabilityScopeSource struct {
	service *APIV1Service
}

func (source *memosEvidenceAuthorityCapabilityScopeSource) ReadCurrentAuthorizedCompleteMemoScope(
	ctx context.Context,
	authenticatedCallerID int32,
) (evidenceAuthorityCapabilityScope, error) {
	if source == nil || source.service == nil || ctx == nil ||
		authenticatedCallerID <= 0 || auth.GetUserID(ctx) != authenticatedCallerID {
		return evidenceAuthorityCapabilityScope{}, errEvidenceAuthorityCapabilityUnavailable
	}
	uids, err := source.service.resolveAgentVisibleMemoUIDs(ctx)
	if err != nil {
		return evidenceAuthorityCapabilityScope{}, errEvidenceAuthorityCapabilityUnavailable
	}
	return evidenceAuthorityCapabilityScope{
		callerID:           authenticatedCallerID,
		callerIsCurrent:    true,
		authorizedMemoUIDs: uids,
	}, nil
}

// evidenceRehydrationMemosRuntime owns only process-local state. Its handler is
// served by the existing Memos HTTP server, and it creates no goroutine,
// listener, transport, timer, or closeable resource.
type evidenceRehydrationMemosRuntime struct {
	handler      *evidenceRehydrationHTTPHandler
	capabilities *evidenceAuthorityCapabilityRegistry
}

func newEvidenceRehydrationMemosRuntime(
	service *APIV1Service,
	config aiagent.EvidenceRehydrationRuntimeConfig,
) (*evidenceRehydrationMemosRuntime, error) {
	if service == nil || config.Validate("") != nil ||
		config.CurrentSecret == strings.TrimSpace(service.Secret) ||
		(config.PreviousSecret != "" && config.PreviousSecret == strings.TrimSpace(service.Secret)) {
		return nil, aiagent.ErrInvalidEvidenceRehydrationRuntimeConfig
	}
	clock := evidenceRehydrationSystemClock{}
	capabilities, err := newEvidenceAuthorityCapabilityRegistry(
		evidenceRehydrationRuntimeCapacity,
		maxEvidenceAuthorityCapabilityTTL,
		clock,
		cryptoEvidenceAuthorityCapabilityTokenSource{},
		&memosEvidenceAuthorityCapabilityScopeSource{service: service},
	)
	if err != nil {
		return nil, err
	}
	replay, err := newEvidenceRehydrationRequestReplayStore(evidenceRehydrationRuntimeCapacity)
	if err != nil {
		return nil, err
	}
	readerFactory := func(
		ctx context.Context,
		binding aiagent.EvidenceAuthorityContextBinding,
		authorityToken string,
	) (aiagent.EvidenceCurrentAuthorityReader, error) {
		return newSQLiteEvidenceCurrentAuthorityReader(ctx, service, binding, authorityToken)
	}
	currentComposition, err := newEvidenceRehydrationComposition(
		config.CurrentSecret,
		maxEvidenceRehydrationCompositionAge,
		clock,
		replay,
		capabilities,
		readerFactory,
	)
	if err != nil {
		return nil, err
	}
	compositions := []*evidenceRehydrationComposition{currentComposition}
	if config.PreviousSecret != "" {
		previousComposition, err := newEvidenceRehydrationComposition(
			config.PreviousSecret,
			maxEvidenceRehydrationCompositionAge,
			clock,
			replay,
			capabilities,
			readerFactory,
		)
		if err != nil {
			return nil, err
		}
		compositions = append(compositions, previousComposition)
	}
	handler, err := newEvidenceRehydrationHTTPHandler(compositions[0], compositions[1:]...)
	if err != nil {
		return nil, err
	}
	return &evidenceRehydrationMemosRuntime{
		handler:      handler,
		capabilities: capabilities,
	}, nil
}

func (s *APIV1Service) registerConfiguredEvidenceRehydrationRoute(router agentRouteRegistrar) error {
	config, err := aiagent.LoadEvidenceRehydrationRuntimeConfigFromEnv()
	if err != nil || !config.Enabled {
		return err
	}
	runtime, err := newEvidenceRehydrationMemosRuntime(s, config)
	if err != nil {
		return err
	}
	router.POST(aiagent.InternalEvidenceRehydrationPath, echo.WrapHandler(runtime.handler))
	s.evidenceRehydrationRuntime = runtime
	return nil
}
