package aiagent

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"io"
	"net/http"
	"regexp"
	"strings"
)

const (
	BrowserAgentRunCreatePath  = "/api/ai/agent/runs"
	BrowserAgentRunStatusPath  = "/api/ai/agent/runs/:runID"
	InternalAgentRunCreatePath = "/internal/ai/agent/runs"
	InternalAgentRunStatusPath = "/internal/ai/agent/runs/status"
)

var (
	opaqueAgentRunID = regexp.MustCompile(`^[a-z][a-z0-9]*(?:[-_][a-z0-9]+)+$`)
	agentRunDigest   = regexp.MustCompile(`^[a-f0-9]{64}$`)
)

type AgentRunSourceRevision struct {
	SourceID string `json:"source_id"`
	Revision string `json:"revision"`
}

type DelegatedAgentRunCreateRequest struct {
	SubjectID      string                   `json:"subject_id"`
	ScopeRef       string                   `json:"scope_ref"`
	RequestKey     string                   `json:"request_key"`
	RequestDigest  string                   `json:"request_digest"`
	SourceSnapshot []AgentRunSourceRevision `json:"source_snapshot"`
}

type AgentRunStatusRequest struct {
	SubjectID string `json:"subject_id"`
	RunID     string `json:"run_id"`
}

type AgentRunStatusResponse struct {
	RunID          string  `json:"run_id"`
	Status         string  `json:"status"`
	CreatedAt      string  `json:"created_at"`
	UpdatedAt      string  `json:"updated_at"`
	LastEventSeq   int     `json:"last_event_seq"`
	SourceCount    int     `json:"source_count"`
	TerminalReason *string `json:"terminal_reason"`
}

type AgentRunExecutor interface {
	CreateRun(context.Context, DelegatedAgentRunCreateRequest) (AgentRunStatusResponse, error)
	GetRun(context.Context, AgentRunStatusRequest) (AgentRunStatusResponse, error)
}

func (c *Client) CreateRun(ctx context.Context, delegated DelegatedAgentRunCreateRequest) (AgentRunStatusResponse, error) {
	if err := delegated.Validate(); err != nil {
		return AgentRunStatusResponse{}, err
	}
	return c.executeAgentRunRequest(ctx, InternalAgentRunCreatePath, delegated)
}

func (c *Client) GetRun(ctx context.Context, request AgentRunStatusRequest) (AgentRunStatusResponse, error) {
	if !opaqueAgentRunID.MatchString(request.SubjectID) || !opaqueAgentRunID.MatchString(request.RunID) {
		return AgentRunStatusResponse{}, ErrInvalidResponse
	}
	return c.executeAgentRunRequest(ctx, InternalAgentRunStatusPath, request)
}

func (r DelegatedAgentRunCreateRequest) Validate() error {
	if !opaqueAgentRunID.MatchString(r.SubjectID) || !opaqueAgentRunID.MatchString(r.ScopeRef) ||
		!opaqueAgentRunID.MatchString(r.RequestKey) || !agentRunDigest.MatchString(r.RequestDigest) ||
		len(r.SourceSnapshot) < 1 || len(r.SourceSnapshot) > 10 {
		return ErrInvalidResponse
	}
	seen := make(map[string]struct{}, len(r.SourceSnapshot))
	for _, source := range r.SourceSnapshot {
		if !opaqueAgentRunID.MatchString(source.SourceID) || !opaqueAgentRunID.MatchString(source.Revision) {
			return ErrInvalidResponse
		}
		if _, ok := seen[source.SourceID]; ok {
			return ErrInvalidResponse
		}
		seen[source.SourceID] = struct{}{}
	}
	return nil
}

func (c *Client) executeAgentRunRequest(ctx context.Context, path string, payload any) (AgentRunStatusResponse, error) {
	body, err := json.Marshal(payload)
	if err != nil {
		return AgentRunStatusResponse{}, ErrUnavailable
	}
	headers, err := SignRequest(http.MethodPost, path, body, c.now(), c.config.Secret)
	if err != nil {
		return AgentRunStatusResponse{}, ErrUnavailable
	}
	req, err := http.NewRequestWithContext(ctx, http.MethodPost, strings.TrimRight(c.config.InternalURL, "/")+path, bytes.NewReader(body))
	if err != nil {
		return AgentRunStatusResponse{}, ErrUnavailable
	}
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set(SignatureHeader, headers.Signature)
	req.Header.Set(TimestampHeader, headers.Timestamp)
	resp, err := c.doer.Do(req)
	if err != nil {
		return AgentRunStatusResponse{}, ErrUnavailable
	}
	defer resp.Body.Close()
	if resp.StatusCode == http.StatusConflict {
		return AgentRunStatusResponse{}, ErrConflict
	}
	if resp.StatusCode == http.StatusNotFound {
		return AgentRunStatusResponse{}, ErrNotFound
	}
	if resp.StatusCode != http.StatusOK {
		return AgentRunStatusResponse{}, ErrUnavailable
	}
	body, err = io.ReadAll(io.LimitReader(resp.Body, maxResponseBytes+1))
	if err != nil || len(body) > maxResponseBytes {
		return AgentRunStatusResponse{}, ErrInvalidResponse
	}
	decoder := json.NewDecoder(bytes.NewReader(body))
	decoder.DisallowUnknownFields()
	var result AgentRunStatusResponse
	if err := decoder.Decode(&result); err != nil {
		return AgentRunStatusResponse{}, ErrInvalidResponse
	}
	var extra any
	if err := decoder.Decode(&extra); !errors.Is(err, io.EOF) || result.validate() != nil {
		return AgentRunStatusResponse{}, ErrInvalidResponse
	}
	return result, nil
}

func (r AgentRunStatusResponse) validate() error {
	if !opaqueAgentRunID.MatchString(r.RunID) || r.CreatedAt == "" || r.UpdatedAt == "" ||
		r.LastEventSeq < 0 || r.SourceCount < 1 || r.SourceCount > 10 {
		return ErrInvalidResponse
	}
	switch r.Status {
	case "queued", "running", "waiting_approval", "succeeded", "failed", "cancelled", "expired":
		return nil
	default:
		return ErrInvalidResponse
	}
}
