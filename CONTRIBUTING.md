# Contributing to DevMemo AI

Thank you for contributing. This repository is an unofficial downstream of
Memos; please keep that boundary explicit in issues and pull requests.

## Before opening an issue

- Use this repository only for DevMemo AI behavior, documentation, CI, and
  deployment concerns.
- Report unchanged upstream Memos behavior to
  [Memos](https://github.com/usememos/memos).
- Do not put passwords, tokens, raw private Memos, Webhook payloads, or other
  secrets in an issue.
- Follow [SECURITY.md](SECURITY.md) for suspected vulnerabilities.

## Development rules

- Preserve Memos as the source of truth for Memo data and permissions.
- Keep AI-derived state in `ai-service/`; do not write raw Memo content into
  Context Packs or public responses.
- Keep public chunk retrieval disabled unless its gateway, visibility mapping,
  and rollback prerequisites are separately approved.
- Do not add dependencies or alter default AI providers without a scoped
  proposal.

## Local verification

```powershell
# From the repository root
Set-Location ai-service
.\.venv\Scripts\python.exe -m pytest -q tests

Set-Location ..\web
pnpm lint
pnpm test
pnpm build

Set-Location ..
docker compose config --quiet
git diff --check
```

Run only the checks affected by your change first, then run the relevant full
suite before requesting review. Keep commits focused and explain the user,
security, and upstream-compatibility impact in the pull request.
