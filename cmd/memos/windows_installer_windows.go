//go:build windows

package main

import (
	"errors"
	"fmt"
	"io"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"syscall"
	"unsafe"

	"golang.org/x/sys/windows"
	"golang.org/x/sys/windows/registry"

	"github.com/usememos/memos/internal/version"
)

const (
	windowsAppName        = "DevMemo AI"
	windowsExecutableName = "DevMemoAI.exe"
	windowsUninstallKey   = `Software\Microsoft\Windows\CurrentVersion\Uninstall\DevMemoAI`
)

type windowsInstallPaths struct {
	InstallDir string
	Executable string
	DataDir    string
}

func maybeRunWindowsInstaller() bool {
	executable, err := os.Executable()
	if err != nil {
		return false
	}

	if len(os.Args) > 1 && os.Args[1] == "--uninstall" {
		if err := uninstallWindowsApp(executable); err != nil {
			showWindowsMessage("Uninstall failed", err.Error(), 0x10)
			return true
		}
		paths, _ := defaultWindowsInstallPaths()
		showWindowsMessage(windowsAppName, fmt.Sprintf("Uninstall started. Close this dialog to finish removal. Your memo data will be preserved.\n\nCompletion status: %s", windowsUninstallStatusPath(paths)), 0x40)
		return true
	}

	if !isWindowsSetupExecutable(filepath.Base(executable)) {
		return false
	}

	paths, err := defaultWindowsInstallPaths()
	if err != nil {
		showWindowsMessage("Installation failed", err.Error(), 0x10)
		return true
	}
	if err := installWindowsApp(executable, paths); err != nil {
		showWindowsMessage("Installation failed", err.Error(), 0x10)
		return true
	}

	showWindowsMessage(windowsAppName, "Installation completed. DevMemo AI will now open. AI/Agent integrations remain disabled in this standalone core mode.", 0x40)
	if err := launchInstalledWindowsApp(paths); err != nil {
		showWindowsMessage("Launch failed", err.Error(), 0x10)
	}
	return true
}

func isWindowsSetupExecutable(name string) bool {
	base := strings.TrimSuffix(strings.ToLower(name), strings.ToLower(filepath.Ext(name)))
	return strings.HasSuffix(base, "setup")
}

func defaultWindowsInstallPaths() (windowsInstallPaths, error) {
	localAppData := strings.TrimSpace(os.Getenv("LOCALAPPDATA"))
	if localAppData == "" {
		return windowsInstallPaths{}, errors.New("LOCALAPPDATA is not available")
	}

	installDir := filepath.Join(localAppData, "Programs", "DevMemoAI")
	return windowsInstallPaths{
		InstallDir: installDir,
		Executable: filepath.Join(installDir, windowsExecutableName),
		DataDir:    filepath.Join(localAppData, "DevMemoAI", "data"),
	}, nil
}

func installWindowsApp(source string, paths windowsInstallPaths) error {
	return installWindowsAppWithOperations(source, paths, windowsInstallOperations{
		rename:              os.Rename,
		createShortcuts:     createWindowsShortcuts,
		registerUninstaller: registerWindowsUninstaller,
	})
}

type windowsInstallOperations struct {
	rename              func(string, string) error
	createShortcuts     func(windowsInstallPaths) error
	registerUninstaller func(windowsInstallPaths) error
}

func installWindowsAppWithOperations(source string, paths windowsInstallPaths, ops windowsInstallOperations) error {
	if err := os.MkdirAll(paths.InstallDir, 0755); err != nil {
		return fmt.Errorf("create installation directory: %w", err)
	}
	if err := os.MkdirAll(paths.DataDir, 0700); err != nil {
		return fmt.Errorf("create data directory: %w", err)
	}

	stagingDir, err := os.MkdirTemp(paths.InstallDir, ".devmemo-install-")
	if err != nil {
		return fmt.Errorf("create installation staging directory: %w", err)
	}
	// Remove only files owned by this attempt. A failed rollback leaves its backup intact.
	defer os.Remove(stagingDir)
	temporaryTarget := filepath.Join(stagingDir, windowsExecutableName)
	defer os.Remove(temporaryTarget)
	if err := copyFile(source, temporaryTarget); err != nil {
		return err
	}

	backup := filepath.Join(stagingDir, "previous.exe")
	hasBackup := false
	if info, err := os.Stat(paths.Executable); err == nil {
		if !info.Mode().IsRegular() {
			return errors.New("existing installation is not a regular executable file")
		}
		if err := ops.rename(paths.Executable, backup); err != nil {
			return fmt.Errorf("back up existing installation: %w", err)
		}
		hasBackup = true
	} else if !os.IsNotExist(err) {
		return fmt.Errorf("inspect existing installation: %w", err)
	}
	rollback := func(cause error, activated bool) error {
		if activated {
			if err := os.Remove(paths.Executable); err != nil && !os.IsNotExist(err) {
				removalError := fmt.Errorf("remove failed executable at %q before rollback: %w", paths.Executable, err)
				if hasBackup {
					removalError = fmt.Errorf("backup retained at %q: %w", backup, removalError)
				}
				return errors.Join(cause, removalError)
			}
		}
		if hasBackup {
			if err := ops.rename(backup, paths.Executable); err != nil {
				return errors.Join(cause, fmt.Errorf("restore previous executable (backup retained at %q): %w", backup, err))
			}
		}
		return cause
	}
	if err := ops.rename(temporaryTarget, paths.Executable); err != nil {
		return rollback(fmt.Errorf("activate installed executable: %w", err), false)
	}

	if err := ops.createShortcuts(paths); err != nil {
		return rollback(err, true)
	}
	if err := ops.registerUninstaller(paths); err != nil {
		return rollback(err, true)
	}
	if hasBackup {
		if err := os.Remove(backup); err != nil {
			return rollback(fmt.Errorf("remove previous executable backup: %w", err), true)
		}
	}
	return nil
}

func copyFile(source, destination string) error {
	input, err := os.Open(source)
	if err != nil {
		return fmt.Errorf("open installer payload: %w", err)
	}
	defer input.Close()

	output, err := os.OpenFile(destination, os.O_CREATE|os.O_TRUNC|os.O_WRONLY, 0755)
	if err != nil {
		return fmt.Errorf("create installed executable: %w", err)
	}
	if _, err := io.Copy(output, input); err != nil {
		output.Close()
		return fmt.Errorf("copy installed executable: %w", err)
	}
	if err := output.Close(); err != nil {
		return fmt.Errorf("finish installed executable: %w", err)
	}
	return nil
}

func createWindowsShortcuts(paths windowsInstallPaths) error {
	arguments := fmt.Sprintf(`--addr 127.0.0.1 --port 5230 --data "%s" --open-browser`, paths.DataDir)
	script := fmt.Sprintf(`
$shell = New-Object -ComObject WScript.Shell
$desktop = [Environment]::GetFolderPath('Desktop')
$programs = [Environment]::GetFolderPath('Programs')
$folder = Join-Path $programs 'DevMemo AI'
New-Item -ItemType Directory -Force -Path $folder | Out-Null
foreach ($shortcutPath in @((Join-Path $desktop 'DevMemo AI.lnk'), (Join-Path $folder 'DevMemo AI.lnk'))) {
  $shortcut = $shell.CreateShortcut($shortcutPath)
  $shortcut.TargetPath = '%s'
  $shortcut.Arguments = '%s'
  $shortcut.WorkingDirectory = '%s'
  $shortcut.IconLocation = '%s,0'
  $shortcut.Description = 'Start DevMemo AI'
  $shortcut.Save()
}
$uninstall = $shell.CreateShortcut((Join-Path $folder 'Uninstall DevMemo AI.lnk'))
$uninstall.TargetPath = '%s'
$uninstall.Arguments = '--uninstall'
$uninstall.WorkingDirectory = '%s'
$uninstall.IconLocation = '%s,0'
$uninstall.Description = 'Uninstall DevMemo AI'
$uninstall.Save()
`, powershellQuote(paths.Executable), powershellQuote(arguments), powershellQuote(paths.InstallDir), powershellQuote(paths.Executable), powershellQuote(paths.Executable), powershellQuote(paths.InstallDir), powershellQuote(paths.Executable))

	if output, err := runWindowsPowerShell(script, false); err != nil {
		return fmt.Errorf("create shortcuts: %w: %s", err, strings.TrimSpace(output))
	}
	return nil
}

func registerWindowsUninstaller(paths windowsInstallPaths) error {
	key, _, err := registry.CreateKey(registry.CURRENT_USER, windowsUninstallKey, registry.SET_VALUE)
	if err != nil {
		return fmt.Errorf("create uninstall registry key: %w", err)
	}
	defer key.Close()

	values := map[string]string{
		"DisplayName":     windowsAppName,
		"DisplayVersion":  version.GetCurrentVersion(),
		"DisplayIcon":     paths.Executable,
		"InstallLocation": paths.InstallDir,
		"Publisher":       "DevMemo AI",
		"UninstallString": fmt.Sprintf(`"%s" --uninstall`, paths.Executable),
	}
	for name, value := range values {
		if err := key.SetStringValue(name, value); err != nil {
			return fmt.Errorf("write uninstall registry value %s: %w", name, err)
		}
	}
	if err := key.SetDWordValue("NoModify", 1); err != nil {
		return fmt.Errorf("write NoModify registry value: %w", err)
	}
	if err := key.SetDWordValue("NoRepair", 1); err != nil {
		return fmt.Errorf("write NoRepair registry value: %w", err)
	}
	return nil
}

func launchInstalledWindowsApp(paths windowsInstallPaths) error {
	command := exec.Command(paths.Executable,
		"--addr", "127.0.0.1",
		"--port", "5230",
		"--data", paths.DataDir,
		"--open-browser",
	)
	command.Dir = paths.InstallDir
	command.SysProcAttr = &syscall.SysProcAttr{CreationFlags: 0x00000010}
	if err := command.Start(); err != nil {
		return fmt.Errorf("start installed application: %w", err)
	}
	return nil
}

func uninstallWindowsApp(currentExecutable string) error {
	return uninstallWindowsAppWithOperations(currentExecutable, runWindowsPowerShell)
}

func windowsUninstallStatusPath(paths windowsInstallPaths) string {
	return filepath.Join(filepath.Dir(paths.DataDir), fmt.Sprintf("uninstall-%d.log", os.Getpid()))
}

func uninstallWindowsAppWithOperations(currentExecutable string, runPowerShell func(string, bool) (string, error)) error {
	paths, err := defaultWindowsInstallPaths()
	if err != nil {
		return err
	}
	currentAbsolute, err := filepath.Abs(currentExecutable)
	if err != nil {
		return err
	}
	installedAbsolute, err := filepath.Abs(paths.Executable)
	if err != nil {
		return err
	}
	if !strings.EqualFold(currentAbsolute, installedAbsolute) {
		return errors.New("uninstall must be run from the installed application")
	}
	statusPath := windowsUninstallStatusPath(paths)
	if err := os.WriteFile(statusPath, []byte("STARTING\n"), 0600); err != nil {
		return fmt.Errorf("create uninstall completion status: %w", err)
	}

	script := fmt.Sprintf(`
$installedExecutable = '%s'
$uninstallerPid = %d
$installDir = '%s'
$statusFile = '%s'
try {
  Set-Content -LiteralPath $statusFile -Value 'STARTED' -Encoding UTF8
  $parent = Get-Process -Id $uninstallerPid -ErrorAction SilentlyContinue
  if ($null -ne $parent -and $parent.Path -eq $installedExecutable) {
    Wait-Process -Id $uninstallerPid -Timeout 120
  }
  Get-Process -Name 'DevMemoAI' -ErrorAction SilentlyContinue |
    Where-Object { $_.Id -ne $uninstallerPid -and $_.Path -eq $installedExecutable } |
    Stop-Process -Force
  # A terminated process can briefly keep its image mapped. Retry only this installation.
  for ($attempt = 0; $attempt -lt 50; $attempt++) {
    try {
      if (Test-Path -LiteralPath $installDir) { Remove-Item -LiteralPath $installDir -Recurse -Force }
      break
    } catch {
      if ($attempt -eq 49) { throw }
      Start-Sleep -Milliseconds 100
    }
  }
  $desktop = [Environment]::GetFolderPath('Desktop')
  $programs = [Environment]::GetFolderPath('Programs')
  $desktopShortcut = Join-Path $desktop 'DevMemo AI.lnk'
  $programsFolder = Join-Path $programs 'DevMemo AI'
  if (Test-Path -LiteralPath $desktopShortcut) { Remove-Item -LiteralPath $desktopShortcut -Force }
  if (Test-Path -LiteralPath $programsFolder) { Remove-Item -LiteralPath $programsFolder -Recurse -Force }
  # Keep the uninstall entry until actual file and shortcut removal has succeeded.
  $registration = 'HKCU:\%s'
  if (Test-Path -LiteralPath $registration) { Remove-Item -LiteralPath $registration -Force }
  Set-Content -LiteralPath $statusFile -Value 'COMPLETED' -Encoding UTF8
} catch {
  Set-Content -LiteralPath $statusFile -Value ('FAILED: ' + $_.Exception.Message) -Encoding UTF8
  exit 1
}
`, powershellQuote(paths.Executable), os.Getpid(), powershellQuote(paths.InstallDir), powershellQuote(statusPath), windowsUninstallKey)
	if _, err := runPowerShell(script, true); err != nil {
		return fmt.Errorf("schedule installed files removal: %w", err)
	}
	return nil
}

func runWindowsPowerShell(script string, detached bool) (string, error) {
	powerShell := filepath.Join(os.Getenv("SystemRoot"), "System32", "WindowsPowerShell", "v1.0", "powershell.exe")
	command := exec.Command(powerShell, "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command", "$ErrorActionPreference = 'Stop';\n"+script)
	// Windows PowerShell needs CREATE_NO_WINDOW, not DETACHED_PROCESS, to execute without a console.
	command.SysProcAttr = &syscall.SysProcAttr{CreationFlags: windows.CREATE_NO_WINDOW, HideWindow: true}
	if detached {
		if err := command.Start(); err != nil {
			return "", err
		}
		return "", command.Process.Release()
	}
	output, err := command.CombinedOutput()
	return string(output), err
}

func powershellQuote(value string) string {
	return strings.ReplaceAll(value, "'", "''")
}

func showWindowsMessage(title, message string, flags uintptr) {
	user32 := syscall.NewLazyDLL("user32.dll")
	messageBox := user32.NewProc("MessageBoxW")
	titlePointer, _ := syscall.UTF16PtrFromString(title)
	messagePointer, _ := syscall.UTF16PtrFromString(message)
	_, _, _ = messageBox.Call(0, uintptr(unsafe.Pointer(messagePointer)), uintptr(unsafe.Pointer(titlePointer)), flags)
}
