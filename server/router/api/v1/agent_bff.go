package v1

import (
	"context"
	"encoding/json"
	"errors"
	"io"
	"net/http"

	"github.com/labstack/echo/v5"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"

	"github.com/usememos/memos/internal/aiagent"
	"github.com/usememos/memos/server/auth"
)

const maxAgentBrowserRequestBytes = 16 << 10

type agentBrowserAnswerRequest struct {
	Question string `json:"question"`
	Limit    int    `json:"limit"`
}

type agentBrowserAnswerResponse struct {
	Answer    string                       `json:"answer"`
	Citations []agentBrowserAnswerCitation `json:"citations"`
	Trace     agentBrowserAnswerTrace      `json:"trace"`
}

type agentBrowserAnswerCitation struct {
	MemoID     string   `json:"memo_id"`
	Title      string   `json:"title"`
	Summary    string   `json:"summary"`
	SourceRefs []string `json:"source_refs"`
}

type agentBrowserAnswerTrace struct {
	TerminalState string                   `json:"terminal_state"`
	Steps         []agentBrowserAnswerStep `json:"steps"`
}

type agentBrowserAnswerStep struct {
	Index       int    `json:"index"`
	Name        string `json:"name"`
	Status      string `json:"status"`
	ResultCount *int   `json:"result_count,omitempty"`
}

type agentRouteRegistrar interface {
	POST(path string, h echo.HandlerFunc, m ...echo.MiddlewareFunc) echo.RouteInfo
}

func (s *APIV1Service) registerAgentRoutes(router agentRouteRegistrar, config aiagent.Config, executor aiagent.AnswerExecutor) {
	authenticator := auth.NewAuthenticator(s.Store, s.Secret)
	router.POST(aiagent.BrowserAnswerPath, func(c *echo.Context) error {
		if !config.Enabled {
			return c.JSON(http.StatusNotFound, map[string]string{"detail": "not found"})
		}
		result := authenticator.Authenticate(c.Request().Context(), c.Request().Header.Get("Authorization"))
		if result == nil {
			return c.JSON(http.StatusUnauthorized, map[string]string{"detail": "authentication required"})
		}
		ctx := auth.ApplyToContext(c.Request().Context(), result)
		request, err := decodeAgentBrowserAnswerRequest(c.Request())
		if err != nil {
			return c.JSON(http.StatusBadRequest, map[string]string{"detail": "invalid Agent request"})
		}
		visibleMemoUIDs, memosAuthorityRef, err := s.resolveAgentDelegationScope(ctx)
		if err != nil {
			if status.Code(err) == codes.Unauthenticated {
				return c.JSON(http.StatusUnauthorized, map[string]string{"detail": "authentication required"})
			}
			return c.JSON(http.StatusServiceUnavailable, map[string]string{"detail": "Agent service unavailable"})
		}
		response, err := executor.Answer(ctx, aiagent.DelegatedAnswerRequest{
			Question:          request.Question,
			Limit:             request.Limit,
			VisibleMemoUIDs:   visibleMemoUIDs,
			MemosAuthorityRef: memosAuthorityRef,
		})
		if err != nil {
			return c.JSON(agentErrorStatus(err), map[string]string{"detail": agentErrorDetail(err)})
		}
		return c.JSON(http.StatusOK, projectAgentBrowserAnswer(response))
	})
}

func projectAgentBrowserAnswer(response aiagent.AnswerResponse) agentBrowserAnswerResponse {
	citations := make([]agentBrowserAnswerCitation, 0, len(response.Citations))
	for _, citation := range response.Citations {
		citations = append(citations, agentBrowserAnswerCitation{
			MemoID:     citation.MemoID,
			Title:      citation.Title,
			Summary:    citation.Summary,
			SourceRefs: citation.SourceRefs,
		})
	}
	steps := make([]agentBrowserAnswerStep, 0, len(response.Trace.Steps))
	for _, step := range response.Trace.Steps {
		steps = append(steps, agentBrowserAnswerStep{
			Index:       step.Index,
			Name:        step.Name,
			Status:      step.Status,
			ResultCount: step.ResultCount,
		})
	}
	return agentBrowserAnswerResponse{
		Answer:    response.Answer,
		Citations: citations,
		Trace: agentBrowserAnswerTrace{
			TerminalState: response.Trace.TerminalState,
			Steps:         steps,
		},
	}
}

func (s *APIV1Service) resolveAgentDelegationScope(ctx context.Context) ([]string, string, error) {
	if s.evidenceRehydrationRuntime == nil || s.evidenceRehydrationRuntime.capabilities == nil {
		uids, err := s.resolveAgentVisibleMemoUIDs(ctx)
		return uids, "", err
	}
	grant, uids, err := s.evidenceRehydrationRuntime.capabilities.issueForDelegation(ctx)
	if err != nil {
		return nil, "", err
	}
	return uids, grant.memosAuthorityRef, nil
}

func (s *APIV1Service) registerConfiguredAgentRoutes(router agentRouteRegistrar) error {
	config, err := aiagent.LoadConfigFromEnv()
	if err != nil {
		return err
	}
	var executor aiagent.AnswerExecutor
	if config.Enabled {
		executor, err = aiagent.NewClient(config)
		if err != nil {
			return err
		}
	}
	s.registerAgentRoutes(router, config, executor)
	return nil
}

func decodeAgentBrowserAnswerRequest(request *http.Request) (agentBrowserAnswerRequest, error) {
	decoder := json.NewDecoder(io.LimitReader(request.Body, maxAgentBrowserRequestBytes+1))
	decoder.DisallowUnknownFields()
	var input agentBrowserAnswerRequest
	if err := decoder.Decode(&input); err != nil {
		return agentBrowserAnswerRequest{}, err
	}
	var extra any
	if err := decoder.Decode(&extra); !errors.Is(err, io.EOF) {
		return agentBrowserAnswerRequest{}, errors.New("unexpected request data")
	}
	if err := (aiagent.DelegatedAnswerRequest{Question: input.Question, Limit: input.Limit}).Validate(); err != nil {
		return agentBrowserAnswerRequest{}, err
	}
	return input, nil
}

func agentErrorStatus(err error) int {
	switch {
	case errors.Is(err, aiagent.ErrRetrievalFailed):
		return http.StatusServiceUnavailable
	case errors.Is(err, aiagent.ErrProviderFailed):
		return http.StatusBadGateway
	default:
		return http.StatusServiceUnavailable
	}
}

func agentErrorDetail(err error) string {
	switch {
	case errors.Is(err, aiagent.ErrRetrievalFailed):
		return "Agent retrieval unavailable"
	case errors.Is(err, aiagent.ErrProviderFailed):
		return "Agent provider unavailable"
	default:
		return "Agent service unavailable"
	}
}
