# DevMemo AI Agent Guide

This file is the repository-level working agreement for coding agents and
automation. Follow the existing architecture and make focused, verifiable
changes; do not redesign the project from scratch.

## Project boundaries

- The Memos Go application (`cmd/`, `server/`, `store/`, `internal/`, and
  `proto/`) is the source of truth for memos, identities, and permissions.
- `ai-service/` is an independent FastAPI sidecar. Its SQLite database stores
  only AI-derived state; it must not become a second system of record for
  Memos data.
- `web/` is the React and TypeScript client. AI product entry points live in
  `web/src/features/ai/`.
- `contracts/` contains cross-language, provider-neutral fixtures. Update the
  relevant contract fixture and its tests when a shared AI output changes.
- `graphify-out/graph.json` is a historical local index, not an architecture
  authority. Prefer current source code and `docs/structure.md`.

## Safe defaults and AI boundaries

Keep these defaults unless a task explicitly changes them and includes a
rollback plan:

```text
AI_PROVIDER=deterministic
AI_EMBEDDING_PROVIDER=deterministic
AI_INDEX_ON_WEBHOOK=false
AI_INDEX_MODE=memo
AI_VECTOR_STORE=memory
AI_PUBLIC_CHUNK_RETRIEVAL=false
```

- FastEmbed and Qdrant are opt-in adapters/profiles, not default requirements.
- Preserve the Compose CPU limits and do not add background workers or agents
  to the default deployment path without an explicit product decision.
- Do not expose raw memo content, webhook payloads, secrets, embeddings, or
  chunk content through public responses or browser state.
- Context Pack is browser-memory-only, provider-neutral output. It may use
  explicitly visible memos and accepted insights, but must not persist to AI
  SQLite, access Qdrant, or start a worker.
- The public chunk retrieval route must remain disabled until a trusted gateway,
  Memos visibility mapping, and a tested rollback condition are available.
- The Evidence Answer Agent is disabled by default. Preserve the Memos-owned
  visibility scope, the `search_memos`-only tool boundary, complete-Memo
  `memo-v1` filtering, server-owned citations, and redacted trace projection.
- A4 lifecycle outbox/ledger code is dormant. Do not connect it to Memo CRUD,
  a dispatcher, worker, timer, automatic indexing, Qdrant, or runtime defaults
  without an explicitly reviewed implementation slice.

## Change discipline

- Work in one small, complete vertical slice at a time.
- Inspect the closest source, tests, and targeted documentation before editing.
- Preserve user changes. Do not use destructive Git commands or broad
  formatting rewrites.
- Use `apply_patch` for intentional file edits.
- Keep public documentation free of local machine paths, private coordination,
  credentials, internal handoffs, and unverified operational claims.
- Keep English and Chinese public guides in separate files; update both when
  changing shared installation, security, or operational guidance.
- Do not change Memos auth, permission mapping, default AI safety flags, or
  persisted data boundaries as an incidental refactor.

## Validation

Run the smallest relevant checks after a change:

| Area | Primary checks |
| --- | --- |
| AI service | From `ai-service/`, run the pinned Ruff, mypy, and branch-coverage commands in `docs/development.md` |
| Go backend | `go test -p 1 ./server/router/api/v1` or the closest affected package |
| Web client | In `web/`: `pnpm lint`, `pnpm test`, and `pnpm build` |
| Compose/configuration | `docker compose config --quiet` when Docker Desktop is available |
| Documentation only | `git diff --check` and targeted link/content checks |

Report any environment-limited check accurately. Do not label browser,
clipboard, authenticated, container, or deployment verification as passing
without real evidence.

## Git and release rules

- Review `git status --short --branch` before and after work.
- Do not commit, push, tag, create a release, or publish an image unless the
  user explicitly requests it.
- Keep commits narrow and descriptive when requested. Do not include local-only
  plans or working notes in public commits.
- Treat GitHub security findings as actionable. Prefer a tested dependency or
  source fix; only dismiss an alert when the unavailable code path has been
  verified and the dismissal includes a clear reason.

## Useful references

- `README.md` and `README.zh-CN.md`: public product and setup overview.
- `README_AI.md` and `README_AI.zh-CN.md`: AI service configuration and safety
  boundaries.
- `docs/structure.md`: current architecture map.
- `docs/api.md`: API and webhook contract details.
- `docs/operations.md` and `docs/operations.zh-CN.md`: backup, restore,
  upgrade, and rollback guidance.
- `docs/agent-architecture.md` and `docs/agent-architecture.zh-CN.md`:
  proposed Evidence Answer Agent contract and safety boundaries.
- `docs/DECISIONS.md`: accepted technical decisions.
