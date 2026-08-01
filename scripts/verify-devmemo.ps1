param(
    [switch]$FullBackend
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
$go = if ($env:DEVMEMO_GO) { $env:DEVMEMO_GO } else { (Get-Command go -ErrorAction Stop).Source }
$python = if ($env:DEVMEMO_PYTHON) {
    $env:DEVMEMO_PYTHON
} else {
    Join-Path $repoRoot "ai-service\.venv\Scripts\python.exe"
}

if (-not (Test-Path $go)) { throw "Go not found. Put go on PATH or set DEVMEMO_GO." }
if (-not (Test-Path $python)) { throw "AI service virtualenv not found. Create ai-service/.venv or set DEVMEMO_PYTHON." }

$env:GOTOOLCHAIN = "local"
$env:GOMAXPROCS = "1"
$env:DEVMEMO_GO_TEST_P = "1"

& $go version
Push-Location (Join-Path $repoRoot "ai-service")
& $python -m pytest -q tests
$pytestExit = $LASTEXITCODE
Pop-Location
if ($pytestExit -ne 0) { throw "AI service tests failed with exit code $pytestExit" }

docker compose config --quiet
if ($LASTEXITCODE -ne 0) { throw "docker compose config failed" }

if ($FullBackend) {
    & $go test -p 1 ./...
    if ($LASTEXITCODE -ne 0) { throw "go test -p 1 ./... failed" }
}

Write-Output "DEVMEMO_VERIFY_OK"
