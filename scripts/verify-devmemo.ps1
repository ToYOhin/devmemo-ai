param(
    [switch]$FullBackend
)

$ErrorActionPreference = "Stop"
$go = "G:\Go\bin\go.exe"
$python = "H:\DevMemoAI\ai-service\.venv\Scripts\python.exe"

if (-not (Test-Path $go)) { throw "Go not found at $go" }
if (-not (Test-Path $python)) { throw "AI service virtualenv not found at $python" }

$env:GOTOOLCHAIN = "local"
$env:GOPATH = "G:\GoWorkspace"
$env:GOCACHE = "G:\GoWorkspace\cache"
$env:GOMAXPROCS = "2"
$env:DEVMEMO_GO_TEST_P = "2"
$env:Path = "G:\Go\bin;$env:Path"

& $go version
$repoRoot = Get-Location
Push-Location "${repoRoot}\ai-service"
& $python -m pytest -q tests
$pytestExit = $LASTEXITCODE
Pop-Location
if ($pytestExit -ne 0) { throw "AI service tests failed with exit code $pytestExit" }

docker compose config --quiet
if ($LASTEXITCODE -ne 0) { throw "docker compose config failed" }

if ($FullBackend) {
    & $go test -p 2 ./...
    if ($LASTEXITCODE -ne 0) { throw "go test -p 2 ./... failed" }
}

Write-Output "DEVMEMO_VERIFY_OK"
