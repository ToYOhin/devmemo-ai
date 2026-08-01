# Security Policy

## Supported versions

Security fixes are made against the latest supported DevMemo AI release line.
The current supported line is `v0.1.x`; users who build from `main` should
update to the latest commit before reporting an issue.

## Reporting a vulnerability

Do not open a public issue, discussion, or pull request for a suspected
vulnerability. Use this repository's enabled GitHub private
vulnerability-reporting flow:

<https://github.com/ToYOhin/devmemo-ai/security/advisories/new>

Reports should include the affected component, reproduction steps, impact, and
any safe mitigation. Do not include real Memo content, credentials, tokens,
Webhook payloads, or API secrets.

## Deployment responsibilities

DevMemo AI is self-hosted. Operators are responsible for restricting access,
keeping Memos and dependencies updated, protecting backups, and leaving
private-network Webhook access disabled except in the documented local Compose
development override.
