[CmdletBinding()]
param(
  [string]$OutputDirectory = "build/windows-installer",
  [string]$Version = ""
)

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$frontendIndex = Join-Path $repoRoot "server/router/frontend/dist/index.html"
$originalFrontendIndex = [IO.File]::ReadAllBytes($frontendIndex)
$previousEnvironment = @{
  GOOS = $env:GOOS
  GOARCH = $env:GOARCH
  CGO_ENABLED = $env:CGO_ENABLED
  NODE_OPTIONS = $env:NODE_OPTIONS
}

function Test-WindowsExecutable {
  param([Parameter(Mandatory = $true)][string]$Path)

  $stream = [IO.File]::OpenRead($Path)
  try {
    return $stream.ReadByte() -eq 0x4d -and $stream.ReadByte() -eq 0x5a
  }
  finally {
    $stream.Dispose()
  }
}

Push-Location $repoRoot
try {
  if ([string]::IsNullOrWhiteSpace($Version)) {
    $Version = (git describe --tags --always --dirty).Trim().TrimStart("v")
    if ($LASTEXITCODE -ne 0) {
      throw "failed to determine build version"
    }
  }
  if ($Version -notmatch '^[0-9A-Za-z][0-9A-Za-z._-]*$') {
    throw "version may contain only letters, numbers, dots, underscores, and hyphens"
  }
  $commit = (git rev-parse HEAD).Trim()
  if ($LASTEXITCODE -ne 0) {
    throw "failed to determine build commit"
  }

  $env:NODE_OPTIONS = "--max-old-space-size=768"
  & pnpm --dir web release
  if ($LASTEXITCODE -ne 0) {
    throw "frontend release build failed with exit code $LASTEXITCODE"
  }

  if ([IO.Path]::IsPathRooted($OutputDirectory)) {
    $resolvedOutput = [IO.Path]::GetFullPath($OutputDirectory)
  }
  else {
    $resolvedOutput = [IO.Path]::GetFullPath((Join-Path $repoRoot $OutputDirectory))
  }
  [IO.Directory]::CreateDirectory($resolvedOutput) | Out-Null

  $portablePath = Join-Path $resolvedOutput "DevMemoAI.exe"
  $installerPath = Join-Path $resolvedOutput "DevMemoAI-$Version-windows-amd64-Setup.exe"
  $ldflags = "-s -w -X github.com/usememos/memos/internal/version.Version=$Version -X github.com/usememos/memos/internal/version.Commit=$commit -extldflags '-static'"

  $env:GOOS = "windows"
  $env:GOARCH = "amd64"
  $env:CGO_ENABLED = "0"
  & go build -trimpath "-ldflags=$ldflags" -tags "netgo,osusergo" -o $portablePath ./cmd/memos
  if ($LASTEXITCODE -ne 0) {
    throw "Windows executable build failed with exit code $LASTEXITCODE"
  }

  Copy-Item -LiteralPath $portablePath -Destination $installerPath -Force
  foreach ($path in @($portablePath, $installerPath)) {
    if (-not (Test-WindowsExecutable -Path $path)) {
      throw "$path is not a Windows PE executable"
    }
  }

  Write-Host "Portable executable: $portablePath"
  Write-Host "One-click installer: $installerPath"
}
finally {
  [IO.File]::WriteAllBytes($frontendIndex, $originalFrontendIndex)
  foreach ($name in $previousEnvironment.Keys) {
    [Environment]::SetEnvironmentVariable($name, $previousEnvironment[$name], "Process")
  }
  Pop-Location
}
