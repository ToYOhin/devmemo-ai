# Development

Current scope and next work: [project status](project-status.md) and [roadmap](roadmap.md).
Commands below are opt-in choices, not a request to start every environment.

## Choose the execution lane

For Windows core, use the existing portable/installed executable. A key-free
local source run with already prepared Web assets can use:

```powershell
$env:GOMAXPROCS = "1"
go run -p 1 ./cmd/memos --addr 127.0.0.1 --port 5230 --data .devmemo-local/core-demo-data --open-browser=false
```

Use a dedicated synthetic data directory. The core path does not start Python
or a model. Build/install instructions are in the root README; no candidate
rebuild is required for documentation or an unchanged validated input.

## Optional AI/Compose commands

```powershell
$env:GOTOOLCHAIN = "local"
.\scripts\verify-devmemo.ps1
ai-service/.venv/Scripts/python.exe -m pytest -q ai-service/tests
docker compose config
docker compose up -d memos ai-service
docker compose --profile qdrant up -d qdrant
docker compose --profile ollama up -d ollama
ai-service/.venv/Scripts/python.exe -m uvicorn main:app --app-dir ai-service --port 8000
```

The default Compose path starts only Memos and AI Service, capped at `0.75` and `0.25` CPU respectively. Qdrant and Ollama are explicit profiles so their resource costs are never part of ordinary deterministic + memory development. `verify-devmemo.ps1` also limits Go verification to one processor and `go test -p 1`; pass `-FullBackend` only when that slower low-CPU check is required.

Install a supported Go toolchain and make `go` available on `PATH`. Create the
AI virtual environment at `ai-service/.venv` before running the verification
script. Set `DEVMEMO_GO` or `DEVMEMO_PYTHON` only when the commands are not
discoverable through `PATH` or the repository virtual environment.

The AI Service container uses the hash-locked `ai-service/requirements.lock.txt`.
After changing `ai-service/requirements.txt`, regenerate the lock with
`uv pip compile ai-service/requirements.txt --generate-hashes --output-file ai-service/requirements.lock.txt`.

The AI Service quality gate uses a separate hash-locked development superset
constrained by the production lock. Regenerate and run it from `ai-service/`:

```powershell
uv pip compile requirements-dev.txt --python-version 3.12 --generate-hashes --output-file requirements-dev.lock.txt
.\.venv\Scripts\python.exe -m pip install --require-hashes -r requirements-dev.lock.txt
.\.venv\Scripts\python.exe -m ruff check app tests scripts main.py database.py embedding.py lifecycle_report.py llm.py rag.py
.\.venv\Scripts\python.exe -m mypy app main.py database.py embedding.py lifecycle_report.py llm.py rag.py
.\.venv\Scripts\python.exe -m coverage run --branch -m pytest -q tests
.\.venv\Scripts\python.exe -m coverage report --show-missing
```

## Provider configuration

Use `AI_PROVIDER=deterministic` for a key-free local smoke. With the Agent opt-in
and AI Service available, administrators can configure the Agent under
Settings → AI → Agent Provider. The server requires a separate master key for
encrypted credential storage; reads are masked. Saved settings affect Agent
paths only. Legacy routes keep `AI_PROVIDER` and environment configuration.
See [AI setup](../README_AI.md) for consent, endpoints and budgets. Never use real
credentials in regression tests; deterministic/synthetic verification needs none.

## Current development slices

Keep changes independently revertable. Check the affected layer rather than
restarting historical slices:

1. Windows installer: `go test -p 1 -parallel 1 -count=1 -timeout 120s ./cmd/memos`
   on Windows. Real PowerShell/COM tests use temporary targets, not an existing install.
2. AI behavior: run the nearest synthetic test file, then the pinned quality gates
   above when the Python input changes. Do not lower coverage's 88.0% threshold.
3. Memos BFF/authority: relevant `internal/aiagent` or `server/router/api/v1` tests.
4. Web: existing lint/tests/build for actual Web changes, not for documentation.
5. Docs only: diff/links/content checks; no frontend, Go candidate or Docker build.

Use `GOMAXPROCS=1`, `-p 1`, serial commands and the existing dependency versions.
Review current evidence before repeating full checks. Package, UI, Provider and
CI lanes remain distinct; publishing needs its own explicit request.

## Scope boundaries

Keep Memos core changes out of AI slices. Chunk Webhook mode is opt-in and isolated from the complete-Memo chat index; do not silently change `AI_INDEX_MODE=memo`, the Webhook `code=0` contract, or the public chat citation shape.

## Task completion docs

Keep public documentation, release notes, and contributor guidance aligned with any user-visible behavior or deployment change. Do not publish secrets, local paths, credentials, or internal planning records.
