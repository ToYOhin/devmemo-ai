# Operations Guide

[简体中文](operations.zh-CN.md)

This guide covers a self-hosted DevMemo AI deployment. Memos remains the source
of truth for Memo content, identities, and permissions; back it up before any
upgrade or host migration.

## Start and health checks

```powershell
docker compose config
docker compose up -d --build
docker compose ps
curl http://localhost:8000/health
```

The default stack starts Memos and AI Service only. Qdrant and Ollama remain
optional profiles. `restart: unless-stopped` lets Docker restart a previously
started service after a daemon or host restart; use `docker compose down` for
an intentional stop.

Use `docker compose logs --tail=200 memos ai-service` for first-line incident
diagnosis. Do not put `AI_WEBHOOK_SECRET`, `AI_OPS_TOKEN`,
`AI_PUBLIC_CHUNK_SECRET`, or provider keys in tickets or logs.

## Backup and restore

Back up these named volumes together:

- `memos-data`: authoritative Memos data, users, and permissions.
- `ai-data`: AI-derived summaries, templates, insight review state, and outbox
  audit state.

When the optional Qdrant profile is used, decide whether to back up
`qdrant-data` or rebuild its derived index after recovery. `ai-model-cache` and
`ollama-data` are model caches, not the only copy of business data.

For a consistent backup, stop the stack or use a storage snapshot mechanism
that guarantees consistency for both authoritative and AI volumes. Record the
Docker volume names with `docker volume ls` before archiving them. Keep backups
encrypted and access-controlled.

To restore, stop the stack, restore `memos-data` and `ai-data` to their original
volume names, then start the stack. Verify Memos login and visibility first,
then `GET /health`, the AI detail view, and an accepted-insight Context Pack.
Never restore a production backup into a public test environment.

## Upgrade and rollback

1. Read the target Memos release notes and back up the required volumes.
2. Update one upstream Memos tag or one pinned dependency set at a time.
3. Run `docker compose config`, AI Service tests, Web checks, and the relevant
   Go checks before deployment.
4. Rebuild with `docker compose up -d --build`, then check Memos and AI health.
5. If the smoke check fails, roll back the image/configuration and restore from
   the verified backup when data migration requires it.

The `docker-compose.local-webhook.yml` override is for a controlled local
Docker topology only. Do not use it for public or multi-user deployments.

## Experimental Agent operations

Keep `AI_AGENT_ENABLED=false` unless the Evidence Answer path is being tested
in an explicitly reviewed local topology. The A4 lifecycle outbox and AI ledger
are dormant proofs: they do not justify enabling a dispatcher, worker,
automatic indexing, or a persistent vector store. Any future rollout requires
an authoritative visibility check, reconciliation and rebuild procedures,
bounded retries, a shared replay store for multi-instance deployment, and a
tested disable-and-rebuild rollback.

## Security boundary

Keep the default deterministic + memory profile unless optional adapters are
needed. Leave `AI_PUBLIC_CHUNK_RETRIEVAL=false` until a real trusted gateway,
Memos visibility mapping, controlled rollout, and a tested disable-and-rollback
path exist. Context Pack output remains browser-memory-only and must not be
treated as a server-side export channel.
