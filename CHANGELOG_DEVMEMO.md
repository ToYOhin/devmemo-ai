# Changelog

All notable changes to DevMemo AI are documented in this file.

DevMemo AI release versions are independent from the Memos upstream baseline.
See [UPSTREAM.md](UPSTREAM.md) for upstream compatibility information.

## [0.4.0] - Unreleased

Prepared release metadata, not a published tag or Release. Complete release
notes, upgrade guidance, local candidate results, and remaining distribution
acceptance checklist are in [the v0.4.0 release guide](docs/releases/v0.4.0.md)
([简体中文](docs/releases/v0.4.0.zh-CN.md)).

### Features

- Added a per-user Windows one-click installer executable that installs the
  standalone DevMemo AI core, creates Start Menu and desktop shortcuts, opens
  the local UI on startup, and preserves memo data during uninstall.
- Added a reproducible PowerShell build script and Release workflow packaging
  for the Windows installer without introducing a third-party installer
  dependency.
- Added an administrator-only Agent Provider settings panel and versioned
  configuration contract for deterministic, OpenAI, DeepSeek, and local Ollama.
  Saved settings apply to Evidence Answer and AgentRun, not legacy AI routes.
- Added encrypted AI-owned SQLite credential storage and authenticated internal
  configuration APIs. Keys are write-only; reads expose only a masked hint and
  whether a key is present.
- Connected configured Providers to Evidence Answer and the AgentRun report
  finalizer, with strict output validation, bounded deadlines, and explicitly
  marked deterministic AgentRun fallback.

### Bug Fixes

- Allow a first keyless Ollama configuration to be saved, close Provider SQLite
  connections deterministically, and give the BFF a bounded finalization budget
  beyond the unchanged 20-second Provider deadline.
- Preserve the old Windows executable on installation/upgrade failures, retain
  its backup if rollback fails, and retain uninstall registration when the
  cleanup helper cannot start. Partial shortcut/registry updates require a
  repair rerun; they are not included in executable rollback.
- Propagate non-terminating PowerShell/COM errors into installer rollback.
  Execute hidden uninstall scripts with `CREATE_NO_WINDOW`, distinguish scheduling
  from completion, and remove uninstall registration only after actual file/shortcut
  cleanup. Publish bounded worker outcome in a separate completion log.
- Protect static files and `/api`, `/file`, and `/mcp` route boundaries against
  encoded path separators, including `%2F`, without an unintended SPA fallback.
- Bound thumbnail dimension/metadata decoding, handle malformed TIFF input and
  original-file fallback, and replace the vulnerable imaging dependency with
  a palette-safe fork.
- Keep unresolved pull requests out of stale-closure automation.

### Dependencies and regression coverage

- Update Echo to 5.2.0, x/image to 0.41.0, x/crypto to 0.55.0, x/net to 0.58.0,
  gRPC to 1.83.2, CEL to 0.29.0, and go-archive to 0.3.0; use
  `github.com/kovidgoyal/imaging` 1.6.5.
- Update Mermaid to 11.16.1 with adversarial XY, Radar, and Architecture
  regressions; update the Web runtime/build/test dependency closure, including
  nanoid 3.3.18 and undici 7.29.1 overrides.
- Update cryptography to 50.0.0 and verify legacy HKDF-SHA256/AES-GCM synthetic
  credential compatibility and tamper rejection. Update pytest to 9.0.3 and
  declare pytest-asyncio 1.4.0 in the development lockfile.
- Add isolated Windows installer lifecycle regressions to Windows CI and
  synthetic Provider configuration, masking, storage, timeout, and fallback
  regressions without reducing safety or coverage thresholds.
- Add real hidden-PowerShell execution, locked-COM upgrade rollback and temporary
  uninstall-worker success/failure regressions. Local Windows candidate acceptance
  covered 51 checks; that evidence is distinct from source CI and browser acceptance.

### Security and operational boundaries

- The standalone Windows executable includes the embedded web UI and Memos
  core only. AI Service, Agent, Qdrant, Ollama, and external Providers remain
  separate explicit opt-ins and are not claimed by the installer.
- Agent and lifecycle defaults remain disabled; deterministic and memory-based
  defaults remain unchanged. Remote Agent Provider use requires explicit Memo
  export consent. Legacy AI routes keep their environment configuration.
- Stored Provider credentials require a separately backed-up master key;
  changing or losing that key makes existing credentials unreadable.
- Source CI and synthetic installer tests do not prove final-package installation,
  real Windows integration, real Provider quality, or real-user-data acceptance.
  A local v0.4.0 core candidate passed real install/rollback/uninstall/data checks;
  broader distribution rows remain unverified. The build path has no Authenticode signing.

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
