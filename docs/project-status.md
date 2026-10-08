# DevMemo AI delivery status

[简体中文](project-status.zh-CN.md) · [Roadmap](roadmap.md) · [Structure](structure.md)

Snapshot: **2026-10-01**. This is the current product/evidence entry point, not
a live CI dashboard. The target is an explainable personal/portfolio demo, not
a commercial multi-instance platform. Verify live Git/GitHub before publication.

## Implemented scope

| Area | Current implementation | Evidence boundary |
| --- | --- | --- |
| Memos core | Go + embedded React; identities, visibility, Memo/attachment persistence | Windows candidate HTTP runtime with synthetic accounts/data, not browser UX acceptance |
| Windows delivery | Per-user core installer, shortcuts, upgrade rollback, asynchronous uninstall preserving data | Local candidate 51/51 checks; `cmd/memos` 22 top-level tests; no AI sidecar bundled |
| Evidence Answer | Same-origin authenticated BFF, one read-only `search_memos` tool, server-owned citations | Bounded single-host opt-in; synthetic evidence is not real-user model quality |
| AgentRun | Fixed synchronous `project_summary`, visible Memo revisions, creator-bound Markdown artifact | Bounded runtime and optional report finalizer; no general task engine/worker/write-back |
| Provider administration | Settings UI, masked API, encrypted SQLite credentials, dynamic Agent Provider | Synthetic configuration/storage/failure tests; legacy summary/chat retain environment configuration |
| Lifecycle/RAG | Source-owned outbox, derived ledger, current-authority rehydration and optional Qdrant composition | Implemented opt-in single-host scope; disabled by default, not multi-instance acceptance |
| Dependencies | Security fixes merged via PRs #25/#28 | GitHub API returned **0 open Dependabot alerts** on this date; not permanent vulnerability freedom |

Deterministic/memory remain defaults. Agent, lifecycle, automatic indexing and
public chunk retrieval remain disabled by default. See [AI setup](../README_AI.md).

## Verification identities

- Last stable release: [v0.3.0](https://github.com/ToYOhin/devmemo-ai/releases/tag/v0.3.0).
  **v0.4.0 is unpublished**. A main push, metadata and candidate checks are not a Release.
- Pre-fix SHA `ca334b64fc3e427a44fc0d78a7f4c800c6c94379` passed
  [Backend/Windows](https://github.com/ToYOhin/devmemo-ai/actions/runs/36809392669),
  [Frontend](https://github.com/ToYOhin/devmemo-ai/actions/runs/36809392743),
  [AI Service](https://github.com/ToYOhin/devmemo-ai/actions/runs/36809392595),
  [Proto](https://github.com/ToYOhin/devmemo-ai/actions/runs/36809392616) and
  [Canary](https://github.com/ToYOhin/devmemo-ai/actions/runs/36809392603).
  These runs do not verify later commits. Canary is cloud Linux image evidence.
- Installer fix source: `aa5cd355e635139a72ca17035e94cff9443df116`.
  Its diff matches the local candidate input; 22 local Go tests passed before
  commit. Exact-head CI must be checked independently after push.
- Candidate input: pre-fix SHA plus patch SHA-256
  `32acb3f9389953fb9677f745b03e348c05fbc554542bce4a05894e35698d94bc`.
  Embedded version is `0.4.0`, embedded commit is the pre-fix SHA, and Go build
  information says `vcs.modified=true`. This is **not** a clean-tag build.
- Portable/setup/ZIP executable SHA-256:
  `6401b88c74bec55ffccc2683c767de877398f3f325c5293d1b488aa01ae8beb0`.
  ZIP SHA-256: `d598a79de29b8c9384c905b6ec4933e904dce5d0e94df10d06b446daf2e146a6`.
  One Go candidate build reused verified production Web assets; no frontend rebuild.

Local acceptance used real HKCU registration/COM shortcuts and a separate
synthetic data directory. It covered install, two explicit installed-process
starts, locked-shortcut upgrade failure/rollback, and real worker uninstall/data
preservation. The install success dialog was not confirmed to auto-open a browser.
Detailed logs, synthetic data and host handoffs remain outside Git.

## D2 local verification record (2026-10-01)

The [native demo entry point](native-agent-demo.md) reuses an existing core binary and
current Python source with isolated synthetic data. It covers settings, cited answers,
consecutive summaries, download/replay, marked configuration fallback, and unavailable
service handling. **25/25 real local HTTP checks** passed; both demo children and listeners
stopped. Docker and browsers were not started, and no real Provider was called.
Run-scoped step IDs also fix the database identity collision on a second AgentRun;
regression coverage checks independent reports and replay of the first run.

Python validation: **983 passed**, **88.6% branch coverage** against the unchanged 88.0%
threshold, Ruff and mypy passed. This is dated local evidence; exact-head CI must be
checked separately after committing. It is not a rebuilt installer or Release. UI interaction remains unverified;
existing Web assets must include the AI UI build-time opt-in to display the panels.

## Progression problems and remaining work

Historical stage-local "unwired" text sent work back to completed R5/R7 gates.
Structure maps omitted settings/finalization and repeated Web trees. Source CI,
synthetic tests, package execution and publication were mixed; commercial goals
also obscured the demo finish line. Current status, plans and dated evidence now
have separate entry points.

| Priority | Remaining item | Completion criterion |
| --- | --- | --- |
| Closeout | Exact-head CI and repository state | Check pushed source gates, clean main/remote parity and dated alert snapshot |
| D2 finish | Native HTTP flow passed; UI demonstration remains | Reuse the native entry point, check existing Web AI UI opt-in, and obtain actual interface evidence |
| Small follow-up | Localized PowerShell error mojibake | Focused encoding regression and readable detail; failure detection/rollback already works |
| Optional distribution | Broader installation/package coverage | Browser/shortcut auto-launch, port conflicts, portable migration, clean-tag multi-platform packaging and downloaded unsigned behavior; see [release guide](releases/v0.4.0.md) |
| Outside current scope | Worker, approvals, write-back, real-user Provider quality, multi-instance authority | New product scope and independent evidence; do not enable incidentally |

Documentation updates do not require rebuilding. [Development](development.md)
defines changed-area checks. Historical Phase/R5/R6 records preserve dated proof,
not an instruction to repeat completed tasks.
