package aiagent

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"io"
	"net/http"
	"net/url"
	"strings"
	"time"
)

const (
	// BrowserAnswerPath is the Memos-only BFF route; it is never sent to AI Service.
	BrowserAnswerPath = "/api/ai/agent/answer"
	maxResponseBytes  = 1 << 20
)

var (
	ErrUnavailable     = errors.New("agent service unavailable")
	ErrRetrievalFailed = errors.New("agent retrieval unavailable")
	ErrProviderFailed  = errors.New("agent provider unavailable")
	ErrInvalidResponse = errors.New("invalid agent service response")
	ErrInvalidConfig   = errors.New("invalid agent configuration")
	ErrConflict        = errors.New("agent request conflicts")
	ErrNotFound        = errors.New("agent run not found")
)

// Config is the Memos-side, local-first Agent composition. It is disabled by default.
type Config struct {
	Enabled     bool
	InternalURL string
	Secret      string
}

// Validate keeps disabled configurations inert and requires a dedicated secret when enabled.
func (c Config) Validate() error {
	if !c.Enabled {
		return nil
	}
	if strings.TrimSpace(c.Secret) == "" {
		return ErrInvalidConfig
	}
	parsed, err := url.Parse(strings.TrimSpace(c.InternalURL))
	if err != nil || parsed.Scheme == "" || parsed.Host == "" || parsed.User != nil {
		return ErrInvalidConfig
	}
	if parsed.Scheme != "http" && parsed.Scheme != "https" {
		return ErrInvalidConfig
	}
	return nil
}

// AnswerExecutor allows the BFF handler to be verified without a network service.
type AnswerExecutor interface {
	Answer(context.Context, DelegatedAnswerRequest) (AnswerResponse, error)
}

type httpDoer interface {
	Do(*http.Request) (*http.Response, error)
}

// Client sends a signed, capability-scoped request to the AI internal endpoint.
type Client struct {
	config Config
	doer   httpDoer
	now    func() time.Time
}

func NewClient(config Config) (*Client, error) {
	if err := config.Validate(); err != nil {
		return nil, err
	}
	return &Client{
		config: config,
		doer:   &http.Client{Timeout: 10 * time.Second},
		now:    time.Now,
	}, nil
}

// Answer calls only the fixed internal route and strictly projects its safe result contract.
func (c *Client) Answer(ctx context.Context, delegated DelegatedAnswerRequest) (AnswerResponse, error) {
	if err := delegated.Validate(); err != nil {
		return AnswerResponse{}, err
	}
	body, err := json.Marshal(delegated)
	if err != nil {
		return AnswerResponse{}, ErrUnavailable
	}
	headers, err := SignRequest(http.MethodPost, InternalAnswerPath, body, c.now(), c.config.Secret)
	if err != nil {
		return AnswerResponse{}, ErrUnavailable
	}

	req, err := http.NewRequestWithContext(
		ctx,
		http.MethodPost,
		strings.TrimRight(c.config.InternalURL, "/")+InternalAnswerPath,
		bytes.NewReader(body),
	)
	if err != nil {
		return AnswerResponse{}, ErrUnavailable
	}
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set(SignatureHeader, headers.Signature)
	req.Header.Set(TimestampHeader, headers.Timestamp)

	resp, err := c.doer.Do(req)
	if err != nil {
		return AnswerResponse{}, ErrUnavailable
	}
	defer resp.Body.Close()
	if resp.StatusCode == http.StatusServiceUnavailable {
		return AnswerResponse{}, ErrRetrievalFailed
	}
	if resp.StatusCode == http.StatusBadGateway {
		return AnswerResponse{}, ErrProviderFailed
	}
	if resp.StatusCode != http.StatusOK {
		return AnswerResponse{}, ErrUnavailable
	}

	responseBody, err := io.ReadAll(io.LimitReader(resp.Body, maxResponseBytes+1))
	if err != nil || len(responseBody) > maxResponseBytes {
		return AnswerResponse{}, ErrInvalidResponse
	}
	response, err := decodeAnswerResponse(responseBody, delegated.VisibleMemoUIDs)
	if err != nil {
		return AnswerResponse{}, ErrInvalidResponse
	}
	return response, nil
}
