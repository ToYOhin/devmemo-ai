package v1

import (
	"context"
	"io"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"github.com/labstack/echo/v5"
	"github.com/stretchr/testify/require"

	"github.com/usememos/memos/internal/aiagent"
	"github.com/usememos/memos/store"
	teststore "github.com/usememos/memos/store/test"
)

type recordingLegacyAIExecutor struct {
	method  string
	path    string
	body    []byte
	status  int
	payload []byte
	err     error
	calls   int
}

func (e *recordingLegacyAIExecutor) Execute(_ context.Context, method, path string, body []byte) (int, []byte, error) {
	e.calls++
	e.method = method
	e.path = path
	e.body = append([]byte(nil), body...)
	return e.status, e.payload, e.err
}

func TestLegacyAIBFFAuthorizesMemoAndProjectsSafeNote(t *testing.T) {
	ctx := context.Background()
	testStore := teststore.NewTestingStore(ctx, t)
	t.Cleanup(func() { _ = testStore.Close() })
	service := &APIV1Service{Store: testStore, Secret: "test-secret"}
	owner := createAgentVisibilityUser(ctx, t, testStore, "legacy-bff-owner")
	other := createAgentVisibilityUser(ctx, t, testStore, "legacy-bff-other")
	createAgentVisibilityMemo(ctx, t, testStore, "legacy-bff-private", owner.ID, store.Private)
	executor := &recordingLegacyAIExecutor{
		status: http.StatusOK,
		payload: []byte(`{
			"memo_id":"legacy-bff-private","summary":"safe","keywords":[],
			"category":"other","suggested_tags":[],"provider":"deterministic",
			"created_at":"2026-08-12T00:00:00Z","internal_secret":"must-not-project"
		}`),
	}
	echoServer := echo.New()
	service.registerLegacyAIRoutes(echoServer, aiagent.Config{Enabled: true}, executor)

	unauthorized := httptest.NewRequest(http.MethodGet, "/api/ai/notes/legacy-bff-private", http.NoBody)
	unauthorized.Header.Set("Authorization", bearerToken(t, other))
	unauthorizedResponse := httptest.NewRecorder()
	echoServer.ServeHTTP(unauthorizedResponse, unauthorized)
	require.Equal(t, http.StatusNotFound, unauthorizedResponse.Code)
	require.Zero(t, executor.calls)

	request := httptest.NewRequest(http.MethodGet, "/api/ai/notes/legacy-bff-private", http.NoBody)
	request.Header.Set("Authorization", bearerToken(t, owner))
	response := httptest.NewRecorder()
	echoServer.ServeHTTP(response, request)

	require.Equal(t, http.StatusOK, response.Code)
	require.Equal(t, http.MethodGet, executor.method)
	require.Equal(t, "/api/ai/notes/legacy-bff-private", executor.path)
	require.NotContains(t, response.Body.String(), "internal_secret")
	require.JSONEq(t, `{
		"memo_id":"legacy-bff-private","summary":"safe","keywords":[],
		"category":"other","suggested_tags":[],"provider":"deterministic",
		"created_at":"2026-08-12T00:00:00Z"
	}`, response.Body.String())
}

func TestLegacyAIBFFBuildsSummaryFromAuthorizedStoreMemo(t *testing.T) {
	ctx := context.Background()
	testStore := teststore.NewTestingStore(ctx, t)
	t.Cleanup(func() { _ = testStore.Close() })
	service := &APIV1Service{Store: testStore, Secret: "test-secret"}
	owner := createAgentVisibilityUser(ctx, t, testStore, "legacy-summary-owner")
	createAgentVisibilityMemo(ctx, t, testStore, "legacy-summary-private", owner.ID, store.Private)
	executor := &recordingLegacyAIExecutor{
		status: http.StatusOK,
		payload: []byte(`{
			"memo_id":"legacy-summary-private","summary":"safe","keywords":[],
			"category":"other","suggested_tags":[],"provider":"deterministic",
			"created_at":"2026-08-12T00:00:00Z"
		}`),
	}
	echoServer := echo.New()
	service.registerLegacyAIRoutes(echoServer, aiagent.Config{Enabled: true}, executor)

	request := httptest.NewRequest(http.MethodPost, "/api/ai/summarize", io.NopCloser(strings.NewReader(`{
		"memo_id":"legacy-summary-private","content":"browser-forged-content"
	}`)))
	request.Header.Set("Content-Type", "application/json")
	request.Header.Set("Authorization", bearerToken(t, owner))
	response := httptest.NewRecorder()
	echoServer.ServeHTTP(response, request)

	require.Equal(t, http.StatusBadRequest, response.Code)
	require.Zero(t, executor.calls)

	request = httptest.NewRequest(http.MethodPost, "/api/ai/summarize", io.NopCloser(strings.NewReader(`{
		"memo_id":"legacy-summary-private"
	}`)))
	request.Header.Set("Content-Type", "application/json")
	request.Header.Set("Authorization", bearerToken(t, owner))
	response = httptest.NewRecorder()
	echoServer.ServeHTTP(response, request)

	require.Equal(t, http.StatusOK, response.Code)
	require.Equal(t, http.MethodPost, executor.method)
	require.Equal(t, "/api/ai/summarize", executor.path)
	require.JSONEq(t, `{
		"memo_id":"legacy-summary-private","title":"","content":"test memo content","tags":[]
	}`, string(executor.body))
}

func TestLegacyAIBFFProjectsTemplateAndInsightsWithoutInternalFields(t *testing.T) {
	ctx := context.Background()
	testStore := teststore.NewTestingStore(ctx, t)
	t.Cleanup(func() { _ = testStore.Close() })
	service := &APIV1Service{Store: testStore, Secret: "test-secret"}
	owner := createAgentVisibilityUser(ctx, t, testStore, "legacy-projection-owner")
	createAgentVisibilityMemo(ctx, t, testStore, "legacy-projection-memo", owner.ID, store.Private)
	executor := &recordingLegacyAIExecutor{status: http.StatusOK}
	echoServer := echo.New()
	service.registerLegacyAIRoutes(echoServer, aiagent.Config{Enabled: true}, executor)

	executor.payload = []byte(`{
		"memo_id":"legacy-projection-memo","kind":"code",
		"payload":{"title":"safe","language":"go","code":"fmt.Println()","description":"safe","tags":[],"secret":"drop"},
		"raw_content":"authorized content","created_at":"2026-08-12T00:00:00Z",
		"updated_at":"2026-08-12T00:00:00Z","provider_trace":"drop"
	}`)
	request := httptest.NewRequest(http.MethodGet, "/api/ai/templates/legacy-projection-memo", http.NoBody)
	request.Header.Set("Authorization", bearerToken(t, owner))
	response := httptest.NewRecorder()
	echoServer.ServeHTTP(response, request)
	require.Equal(t, http.StatusOK, response.Code)
	require.NotContains(t, response.Body.String(), "secret")
	require.NotContains(t, response.Body.String(), "provider_trace")

	executor.payload = []byte(`[{
		"insight_id":"insight-001","memo_id":"legacy-projection-memo","insight_type":"fact",
		"title":"safe","summary":"safe","confidence":0.8,"status":"pending",
		"source_refs":["summary"],"version":1,"created_at":"2026-08-12T00:00:00Z",
		"updated_at":"2026-08-12T00:00:00Z","embedding":"drop"
	}]`)
	request = httptest.NewRequest(http.MethodGet, "/api/ai/insights/legacy-projection-memo", http.NoBody)
	request.Header.Set("Authorization", bearerToken(t, owner))
	response = httptest.NewRecorder()
	echoServer.ServeHTTP(response, request)
	require.Equal(t, http.StatusOK, response.Code)
	require.NotContains(t, response.Body.String(), "embedding")
}

func TestLegacyAIBFFBindsInsightStatusUpdateToAuthorizedMemo(t *testing.T) {
	ctx := context.Background()
	testStore := teststore.NewTestingStore(ctx, t)
	t.Cleanup(func() { _ = testStore.Close() })
	service := &APIV1Service{Store: testStore, Secret: "test-secret"}
	owner := createAgentVisibilityUser(ctx, t, testStore, "legacy-status-owner")
	createAgentVisibilityMemo(ctx, t, testStore, "legacy-status-memo", owner.ID, store.Private)
	executor := &recordingLegacyAIExecutor{
		status: http.StatusOK,
		payload: []byte(`{
			"insight_id":"insight-001","memo_id":"legacy-status-memo","insight_type":"fact",
			"title":"safe","summary":"safe","confidence":0.8,"status":"accepted",
			"source_refs":["summary"],"version":2,"created_at":"2026-08-12T00:00:00Z",
			"updated_at":"2026-08-12T00:01:00Z"
		}`),
	}
	echoServer := echo.New()
	service.registerLegacyAIRoutes(echoServer, aiagent.Config{Enabled: true}, executor)

	request := httptest.NewRequest(http.MethodPost, "/api/ai/insights/insight-001/status", io.NopCloser(strings.NewReader(`{
		"memo_id":"legacy-status-memo","status":"accepted","version":1
	}`)))
	request.Header.Set("Content-Type", "application/json")
	request.Header.Set("Authorization", bearerToken(t, owner))
	response := httptest.NewRecorder()
	echoServer.ServeHTTP(response, request)

	require.Equal(t, http.StatusOK, response.Code)
	require.Equal(t, "/api/ai/insights/insight-001/status", executor.path)
	require.JSONEq(t, `{"status":"accepted","version":1}`, string(executor.body))

	executor.payload = []byte(`{
		"insight_id":"insight-other","memo_id":"legacy-status-memo","insight_type":"fact",
		"title":"safe","summary":"safe","confidence":0.8,"status":"accepted",
		"source_refs":["summary"],"version":2,"created_at":"2026-08-12T00:00:00Z",
		"updated_at":"2026-08-12T00:01:00Z"
	}`)
	request = httptest.NewRequest(http.MethodPost, "/api/ai/insights/insight-001/status", io.NopCloser(strings.NewReader(`{
		"memo_id":"legacy-status-memo","status":"accepted","version":1
	}`)))
	request.Header.Set("Content-Type", "application/json")
	request.Header.Set("Authorization", bearerToken(t, owner))
	response = httptest.NewRecorder()
	echoServer.ServeHTTP(response, request)
	require.Equal(t, http.StatusServiceUnavailable, response.Code)
}

func TestLegacyAIBFFIsUnavailableWhenAgentModeIsDisabled(t *testing.T) {
	service := &APIV1Service{Store: teststore.NewTestingStore(context.Background(), t), Secret: "test-secret"}
	t.Cleanup(func() { _ = service.Store.Close() })
	executor := &recordingLegacyAIExecutor{}
	echoServer := echo.New()
	service.registerLegacyAIRoutes(echoServer, aiagent.Config{}, executor)

	request := httptest.NewRequest(http.MethodGet, "/api/ai/notes/memo-001", http.NoBody)
	response := httptest.NewRecorder()
	echoServer.ServeHTTP(response, request)

	require.Equal(t, http.StatusNotFound, response.Code)
	require.Zero(t, executor.calls)
}
