package v1

import (
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"github.com/labstack/echo/v5"
	"github.com/stretchr/testify/require"

	"github.com/usememos/memos/internal/aiagent"
)

const (
	r5I11BCurrentSecret  = "AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8"
	r5I11BPreviousSecret = "ICEiIyQlJicoKSorLC0uLzAxMjM0NTY3ODk6Ozw9Pj8"
)

func TestEvidenceRehydrationRouteIsAbsentWhenDisabled(t *testing.T) {
	t.Setenv("AI_AGENT_REHYDRATION_ENABLED", "false")
	t.Setenv("AI_AGENT_REHYDRATION_SECRET_CURRENT", r5I11BCurrentSecret)
	service := &APIV1Service{Secret: "synthetic-session-secret"}
	router := echo.New()

	require.NoError(t, service.registerConfiguredEvidenceRehydrationRoute(router))
	require.Nil(t, service.evidenceRehydrationRuntime)
	request := httptest.NewRequest(http.MethodPost, aiagent.InternalEvidenceRehydrationPath, strings.NewReader(`{}`))
	response := httptest.NewRecorder()
	router.ServeHTTP(response, request)
	require.Equal(t, http.StatusNotFound, response.Code)
	require.NotEmpty(t, response.Body.Bytes())
}

func TestEvidenceRehydrationRouteRegistersOnExistingEchoWhenEnabled(t *testing.T) {
	t.Setenv("AI_AGENT_ENABLED", "true")
	t.Setenv("AI_AGENT_INTERNAL_SECRET", "synthetic-delegation-secret")
	t.Setenv("AI_AGENT_REHYDRATION_ENABLED", "true")
	t.Setenv("AI_AGENT_REHYDRATION_SECRET_CURRENT", r5I11BCurrentSecret)
	t.Setenv("AI_AGENT_REHYDRATION_SECRET_PREVIOUS", r5I11BPreviousSecret)
	service := &APIV1Service{Secret: "synthetic-session-secret"}
	router := echo.New()

	require.NoError(t, service.registerConfiguredEvidenceRehydrationRoute(router))
	require.NotNil(t, service.evidenceRehydrationRuntime)
	require.NotNil(t, service.evidenceRehydrationRuntime.capabilities)
	require.NotNil(t, service.evidenceRehydrationRuntime.handler.previousComposition)

	request := httptest.NewRequest(
		http.MethodPost,
		aiagent.InternalEvidenceRehydrationPath,
		strings.NewReader(`{}`),
	)
	request.Header.Set("Content-Type", evidenceRehydrationHTTPContentType)
	response := httptest.NewRecorder()
	router.ServeHTTP(response, request)

	require.Equal(t, http.StatusNotFound, response.Code)
	require.Empty(t, response.Body.Bytes())
	require.Equal(t, evidenceRehydrationHTTPNoStore, response.Header().Get("Cache-Control"))

	wrongMethod := httptest.NewRequest(http.MethodGet, aiagent.InternalEvidenceRehydrationPath, http.NoBody)
	wrongMethodResponse := httptest.NewRecorder()
	router.ServeHTTP(wrongMethodResponse, wrongMethod)
	require.Equal(t, http.StatusMethodNotAllowed, wrongMethodResponse.Code)
	require.NotEmpty(t, wrongMethodResponse.Body.Bytes())
}

func TestEvidenceRehydrationRuntimeRejectsMemosSessionSecretReuse(t *testing.T) {
	service := &APIV1Service{Secret: r5I11BCurrentSecret}
	_, err := newEvidenceRehydrationMemosRuntime(service, aiagent.EvidenceRehydrationRuntimeConfig{
		Enabled:       true,
		CurrentSecret: r5I11BCurrentSecret,
	})
	require.ErrorIs(t, err, aiagent.ErrInvalidEvidenceRehydrationRuntimeConfig)
}
