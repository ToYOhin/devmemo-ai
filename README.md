# DevMemo AI

[Chinese](README.zh-CN.md)

DevMemo AI is a self-hosted developer knowledge base for individuals and small
teams. It is built on Memos, which remains the source of truth for original
Memo data, user identities, and visibility permissions. A separate FastAPI AI
Service stores AI-derived state only; it does not introduce a second identity
or authorization system.

Use DevMemo AI to capture code snippets, bug reports, solutions, and technical
decisions as traceable developer knowledge. After human review, accepted
insights can be compiled into bounded, copyable Context Packs for an IDE or a
subsequent tool.

> **Unofficial downstream project.** DevMemo AI is not affiliated with,
> endorsed by, or supported by the Memos project. Read [UPSTREAM.md](UPSTREAM.md)
> and [NOTICE](NOTICE) for the upstream baseline, ownership boundary, and
> attribution.

## Key capabilities

- Keep Memo data, users, and permissions in Memos; AI state never replaces the
  Memos source of truth.
- Generate structured templates and AI-derived insights for Code Snippets and
  Bug Reports.
- Review and accept or reject insights in the Memo detail view before they can
  contribute to a working context.
- Build `context-pack-v1` from explicitly visible Memos and accepted insights.
  It contains only safe titles, summaries, and source references—not raw Memo
  content, Webhook payloads, secrets, or chunk content.
- Run locally with deterministic providers and in-memory retrieval by default,
  with a low-resource, offline-first baseline.
- Keep FastEmbed, Qdrant, Ollama, Webhook indexing, and public chunk retrieval
  as explicit opt-ins rather than default behavior.
- Offer an experimental, read-only Evidence Answer entry through the Memos BFF.
  It is disabled by default and returns only bounded answers, server-owned
  citations, and a redacted execution trace.
- Stage a fixed `project_summary` AgentRun through a default-disabled,
  authenticated same-origin BFF. Memos resolves one to ten visible Memo
  revisions before AI Service creates a content-free queued run and exposes
  creator-bound status.

## Architecture and data boundaries

```text
Memos (Go + React)
  ├─ Memo data, users, and permissions: source of truth
  └─ explicit Webhook integration
             │
             ▼
FastAPI AI Service
  ├─ AI-derived SQLite state only
  ├─ templates, insights, and optional index state
  └─ provider/vector-store adapters
             │
             ▼
Memo detail view
  ├─ AI insights review
  └─ in-memory Context Pack generation and copy
```

See [docs/structure.md](docs/structure.md) for repository and runtime
boundaries, and [docs/api.md](docs/api.md) for API contracts. The experimental
Agent design and remaining delivery gates are documented separately in
[docs/agent-architecture.md](docs/agent-architecture.md) and
[docs/agent-development-roadmap.md](docs/agent-development-roadmap.md). The
sanitized evaluation method/results and current completion gates are recorded in
[docs/agent-evaluation-benchmark.md](docs/agent-evaluation-benchmark.md) and
[docs/r6-completion-audit.md](docs/r6-completion-audit.md).

## Quick start

Prerequisite: Docker Desktop with Docker Compose.

```powershell
git clone https://github.com/ToYOhin/devmemo-ai.git
Set-Location devmemo-ai
docker compose config
docker compose up -d --build
```

After startup:

- Memos: <http://localhost:5230>
- AI Service health: <http://localhost:8000/health>

The published stable image is also available directly:

```powershell
docker pull ghcr.io/toyohin/devmemo-ai:stable
```

The stable image publishes `linux/amd64`, `linux/arm64`, and `linux/arm/v7`
manifests. Download native executables from [GitHub
Releases](https://github.com/ToYOhin/devmemo-ai/releases).

## Default security and resource posture

The default configuration is intentionally lightweight and conservative:

```text
AI_INDEX_ON_WEBHOOK=false
AI_INDEX_MODE=memo
AI_VECTOR_STORE=memory
AI_PUBLIC_CHUNK_RETRIEVAL=false
AI_AGENT_ENABLED=false
```

- Default Compose does not allow private-network Webhook targets.
- The default stack runs only Memos and the AI Service with modest CPU budgets.
- Qdrant and Ollama require explicit Compose profiles.
- Public chunk retrieval remains disabled. It requires a real trusted gateway,
  Memos visibility mapping, and a verified disable-and-rollback path.
- The Evidence Answer Agent remains an opt-in experiment. The reviewed R6
  baseline is published at `v0.2.0`; later R7 slices add frozen AgentRun
  contracts, single-host derived-only SQLite persistence, a bounded runtime,
  and authenticated create/status BFF routes for the fixed `project_summary`
  task kind. Execution, artifacts, a worker, and UI remain separate slices.
- A bounded DeepSeek adapter is available only through explicit configuration.
  Deterministic remains the default; the external endpoint smoke uses synthetic
  evidence and does not establish real-Memo or production deployment readiness.

For a controlled local Docker development topology where a Memos Webhook must
target `ai-service`, use the `docker-compose.local-webhook.yml` override
documented in [README_AI.md](README_AI.md). Do not use that override for a
public or multi-user deployment.

## Further reading

[README_AI.md](README_AI.md) documents AI Service configuration and optional
adapters. [docs/operations.md](docs/operations.md) covers deployment, backup,
restore, and upgrades. Contributions are welcome through
[CONTRIBUTING.md](CONTRIBUTING.md).

## Support, security, and governance

- Setup and usage support: [SUPPORT.md](SUPPORT.md).
- Bugs and feature requests: use this repository's GitHub issue forms.
- Security reports: follow [SECURITY.md](SECURITY.md); do not disclose
  vulnerabilities in public issues.
- Governance, maintainer responsibilities, and release expectations:
  [GOVERNANCE.md](GOVERNANCE.md).
- For Memos behavior unchanged by this project, use the upstream
  [Memos](https://github.com/usememos/memos) support and issue channels.

## License

DevMemo AI is distributed under the [MIT License](LICENSE). It contains
downstream changes based on Memos; upstream attribution and licensing details
are preserved in [NOTICE](NOTICE) and [UPSTREAM.md](UPSTREAM.md).
