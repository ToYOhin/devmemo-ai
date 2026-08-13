# DeepSeek Provider smoke

This smoke verifies the real DeepSeek adapter with synthetic evidence. It does
not start Docker, write a Memo, use real user data, or persist the API key.

## What it verifies

- `AI_PROVIDER=deepseek` selects the dedicated adapter.
- The request uses the OpenAI-compatible `/chat/completions` endpoint.
- Thinking is disabled, JSON output is required, and output is capped at 1,200
  tokens.
- The response is valid `grounded-answer-result-v1` JSON bound to the supplied
  synthetic citation.
- Transport errors, HTTP 408/429, and server errors receive at most one retry;
  other client errors fail immediately.

## Run

Create `ai-service/.venv` and install the pinned requirements first. Then run:

```powershell
Set-Location <repository-root>
.\scripts\smoke-deepseek-provider.ps1
```

Enter the API key at the masked prompt. The script keeps it only in the current
process, restores any previous Provider environment variables in `finally`, and
prints only bounded synthetic verification metadata. A passing result resembles:

```json
{"status":"passed","provider":"deepseek","version":"grounded-answer-result-v1","citation_refs":["evidence-1"],"answer_chars":42}
```

The character count varies. Never put a real key in `.env`, command history,
Compose files, test fixtures, screenshots, or committed logs. Revoke a temporary
key in the DeepSeek console after the smoke.

## Optional configuration

- `-Model deepseek-v4-pro` selects the current default model.
- `-BaseUrl https://api.deepseek.com` selects the official endpoint.

Compose passes `DEEPSEEK_API_KEY`, `DEEPSEEK_MODEL`, and `DEEPSEEK_BASE_URL` only
when explicitly supplied. The default application path remains deterministic,
offline-first, and low-resource. If a credential is present in the shell, use
only `docker compose config --quiet`; ordinary `docker compose config` renders
resolved environment values and must not be captured in logs.

The smoke proves external Provider compatibility only. It does not prove real
Memo privacy acceptance, multi-instance operation, AgentRun product wiring, or
production readiness.

DeepSeek documents the OpenAI-compatible base URL and current model IDs in its
[Models & Pricing](https://api-docs.deepseek.com/quick_start/pricing/) reference.
The fixed request settings follow its
[Thinking Mode](https://api-docs.deepseek.com/guides/thinking_mode) and
[JSON Output](https://api-docs.deepseek.com/guides/json_mode/) guidance.
