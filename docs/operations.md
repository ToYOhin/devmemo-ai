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

Keep `AI_AGENT_ENABLED=false` unless explicitly using the documented single-host
Agent path. Lifecycle/outbox/ledger/rehydration have opt-in composition; they are
not merely unwired proofs, but neither are they default-enabled or multi-instance
authority. Use the [AI guide](../README_AI.md) and [R5 acceptance](r5-acceptance.md)
for the bounded topology. Worker, automatic indexing, real-data migration and
shared replay/rebuild authority are separate extensions, not demo prerequisites.

For saved Agent credentials, back up the AI SQLite database and
`AI_AGENT_PROVIDER_MASTER_KEY` separately. Do not generate a replacement master
key during upgrade; existing ciphertext would become unreadable. Only Agent
paths use the administrator's saved configuration; legacy AI routes retain environment settings.

## Windows core installation

Program files are under `%LOCALAPPDATA%\Programs\DevMemoAI`; Memo data/attachments
are under `%LOCALAPPDATA%\DevMemoAI\data`. Stop the owned application before a
consistent data-directory backup. A custom portable data directory is not migrated automatically.

An installation/upgrade failure restores the old executable when possible;
partial shortcut/registry updates may need a repair rerun. PowerShell failures are
not treated as successful installation. Uninstall schedules a hidden worker:
close the controller dialog, then inspect its named `uninstall-<pid>.log` under
`%LOCALAPPDATA%\DevMemoAI`. `STARTING`/`STARTED` are not completion; `COMPLETED`
means files/shortcuts/registration were removed, while `FAILED` records failure.
Memo data is retained. Registration remains until actual file/shortcut cleanup succeeds.

This core package does not install/start AI Service or model runtimes. Current
candidate evidence and unverified browser/distribution checks are in the
[v0.4.0 guide](releases/v0.4.0.md).

## Security boundary

Thumbnail generation checks image dimensions within a 1 MiB header probe before
full decoding and accepts at most 50 million source pixels. Invalid or oversized
images, or headers that cannot be inspected within that budget, use the existing
original-file fallback; this does not reject the upload or delete the attachment.
TIFF palette checks rely on the pinned `golang.org/x/image` decoder. Image
processing uses `github.com/kovidgoyal/imaging v1.6.5`, replacing the dependency
affected by GHSA-q7pp-wcgr-pffx. Its scanner handles all byte-sized palette indices;
synthetic regressions cover invalid indices, TIFF rejection, and original-file
fallback while retaining automatic EXIF orientation and Lanczos resizing.

Keep the default deterministic + memory profile unless optional adapters are
needed. Leave `AI_PUBLIC_CHUNK_RETRIEVAL=false` until a real trusted gateway,
Memos visibility mapping, controlled rollout, and a tested disable-and-rollback
path exist. Context Pack output remains browser-memory-only and must not be
treated as a server-side export channel.
