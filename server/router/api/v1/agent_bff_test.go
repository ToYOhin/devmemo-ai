package v1

import (
	"context"
	"errors"
	"io"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"github.com/labstack/echo/v5"
	"github.com/stretchr/testify/require"

	"github.com/usememos/memos/internal/aiagent"
	"github.com/usememos/memos/server/auth"
	"github.com/usememos/memos/store"
	teststore "github.com/usememos/memos/store/test"
)

type recordingAgentExecutor struct {
	delegated aiagent.DelegatedAnswerRequest
	response  aiagent.AnswerResponse
	err       error
	calls     int
}

func (e *recordingAgentExecutor) Answer(_ context.Context, delegated aiagent.DelegatedAnswerRequest) (aiagent.AnswerResponse, error) {
	e.calls++
	e.delegated = delegated
	return e.response, e.err
}

func TestAgentBFFUsesAuthenticatedMemosVisibilityAndSafeProjection(t *testing.T) {
	ctx := context.Background()
	testStore := teststore.NewTestingStore(ctx, t)
	t.Cleanup(func() { _ = testStore.Close() })
	service := &APIV1Service{Store: testStore, Secret: "test-secret"}
	caller := createAgentVisibilityUser(t, ctx, testStore, "agent-bff-caller")
	other := createAgentVisibilityUser(t, ctx, testStore, "agent-bff-other")
	createAgentVisibilityMemo(t, ctx, testStore, "agent-bff-private", caller.ID, store.Private)
	createAgentVisibilityMemo(t, ctx, testStore, "agent-bff-public", other.ID, store.Public)
	createAgentVisibilityMemo(t, ctx, testStore, "agent-bff-protected", other.ID, store.Protected)
	createAgentVisibilityMemo(t, ctx, testStore, "agent-bff-hidden", other.ID, store.Private)

	executor := &recordingAgentExecutor{response: validAgentAnswerResponse("agent-bff-private")}
	echoServer := echo.New()
	service.registerAgentRoutes(echoServer, aiagent.Config{Enabled: true}, executor)

	request := httptest.NewRequest(http.MethodPost, aiagent.BrowserAnswerPath, http.NoBody)
	request.Body = io.NopCloser(strings.NewReader(`{"question":"Docker ports","limit":3}`))
	request.Header.Set("Content-Type", "application/json")
	request.Header.Set("Authorization", bearerToken(t, caller))
	response := httptest.NewRecorder()
	echoServer.ServeHTTP(response, request)

	require.Equal(t, http.StatusOK, response.Code)
	require.Equal(t, 1, executor.calls)
	require.Equal(t, "Docker ports", executor.delegated.Question)
	require.ElementsMatch(t, []string{
		"agent-bff-private", "agent-bff-public", "agent-bff-protected",
	}, executor.delegated.VisibleMemoUIDs)
	require.NotContains(t, response.Body.String(), "content")
}

func TestAgentBFFRejectsBrowserScopeAndUnauthenticatedRequests(t *testing.T) {
	ctx := context.Background()
	testStore := teststore.NewTestingStore(ctx, t)
	t.Cleanup(func() { _ = testStore.Close() })
	service := &APIV1Service{Store: testStore, Secret: "test-secret"}
	caller := createAgentVisibilityUser(t, ctx, testStore, "agent-bff-request")
	executor := &recordingAgentExecutor{response: validAgentAnswerResponse("unused")}
	echoServer := echo.New()
	service.registerAgentRoutes(echoServer, aiagent.Config{Enabled: true}, executor)

	unauthenticated := httptest.NewRequest(http.MethodPost, aiagent.BrowserAnswerPath, http.NoBody)
	unauthenticated.Body = io.NopCloser(strings.NewReader(`{"question":"Docker ports","limit":3}`))
	unauthenticatedResponse := httptest.NewRecorder()
	echoServer.ServeHTTP(unauthenticatedResponse, unauthenticated)
	require.Equal(t, http.StatusUnauthorized, unauthenticatedResponse.Code)

	withScope := httptest.NewRequest(http.MethodPost, aiagent.BrowserAnswerPath, http.NoBody)
	withScope.Body = io.NopCloser(strings.NewReader(`{"question":"Docker ports","limit":3,"visible_memo_uids":["forbidden"]}`))
	withScope.Header.Set("Authorization", bearerToken(t, caller))
	withScopeResponse := httptest.NewRecorder()
	echoServer.ServeHTTP(withScopeResponse, withScope)
	require.Equal(t, http.StatusBadRequest, withScopeResponse.Code)
	require.Zero(t, executor.calls)
}

func TestAgentBFFIsNotAvailableWhenDisabledAndMapsSafeFailures(t *testing.T) {
	service := &APIV1Service{Store: teststore.NewTestingStore(context.Background(), t), Secret: "test-secret"}
	t.Cleanup(func() { _ = service.Store.Close() })
	echoServer := echo.New()
	executor := &recordingAgentExecutor{}
	service.registerAgentRoutes(echoServer, aiagent.Config{}, executor)

	disabled := httptest.NewRequest(http.MethodPost, aiagent.BrowserAnswerPath, http.NoBody)
	disabledResponse := httptest.NewRecorder()
	echoServer.ServeHTTP(disabledResponse, disabled)
	require.Equal(t, http.StatusNotFound, disabledResponse.Code)
	require.Zero(t, executor.calls)

	caller := createAgentVisibilityUser(t, context.Background(), service.Store, "agent-bff-errors")
	executor.err = errors.New("raw internal error")
	echoServer = echo.New()
	service.registerAgentRoutes(echoServer, aiagent.Config{Enabled: true}, executor)
	request := httptest.NewRequest(http.MethodPost, aiagent.BrowserAnswerPath, http.NoBody)
	request.Body = io.NopCloser(strings.NewReader(`{"question":"Docker ports","limit":3}`))
	request.Header.Set("Authorization", bearerToken(t, caller))
	response := httptest.NewRecorder()
	echoServer.ServeHTTP(response, request)
	require.Equal(t, http.StatusServiceUnavailable, response.Code)
	require.Equal(t, `{"detail":"Agent service unavailable"}`+"\n", response.Body.String())
}

func validAgentAnswerResponse(memoID string) aiagent.AnswerResponse {
	count := 1
	return aiagent.AnswerResponse{
		Answer:         "Authorized answer [1].",
		Provider:       "deterministic",
		RetrievedCount: 1,
		AgentVersion:   "evidence-answer-agent-v1",
		Citations: []aiagent.Citation{{
			MemoID:      memoID,
			EmbeddingID: memoID,
			Title:       "Safe title",
			Summary:     "Authorized complete Memo retrieved as evidence.",
			SourceRefs:  []string{"memos/" + memoID},
			Metadata:    aiagent.Metadata{MemoType: "plain", IndexVersion: "memo-v1"},
		}},
		Trace: aiagent.Trace{TerminalState: "answered", Steps: []aiagent.Step{
			{Index: 1, Kind: "tool", Name: "search_memos", Status: "completed", ResultCount: &count},
			{Index: 2, Kind: "final", Name: "answer_from_evidence", Status: "completed"},
		}},
	}
}

func bearerToken(t *testing.T, user *store.User) string {
	t.Helper()
	token, _, err := auth.GenerateAccessTokenV2(user.ID, user.Username, string(user.Role), "ACTIVE", []byte("test-secret"))
	require.NoError(t, err)
	return "Bearer " + token
}
