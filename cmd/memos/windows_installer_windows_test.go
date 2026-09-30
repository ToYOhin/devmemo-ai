//go:build windows

package main

import (
	"encoding/json"
	"errors"
	"fmt"
	"os"
	"path/filepath"
	"strings"
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

func TestWindowsInstallLifecycle(t *testing.T) {
	for _, upgrade := range []bool{false, true} {
		t.Run(fmt.Sprintf("upgrade=%t", upgrade), func(t *testing.T) {
			paths, source := windowsInstallerFixture(t, upgrade)
			var calls []string
			ops := fakeWindowsInstallOperations(t, paths, &calls)

			require.NoError(t, installWindowsAppWithOperations(source, paths, ops))
			require.Equal(t, []string{"shortcuts", "registry"}, calls)
			require.Equal(t, "synthetic new executable", readInstallerFile(t, paths.Executable))
			require.Equal(t, "synthetic new executable", readInstallerFile(t, source))
			require.Equal(t, "synthetic memo data", readInstallerFile(t, filepath.Join(paths.DataDir, "memos_prod.db")))
			entries, err := os.ReadDir(paths.InstallDir)
			require.NoError(t, err)
			require.Len(t, entries, 1, "successful installation must remove its staging files")
			require.Equal(t, windowsExecutableName, entries[0].Name())
		})
	}
}

func TestWindowsInstallCreatesDirectories(t *testing.T) {
	root := t.TempDir()
	t.Setenv("LOCALAPPDATA", filepath.Join(root, "fresh"))
	paths, err := defaultWindowsInstallPaths()
	require.NoError(t, err)
	require.Equal(t, filepath.Join(root, "fresh", "Programs", "DevMemoAI"), paths.InstallDir)
	require.Equal(t, filepath.Join(root, "fresh", "DevMemoAI", "data"), paths.DataDir)
	source := filepath.Join(root, "Setup.exe")
	require.NoError(t, os.WriteFile(source, []byte("synthetic new executable"), 0755))
	require.NoDirExists(t, paths.InstallDir)
	require.NoDirExists(t, paths.DataDir)
	var calls []string

	require.NoError(t, installWindowsAppWithOperations(source, paths, fakeWindowsInstallOperations(t, paths, &calls)))
	require.Equal(t, "synthetic new executable", readInstallerFile(t, paths.Executable))
	require.DirExists(t, paths.DataDir)
	require.Equal(t, []string{"shortcuts", "registry"}, calls)
}

func TestWindowsUpgradeFailurePreservesInstallation(t *testing.T) {
	for _, failure := range []string{"payload", "payload-directory", "backup", "activation", "shortcuts", "registry"} {
		t.Run(failure, func(t *testing.T) {
			paths, source := windowsInstallerFixture(t, true)
			var calls []string
			ops := fakeWindowsInstallOperations(t, paths, &calls)
			injected := errors.New("synthetic " + failure + " failure")
			failed := false
			ops.rename = func(oldPath, newPath string) error {
				if !failed && ((failure == "backup" && oldPath == paths.Executable) ||
					(failure == "activation" && newPath == paths.Executable)) {
					failed = true
					return injected
				}
				return os.Rename(oldPath, newPath)
			}
			if failure == "payload" {
				source += ".missing"
			}
			if failure == "payload-directory" {
				source = paths.DataDir
			}
			if failure == "shortcuts" {
				ops.createShortcuts = func(windowsInstallPaths) error { return injected }
			}
			if failure == "registry" {
				ops.registerUninstaller = func(windowsInstallPaths) error { return injected }
			}

			err := installWindowsAppWithOperations(source, paths, ops)
			require.Error(t, err)
			if !strings.HasPrefix(failure, "payload") {
				require.ErrorIs(t, err, injected)
			}
			require.Equal(t, "synthetic old executable", readInstallerFile(t, paths.Executable))
			require.Equal(t, "synthetic memo data", readInstallerFile(t, filepath.Join(paths.DataDir, "memos_prod.db")))
			entries, err := os.ReadDir(paths.InstallDir)
			require.NoError(t, err)
			require.Len(t, entries, 1, "failed upgrade must not leave staging files after successful rollback")
			if strings.HasPrefix(failure, "payload") || failure == "backup" || failure == "activation" {
				require.Empty(t, calls, "metadata must not be changed before activation")
			}
		})
	}
}

func TestWindowsFreshInstallFailurePreservesData(t *testing.T) {
	paths, source := windowsInstallerFixture(t, false)
	var calls []string
	ops := fakeWindowsInstallOperations(t, paths, &calls)
	injected := errors.New("synthetic shortcut failure")
	ops.createShortcuts = func(windowsInstallPaths) error { return injected }

	require.ErrorIs(t, installWindowsAppWithOperations(source, paths, ops), injected)
	require.NoFileExists(t, paths.Executable)
	require.Equal(t, "synthetic memo data", readInstallerFile(t, filepath.Join(paths.DataDir, "memos_prod.db")))
	require.Empty(t, calls)
}

func TestWindowsUpgradeRollbackFailureRetainsBackup(t *testing.T) {
	paths, source := windowsInstallerFixture(t, true)
	var calls []string
	ops := fakeWindowsInstallOperations(t, paths, &calls)
	activationError := errors.New("synthetic activation failure")
	rollbackError := errors.New("synthetic rollback failure")
	var backup string
	ops.rename = func(oldPath, newPath string) error {
		if oldPath == paths.Executable {
			backup = newPath
			return os.Rename(oldPath, newPath)
		}
		if oldPath == backup {
			return rollbackError
		}
		return activationError
	}

	err := installWindowsAppWithOperations(source, paths, ops)
	require.ErrorIs(t, err, activationError)
	require.ErrorIs(t, err, rollbackError)
	require.ErrorContains(t, err, fmt.Sprintf("backup retained at %q", backup))
	require.Equal(t, "synthetic old executable", readInstallerFile(t, backup))
	require.NoFileExists(t, paths.Executable)
	require.NoFileExists(t, filepath.Join(filepath.Dir(backup), windowsExecutableName))
	require.Equal(t, "synthetic memo data", readInstallerFile(t, filepath.Join(paths.DataDir, "memos_prod.db")))
	require.Empty(t, calls)
}

func TestWindowsInstallDoesNotOverwriteUnownedStagingFile(t *testing.T) {
	paths, source := windowsInstallerFixture(t, true)
	unowned := paths.Executable + ".new"
	require.NoError(t, os.WriteFile(unowned, []byte("unrelated pending file"), 0600))
	var calls []string

	require.NoError(t, installWindowsAppWithOperations(source, paths, fakeWindowsInstallOperations(t, paths, &calls)))
	require.Equal(t, "unrelated pending file", readInstallerFile(t, unowned))
}

func TestWindowsUninstallPreservesData(t *testing.T) {
	paths, _ := windowsInstallerFixture(t, true)
	var calls []string
	var removalScript string
	runPowerShell := func(script string, detached bool) (string, error) {
		require.True(t, detached)
		calls = append(calls, "schedule")
		removalScript = script
		return "", nil
	}
	removeRegistration := func() { calls = append(calls, "registry") }

	require.NoError(t, uninstallWindowsAppWithOperations(strings.ToUpper(paths.Executable), runPowerShell, removeRegistration))
	require.Equal(t, []string{"schedule", "registry"}, calls)
	// Scheduling is simulated; only the mocked script below is executed, with no system side effects.
	require.Contains(t, removalScript, "$installedExecutable = '"+powershellQuote(paths.Executable)+"'")
	require.Contains(t, removalScript, "Remove-Item -LiteralPath '"+powershellQuote(paths.InstallDir)+"' -Recurse")
	require.Contains(t, removalScript, "$_.Id -ne $uninstallerPid -and $_.Path -eq $installedExecutable")
	require.Contains(t, removalScript, "Wait-Process -Id $uninstallerPid")
	require.NotContains(t, removalScript, powershellQuote(paths.DataDir))
	require.Equal(t, "synthetic old executable", readInstallerFile(t, paths.Executable), "scheduling must not delete the running executable")

	removals := simulateWindowsUninstallScript(t, removalScript, paths)
	require.Len(t, removals, 3)
	require.Equal(t, "DevMemo AI.lnk", filepath.Base(removals[0].Path))
	require.False(t, removals[0].Recurse)
	require.Equal(t, "DevMemo AI", filepath.Base(removals[1].Path))
	require.True(t, removals[1].Recurse)
	require.Equal(t, paths.InstallDir, removals[2].Path)
	require.True(t, removals[2].Recurse)
	// Only the exact fixture installation target is physically removed, never a shortcut target.
	require.NoError(t, os.RemoveAll(paths.InstallDir))
	require.NoDirExists(t, paths.InstallDir)
	require.Equal(t, "synthetic memo data", readInstallerFile(t, filepath.Join(paths.DataDir, "memos_prod.db")))
}

func TestWindowsUninstallScheduleFailureRetainsRegistration(t *testing.T) {
	paths, _ := windowsInstallerFixture(t, true)
	injected := errors.New("synthetic helper start failure")
	removed := false
	err := uninstallWindowsAppWithOperations(paths.Executable, func(string, bool) (string, error) {
		return "", injected
	}, func() { removed = true })

	require.ErrorIs(t, err, injected)
	require.False(t, removed, "retain the uninstall entry when the helper cannot start")
	require.Equal(t, "synthetic old executable", readInstallerFile(t, paths.Executable))
	require.Equal(t, "synthetic memo data", readInstallerFile(t, filepath.Join(paths.DataDir, "memos_prod.db")))
}

func TestWindowsUninstallRejectsOtherExecutable(t *testing.T) {
	paths, source := windowsInstallerFixture(t, true)
	err := uninstallWindowsAppWithOperations(source, func(string, bool) (string, error) {
		t.Fatal("must not start helper for an uninstalled executable")
		return "", nil
	}, func() { t.Fatal("must not delete registration for an uninstalled executable") })

	require.ErrorContains(t, err, "uninstall must be run from the installed application")
	require.Equal(t, "synthetic old executable", readInstallerFile(t, paths.Executable))
	require.Equal(t, "synthetic memo data", readInstallerFile(t, filepath.Join(paths.DataDir, "memos_prod.db")))
}

func windowsInstallerFixture(t *testing.T, installed bool) (windowsInstallPaths, string) {
	t.Helper()
	root := filepath.Join(t.TempDir(), "O'Brien synthetic app data")
	t.Setenv("LOCALAPPDATA", root)
	paths, err := defaultWindowsInstallPaths()
	require.NoError(t, err)
	require.Equal(t, filepath.Join(root, "Programs", "DevMemoAI"), paths.InstallDir)
	require.Equal(t, filepath.Join(paths.InstallDir, windowsExecutableName), paths.Executable)
	require.Equal(t, filepath.Join(root, "DevMemoAI", "data"), paths.DataDir)
	require.NoError(t, os.MkdirAll(paths.InstallDir, 0755))
	require.NoError(t, os.MkdirAll(paths.DataDir, 0700))
	require.NoError(t, os.WriteFile(filepath.Join(paths.DataDir, "memos_prod.db"), []byte("synthetic memo data"), 0600))
	if installed {
		require.NoError(t, os.WriteFile(paths.Executable, []byte("synthetic old executable"), 0755))
	}
	source := filepath.Join(root, "DevMemoAI-Setup.exe")
	require.NoError(t, os.WriteFile(source, []byte("synthetic new executable"), 0755))
	return paths, source
}

func fakeWindowsInstallOperations(t *testing.T, paths windowsInstallPaths, calls *[]string) windowsInstallOperations {
	t.Helper()
	return windowsInstallOperations{
		rename: os.Rename,
		createShortcuts: func(got windowsInstallPaths) error {
			require.Equal(t, paths, got)
			*calls = append(*calls, "shortcuts")
			return nil
		},
		registerUninstaller: func(got windowsInstallPaths) error {
			require.Equal(t, paths, got)
			*calls = append(*calls, "registry")
			return nil
		},
	}
}

func readInstallerFile(t *testing.T, path string) string {
	t.Helper()
	contents, err := os.ReadFile(path)
	require.NoError(t, err)
	return string(contents)
}

type simulatedWindowsRemoval struct {
	Path    string
	Recurse bool
}

func simulateWindowsUninstallScript(t *testing.T, script string, paths windowsInstallPaths) []simulatedWindowsRemoval {
	t.Helper()
	// Mock every side-effecting command. Even Remove-Item only records targets; it deletes nothing.
	// Reject unexpected commands before running the generated script to keep this harness isolated.
	prefix := fmt.Sprintf(`
$ErrorActionPreference = 'Stop'
$script:removals = @()
$script:stopped = @()
$script:waited = @()
function Remove-Item {
  [CmdletBinding()] param([string]$LiteralPath, [switch]$Force, [switch]$Recurse)
  $script:removals += [PSCustomObject]@{Path=$LiteralPath; Recurse=[bool]$Recurse}
}
function Get-Process {
  [CmdletBinding()] param([string]$Name)
  @([PSCustomObject]@{Id=%d; Path='%s'},
    [PSCustomObject]@{Id=-1; Path='%s'},
    [PSCustomObject]@{Id=-2; Path='unrelated.exe'})
}
function Stop-Process {
  [CmdletBinding()] param([Parameter(ValueFromPipeline=$true)]$InputObject, [switch]$Force)
  process { $script:stopped += $InputObject.Id }
}
function Wait-Process {
  [CmdletBinding()] param([int]$Id, [int]$Timeout)
  $script:waited += $Id
}
$target = {
`, os.Getpid(), powershellQuote(paths.Executable), powershellQuote(paths.Executable))
	suffix := fmt.Sprintf(`
}
$allowed = @('Remove-Item', 'Join-Path', 'Get-Process', 'Where-Object', 'Stop-Process', 'Wait-Process')
foreach ($node in $target.Ast.FindAll({param($n) $n -is [System.Management.Automation.Language.CommandAst]}, $true)) {
  if ($allowed -cnotcontains $node.GetCommandName()) { throw 'Unexpected command in uninstall script' }
}
# The only method call permitted in the generated helper is read-only folder resolution.
foreach ($node in $target.Ast.FindAll({param($n) $n -is [System.Management.Automation.Language.InvokeMemberExpressionAst]}, $true)) {
  if ($node.Extent.Text -cnotin @("[Environment]::GetFolderPath('Desktop')", "[Environment]::GetFolderPath('Programs')")) {
    throw 'Unexpected method call in uninstall script'
  }
}
& $target
if ($script:stopped.Count -ne 1 -or $script:stopped[0] -ne -1) { throw 'Unrelated process targeted' }
if ($script:waited.Count -ne 1 -or $script:waited[0] -ne %d) { throw 'Incorrect parent wait' }
ConvertTo-Json -InputObject @($script:removals) -Compress
`, os.Getpid())
	output, err := runWindowsPowerShell(prefix+script+suffix, false)
	require.NoError(t, err, "%s", output)
	var removals []simulatedWindowsRemoval
	require.NoError(t, json.Unmarshal([]byte(strings.TrimPrefix(output, "\ufeff")), &removals))
	return removals
}
