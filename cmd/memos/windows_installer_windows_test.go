//go:build windows

package main

import (
	"path/filepath"
	"testing"

	"github.com/stretchr/testify/require"
)

func TestIsWindowsSetupExecutable(t *testing.T) {
	require.True(t, isWindowsSetupExecutable("DevMemoAI-Setup.exe"))
	require.True(t, isWindowsSetupExecutable("devmemo-ai_0.4.0_windows_amd64_setup.exe"))
	require.False(t, isWindowsSetupExecutable("DevMemoAI.exe"))
	require.False(t, isWindowsSetupExecutable("setup-helper.exe"))
}

func TestDefaultWindowsInstallPaths(t *testing.T) {
	localAppData := t.TempDir()
	t.Setenv("LOCALAPPDATA", localAppData)

	paths, err := defaultWindowsInstallPaths()
	require.NoError(t, err)
	require.Equal(t, filepath.Join(localAppData, "Programs", "DevMemoAI"), paths.InstallDir)
	require.Equal(t, filepath.Join(localAppData, "Programs", "DevMemoAI", windowsExecutableName), paths.Executable)
	require.Equal(t, filepath.Join(localAppData, "DevMemoAI", "data"), paths.DataDir)
}

func TestPowerShellQuote(t *testing.T) {
	require.Equal(t, `C:\Data\O''Brien`, powershellQuote(`C:\Data\O'Brien`))
}
