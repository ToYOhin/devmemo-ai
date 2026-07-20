# Development

## MVP commands

```powershell
$env:GOTOOLCHAIN = "local"
$env:Path = "G:\Go\bin;$env:Path"
.\scripts\verify-devmemo.ps1
ai-service/.venv/Scripts/python.exe -m pytest -q ai-service/tests
docker compose config
docker compose up -d memos ai-service
docker compose --profile qdrant up -d qdrant
docker compose --profile ollama up -d ollama
ai-service/.venv/Scripts/python.exe -m uvicorn main:app --app-dir ai-service --port 8000
```

The default Compose path starts only Memos and AI Service, capped at `0.75` and `0.25` CPU respectively. Qdrant and Ollama are explicit profiles so their resource costs are never part of ordinary deterministic + memory development. `verify-devmemo.ps1` also limits Go verification to one processor and `go test -p 1`; pass `-FullBackend` only when that slower low-CPU check is required.

The reproducible local Go installation is `G:\Go` with `GOPATH=G:\GoWorkspace`. Open a new PowerShell window after changing the user PATH, or set the variables shown above for the current session.

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

After every completed slice, update `docs/PROJECT_STATUS.md`, append `docs/CHANGELOG_AI.md`, refresh `docs/HANDOFF.md`, and replace `docs/prompts/NEXT_STAGE_PROMPT.md`. Use `docs/prompts/TASK_PROMPT_TEMPLATE.md` when starting a new slice.
