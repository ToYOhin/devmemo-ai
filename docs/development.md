# Development

## MVP commands

```powershell
$env:GOTOOLCHAIN = "local"
$env:Path = "G:\Go\bin;$env:Path"
.\scripts\verify-devmemo.ps1
ai-service/.venv/Scripts/python.exe -m pytest -q ai-service/tests
docker compose config
ai-service/.venv/Scripts/python.exe -m uvicorn main:app --app-dir ai-service --port 8000
```

The reproducible local Go installation is `G:\Go` with `GOPATH=G:\GoWorkspace`. Open a new PowerShell window after changing the user PATH, or set the variables shown above for the current session.

## Provider configuration

Use `AI_PROVIDER=deterministic` for a key-free local smoke test. Use `openai` with `OPENAI_API_KEY`, or `ollama` with `OLLAMA_BASE_URL` and `OLLAMA_MODEL`.

## Commit slices

Keep changes independently revertable. The current MVP slices are:

1. FastAPI service and LLM adapter boundary.
2. Summary generation and `ai_notes` persistence.
3. Memos webhook trigger and Docker/documentation foundation.

## Scope boundaries

Do not add code snippet forms, Bug Report templates, Qdrant indexing, RAG chat, or broad Memos refactors to the summary slice. Each is a separate phase.

## Task completion docs

After every completed slice, update `docs/PROJECT_STATUS.md`, append `docs/CHANGELOG_AI.md`, refresh `docs/HANDOFF.md`, and replace `docs/prompts/NEXT_STAGE_PROMPT.md`. Use `docs/prompts/TASK_PROMPT_TEMPLATE.md` when starting a new slice.
