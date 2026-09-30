package main

import (
	"runtime"
	"testing"

	"github.com/stretchr/testify/require"

	"github.com/usememos/memos/internal/profile"
)

func TestProfileAccessURL(t *testing.T) {
	tests := []struct {
		name    string
		profile *profile.Profile
		want    string
	}{
		{
			name:    "unspecified address uses localhost",
			profile: &profile.Profile{Port: 5230},
			want:    "http://localhost:5230",
		},
		{
			name:    "wildcard IPv4 uses localhost",
			profile: &profile.Profile{Addr: "0.0.0.0", Port: 8081},
			want:    "http://localhost:8081",
		},
		{
			name:    "IPv6 address is bracketed",
			profile: &profile.Profile{Addr: "::1", Port: 5230},
			want:    "http://[::1]:5230",
		},
	}

	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			require.Equal(t, test.want, profileAccessURL(test.profile))
		})
	}
}

func TestOpenBrowserUsesPlatformCommand(t *testing.T) {
	original := runBrowserCommand
	t.Cleanup(func() { runBrowserCommand = original })

	var gotName string
	var gotArgs []string
	runBrowserCommand = func(name string, args ...string) error {
		gotName = name
		gotArgs = args
		return nil
	}

	err := openBrowser("http://localhost:5230")

	switch runtime.GOOS {
	case "windows":
		require.Equal(t, "rundll32", gotName)
		require.Equal(t, []string{"url.dll,FileProtocolHandler", "http://localhost:5230"}, gotArgs)
	case "darwin":
		require.Equal(t, "open", gotName)
		require.Equal(t, []string{"http://localhost:5230"}, gotArgs)
	case "linux":
		require.Equal(t, "xdg-open", gotName)
		require.Equal(t, []string{"http://localhost:5230"}, gotArgs)
	default:
		require.ErrorContains(t, err, "not supported")
		require.Empty(t, gotName)
		require.Empty(t, gotArgs)
		return
	}
	require.NoError(t, err)
}
