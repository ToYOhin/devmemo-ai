# Changelog

All notable changes to DevMemo AI are documented in this file.

DevMemo AI release versions are independent from the Memos upstream baseline.
See [UPSTREAM.md](UPSTREAM.md) for upstream compatibility information.

## Unreleased

## [0.3.0] - 2026-08-13

### Features

- Added frozen AgentRun contracts, derived-only SQLite persistence, and a
  bounded runtime with deterministic planning, checkpointing, and recovery.
- Added an authenticated same-origin AgentRun BFF that rechecks Memos-owned
  visibility and accepts only the fixed `project_summary` task.
- Added synchronous deterministic execution from a visible Memo to a
  creator-bound Markdown artifact with preview and download in the Memo detail
  view.
- Added an explicit opt-in DeepSeek adapter with non-thinking JSON mode,
  bounded output, fail-closed validation, and synthetic endpoint smoke.
- Added a local PowerShell launcher for the deterministic Agent demo while
  keeping the AI Service port private to the Compose network.

### Bug Fixes

- Routed legacy browser AI requests through authenticated same-origin Memos BFF
  projections instead of direct browser access to AI Service.
- Reject unknown AgentRun fields and task kinds, unauthenticated status reads,
  stale visibility scope, malformed Provider output, and conflicting artifact
  replay.

### Security and operational boundaries

- Deterministic remains the default Provider and AgentRun remains disabled by
  default; Provider credentials stay environment-only and are not printed or
  persisted by Compose.
- The release is intended for the documented personal, single-host demo path.
  It does not claim a background worker, approval flow, Memo write-back,
  free-form Agent tasks, real-user external-Provider acceptance, or
  production-ready multi-instance operation.

## [0.2.0] - 2026-08-10

### Features

- Added an opt-in Evidence Answer Agent behind the authenticated, same-origin
  Memos BFF, with Memos-owned visibility scope, server-owned citations, and a
  browser-safe response projection.
- Added durable authorized evidence rehydration and a default-disabled,
  source-owned lifecycle path for single-host local deployments.
- Added a versioned 64-case synthetic evaluation corpus, fixed safety
  thresholds, content-free observability, and reproducible Python, Go, Web,
  Proto, and CodeQL quality gates.

### Bug Fixes

- Refuse protected-prompt, private-secret, authorization-bypass, and forbidden
  evidence requests before retrieval or Provider execution.
- Prevent Provider, embedding, score, index, and internal trace metadata from
  reaching the browser Evidence Answer response.
- Wait for AI Service health in the Agent Compose overlay while keeping AI
  Service and Qdrant off host-published ports.

### Security and operational boundaries

- The Agent, lifecycle dispatcher, external Providers, and Qdrant remain
  explicit opt-ins; deterministic and in-memory adapters remain the defaults.
- This release is validated for the documented single-host local path. It does
  not claim public AI ports, real-user-data acceptance, or production-ready
  multi-instance deployment.

## [0.1.0] - 2026-07-28

### Added

- Initial DevMemo AI open-source distribution and release infrastructure.
- Independent DevMemo AI release assets and multi-architecture GHCR image namespace.

### Changed

- Release Please now safely skips when a dedicated `RELEASE_PLEASE_TOKEN` is absent; manual stable tags remain the supported release path.
