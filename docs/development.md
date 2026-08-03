# Development

## MVP commands

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

Use `AI_PROVIDER=deterministic` for a key-free local smoke test. Use `openai` with `OPENAI_API_KEY`, or `ollama` with `OLLAMA_BASE_URL` and `OLLAMA_MODEL`.

## Current development slices

Keep changes independently revertable. The current slices are:

1. FastAPI service, LLM adapter and AI-owned SQLite boundary.
2. Memo templates and summary UI through `web/src/features/ai/`.
3. Provider-neutral embeddings, optional FastEmbed/Qdrant and index health.
4. RAG retrieval, HMAC Webhook, outbox retry/ops/retention audit.
5. Offline chunk evaluation and explicit chunk Webhook lifecycle.

## Scope boundaries

Keep Memos core changes out of AI slices. Chunk Webhook mode is opt-in and isolated from the complete-Memo chat index; do not silently change `AI_INDEX_MODE=memo`, the Webhook `code=0` contract, or the public chat citation shape.

## Task completion docs

Keep public documentation, release notes, and contributor guidance aligned with any user-visible behavior or deployment change. Do not publish secrets, local paths, credentials, or internal planning records.
