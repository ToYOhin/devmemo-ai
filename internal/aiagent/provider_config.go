package aiagent

import (
	"bytes"
	"context"
	"encoding/json"
	"io"
	"net/http"
	"strings"
)

const (
	AgentProviderConfigVersion    = "agent-provider-config-v1"
	BrowserAgentProviderPath      = "/api/ai/agent/provider"
	BrowserAgentProviderTestPath  = "/api/ai/agent/provider/test"
	InternalAgentProviderPath     = "/internal/ai/agent/provider"
	InternalAgentProviderTestPath = "/internal/ai/agent/provider/test"
)

type AgentProviderSettings struct {
	Version           string `json:"version"`
	Provider          string `json:"provider"`
	Model             string `json:"model"`
	BaseURL           string `json:"base_url"`
	Enabled           bool   `json:"enabled"`
	AllowRealMemoData bool   `json:"allow_real_memo_data"`
	APIKeySet         bool   `json:"api_key_set"`
	APIKeyHint        string `json:"api_key_hint"`
	ConfigVersion     int    `json:"config_version"`
	Source            string `json:"source"`
}

type AgentProviderUpdateRequest struct {
	Version           string `json:"version"`
	Provider          string `json:"provider"`
	Model             string `json:"model"`
	BaseURL           string `json:"base_url"`
	APIKey            string `json:"api_key,omitempty"`
	Enabled           bool   `json:"enabled"`
	AllowRealMemoData bool   `json:"allow_real_memo_data"`
}

type AgentProviderTestResult struct {
	Status    string `json:"status"`
	Provider  string `json:"provider"`
	Model     string `json:"model"`
	LatencyMS int    `json:"latency_ms"`
}

type AgentProviderSettingsExecutor interface {
	GetAgentProviderSettings(context.Context) (AgentProviderSettings, error)
	UpdateAgentProviderSettings(context.Context, AgentProviderUpdateRequest) (AgentProviderSettings, error)
	TestAgentProvider(context.Context) (AgentProviderTestResult, error)
}

func (c *Client) GetAgentProviderSettings(ctx context.Context) (AgentProviderSettings, error) {
	var response AgentProviderSettings
	err := c.executeAgentProviderRequest(ctx, http.MethodGet, InternalAgentProviderPath, nil, &response)
	if err != nil {
		return AgentProviderSettings{}, err
	}
	if err := response.validate(); err != nil {
		return AgentProviderSettings{}, ErrInvalidResponse
	}
	return response, nil
}

func (c *Client) UpdateAgentProviderSettings(ctx context.Context, input AgentProviderUpdateRequest) (AgentProviderSettings, error) {
	if err := input.Validate(); err != nil {
		return AgentProviderSettings{}, err
	}
	var response AgentProviderSettings
	err := c.executeAgentProviderRequest(ctx, http.MethodPut, InternalAgentProviderPath, input, &response)
	if err != nil {
		return AgentProviderSettings{}, err
	}
	if err := response.validate(); err != nil {
		return AgentProviderSettings{}, ErrInvalidResponse
	}
	return response, nil
}

func (c *Client) TestAgentProvider(ctx context.Context) (AgentProviderTestResult, error) {
	payload := map[string]string{"version": AgentProviderConfigVersion}
	var response AgentProviderTestResult
	err := c.executeAgentProviderRequest(ctx, http.MethodPost, InternalAgentProviderTestPath, payload, &response)
	if err != nil {
		return AgentProviderTestResult{}, err
	}
	if response.Status != "ok" || strings.TrimSpace(response.Provider) == "" || response.LatencyMS < 0 {
		return AgentProviderTestResult{}, ErrInvalidResponse
	}
	return response, nil
}

func (c *Client) executeAgentProviderRequest(ctx context.Context, method, path string, payload any, target any) error {
	body := []byte{}
	var err error
	if payload != nil {
		body, err = json.Marshal(payload)
		if err != nil {
			return ErrUnavailable
		}
	}
	headers, err := SignRequest(method, path, body, c.now(), c.config.Secret)
	if err != nil {
		return ErrUnavailable
	}
	req, err := http.NewRequestWithContext(
		ctx,
		method,
		strings.TrimRight(c.config.InternalURL, "/")+path,
		bytes.NewReader(body),
	)
	if err != nil {
		return ErrUnavailable
	}
	if payload != nil {
		req.Header.Set("Content-Type", "application/json")
	}
	req.Header.Set(SignatureHeader, headers.Signature)
	req.Header.Set(TimestampHeader, headers.Timestamp)
	response, err := c.doer.Do(req)
	if err != nil {
		return ErrUnavailable
	}
	defer response.Body.Close()
	switch response.StatusCode {
	case http.StatusOK:
	case http.StatusBadRequest:
		return ErrInvalidProviderConfig
	case http.StatusBadGateway:
		return ErrProviderFailed
	default:
		return ErrUnavailable
	}
	responseBody, err := io.ReadAll(io.LimitReader(response.Body, maxResponseBytes+1))
	if err != nil || len(responseBody) > maxResponseBytes {
		return ErrInvalidResponse
	}
	decoder := json.NewDecoder(bytes.NewReader(responseBody))
	decoder.DisallowUnknownFields()
	if err := decoder.Decode(target); err != nil {
		return ErrInvalidResponse
	}
	var extra any
	if err := decoder.Decode(&extra); err != io.EOF {
		return ErrInvalidResponse
	}
	return nil
}

func (r AgentProviderUpdateRequest) Validate() error {
	if r.Version != AgentProviderConfigVersion || strings.TrimSpace(r.Provider) == "" {
		return ErrInvalidProviderConfig
	}
	if len(r.Model) > 128 || len(r.BaseURL) > 2048 || len(r.APIKey) > 4096 {
		return ErrInvalidProviderConfig
	}
	return nil
}

func (r AgentProviderSettings) validate() error {
	if r.Version != AgentProviderConfigVersion || strings.TrimSpace(r.Provider) == "" || r.ConfigVersion < 0 {
		return ErrInvalidResponse
	}
	if r.APIKeySet == (r.APIKeyHint == "") || len(r.APIKeyHint) > 32 {
		return ErrInvalidResponse
	}
	if r.Source != "stored" && r.Source != "environment" {
		return ErrInvalidResponse
	}
	return nil
}
