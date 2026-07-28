# DevMemo AI

DevMemo AI is an open-source, self-hosted developer knowledge base built on
[Memos](https://github.com/usememos/memos). It keeps Memos as the source of
truth for Memo data and permissions, and adds a separate AI Service for safe,
reviewable derived insights and Context Packs.

> **Unofficial downstream project.** DevMemo AI is not affiliated with,
> endorsed by, or supported by the Memos project. See [UPSTREAM.md](UPSTREAM.md)
> and [NOTICE](NOTICE) for the upstream baseline and attribution.

## What it does

- Keep notes, permissions, and primary storage in Memos.
- Derive Code Snippet and Bug Report summaries through a separate FastAPI
  service.
- Review AI insights before they can appear in a bounded, copyable Context
  Pack.
- Run locally by default with deterministic providers and in-memory retrieval;
  cloud models, FastEmbed, Qdrant, Ollama, indexing, and public chunk retrieval
  are explicit opt-ins.

## Quick start

Prerequisites: Docker Desktop with Compose.

```powershell
git clone https://github.com/ToYOhin/devmemo-ai.git
Set-Location devmemo-ai
docker compose config
docker compose up -d --build
```

Open Memos at <http://localhost:5230> and AI Service health at
<http://localhost:8000/health>.

The default deployment keeps `AI_INDEX_ON_WEBHOOK=false`,
`AI_INDEX_MODE=memo`, `AI_VECTOR_STORE=memory`, and
`AI_PUBLIC_CHUNK_RETRIEVAL=false`. It does **not** permit private-network
Webhook targets. Local development that intentionally connects a Memos Webhook
to the Compose AI Service must use the explicit override documented in
[README_AI.md](README_AI.md).

## Development

```powershell
# AI Service tests
Set-Location ai-service
.\.venv\Scripts\python.exe -m pytest -q tests

# Web checks
Set-Location ..\web
pnpm lint
pnpm test
pnpm build
```

Read [CONTRIBUTING.md](CONTRIBUTING.md) before opening a pull request. The
project's current product boundaries and configuration are documented in
[README_AI.md](README_AI.md).

## Getting help

- For DevMemo AI bugs and feature requests, use this repository's issue forms.
- For setup and usage guidance, read [SUPPORT.md](SUPPORT.md).
- For security reports, follow [SECURITY.md](SECURITY.md); do not disclose
  vulnerabilities in public issues.
- For behavior that is unchanged from upstream Memos, consult the
  [Memos project](https://github.com/usememos/memos) rather than treating
  upstream maintainers as DevMemo AI support staff.

## Maintainer and governance

The project is currently maintained by [@ToYOhin](https://github.com/ToYOhin).
Decision-making, review, and release expectations are described in
[GOVERNANCE.md](GOVERNANCE.md). Community expectations are in
[CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md).

## License

DevMemo AI is distributed under the [MIT License](LICENSE). It contains
downstream modifications of Memos; the required upstream attribution and
licensing notices are preserved in [NOTICE](NOTICE).
