package v1

import (
	"context"
	"io"
	"net/http"
	"net/http/httptest"
	"strconv"
	"strings"
	"testing"

	"github.com/labstack/echo/v5"
	"github.com/stretchr/testify/require"

	"github.com/usememos/memos/internal/aiagent"
	"github.com/usememos/memos/store"
	teststore "github.com/usememos/memos/store/test"
)

type recordingAgentRunExecutor struct {
	created   aiagent.DelegatedAgentRunCreateRequest
	executed  aiagent.AgentRunExecuteRequest
	status    aiagent.AgentRunStatusRequest
	result    aiagent.AgentRunStatusResponse
	artifact  aiagent.AgentRunArtifactResponse
	createErr error
	statusErr error
	calls     int
}

func (e *recordingAgentRunExecutor) CreateRun(_ context.Context, request aiagent.DelegatedAgentRunCreateRequest) (aiagent.AgentRunStatusResponse, error) {
	e.calls++
	e.created = request
	return e.result, e.createErr
}

func (e *recordingAgentRunExecutor) GetRun(_ context.Context, request aiagent.AgentRunStatusRequest) (aiagent.AgentRunStatusResponse, error) {
	e.calls++
	e.status = request
	return e.result, e.statusErr
}

func (e *recordingAgentRunExecutor) ExecuteRun(_ context.Context, request aiagent.AgentRunExecuteRequest) (aiagent.AgentRunStatusResponse, error) {
	e.calls++
	e.executed = request
	return e.result, nil
}

func (e *recordingAgentRunExecutor) GetArtifact(_ context.Context, request aiagent.AgentRunStatusRequest) (aiagent.AgentRunArtifactResponse, error) {
	e.calls++
	e.status = request
	return e.artifact, nil
}

func TestAgentRunBFFCreatesContentFreeVisibleScope(t *testing.T) {
	ctx := context.Background()
	testStore := teststore.NewTestingStore(ctx, t)
	t.Cleanup(func() { _ = testStore.Close() })
	service := &APIV1Service{Store: testStore, Secret: "test-secret"}
	caller := createAgentVisibilityUser(ctx, t, testStore, "agent-run-caller")
	other := createAgentVisibilityUser(ctx, t, testStore, "agent-run-other")
	createAgentVisibilityMemo(ctx, t, testStore, "run-private", caller.ID, store.Private)
	createAgentVisibilityMemo(ctx, t, testStore, "run-public", other.ID, store.Public)
	createAgentVisibilityMemo(ctx, t, testStore, "run-hidden", other.ID, store.Private)

	executor := &recordingAgentRunExecutor{result: validAgentRunStatus()}
	echoServer := echo.New()
	service.registerAgentRunRoutes(echoServer, aiagent.Config{Enabled: true}, executor)
	body := `{"task_kind":"project_summary","request_key":"demo-1","memo_uids":["run-private","run-public"]}`
	request := httptest.NewRequest(http.MethodPost, aiagent.BrowserAgentRunCreatePath, io.NopCloser(strings.NewReader(body)))
	request.Header.Set("Content-Type", "application/json")
	request.Header.Set("Authorization", bearerToken(t, caller))
	response := httptest.NewRecorder()
	echoServer.ServeHTTP(response, request)

	require.Equal(t, http.StatusOK, response.Code)
	require.Equal(t, 2, executor.calls)
	require.Equal(t, "user-"+formatAgentUserID(caller.ID), executor.created.SubjectID)
	require.Equal(t, digestHex(agentRunTaskProjectSummary), executor.created.RequestDigest)
	require.Len(t, executor.created.SourceSnapshot, 2)
	require.Equal(t, "project_summary", executor.executed.TaskKind)
	require.Equal(t, executor.result.RunID, executor.executed.RunID)
	require.Len(t, executor.executed.Sources, 2)
	require.NotContains(t, response.Body.String(), "subject_id")
	require.NotContains(t, response.Body.String(), "request_digest")
	require.NotContains(t, response.Body.String(), "source_snapshot")
	require.NotContains(t, response.Body.String(), "project_summary")
	require.NotContains(t, response.Body.String(), "content")
}

func TestAgentRunBFFRejectsInvisibleMemo(t *testing.T) {
	ctx := context.Background()
	testStore := teststore.NewTestingStore(ctx, t)
	t.Cleanup(func() { _ = testStore.Close() })
	service := &APIV1Service{Store: testStore, Secret: "test-secret"}
	caller := createAgentVisibilityUser(ctx, t, testStore, "agent-run-scope-caller")
	other := createAgentVisibilityUser(ctx, t, testStore, "agent-run-scope-other")
	createAgentVisibilityMemo(ctx, t, testStore, "run-scope-hidden", other.ID, store.Private)

	executor := &recordingAgentRunExecutor{result: validAgentRunStatus()}
	echoServer := echo.New()
	service.registerAgentRunRoutes(echoServer, aiagent.Config{Enabled: true}, executor)
	body := `{"task_kind":"project_summary","request_key":"demo-2","memo_uids":["run-scope-hidden"]}`
	request := httptest.NewRequest(http.MethodPost, aiagent.BrowserAgentRunCreatePath, io.NopCloser(strings.NewReader(body)))
	request.Header.Set("Authorization", bearerToken(t, caller))
	response := httptest.NewRecorder()
	echoServer.ServeHTTP(response, request)

	require.Equal(t, http.StatusBadRequest, response.Code)
	require.Zero(t, executor.calls)
}

func TestAgentRunBFFRejectsUncontractedCreateRequests(t *testing.T) {
	ctx := context.Background()
	testStore := teststore.NewTestingStore(ctx, t)
	t.Cleanup(func() { _ = testStore.Close() })
	service := &APIV1Service{Store: testStore, Secret: "test-secret"}
	caller := createAgentVisibilityUser(ctx, t, testStore, "agent-run-invalid-caller")
	executor := &recordingAgentRunExecutor{result: validAgentRunStatus()}
	echoServer := echo.New()
	service.registerAgentRunRoutes(echoServer, aiagent.Config{Enabled: true}, executor)

	for _, body := range []string{
		`{"task_kind":"project_summary","request_key":"demo-3","memo_uids":["memo-1"],"unknown":true}`,
		`{"task_kind":"custom_summary","request_key":"demo-4","memo_uids":["memo-1"]}`,
	} {
		request := httptest.NewRequest(http.MethodPost, aiagent.BrowserAgentRunCreatePath, strings.NewReader(body))
		request.Header.Set("Authorization", bearerToken(t, caller))
		response := httptest.NewRecorder()

		echoServer.ServeHTTP(response, request)

		require.Equal(t, http.StatusBadRequest, response.Code)
	}
	require.Zero(t, executor.calls)
}

func TestAgentRunBFFStatusUsesAuthenticatedSubject(t *testing.T) {
	ctx := context.Background()
	testStore := teststore.NewTestingStore(ctx, t)
	t.Cleanup(func() { _ = testStore.Close() })
	service := &APIV1Service{Store: testStore, Secret: "test-secret"}
	caller := createAgentVisibilityUser(ctx, t, testStore, "agent-run-status-caller")
	executor := &recordingAgentRunExecutor{result: validAgentRunStatus()}
	echoServer := echo.New()
	service.registerAgentRunRoutes(echoServer, aiagent.Config{Enabled: true}, executor)

	request := httptest.NewRequest(http.MethodGet, "/api/ai/agent/runs/run-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa", http.NoBody)
	request.Header.Set("Authorization", bearerToken(t, caller))
	response := httptest.NewRecorder()
	echoServer.ServeHTTP(response, request)

	require.Equal(t, http.StatusOK, response.Code)
	require.Equal(t, "user-"+formatAgentUserID(caller.ID), executor.status.SubjectID)
	require.Equal(t, "run-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa", executor.status.RunID)
	require.NotContains(t, response.Body.String(), "subject_id")
}

func TestAgentRunBFFStatusRequiresAuthentication(t *testing.T) {
	ctx := context.Background()
	testStore := teststore.NewTestingStore(ctx, t)
	t.Cleanup(func() { _ = testStore.Close() })
	service := &APIV1Service{Store: testStore, Secret: "test-secret"}
	executor := &recordingAgentRunExecutor{result: validAgentRunStatus()}
	echoServer := echo.New()
	service.registerAgentRunRoutes(echoServer, aiagent.Config{Enabled: true}, executor)
	request := httptest.NewRequest(http.MethodGet, "/api/ai/agent/runs/run-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa", http.NoBody)
	response := httptest.NewRecorder()

	echoServer.ServeHTTP(response, request)

	require.Equal(t, http.StatusUnauthorized, response.Code)
	require.Zero(t, executor.calls)
}

func TestAgentRunBFFMapsAIServiceStatusErrors(t *testing.T) {
	ctx := context.Background()
	testStore := teststore.NewTestingStore(ctx, t)
	t.Cleanup(func() { _ = testStore.Close() })
	service := &APIV1Service{Store: testStore, Secret: "test-secret"}
	caller := createAgentVisibilityUser(ctx, t, testStore, "agent-run-error-caller")

	for _, test := range []struct {
		name string
		err  error
		want int
	}{
		{name: "not found", err: aiagent.ErrNotFound, want: http.StatusNotFound},
		{name: "unavailable", err: aiagent.ErrUnavailable, want: http.StatusServiceUnavailable},
	} {
		t.Run(test.name, func(t *testing.T) {
			executor := &recordingAgentRunExecutor{statusErr: test.err}
			echoServer := echo.New()
			service.registerAgentRunRoutes(echoServer, aiagent.Config{Enabled: true}, executor)
			request := httptest.NewRequest(http.MethodGet, "/api/ai/agent/runs/run-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa", http.NoBody)
			request.Header.Set("Authorization", bearerToken(t, caller))
			response := httptest.NewRecorder()

			echoServer.ServeHTTP(response, request)

			require.Equal(t, test.want, response.Code)
			require.Equal(t, 1, executor.calls)
		})
	}
}

func TestAgentRunBFFIsAbsentWhenDisabled(t *testing.T) {
	service := &APIV1Service{}
	echoServer := echo.New()
	service.registerAgentRunRoutes(echoServer, aiagent.Config{}, nil)
	request := httptest.NewRequest(http.MethodPost, aiagent.BrowserAgentRunCreatePath, http.NoBody)
	response := httptest.NewRecorder()

	echoServer.ServeHTTP(response, request)

	require.Equal(t, http.StatusNotFound, response.Code)
}

func TestAgentRunBFFArtifactUsesAuthenticatedSubject(t *testing.T) {
	ctx := context.Background()
	testStore := teststore.NewTestingStore(ctx, t)
	t.Cleanup(func() { _ = testStore.Close() })
	service := &APIV1Service{Store: testStore, Secret: "test-secret"}
	caller := createAgentVisibilityUser(ctx, t, testStore, "agent-run-artifact-caller")
	executor := &recordingAgentRunExecutor{artifact: aiagent.AgentRunArtifactResponse{
		ArtifactID: "artifact-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
		FileName:   "project-summary.md",
		MediaType:  "text/markdown",
		Markdown:   "# Project summary\n",
		Digest:     strings.Repeat("a", 64),
	}}
	echoServer := echo.New()
	service.registerAgentRunRoutes(echoServer, aiagent.Config{Enabled: true}, executor)

	request := httptest.NewRequest(http.MethodGet, "/api/ai/agent/runs/run-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa/artifact", http.NoBody)
	request.Header.Set("Authorization", bearerToken(t, caller))
	response := httptest.NewRecorder()
	echoServer.ServeHTTP(response, request)

	require.Equal(t, http.StatusOK, response.Code)
	require.Equal(t, "user-"+formatAgentUserID(caller.ID), executor.status.SubjectID)
	require.Contains(t, response.Body.String(), "project-summary.md")
	require.NotContains(t, response.Body.String(), "subject_id")
}

func validAgentRunStatus() aiagent.AgentRunStatusResponse {
	return aiagent.AgentRunStatusResponse{
		RunID:        "run-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
		Status:       "queued",
		CreatedAt:    "2026-08-13T00:00:00Z",
		UpdatedAt:    "2026-08-13T00:00:00Z",
		SourceCount:  2,
		LastEventSeq: 0,
	}
}

func formatAgentUserID(id int32) string {
	return strconv.FormatInt(int64(id), 10)
}
