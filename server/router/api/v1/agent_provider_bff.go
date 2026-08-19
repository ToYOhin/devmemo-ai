package v1

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"io"
	"net/http"

	"github.com/labstack/echo/v5"

	"github.com/usememos/memos/internal/aiagent"
	"github.com/usememos/memos/server/auth"
	"github.com/usememos/memos/store"
)

func (s *APIV1Service) registerAgentProviderRoutes(
	router agentRouteRegistrar,
	config aiagent.Config,
	executor aiagent.AgentProviderSettingsExecutor,
) {
	authenticator := auth.NewAuthenticator(s.Store, s.Secret)
	requireAdmin := func(c *echo.Context) (context.Context, int) {
		if !config.Enabled {
			return nil, http.StatusNotFound
		}
		result := authenticator.Authenticate(c.Request().Context(), c.Request().Header.Get("Authorization"))
		if result == nil {
			return nil, http.StatusUnauthorized
		}
		ctx := auth.ApplyToContext(c.Request().Context(), result)
		user, err := s.fetchCurrentUser(ctx)
		if err != nil {
			return nil, http.StatusServiceUnavailable
		}
		if user == nil {
			return nil, http.StatusUnauthorized
		}
		if user.Role != store.RoleAdmin {
			return nil, http.StatusForbidden
		}
		return ctx, 0
	}

	router.GET(aiagent.BrowserAgentProviderPath, func(c *echo.Context) error {
		ctx, statusCode := requireAdmin(c)
		if statusCode != 0 {
			return agentProviderBrowserError(c, statusCode)
		}
		response, err := executor.GetAgentProviderSettings(ctx)
		if err != nil {
			return agentProviderExecutorError(c, err)
		}
		return c.JSON(http.StatusOK, response)
	})

	router.PUT(aiagent.BrowserAgentProviderPath, func(c *echo.Context) error {
		ctx, statusCode := requireAdmin(c)
		if statusCode != 0 {
			return agentProviderBrowserError(c, statusCode)
		}
		input, err := decodeAgentProviderUpdate(c.Request())
		if err != nil {
			return c.JSON(http.StatusBadRequest, map[string]string{"detail": "invalid Agent provider setting"})
		}
		response, err := executor.UpdateAgentProviderSettings(ctx, input)
		if err != nil {
			return agentProviderExecutorError(c, err)
		}
		return c.JSON(http.StatusOK, response)
	})

	router.POST(aiagent.BrowserAgentProviderTestPath, func(c *echo.Context) error {
		ctx, statusCode := requireAdmin(c)
		if statusCode != 0 {
			return agentProviderBrowserError(c, statusCode)
		}
		response, err := executor.TestAgentProvider(ctx)
		if err != nil {
			return agentProviderExecutorError(c, err)
		}
		return c.JSON(http.StatusOK, response)
	})
}

func decodeAgentProviderUpdate(request *http.Request) (aiagent.AgentProviderUpdateRequest, error) {
	body, err := io.ReadAll(io.LimitReader(request.Body, maxAgentBrowserRequestBytes+1))
	if err != nil || len(body) > maxAgentBrowserRequestBytes {
		return aiagent.AgentProviderUpdateRequest{}, aiagent.ErrInvalidProviderConfig
	}
	decoder := json.NewDecoder(bytes.NewReader(body))
	decoder.DisallowUnknownFields()
	var input aiagent.AgentProviderUpdateRequest
	if err := decoder.Decode(&input); err != nil {
		return aiagent.AgentProviderUpdateRequest{}, err
	}
	var extra any
	if err := decoder.Decode(&extra); !errors.Is(err, io.EOF) {
		return aiagent.AgentProviderUpdateRequest{}, aiagent.ErrInvalidProviderConfig
	}
	if err := input.Validate(); err != nil {
		return aiagent.AgentProviderUpdateRequest{}, err
	}
	return input, nil
}

func agentProviderExecutorError(c *echo.Context, err error) error {
	if errors.Is(err, aiagent.ErrInvalidProviderConfig) {
		return c.JSON(http.StatusBadRequest, map[string]string{"detail": "invalid Agent provider setting"})
	}
	if errors.Is(err, aiagent.ErrProviderFailed) {
		return c.JSON(http.StatusBadGateway, map[string]string{"detail": "Agent provider connection test failed"})
	}
	return c.JSON(http.StatusServiceUnavailable, map[string]string{"detail": "Agent provider settings unavailable"})
}

func agentProviderBrowserError(c *echo.Context, statusCode int) error {
	detail := "Agent provider settings unavailable"
	if statusCode == http.StatusNotFound {
		detail = "not found"
	} else if statusCode == http.StatusUnauthorized {
		detail = "authentication required"
	} else if statusCode == http.StatusForbidden {
		detail = "permission denied"
	}
	return c.JSON(statusCode, map[string]string{"detail": detail})
}
