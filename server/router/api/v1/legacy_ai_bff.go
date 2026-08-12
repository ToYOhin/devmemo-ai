package v1

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"io"
	"net/http"
	"net/url"
	"strconv"
	"strings"
	"time"

	"github.com/labstack/echo/v5"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"

	"github.com/usememos/memos/internal/aiagent"
	"github.com/usememos/memos/server/auth"
	"github.com/usememos/memos/store"
)

const (
	maxLegacyAIBrowserRequestBytes = 16 << 10
	maxLegacyAIResponseBytes       = 1 << 20
)

type legacyAIExecutor interface {
	Execute(ctx context.Context, method, path string, body []byte) (int, []byte, error)
}

type legacyAIHTTPExecutor struct {
	baseURL string
	client  *http.Client
}

func newLegacyAIHTTPExecutor(config aiagent.Config) (*legacyAIHTTPExecutor, error) {
	if err := config.Validate(); err != nil {
		return nil, err
	}
	if !config.Enabled {
		return nil, nil
	}
	return &legacyAIHTTPExecutor{
		baseURL: strings.TrimRight(config.InternalURL, "/"),
		client: &http.Client{
			Timeout: 10 * time.Second,
			CheckRedirect: func(*http.Request, []*http.Request) error {
				return http.ErrUseLastResponse
			},
		},
	}, nil
}

func (e *legacyAIHTTPExecutor) Execute(ctx context.Context, method, path string, body []byte) (int, []byte, error) {
	if (method != http.MethodGet && method != http.MethodPost) || !strings.HasPrefix(path, "/api/ai/") {
		return 0, nil, errors.New("invalid legacy AI request")
	}
	request, err := http.NewRequestWithContext(ctx, method, e.baseURL+path, bytes.NewReader(body))
	if err != nil {
		return 0, nil, err
	}
	request.Header.Set("Accept", "application/json")
	if method == http.MethodPost {
		request.Header.Set("Content-Type", "application/json")
	}
	response, err := e.client.Do(request)
	if err != nil {
		return 0, nil, err
	}
	defer response.Body.Close()
	payload, err := io.ReadAll(io.LimitReader(response.Body, maxLegacyAIResponseBytes+1))
	if err != nil || len(payload) > maxLegacyAIResponseBytes {
		return 0, nil, errors.New("invalid legacy AI response")
	}
	return response.StatusCode, payload, nil
}

type legacyAISummaryRequest struct {
	MemoID string `json:"memo_id"`
}

type legacyAISummaryUpstreamRequest struct {
	MemoID  string   `json:"memo_id"`
	Title   string   `json:"title"`
	Content string   `json:"content"`
	Tags    []string `json:"tags"`
}

type legacyAINoteResponse struct {
	MemoID        any      `json:"memo_id"`
	Summary       string   `json:"summary"`
	Keywords      []string `json:"keywords"`
	Category      string   `json:"category"`
	SuggestedTags []string `json:"suggested_tags"`
	Provider      string   `json:"provider"`
	CreatedAt     string   `json:"created_at"`
}

type legacyAITemplateResponse struct {
	MemoID     any    `json:"memo_id"`
	Kind       string `json:"kind"`
	Payload    any    `json:"payload"`
	RawContent string `json:"raw_content"`
	CreatedAt  string `json:"created_at"`
	UpdatedAt  string `json:"updated_at"`
}

type legacyAICodeTemplate struct {
	Title       string   `json:"title"`
	Language    string   `json:"language"`
	Code        string   `json:"code"`
	Description string   `json:"description"`
	Tags        []string `json:"tags"`
}

type legacyAIBugTemplate struct {
	Title             string   `json:"title"`
	Environment       string   `json:"environment"`
	Error             string   `json:"error"`
	ReproductionSteps string   `json:"reproduction_steps"`
	RootCause         string   `json:"root_cause"`
	Solution          string   `json:"solution"`
	Tags              []string `json:"tags"`
}

type legacyAIInsightResponse struct {
	InsightID   string   `json:"insight_id"`
	MemoID      string   `json:"memo_id"`
	InsightType string   `json:"insight_type"`
	Title       string   `json:"title"`
	Summary     string   `json:"summary"`
	Confidence  float64  `json:"confidence"`
	Status      string   `json:"status"`
	SourceRefs  []string `json:"source_refs"`
	Version     int      `json:"version"`
	CreatedAt   string   `json:"created_at"`
	UpdatedAt   string   `json:"updated_at"`
}

type legacyAIInsightStatusRequest struct {
	MemoID  string `json:"memo_id"`
	Status  string `json:"status"`
	Version int    `json:"version"`
}

type legacyAIInsightStatusUpstreamRequest struct {
	Status  string `json:"status"`
	Version int    `json:"version"`
}

func (s *APIV1Service) registerLegacyAIRoutes(router agentRouteRegistrar, config aiagent.Config, executor legacyAIExecutor) {
	authenticator := auth.NewAuthenticator(s.Store, s.Secret)
	router.GET("/api/ai/notes/:memoID", func(c *echo.Context) error {
		ctx, ok := legacyAIAuthenticatedContext(c, config, authenticator)
		if !ok {
			return nil
		}
		memoID := c.Param("memoID")
		if _, err := s.loadLegacyAIMemo(ctx, memoID); err != nil {
			return legacyAIMemoAccessError(c, err)
		}
		return executeLegacyAINote(ctx, c, executor, http.MethodGet, "/api/ai/notes/"+url.PathEscape(memoID), nil, memoID)
	})

	router.GET("/api/ai/templates/:memoID", func(c *echo.Context) error {
		ctx, ok := legacyAIAuthenticatedContext(c, config, authenticator)
		if !ok {
			return nil
		}
		memoID := c.Param("memoID")
		if _, err := s.loadLegacyAIMemo(ctx, memoID); err != nil {
			return legacyAIMemoAccessError(c, err)
		}
		statusCode, payload, err := executeLegacyAI(ctx, executor, http.MethodGet, "/api/ai/templates/"+url.PathEscape(memoID), nil)
		if err != nil || statusCode != http.StatusOK {
			return legacyAIUpstreamError(c, statusCode)
		}
		projected, err := projectLegacyAITemplate(payload, memoID)
		if err != nil {
			return c.JSON(http.StatusServiceUnavailable, map[string]string{"detail": "AI service unavailable"})
		}
		return c.JSON(http.StatusOK, projected)
	})

	router.GET("/api/ai/insights/:memoID", func(c *echo.Context) error {
		ctx, ok := legacyAIAuthenticatedContext(c, config, authenticator)
		if !ok {
			return nil
		}
		memoID := c.Param("memoID")
		if _, err := s.loadLegacyAIMemo(ctx, memoID); err != nil {
			return legacyAIMemoAccessError(c, err)
		}
		statusCode, payload, err := executeLegacyAI(ctx, executor, http.MethodGet, "/api/ai/insights/"+url.PathEscape(memoID), nil)
		if err != nil || statusCode != http.StatusOK {
			return legacyAIUpstreamError(c, statusCode)
		}
		projected, err := projectLegacyAIInsights(payload, memoID)
		if err != nil {
			return c.JSON(http.StatusServiceUnavailable, map[string]string{"detail": "AI service unavailable"})
		}
		return c.JSON(http.StatusOK, projected)
	})

	router.POST("/api/ai/summarize", func(c *echo.Context) error {
		ctx, ok := legacyAIAuthenticatedContext(c, config, authenticator)
		if !ok {
			return nil
		}
		input, err := decodeLegacyAISummaryRequest(c.Request())
		if err != nil {
			return c.JSON(http.StatusBadRequest, map[string]string{"detail": "invalid AI summary request"})
		}
		memo, err := s.loadLegacyAIMemo(ctx, input.MemoID)
		if err != nil {
			return legacyAIMemoAccessError(c, err)
		}
		title := ""
		tags := []string{}
		if memo.Payload != nil {
			tags = append(tags, memo.Payload.Tags...)
			if memo.Payload.Property != nil {
				title = memo.Payload.Property.Title
			}
		}
		body, err := json.Marshal(legacyAISummaryUpstreamRequest{
			MemoID: input.MemoID, Title: title, Content: memo.Content, Tags: tags,
		})
		if err != nil {
			return c.JSON(http.StatusServiceUnavailable, map[string]string{"detail": "AI service unavailable"})
		}
		return executeLegacyAINote(ctx, c, executor, http.MethodPost, "/api/ai/summarize", body, input.MemoID)
	})

	router.POST("/api/ai/insights/:insightID/status", func(c *echo.Context) error {
		ctx, ok := legacyAIAuthenticatedContext(c, config, authenticator)
		if !ok {
			return nil
		}
		input, err := decodeLegacyAIInsightStatusRequest(c.Request())
		if err != nil {
			return c.JSON(http.StatusBadRequest, map[string]string{"detail": "invalid AI insight request"})
		}
		if _, err := s.loadLegacyAIMemo(ctx, input.MemoID); err != nil {
			return legacyAIMemoAccessError(c, err)
		}
		body, err := json.Marshal(legacyAIInsightStatusUpstreamRequest{Status: input.Status, Version: input.Version})
		if err != nil {
			return c.JSON(http.StatusServiceUnavailable, map[string]string{"detail": "AI service unavailable"})
		}
		statusCode, payload, err := executeLegacyAI(
			ctx, executor, http.MethodPost,
			"/api/ai/insights/"+url.PathEscape(c.Param("insightID"))+"/status", body,
		)
		if err != nil || statusCode != http.StatusOK {
			return legacyAIUpstreamError(c, statusCode)
		}
		projected, err := projectLegacyAIInsight(payload, input.MemoID, c.Param("insightID"))
		if err != nil {
			return c.JSON(http.StatusServiceUnavailable, map[string]string{"detail": "AI service unavailable"})
		}
		return c.JSON(http.StatusOK, projected)
	})
}

func legacyAIAuthenticatedContext(c *echo.Context, config aiagent.Config, authenticator *auth.Authenticator) (context.Context, bool) {
	if !config.Enabled {
		_ = c.JSON(http.StatusNotFound, map[string]string{"detail": "not found"})
		return nil, false
	}
	result := authenticator.Authenticate(c.Request().Context(), c.Request().Header.Get("Authorization"))
	if result == nil {
		_ = c.JSON(http.StatusUnauthorized, map[string]string{"detail": "authentication required"})
		return nil, false
	}
	return auth.ApplyToContext(c.Request().Context(), result), true
}

func (s *APIV1Service) loadLegacyAIMemo(ctx context.Context, memoID string) (*store.Memo, error) {
	if memoID == "" {
		return nil, status.Error(codes.NotFound, "memo not found")
	}
	memo, err := s.Store.GetMemo(ctx, &store.FindMemo{UID: &memoID})
	if err != nil {
		return nil, status.Error(codes.Internal, "failed to get memo")
	}
	if memo == nil {
		return nil, status.Error(codes.NotFound, "memo not found")
	}
	if memo.RowStatus != store.Normal {
		return nil, status.Error(codes.NotFound, "memo not found")
	}
	if err := s.checkMemoReadAccess(ctx, memo); err != nil {
		return nil, err
	}
	return memo, nil
}

func legacyAIMemoAccessError(c *echo.Context, err error) error {
	switch status.Code(err) {
	case codes.Unauthenticated:
		return c.JSON(http.StatusUnauthorized, map[string]string{"detail": "authentication required"})
	case codes.NotFound, codes.PermissionDenied:
		return c.JSON(http.StatusNotFound, map[string]string{"detail": "not found"})
	default:
		return c.JSON(http.StatusServiceUnavailable, map[string]string{"detail": "AI service unavailable"})
	}
}

func decodeLegacyAISummaryRequest(request *http.Request) (legacyAISummaryRequest, error) {
	decoder := json.NewDecoder(io.LimitReader(request.Body, maxLegacyAIBrowserRequestBytes+1))
	decoder.DisallowUnknownFields()
	var input legacyAISummaryRequest
	if err := decoder.Decode(&input); err != nil || input.MemoID == "" {
		return legacyAISummaryRequest{}, errors.New("invalid summary request")
	}
	var extra any
	if err := decoder.Decode(&extra); !errors.Is(err, io.EOF) {
		return legacyAISummaryRequest{}, errors.New("unexpected request data")
	}
	return input, nil
}

func decodeLegacyAIInsightStatusRequest(request *http.Request) (legacyAIInsightStatusRequest, error) {
	decoder := json.NewDecoder(io.LimitReader(request.Body, maxLegacyAIBrowserRequestBytes+1))
	decoder.DisallowUnknownFields()
	var input legacyAIInsightStatusRequest
	if err := decoder.Decode(&input); err != nil || input.MemoID == "" || input.Version < 1 || (input.Status != "accepted" && input.Status != "rejected") {
		return legacyAIInsightStatusRequest{}, errors.New("invalid insight request")
	}
	var extra any
	if err := decoder.Decode(&extra); !errors.Is(err, io.EOF) {
		return legacyAIInsightStatusRequest{}, errors.New("unexpected request data")
	}
	return input, nil
}

func executeLegacyAINote(ctx context.Context, c *echo.Context, executor legacyAIExecutor, method, path string, body []byte, memoID string) error {
	upstreamStatus, payload, err := executeLegacyAI(ctx, executor, method, path, body)
	if err != nil {
		return c.JSON(http.StatusServiceUnavailable, map[string]string{"detail": "AI service unavailable"})
	}
	if upstreamStatus != http.StatusOK {
		return legacyAIUpstreamError(c, upstreamStatus)
	}
	decoder := json.NewDecoder(bytes.NewReader(payload))
	decoder.UseNumber()
	var projected legacyAINoteResponse
	if err := decoder.Decode(&projected); err != nil || !legacyAIMemoIDMatches(projected.MemoID, memoID) ||
		projected.Keywords == nil || projected.SuggestedTags == nil || projected.CreatedAt == "" {
		return c.JSON(http.StatusServiceUnavailable, map[string]string{"detail": "AI service unavailable"})
	}
	return c.JSON(http.StatusOK, projected)
}

func executeLegacyAI(ctx context.Context, executor legacyAIExecutor, method, path string, body []byte) (int, []byte, error) {
	if executor == nil {
		return 0, nil, errors.New("legacy AI executor unavailable")
	}
	return executor.Execute(ctx, method, path, body)
}

func legacyAIUpstreamError(c *echo.Context, statusCode int) error {
	switch statusCode {
	case http.StatusNotFound:
		return c.JSON(http.StatusNotFound, map[string]string{"detail": "not found"})
	case http.StatusConflict:
		return c.JSON(http.StatusConflict, map[string]string{"detail": "AI insight is stale"})
	default:
		return c.JSON(http.StatusServiceUnavailable, map[string]string{"detail": "AI service unavailable"})
	}
}

func projectLegacyAITemplate(payload []byte, memoID string) (legacyAITemplateResponse, error) {
	var raw struct {
		MemoID     any             `json:"memo_id"`
		Kind       string          `json:"kind"`
		Payload    json.RawMessage `json:"payload"`
		RawContent string          `json:"raw_content"`
		CreatedAt  string          `json:"created_at"`
		UpdatedAt  string          `json:"updated_at"`
	}
	decoder := json.NewDecoder(bytes.NewReader(payload))
	decoder.UseNumber()
	if err := decoder.Decode(&raw); err != nil || !legacyAIMemoIDMatches(raw.MemoID, memoID) || raw.CreatedAt == "" || raw.UpdatedAt == "" {
		return legacyAITemplateResponse{}, errors.New("invalid template response")
	}
	projected := legacyAITemplateResponse{
		MemoID: raw.MemoID, Kind: raw.Kind, RawContent: raw.RawContent,
		CreatedAt: raw.CreatedAt, UpdatedAt: raw.UpdatedAt,
	}
	switch raw.Kind {
	case "code":
		var code legacyAICodeTemplate
		if err := json.Unmarshal(raw.Payload, &code); err != nil || code.Tags == nil {
			return legacyAITemplateResponse{}, errors.New("invalid code template")
		}
		projected.Payload = code
	case "bug":
		var bug legacyAIBugTemplate
		if err := json.Unmarshal(raw.Payload, &bug); err != nil || bug.Tags == nil {
			return legacyAITemplateResponse{}, errors.New("invalid bug template")
		}
		projected.Payload = bug
	default:
		return legacyAITemplateResponse{}, errors.New("unsupported template kind")
	}
	return projected, nil
}

func projectLegacyAIInsights(payload []byte, memoID string) ([]legacyAIInsightResponse, error) {
	var insights []legacyAIInsightResponse
	if err := json.Unmarshal(payload, &insights); err != nil {
		return nil, errors.New("invalid insights response")
	}
	for _, insight := range insights {
		if insight.MemoID != memoID || !validLegacyAIInsight(insight) {
			return nil, errors.New("invalid insight binding")
		}
	}
	return insights, nil
}

func projectLegacyAIInsight(payload []byte, memoID, insightID string) (legacyAIInsightResponse, error) {
	var insight legacyAIInsightResponse
	if err := json.Unmarshal(payload, &insight); err != nil || insight.MemoID != memoID || insight.InsightID != insightID || !validLegacyAIInsight(insight) {
		return legacyAIInsightResponse{}, errors.New("invalid insight response")
	}
	return insight, nil
}

func validLegacyAIInsight(insight legacyAIInsightResponse) bool {
	validType := insight.InsightType == "fact" || insight.InsightType == "decision" || insight.InsightType == "action" || insight.InsightType == "bug"
	validStatus := insight.Status == "pending" || insight.Status == "accepted" || insight.Status == "rejected"
	return insight.InsightID != "" && validType && validStatus && insight.SourceRefs != nil && insight.Version >= 1 && insight.Confidence >= 0 && insight.Confidence <= 1 && insight.CreatedAt != "" && insight.UpdatedAt != ""
}

func legacyAIMemoIDMatches(value any, expected string) bool {
	switch typed := value.(type) {
	case string:
		return typed == expected
	case json.Number:
		return typed.String() == expected
	case float64:
		return strconv.FormatFloat(typed, 'f', -1, 64) == expected
	default:
		return false
	}
}
