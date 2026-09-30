package v1

import (
	"context"
	"errors"
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

type recordingAgentProviderExecutor struct {
	settings aiagent.AgentProviderSettings
	updated  aiagent.AgentProviderUpdateRequest
	test     aiagent.AgentProviderTestResult
	err      error
}

func (e *recordingAgentProviderExecutor) GetAgentProviderSettings(context.Context) (aiagent.AgentProviderSettings, error) {
	return e.settings, e.err
}

func (e *recordingAgentProviderExecutor) UpdateAgentProviderSettings(_ context.Context, input aiagent.AgentProviderUpdateRequest) (aiagent.AgentProviderSettings, error) {
	e.updated = input
	return e.settings, e.err
}

func (e *recordingAgentProviderExecutor) TestAgentProvider(context.Context) (aiagent.AgentProviderTestResult, error) {
	return e.test, e.err
}

func TestAgentProviderBFFIsAdminOnlyAndReturnsMaskedSetting(t *testing.T) {
	ctx := context.Background()
	testStore := teststore.NewTestingStore(ctx, t)
	t.Cleanup(func() { _ = testStore.Close() })
	service := &APIV1Service{Store: testStore, Secret: "test-secret"}
	admin := createAgentProviderUser(ctx, t, testStore, "provider-admin", store.RoleAdmin)
	user := createAgentProviderUser(ctx, t, testStore, "provider-user", store.RoleUser)
	executor := &recordingAgentProviderExecutor{settings: validAgentProviderSettings()}
	server := echo.New()
	service.registerAgentProviderRoutes(server, aiagent.Config{Enabled: true}, executor)

	request := httptest.NewRequest(http.MethodGet, aiagent.BrowserAgentProviderPath, http.NoBody)
	request.Header.Set("Authorization", bearerToken(t, admin))
	response := httptest.NewRecorder()
	server.ServeHTTP(response, request)

	require.Equal(t, http.StatusOK, response.Code)
	require.NotContains(t, response.Body.String(), "synthetic-secret")
	require.JSONEq(t, `{
		"version":"agent-provider-config-v1",
		"provider":"openai",
		"model":"gpt-4o-mini",
		"base_url":"https://api.openai.com/v1",
		"enabled":true,
		"allow_real_memo_data":false,
		"api_key_set":true,
		"api_key_hint":"••••alue",
		"config_version":2,
		"source":"stored"
	}`, response.Body.String())

	denied := httptest.NewRequest(http.MethodGet, aiagent.BrowserAgentProviderPath, http.NoBody)
	denied.Header.Set("Authorization", bearerToken(t, user))
	deniedResponse := httptest.NewRecorder()
	server.ServeHTTP(deniedResponse, denied)
	require.Equal(t, http.StatusForbidden, deniedResponse.Code)
}

func TestAgentProviderBFFAcceptsWriteOnlyKeyWithoutEchoingIt(t *testing.T) {
	ctx := context.Background()
	testStore := teststore.NewTestingStore(ctx, t)
	t.Cleanup(func() { _ = testStore.Close() })
	service := &APIV1Service{Store: testStore, Secret: "test-secret"}
	admin := createAgentProviderUser(ctx, t, testStore, "provider-update-admin", store.RoleAdmin)
	executor := &recordingAgentProviderExecutor{settings: validAgentProviderSettings()}
	server := echo.New()
	service.registerAgentProviderRoutes(server, aiagent.Config{Enabled: true}, executor)
	body := `{"version":"agent-provider-config-v1","provider":"openai","model":"gpt-4o-mini","base_url":"https://api.openai.com/v1","api_key":"synthetic-secret-value","enabled":true,"allow_real_memo_data":true}`
	request := httptest.NewRequest(http.MethodPut, aiagent.BrowserAgentProviderPath, strings.NewReader(body))
	request.Header.Set("Authorization", bearerToken(t, admin))
	request.Header.Set("Content-Type", "application/json")
	response := httptest.NewRecorder()

	server.ServeHTTP(response, request)

	require.Equal(t, http.StatusOK, response.Code)
	require.Equal(t, "synthetic-secret-value", executor.updated.APIKey)
	require.NotContains(t, response.Body.String(), "synthetic-secret-value")
}

func TestAgentProviderBFFMapsSyntheticTestFailureWithoutDetails(t *testing.T) {
	ctx := context.Background()
	testStore := teststore.NewTestingStore(ctx, t)
	t.Cleanup(func() { _ = testStore.Close() })
	service := &APIV1Service{Store: testStore, Secret: "test-secret"}
	admin := createAgentProviderUser(ctx, t, testStore, "provider-test-admin", store.RoleAdmin)
	executor := &recordingAgentProviderExecutor{err: errors.Join(aiagent.ErrProviderFailed, errors.New("upstream secret detail"))}
	server := echo.New()
	service.registerAgentProviderRoutes(server, aiagent.Config{Enabled: true}, executor)
	request := httptest.NewRequest(http.MethodPost, aiagent.BrowserAgentProviderTestPath, http.NoBody)
	request.Header.Set("Authorization", bearerToken(t, admin))
	response := httptest.NewRecorder()

	server.ServeHTTP(response, request)

	require.Equal(t, http.StatusBadGateway, response.Code)
	require.NotContains(t, response.Body.String(), "upstream secret detail")
}

func createAgentProviderUser(ctx context.Context, t *testing.T, testStore *store.Store, username string, role store.Role) *store.User {
	t.Helper()
	user, err := testStore.CreateUser(ctx, &store.User{Username: username, Role: role, Email: username + "@example.com"})
	require.NoError(t, err)
	return user
}

func validAgentProviderSettings() aiagent.AgentProviderSettings {
	return aiagent.AgentProviderSettings{
		Version:           aiagent.AgentProviderConfigVersion,
		Provider:          "openai",
		Model:             "gpt-4o-mini",
		BaseURL:           "https://api.openai.com/v1",
		Enabled:           true,
		AllowRealMemoData: false,
		APIKeySet:         true,
		APIKeyHint:        "••••alue",
		ConfigVersion:     2,
		Source:            "stored",
	}
}
