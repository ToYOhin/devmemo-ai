package aiagent

import (
	"context"
	"io"
	"net/http"
	"strings"
	"testing"
	"time"

	"github.com/stretchr/testify/require"
)

func TestAgentProviderClientSignsUpdateAndAcceptsOnlyMaskedResponse(t *testing.T) {
	config := Config{Enabled: true, InternalURL: "http://ai-service:8000", Secret: "test-agent-secret"}
	client, err := NewClient(config)
	require.NoError(t, err)
	now := time.Date(2026, time.August, 14, 8, 0, 0, 0, time.UTC)
	client.now = func() time.Time { return now }
	client.doer = testHTTPDoer(func(request *http.Request) (*http.Response, error) {
		require.Equal(t, http.MethodPut, request.Method)
		require.Equal(t, InternalAgentProviderPath, request.URL.Path)
		body, err := io.ReadAll(request.Body)
		require.NoError(t, err)
		require.Contains(t, string(body), `"api_key":"synthetic-secret-value"`)
		require.NoError(t, VerifyRequest(
			request.Method,
			request.URL.Path,
			body,
			SignedHeaders{
				Signature: request.Header.Get(SignatureHeader),
				Timestamp: request.Header.Get(TimestampHeader),
			},
			now,
			time.Minute,
			config.Secret,
		))
		return jsonResponse(http.StatusOK, validAgentProviderSettingsJSON()), nil
	})

	settings, err := client.UpdateAgentProviderSettings(context.Background(), AgentProviderUpdateRequest{
		Version:           AgentProviderConfigVersion,
		Provider:          "openai",
		Model:             "gpt-4o-mini",
		BaseURL:           "https://api.openai.com/v1",
		APIKey:            "synthetic-secret-value",
		Enabled:           true,
		AllowRealMemoData: false,
	})

	require.NoError(t, err)
	require.True(t, settings.APIKeySet)
	require.Equal(t, "••••alue", settings.APIKeyHint)
}

func TestAgentProviderClientSignsEmptyGetBodyAndRejectsRawKeyResponse(t *testing.T) {
	config := Config{Enabled: true, InternalURL: "http://ai-service:8000", Secret: "test-agent-secret"}
	client, err := NewClient(config)
	require.NoError(t, err)
	now := time.Date(2026, time.August, 14, 8, 0, 0, 0, time.UTC)
	client.now = func() time.Time { return now }
	client.doer = testHTTPDoer(func(request *http.Request) (*http.Response, error) {
		body, err := io.ReadAll(request.Body)
		require.NoError(t, err)
		require.Empty(t, body)
		require.NoError(t, VerifyRequest(
			request.Method,
			request.URL.Path,
			body,
			SignedHeaders{
				Signature: request.Header.Get(SignatureHeader),
				Timestamp: request.Header.Get(TimestampHeader),
			},
			now,
			time.Minute,
			config.Secret,
		))
		unsafe := strings.Replace(validAgentProviderSettingsJSON(), `"api_key_set":true`, `"api_key_set":true,"api_key":"secret"`, 1)
		return jsonResponse(http.StatusOK, unsafe), nil
	})

	_, err = client.GetAgentProviderSettings(context.Background())

	require.ErrorIs(t, err, ErrInvalidResponse)
}

func validAgentProviderSettingsJSON() string {
	return `{"version":"agent-provider-config-v1","provider":"openai","model":"gpt-4o-mini","base_url":"https://api.openai.com/v1","enabled":true,"allow_real_memo_data":false,"api_key_set":true,"api_key_hint":"••••alue","config_version":1,"source":"stored"}`
}
