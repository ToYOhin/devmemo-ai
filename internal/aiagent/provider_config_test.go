package aiagent

import (
	"context"
	"encoding/json"
	"io"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
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

type providerTestTransport func(*http.Request) (*http.Response, error)

func (transport providerTestTransport) RoundTrip(request *http.Request) (*http.Response, error) {
	return transport(request)
}

func TestAgentClientRequestTimeoutBudgets(t *testing.T) {
	data, err := os.ReadFile(filepath.Join("..", "..", "contracts", "agent-provider-config-v1.json"))
	require.NoError(t, err)
	var contract struct {
		Budget struct {
			Provider int `json:"provider_seconds"`
			BFF      int `json:"bff_provider_seconds"`
			Metadata int `json:"bff_metadata_seconds"`
		} `json:"timeout_budget"`
	}
	require.NoError(t, json.Unmarshal(data, &contract))
	require.Equal(t, 20, contract.Budget.Provider)
	require.Equal(t, 25, contract.Budget.BFF)
	require.Equal(t, 10, contract.Budget.Metadata)

	// Serial synthetic transport: no network or wall-clock timeout wait is needed.
	originalTransport := http.DefaultTransport
	t.Cleanup(func() { http.DefaultTransport = originalTransport })
	for _, test := range []struct {
		method string
		path   string
		budget int
	}{
		{http.MethodPost, InternalAnswerPath, contract.Budget.BFF},
		{http.MethodPost, InternalAgentRunExecutePath, contract.Budget.BFF},
		{http.MethodPost, InternalAgentProviderTestPath, contract.Budget.BFF},
		{http.MethodGet, InternalAgentProviderPath, contract.Budget.Metadata},
		{http.MethodPut, InternalAgentProviderPath, contract.Budget.Metadata},
		{http.MethodPost, InternalAgentRunCreatePath, contract.Budget.Metadata},
		{http.MethodPost, InternalAgentRunStatusPath, contract.Budget.Metadata},
		{http.MethodPost, InternalAgentRunArtifactPath, contract.Budget.Metadata},
		{http.MethodGet, InternalAgentProviderTestPath, contract.Budget.Metadata},
	} {
		t.Run(test.method+test.path, func(t *testing.T) {
			http.DefaultTransport = providerTestTransport(func(request *http.Request) (*http.Response, error) {
				deadline, ok := request.Context().Deadline()
				require.True(t, ok)
				require.InDelta(t, float64(test.budget), time.Until(deadline).Seconds(), 0.5)
				return jsonResponse(http.StatusOK, `{}`), nil
			})
			client, err := NewClient(Config{Enabled: true, InternalURL: "http://synthetic.invalid", Secret: "synthetic-secret"})
			require.NoError(t, err)
			request, err := http.NewRequestWithContext(context.Background(), test.method, client.config.InternalURL+test.path, nil)
			require.NoError(t, err)
			response, err := client.doer.Do(request)
			require.NoError(t, err)
			require.NoError(t, response.Body.Close())
		})
	}
}

func TestAgentProviderClientHonorsEarlierCallerDeadline(t *testing.T) {
	originalTransport := http.DefaultTransport
	t.Cleanup(func() { http.DefaultTransport = originalTransport })
	http.DefaultTransport = providerTestTransport(func(request *http.Request) (*http.Response, error) {
		<-request.Context().Done()
		return nil, request.Context().Err()
	})
	client, err := NewClient(Config{Enabled: true, InternalURL: "http://synthetic.invalid", Secret: "synthetic-secret"})
	require.NoError(t, err)
	ctx, cancel := context.WithTimeout(context.Background(), 20*time.Millisecond)
	defer cancel()
	started := time.Now()
	_, err = client.TestAgentProvider(ctx)
	require.ErrorIs(t, err, ErrUnavailable)
	require.ErrorIs(t, ctx.Err(), context.DeadlineExceeded)
	require.Less(t, time.Since(started), time.Second)
}

func TestAgentProviderClientAcceptsResponseAfterOldTenSecondLimit(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		timer := time.NewTimer(11 * time.Second)
		defer timer.Stop()
		select {
		case <-r.Context().Done():
			return
		case <-timer.C:
			w.Header().Set("Content-Type", "application/json")
			_, _ = io.WriteString(w, `{"status":"ok","provider":"openai","model":"synthetic","latency_ms":11000}`)
		}
	}))
	defer server.Close()
	client, err := NewClient(Config{Enabled: true, InternalURL: server.URL, Secret: "synthetic-secret"})
	require.NoError(t, err)
	result, err := client.TestAgentProvider(context.Background())
	require.NoError(t, err)
	require.Equal(t, "ok", result.Status)
	require.Equal(t, 11000, result.LatencyMS)
}
