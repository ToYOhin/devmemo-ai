# R6 Completion Audit

R6 is release-complete. Pull request #6 merged the canary acceptance fixes to
`main`; pull request #7 closed the release metadata; annotated tag `v0.2.0`
resolves to exact default-branch commit
`eddaa602537cda1adc27c0cd1d8c58b40c8e503b`. This record keeps release,
clean-checkout CI, local Windows validation, and synthetic canary evidence as
separate evidence lanes.

## Current project shape

- The Go Memos core owns authentication, Memo visibility, source mutations,
  lifecycle outbox state, the same-origin Agent BFF, current-authority
  rehydration, and the browser-safe response projection.
- The FastAPI AI Service owns provider-neutral Agent contracts, deterministic
  and optional Provider/vector adapters, derived SQLite/Qdrant state, fixed
  refusal, offline evaluation, and bounded content-free observations.
- React Evidence Answer calls only the Memos BFF. Legacy
  insight/template/summary panels still use the optional direct AI client and
  remain a separate product-hardening decision.
- Cross-language fixtures live in `contracts/`; public design and operations
  evidence lives in `docs/`. Local coordination state, handoffs, generated
  graphs, and browser artifacts are ignored or stored outside the repository
  and are not release artifacts.

## Verified release evidence

- Pull request #6 exact head
  `bc84b244ec6cbd3186471c08fa4b0c05e832db6f` passed clean-checkout AI Service
  Tests `31310964079`, Backend Tests `31310964022`, Frontend Tests
  `31310964015`, Proto Linter `31310964026`, and its required CodeQL checks.
- Pull request #6 merged to `main` as
  `0f6a1ecf32068a3ef3a429c25d6c0e7c7b5eff41`; its exact post-merge AI
  Service, Backend, Frontend, Proto, and CodeQL contexts passed.
- Pull request #7 exact head
  `a60932a6226bc17a77cd410138a2c481ad2ab900` merged to `main` as
  `eddaa602537cda1adc27c0cd1d8c58b40c8e503b`.
- Annotated tag `v0.2.0` peels to `eddaa602`; Release run `31357981476`
  succeeded, and the published GitHub Release contains checksums plus Windows,
  Linux, and macOS archives.
- The strict 64-case synthetic corpus and seven versioned thresholds pass
  through the deterministic retrieval and Agent core. Python, Go, and Web
  parsers agree on answered, no-context, and fixed-refusal projections.
- The release candidate passed Ruff, mypy over 64 production files, and 767
  Windows tests with 88.6% branch coverage against an 88.0% fail-under floor.

## Synthetic canary boundary

A disposable Windows Docker/Qdrant/authenticated-browser canary using only
synthetic data proved a same-origin cited answer, original and synonym
pre-retrieval refusals, browser-safe BFF projection, explicit disablement,
health-ordered Compose startup, zero AI/Qdrant host ports, and exact cleanup.
This remains pre-release synthetic acceptance evidence. It is not real-user
data, an external-Provider result, a published-image proof, or a post-release
browser run.

## Remaining problems

- Legacy insight/template/summary panels are not yet migrated to Memos BFF or
  hidden in Agent-overlay mode.
- The deterministic Provider answer is useful for acceptance but is not a
  polished user-facing synthesis, and refusal still shares generic empty-result
  presentation.
- Authoritative oldest-pending outbox lag, cross-process rebuild state, and a
  dedicated reconciliation owner are still missing; these states must not be
  inferred.
- Multi-instance deployment still requires encrypted transport and shared
  atomic replay/capability storage.
- The Docker build context remains larger and more failure-prone than desired;
  startup readiness is fixed, but build-transfer efficiency is separate work.

## Next stage

R6 publication is closed. Before any R7 implementation, complete the bilingual
R7-I0 definition gate for outcome, scope, non-goals, threat model, acceptance,
rollback, privacy/data flow, approval boundaries, bounded planning, durable run
state, recovery, and a fixed multi-tool task set.

Legacy direct-AI panel compatibility remains an independent product-hardening
slice: either hide unsupported panels in Agent-overlay mode or move their reads
and review writes behind an authenticated Memos BFF with a strict safe
projection. Do not publish the AI Service host port as a compatibility fix.

R6 evidence does not authorize real user data, external Providers, public AI
ports, background autonomous jobs, or multi-instance use.
