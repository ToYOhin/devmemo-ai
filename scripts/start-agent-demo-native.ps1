[CmdletBinding()]
param(
  [Parameter(Mandatory = $true)]
  [string]$MemosExe,
  [ValidateRange(0, 65535)]
  [int]$MemosPort = 0,
  [ValidateRange(0, 65535)]
  [int]$AiPort = 0,
  [switch]$VerifyOnly
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
$python = Join-Path $repoRoot "ai-service\.venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
  throw "AI Service venv is missing. Follow docs/development.md to install the pinned dependencies first."
}
$resolvedExe = (Resolve-Path -LiteralPath $MemosExe).ProviderPath
$demoArguments = @(
  (Join-Path $repoRoot "ai-service\scripts\native_agent_demo.py"),
  "--memos-exe", $resolvedExe,
  "--memos-port", "$MemosPort",
  "--ai-port", "$AiPort"
)
if ($VerifyOnly) { $demoArguments += "--verify-only" }
& $python @demoArguments
if ($LASTEXITCODE -ne 0) {
  throw "Native Agent demo failed with exit code $LASTEXITCODE. See the printed local log directory."
}
