[CmdletBinding()]
param(
  [ValidateSet("start", "status", "stop")]
  [string]$Action = "start",

  [string]$GoProxy = "https://goproxy.cn,direct",

  [switch]$NoBuild
)

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$composeFiles = @(
  "-p", "devmemo-agent-demo",
  "-f", (Join-Path $repoRoot "docker-compose.yml"),
  "-f", (Join-Path $repoRoot "docker-compose.agent.yml"),
  "-f", (Join-Path $repoRoot "docker-compose.local-webhook.yml"),
  "--profile", "agent"
)

function Invoke-DemoCompose {
  param([Parameter(ValueFromRemainingArguments = $true)][string[]]$Arguments)

  & docker compose @composeFiles @Arguments
  if ($LASTEXITCODE -ne 0) {
    throw "docker compose failed with exit code $LASTEXITCODE"
  }
}

if ($Action -eq "status") {
  Invoke-DemoCompose -Arguments @("ps")
  exit 0
}

if ($Action -eq "stop") {
  Invoke-DemoCompose -Arguments @("down")
  Write-Host "Demo stopped. Docker volumes were preserved."
  exit 0
}

$managedEnvironment = @(
  "AI_AGENT_ENABLED",
  "AI_AGENT_INTERNAL_SECRET",
  "AI_INDEX_ON_WEBHOOK",
  "AI_PROVIDER",
  "AI_EMBEDDING_PROVIDER",
  "AI_VECTOR_STORE",
  "DEVMEMO_GOPROXY",
  "NODE_OPTIONS"
)
$previousEnvironment = @{}
foreach ($name in $managedEnvironment) {
  $previousEnvironment[$name] = [Environment]::GetEnvironmentVariable($name, "Process")
}

try {
  $secretBytes = [byte[]]::new(32)
  $random = [Security.Cryptography.RandomNumberGenerator]::Create()
  try {
    $random.GetBytes($secretBytes)
  }
  finally {
    $random.Dispose()
  }

  $env:AI_AGENT_INTERNAL_SECRET = [Convert]::ToBase64String($secretBytes).TrimEnd("=").Replace("+", "-").Replace("/", "_")
  $env:AI_AGENT_ENABLED = "true"
  $env:AI_INDEX_ON_WEBHOOK = "true"
  $env:AI_PROVIDER = "deterministic"
  $env:AI_EMBEDDING_PROVIDER = "deterministic"
  $env:AI_VECTOR_STORE = "memory"
  $env:DEVMEMO_GOPROXY = $GoProxy

  $frontendIndex = Join-Path $repoRoot "server/router/frontend/dist/index.html"
  $originalFrontendIndex = [IO.File]::ReadAllBytes($frontendIndex)
  Push-Location $repoRoot
  try {
    Invoke-DemoCompose -Arguments @("config", "--quiet")

    if ($NoBuild) {
      $upArguments = @("up", "-d", "--no-build")
    }
    else {
      $env:NODE_OPTIONS = "--max-old-space-size=768"
      & pnpm --dir web release
      if ($LASTEXITCODE -ne 0) {
        throw "frontend release build failed with exit code $LASTEXITCODE"
      }
      $upArguments = @("up", "-d", "--build")
    }

    $startedAt = Get-Date
    Invoke-DemoCompose -Arguments $upArguments
    $elapsedSeconds = [Math]::Round(((Get-Date) - $startedAt).TotalSeconds, 1)

    Invoke-DemoCompose -Arguments @("ps")
    Write-Host "Agent demo is ready after the Compose build/start step completed in $elapsedSeconds seconds."
    Write-Host "Browser: http://localhost:5230"
    Write-Host "Webhook: http://ai-service:8000/api/integrations/memos/webhook"
  }
  finally {
    [IO.File]::WriteAllBytes($frontendIndex, $originalFrontendIndex)
    Pop-Location
  }
}
finally {
  foreach ($name in $managedEnvironment) {
    $previousValue = $previousEnvironment[$name]
    if ($null -eq $previousValue) {
      [Environment]::SetEnvironmentVariable($name, $null, "Process")
    }
    else {
      [Environment]::SetEnvironmentVariable($name, $previousValue, "Process")
    }
  }
}
