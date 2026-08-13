package v1

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"slices"
	"strings"

	"github.com/labstack/echo/v5"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"

	"github.com/usememos/memos/internal/aiagent"
	"github.com/usememos/memos/server/auth"
	"github.com/usememos/memos/store"
)

const (
	agentRunTaskProjectSummary       = "project_summary"
	maxAgentRunSources               = 10
	maxAgentRunDelegatedContentBytes = 96 << 10
)

type agentBrowserRunCreateRequest struct {
	TaskKind   string   `json:"task_kind"`
	RequestKey string   `json:"request_key"`
	MemoUIDs   []string `json:"memo_uids"`
}

func (s *APIV1Service) registerAgentRunRoutes(router agentRouteRegistrar, config aiagent.Config, executor aiagent.AgentRunExecutor) {
	authenticator := auth.NewAuthenticator(s.Store, s.Secret)
	authenticate := func(c *echo.Context) (context.Context, bool) {
		result := authenticator.Authenticate(c.Request().Context(), c.Request().Header.Get("Authorization"))
		if result == nil {
			return nil, false
		}
		return auth.ApplyToContext(c.Request().Context(), result), true
	}

	router.POST(aiagent.BrowserAgentRunCreatePath, func(c *echo.Context) error {
		if !config.Enabled {
			return c.JSON(http.StatusNotFound, map[string]string{"detail": "not found"})
		}
		ctx, ok := authenticate(c)
		if !ok {
			return c.JSON(http.StatusUnauthorized, map[string]string{"detail": "authentication required"})
		}
		input, err := decodeAgentBrowserRunCreateRequest(c.Request())
		if err != nil {
			return c.JSON(http.StatusBadRequest, map[string]string{"detail": "invalid AgentRun request"})
		}
		delegated, execution, err := s.resolveAgentRunCreateRequest(ctx, input)
		if err != nil {
			if status.Code(err) == codes.InvalidArgument {
				return c.JSON(http.StatusBadRequest, map[string]string{"detail": "invalid AgentRun scope"})
			}
			return c.JSON(http.StatusServiceUnavailable, map[string]string{"detail": "AgentRun service unavailable"})
		}
		created, err := executor.CreateRun(ctx, delegated)
		if err != nil {
			if errors.Is(err, aiagent.ErrConflict) {
				return c.JSON(http.StatusConflict, map[string]string{"detail": "AgentRun request conflicts"})
			}
			return c.JSON(http.StatusServiceUnavailable, map[string]string{"detail": "AgentRun service unavailable"})
		}
		execution.RunID = created.RunID
		response, err := executor.ExecuteRun(ctx, execution)
		if err != nil {
			return c.JSON(http.StatusServiceUnavailable, map[string]string{"detail": "AgentRun service unavailable"})
		}
		return c.JSON(http.StatusOK, response)
	})

	router.GET(aiagent.BrowserAgentRunStatusPath, func(c *echo.Context) error {
		if !config.Enabled {
			return c.JSON(http.StatusNotFound, map[string]string{"detail": "not found"})
		}
		ctx, ok := authenticate(c)
		if !ok {
			return c.JSON(http.StatusUnauthorized, map[string]string{"detail": "authentication required"})
		}
		currentUser, err := s.fetchCurrentUser(ctx)
		if err != nil || currentUser == nil {
			return c.JSON(http.StatusServiceUnavailable, map[string]string{"detail": "AgentRun service unavailable"})
		}
		response, err := executor.GetRun(ctx, aiagent.AgentRunStatusRequest{
			SubjectID: fmt.Sprintf("user-%d", currentUser.ID),
			RunID:     c.Param("runID"),
		})
		if err != nil {
			if errors.Is(err, aiagent.ErrNotFound) || errors.Is(err, aiagent.ErrInvalidResponse) {
				return c.JSON(http.StatusNotFound, map[string]string{"detail": "AgentRun not found"})
			}
			return c.JSON(http.StatusServiceUnavailable, map[string]string{"detail": "AgentRun service unavailable"})
		}
		return c.JSON(http.StatusOK, response)
	})

	router.GET(aiagent.BrowserAgentRunArtifactPath, func(c *echo.Context) error {
		if !config.Enabled {
			return c.JSON(http.StatusNotFound, map[string]string{"detail": "not found"})
		}
		ctx, ok := authenticate(c)
		if !ok {
			return c.JSON(http.StatusUnauthorized, map[string]string{"detail": "authentication required"})
		}
		currentUser, err := s.fetchCurrentUser(ctx)
		if err != nil || currentUser == nil {
			return c.JSON(http.StatusServiceUnavailable, map[string]string{"detail": "AgentRun service unavailable"})
		}
		artifact, err := executor.GetArtifact(ctx, aiagent.AgentRunStatusRequest{
			SubjectID: fmt.Sprintf("user-%d", currentUser.ID),
			RunID:     c.Param("runID"),
		})
		if err != nil {
			if errors.Is(err, aiagent.ErrNotFound) || errors.Is(err, aiagent.ErrInvalidResponse) {
				return c.JSON(http.StatusNotFound, map[string]string{"detail": "AgentRun artifact not found"})
			}
			return c.JSON(http.StatusServiceUnavailable, map[string]string{"detail": "AgentRun service unavailable"})
		}
		return c.JSON(http.StatusOK, artifact)
	})
}

func decodeAgentBrowserRunCreateRequest(request *http.Request) (agentBrowserRunCreateRequest, error) {
	decoder := json.NewDecoder(io.LimitReader(request.Body, maxAgentBrowserRequestBytes+1))
	decoder.DisallowUnknownFields()
	var input agentBrowserRunCreateRequest
	if err := decoder.Decode(&input); err != nil {
		return input, err
	}
	var extra any
	if err := decoder.Decode(&extra); !errors.Is(err, io.EOF) {
		return input, errors.New("unexpected request data")
	}
	input.RequestKey = strings.TrimSpace(input.RequestKey)
	if input.TaskKind != agentRunTaskProjectSummary || input.RequestKey == "" || len(input.RequestKey) > 128 ||
		len(input.MemoUIDs) < 1 || len(input.MemoUIDs) > maxAgentRunSources {
		return input, errors.New("invalid AgentRun request")
	}
	seen := make(map[string]struct{}, len(input.MemoUIDs))
	for _, uid := range input.MemoUIDs {
		if strings.TrimSpace(uid) != uid || uid == "" {
			return input, errors.New("invalid AgentRun request")
		}
		if _, ok := seen[uid]; ok {
			return input, errors.New("invalid AgentRun request")
		}
		seen[uid] = struct{}{}
	}
	return input, nil
}

func (s *APIV1Service) resolveAgentRunCreateRequest(ctx context.Context, input agentBrowserRunCreateRequest) (aiagent.DelegatedAgentRunCreateRequest, aiagent.AgentRunExecuteRequest, error) {
	currentUser, err := s.fetchCurrentUser(ctx)
	if err != nil || currentUser == nil {
		return aiagent.DelegatedAgentRunCreateRequest{}, aiagent.AgentRunExecuteRequest{}, status.Error(codes.Unauthenticated, "user not authenticated")
	}
	state := store.Normal
	find := &store.FindMemo{UIDList: input.MemoUIDs, RowStatus: &state, ExcludeComments: true}
	applyMemoListVisibility(find, currentUser)
	memos, err := s.Store.ListMemos(ctx, find)
	if err != nil {
		return aiagent.DelegatedAgentRunCreateRequest{}, aiagent.AgentRunExecuteRequest{}, status.Error(codes.Internal, "failed to resolve AgentRun scope")
	}
	if len(memos) != len(input.MemoUIDs) {
		return aiagent.DelegatedAgentRunCreateRequest{}, aiagent.AgentRunExecuteRequest{}, status.Error(codes.InvalidArgument, "invalid AgentRun scope")
	}
	sources := make([]aiagent.AgentRunSourceRevision, 0, len(memos))
	executionSources := make([]aiagent.AgentRunExecutionSource, 0, len(memos))
	contentBytes := 0
	for _, memo := range memos {
		sourceID := "memo-" + hex.EncodeToString([]byte(memo.UID))
		revision := fmt.Sprintf("rev-%d", memo.UpdatedTs)
		sources = append(sources, aiagent.AgentRunSourceRevision{
			SourceID: sourceID,
			Revision: revision,
		})
		executionSources = append(executionSources, aiagent.AgentRunExecutionSource{SourceID: sourceID, Revision: revision, Content: memo.Content})
		contentBytes += len(memo.Content)
	}
	if contentBytes > maxAgentRunDelegatedContentBytes {
		return aiagent.DelegatedAgentRunCreateRequest{}, aiagent.AgentRunExecuteRequest{}, status.Error(codes.InvalidArgument, "AgentRun source content is too large")
	}
	slices.SortFunc(sources, func(a, b aiagent.AgentRunSourceRevision) int {
		return strings.Compare(a.SourceID, b.SourceID)
	})
	slices.SortFunc(executionSources, func(a, b aiagent.AgentRunExecutionSource) int {
		return strings.Compare(a.SourceID, b.SourceID)
	})
	scopeMaterial, _ := json.Marshal(sources)
	subjectID := fmt.Sprintf("user-%d", currentUser.ID)
	return aiagent.DelegatedAgentRunCreateRequest{
			SubjectID:      subjectID,
			ScopeRef:       digestOpaque("scope", string(scopeMaterial)),
			RequestKey:     digestOpaque("request", input.RequestKey),
			RequestDigest:  digestHex(input.TaskKind),
			SourceSnapshot: sources,
		}, aiagent.AgentRunExecuteRequest{
			SubjectID: subjectID,
			TaskKind:  input.TaskKind,
			Sources:   executionSources,
		}, nil
}

func digestOpaque(prefix, value string) string {
	return prefix + "-" + digestHex(value)
}

func digestHex(value string) string {
	digest := sha256.Sum256([]byte(value))
	return hex.EncodeToString(digest[:])
}
