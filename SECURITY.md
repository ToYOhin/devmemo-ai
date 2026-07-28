# Security Policy

## Supported versions

Security fixes are made against the latest DevMemo AI release line. Until the
first public release, the default branch is the only supported development
version.

## Reporting a vulnerability

Do not open a public issue, discussion, or pull request for a suspected
vulnerability. Use GitHub's private vulnerability-reporting flow for this
repository when it is enabled:

<https://github.com/ToYOhin/devmemo-ai/security/advisories/new>

Before a public release, the maintainer must enable that GitHub setting or
publish an equivalent private reporting channel. Reports should include the
affected component, reproduction steps, impact, and any safe mitigation. Do
not include real Memo content, credentials, tokens, Webhook payloads, or API
secrets.

## Deployment responsibilities

DevMemo AI is self-hosted. Operators are responsible for restricting access,
keeping Memos and dependencies updated, protecting backups, and leaving
private-network Webhook access disabled except in the documented local Compose
development override.
