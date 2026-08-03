# DevMemo AI Service Guide

[Chinese](README_AI.zh-CN.md)

This guide covers the optional AI Service that accompanies Memos. Memos remains
the source of truth for Memo content, identities, and permissions. The AI
Service stores derived summaries, templates, insights, outbox state, and
optional index state only.

## Default profile

The default profile is intentionally offline-first and low-resource:

```text
AI_PROVIDER=deterministic
AI_EMBEDDING_PROVIDER=deterministic
AI_VECTOR_STORE=memory
AI_INDEX_ON_WEBHOOK=false
AI_INDEX_MODE=memo
AI_PUBLIC_CHUNK_RETRIEVAL=false
AI_AGENT_ENABLED=false
```

It starts Memos and AI Service with modest CPU limits. Qdrant and Ollama are
explicit profiles; they are not required for normal summaries, insights, or
browser-memory Context Packs.

## Start with Docker Compose

```powershell
docker compose config
docker compose up -d --build
```

Useful endpoints:

- Memos: <http://localhost:5230>
- AI Service health: <http://localhost:8000/health>
- Complete-Memo index health: <http://localhost:8000/api/ai/index/health>

For deployment, backup, restoration, and upgrade procedures, read
[docs/operations.md](docs/operations.md).

## Optional adapters

Enable optional services only when their operational cost and data boundaries
are understood:

```powershell
docker compose --profile qdrant up -d qdrant
docker compose --profile ollama up -d ollama
```

- Qdrant is an optional derived vector store. Complete-Memo and chunk indexes
  use distinct collections.
- FastEmbed is an optional CPU embedding provider and may download model data.
- Ollama is an optional local model runtime; its image is pinned to an explicit
  upstream release in Compose.

Use environment variables for provider configuration, never committed files:

- `AI_PROVIDER=deterministic|openai|ollama`
- `OPENAI_API_KEY`, `OPENAI_MODEL`, `OPENAI_BASE_URL`
- `OLLAMA_BASE_URL`, `OLLAMA_MODEL`
- `AI_EMBEDDING_PROVIDER=deterministic|fastembed`
- `AI_VECTOR_STORE=memory|qdrant`

## Webhook and public retrieval boundaries

The default Compose file blocks private-network Webhook targets. The
`docker-compose.local-webhook.yml` override is only for a controlled local
Docker development topology where Memos must call `ai-service`; do not use it
for public or multi-user deployments.

The controlled `POST /api/ai/v1/chunks/search` route exists but remains off by
default. Do not set `AI_PUBLIC_CHUNK_RETRIEVAL=true` until a real trusted
gateway, Memos visibility mapping, controlled rollout, and verified rollback
path are available.

## Experimental Evidence Answer Agent

The read-only Evidence Answer feature is disabled by default. When explicitly
configured, the browser calls only the authenticated Memos BFF at
`POST /api/ai/agent/answer`; Memos derives the caller's visible Memo scope and
delegates a short-lived, purpose-separated HMAC request to AI Service. The
browser never receives the delegation secret or sends its own visibility list.

The Agent has one tool, `search_memos`, and accepts only authorized complete-Memo
`memo-v1` evidence. Non-deterministic Provider output must satisfy the strict
`grounded-answer-result-v1` contract before the server maps citations. Public
results contain a bounded answer, server-owned citation fields, and a redacted
trace—never raw Memo content, prompt/context, embeddings, identities,
visibility data, or secrets.

The lifecycle event/outbox/ledger work is currently a dormant contract and
integration proof. It is not wired to Memo CRUD, a dispatcher, a worker,
automatic indexing, Qdrant, or default Compose. Read
[docs/agent-architecture.md](docs/agent-architecture.md) and
[docs/agent-development-roadmap.md](docs/agent-development-roadmap.md) before
attempting any runtime rollout.

R5 is complete for a default-disabled single-host scope. Authorized candidate
selection, current-authority rehydration, authenticated internal HTTP,
Memos-owned lifecycle dispatch, generation-scoped Qdrant state, rebuild
activation, and no-fallback answer selection have passed disposable Docker and
authenticated-browser acceptance, including visibility isolation,
update/delete, restart, rollback, and cleanup. AI Service and Qdrant remain
unpublished to the host. Real data, external Providers, cross-host transport,
and multi-instance operation remain separate gates. Memos remains the final
content, identity, visibility, and lifecycle authority; see the
[R5 Acceptance Record](docs/r5-acceptance.md).

## Local development and verification

Install Go, Node.js, pnpm, and Python. Create `ai-service/.venv`, then run:

```powershell
.\scripts\verify-devmemo.ps1
pnpm --dir web lint
pnpm --dir web test
pnpm --dir web build
```

The verification script discovers Go from `PATH` and the Python environment
from `ai-service/.venv`. Set `DEVMEMO_GO` or `DEVMEMO_PYTHON` only to override
those locations.

The container build installs the hash-locked `ai-service/requirements.lock.txt`.
After changing `ai-service/requirements.txt`, regenerate it with:

```powershell
uv pip compile ai-service/requirements.txt --generate-hashes --output-file ai-service/requirements.lock.txt
```

## API and extension scope

API contracts and request examples are in [docs/api.md](docs/api.md). Keep
Memos core changes separate from AI slices. Context Pack may consume only
explicitly visible Memos and accepted insights; it never exposes raw Memo
content, Webhook payloads, secrets, or chunk content.
