package frontend

import (
	"context"
	"net/http"
	"net/http/httptest"
	"testing"
	"testing/fstest"

	"github.com/labstack/echo/v5"
	"github.com/stretchr/testify/require"

	"github.com/usememos/memos/internal/profile"
	"github.com/usememos/memos/store"
	teststore "github.com/usememos/memos/store/test"
)

func newFrontendTestingStore(ctx context.Context, t *testing.T) *store.Store {
	testStore := teststore.NewTestingStore(ctx, t)
	t.Cleanup(func() {
		_ = testStore.Close()
	})
	return testStore
}

func TestFrontendService_CacheHeaderRules(t *testing.T) {
	tests := []struct {
		name         string
		path         string
		cacheControl string
		pragma       string
		expires      string
	}{
		{
			name:         "root html is not stored",
			path:         "/",
			cacheControl: frontendHTMLCacheControl,
			pragma:       "no-cache",
			expires:      "0",
		},
		{
			name:         "index html is not stored",
			path:         "/index.html",
			cacheControl: frontendHTMLCacheControl,
			pragma:       "no-cache",
			expires:      "0",
		},
		{
			name:         "spa fallback html is not stored",
			path:         "/memos/publicmemo",
			cacheControl: frontendHTMLCacheControl,
			pragma:       "no-cache",
			expires:      "0",
		},
		{
			name:         "hashed asset is immutable",
			path:         "/assets/index-deadbeef.js",
			cacheControl: frontendHashedAssetCacheControl,
		},
		{
			name:         "stable root asset is revalidated after max age",
			path:         "/logo.webp",
			cacheControl: frontendStaticAssetCacheControl,
		},
	}

	e := echo.New()
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			req := httptest.NewRequest(http.MethodGet, tt.path, nil)
			rec := httptest.NewRecorder()
			c := e.NewContext(req, rec)

			setFrontendCacheHeaders(c, tt.path)

			require.Equal(t, tt.cacheControl, rec.Header().Get(echo.HeaderCacheControl))
			require.Equal(t, tt.pragma, rec.Header().Get("Pragma"))
			require.Equal(t, tt.expires, rec.Header().Get("Expires"))
		})
	}
}

func TestFrontendService_StaticCacheHeaders(t *testing.T) {
	ctx := context.Background()
	testStore := newFrontendTestingStore(ctx, t)

	e := echo.New()
	NewFrontendService(&profile.Profile{}, testStore).Serve(ctx, e)

	tests := []struct {
		name         string
		path         string
		cacheControl string
		pragma       string
		expires      string
	}{
		{
			name:         "root html is not stored",
			path:         "/",
			cacheControl: frontendHTMLCacheControl,
			pragma:       "no-cache",
			expires:      "0",
		},
		{
			name:         "index html is not stored",
			path:         "/index.html",
			cacheControl: frontendHTMLCacheControl,
			pragma:       "no-cache",
			expires:      "0",
		},
		{
			name:         "spa fallback html is not stored",
			path:         "/memos/publicmemo",
			cacheControl: frontendHTMLCacheControl,
			pragma:       "no-cache",
			expires:      "0",
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			req := httptest.NewRequest(http.MethodGet, tt.path, nil)
			rec := httptest.NewRecorder()
			e.ServeHTTP(rec, req)

			require.Equal(t, http.StatusOK, rec.Code)
			require.Equal(t, tt.cacheControl, rec.Header().Get(echo.HeaderCacheControl))
			require.Equal(t, tt.pragma, rec.Header().Get("Pragma"))
			require.Equal(t, tt.expires, rec.Header().Get("Expires"))
		})
	}
}

func TestFrontendService_MissingAssetDoesNotFallbackToIndex(t *testing.T) {
	ctx := context.Background()
	testStore := newFrontendTestingStore(ctx, t)

	e := echo.New()
	NewFrontendService(&profile.Profile{}, testStore).Serve(ctx, e)

	req := httptest.NewRequest(http.MethodGet, "/assets/missing.js", nil)
	rec := httptest.NewRecorder()
	e.ServeHTTP(rec, req)

	require.Equal(t, http.StatusNotFound, rec.Code)
}

func TestFrontendService_SkipsDynamicRoutes(t *testing.T) {
	ctx := context.Background()
	testStore := newFrontendTestingStore(ctx, t)

	e := echo.New()
	NewFrontendService(&profile.Profile{}, testStore).Serve(ctx, e)

	for _, route := range []string{"/api/test", "/file/test", "/mcp/test"} {
		e.GET(route, func(c *echo.Context) error {
			return c.String(http.StatusOK, "dynamic-route")
		})

		req := httptest.NewRequest(http.MethodGet, route, nil)
		rec := httptest.NewRecorder()
		e.ServeHTTP(rec, req)

		require.Equal(t, http.StatusOK, rec.Code)
		require.Equal(t, "dynamic-route", rec.Body.String())
		require.Empty(t, rec.Header().Get(echo.HeaderCacheControl))
	}
}

func TestFrontendService_EncodedSlashPreservesDynamicRouteBoundaries(t *testing.T) {
	frontendFS := fstest.MapFS{
		"index.html":      {Data: []byte("frontend-index")},
		"assets/app.js":   {Data: []byte("static-asset")},
		"api/secret.txt":  {Data: []byte("api-secret")},
		"file/secret.txt": {Data: []byte("file-secret")},
		"mcp/secret.txt":  {Data: []byte("mcp-secret")},
	}

	e := echo.New()
	(&FrontendService{}).serveWithFilesystem(e, frontendFS)

	req := httptest.NewRequest(http.MethodGet, "/assets/app.js", nil)
	rec := httptest.NewRecorder()
	e.ServeHTTP(rec, req)
	require.Equal(t, http.StatusOK, rec.Code)
	require.Equal(t, "static-asset", rec.Body.String())

	for _, protectedPath := range []string{
		"/api%2Fsecret.txt",
		"/file%2Fsecret.txt",
		"/mcp%2Fsecret.txt",
	} {
		req := httptest.NewRequest(http.MethodGet, protectedPath, nil)
		rec := httptest.NewRecorder()
		e.ServeHTTP(rec, req)

		require.Equal(t, http.StatusNotFound, rec.Code)
		require.NotContains(t, rec.Body.String(), "secret")
	}
}

func TestEchoStaticFSRejectsEncodedPathSeparator(t *testing.T) {
	frontendFS := fstest.MapFS{
		"api/secret.txt": {Data: []byte("api-secret")},
	}

	e := echo.New()
	protected := e.Group("/api")
	protected.Use(func(_ echo.HandlerFunc) echo.HandlerFunc {
		return func(_ *echo.Context) error {
			return echo.NewHTTPError(http.StatusForbidden, http.StatusText(http.StatusForbidden))
		}
	})
	protected.GET("/*", func(c *echo.Context) error {
		return c.NoContent(http.StatusNoContent)
	})
	e.StaticFS("/", frontendFS)

	req := httptest.NewRequest(http.MethodGet, "/api%2Fsecret.txt", nil)
	rec := httptest.NewRecorder()
	e.ServeHTTP(rec, req)

	require.Equal(t, http.StatusNotFound, rec.Code)
	require.NotContains(t, rec.Body.String(), "api-secret")
}

func TestFrontendService_RobotsTXT(t *testing.T) {
	ctx := context.Background()
	testStore := newFrontendTestingStore(ctx, t)
	profile := &profile.Profile{
		InstanceURL: "https://demo.usememos.com/",
	}

	e := echo.New()
	NewFrontendService(profile, testStore).Serve(ctx, e)

	req := httptest.NewRequest(http.MethodGet, "/robots.txt", nil)
	rec := httptest.NewRecorder()
	e.ServeHTTP(rec, req)

	require.Equal(t, http.StatusOK, rec.Code)
	require.Equal(t, "text/plain; charset=UTF-8", rec.Header().Get("Content-Type"))
	require.Equal(t, "User-agent: *\nAllow: /\nHost: https://demo.usememos.com\nSitemap: https://demo.usememos.com/sitemap.xml", rec.Body.String())
}

func TestFrontendService_SitemapXML(t *testing.T) {
	ctx := context.Background()
	testStore := newFrontendTestingStore(ctx, t)
	profile := &profile.Profile{
		InstanceURL: "https://demo.usememos.com",
	}

	user, err := testStore.CreateUser(ctx, &store.User{
		Username: "sitemap-owner",
		Role:     store.RoleUser,
		Email:    "sitemap-owner@example.com",
	})
	require.NoError(t, err)

	_, err = testStore.CreateMemo(ctx, &store.Memo{
		UID:        "publicmemo",
		CreatorID:  user.ID,
		Content:    "public memo",
		Visibility: store.Public,
	})
	require.NoError(t, err)

	_, err = testStore.CreateMemo(ctx, &store.Memo{
		UID:        "privatememo",
		CreatorID:  user.ID,
		Content:    "private memo",
		Visibility: store.Private,
	})
	require.NoError(t, err)

	e := echo.New()
	NewFrontendService(profile, testStore).Serve(ctx, e)

	req := httptest.NewRequest(http.MethodGet, "/sitemap.xml", nil)
	rec := httptest.NewRecorder()
	e.ServeHTTP(rec, req)

	require.Equal(t, http.StatusOK, rec.Code)
	require.Contains(t, rec.Header().Get("Content-Type"), "application/xml")
	require.Contains(t, rec.Body.String(), `<loc>https://demo.usememos.com/memos/publicmemo</loc>`)
	require.NotContains(t, rec.Body.String(), "privatememo")
}

func TestFrontendService_SitemapRoutesRequireInstanceURL(t *testing.T) {
	ctx := context.Background()
	testStore := newFrontendTestingStore(ctx, t)

	e := echo.New()
	NewFrontendService(&profile.Profile{}, testStore).Serve(ctx, e)

	for _, path := range []string{"/robots.txt", "/sitemap.xml"} {
		req := httptest.NewRequest(http.MethodGet, path, nil)
		rec := httptest.NewRecorder()
		e.ServeHTTP(rec, req)

		require.Equal(t, http.StatusNotFound, rec.Code)
	}
}
