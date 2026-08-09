# R6 Completion Audit

R6 is merged to the default branch at `b8012ba` and its post-merge required CI
is green. It is still not release-complete: three canary fixes remain on a
local, unpublished candidate branch, and no R6 tag or release artifact exists.
This record separates default-branch evidence, local candidate evidence, and
the authorization gates that remain open.

## Current project shape

- The Go Memos core owns authentication, Memo visibility, source mutations,
  lifecycle outbox state, the same-origin Agent BFF, and the browser-safe
  response projection.
- The FastAPI AI Service owns provider-neutral Agent contracts, deterministic
  and optional Provider/vector adapters, derived SQLite/Qdrant state, durable
  rehydration, fixed refusal, offline evaluation, and bounded content-free
  observations.
- React Evidence Answer calls only the Memos BFF. Legacy
  insight/template/summary panels still use the optional direct AI client and
  remain a separate compatibility decision.
- Cross-language fixtures live in `contracts/`; public design and operations
  evidence lives in `docs/`. Local Agent state, prompts, handoffs, generated
  graphs, and browser artifacts are ignored or stored outside the repository
  and are not release artifacts.

## Verified default-branch evidence

- PR #3 was merged by GitHub rebase to `main` as `b8012ba` on 2026-08-09.
- Required post-merge runs on that exact commit passed: AI Service Tests
  `31290057008`, Backend Tests `31290056997`, Frontend Tests `31290057010`,
  Proto Linter `31290057002`, and CodeQL `31290058919`.
- The strict 64-case synthetic corpus and seven versioned thresholds pass
  through the deterministic retrieval and Agent core. Python, Go, and Web
  parsers agree on answered, no-context, and fixed-refusal projections.
- The Python engineering gate pins hash-locked Ruff 0.16.1, mypy 1.20.2, and
  coverage.py 7.15.3. Its established Windows baseline passes Ruff, mypy over
  64 production files, and 764 tests with 88.6% branch coverage against an
  88.0% fail-under threshold.
- A disposable Windows Docker/Qdrant/authenticated-browser run using only
  synthetic data proved a same-origin cited answer, fixed pre-retrieval
  refusal, explicit disablement, zero AI/Qdrant host ports, and exact cleanup.

## Verified local candidate evidence

The unpublished `codex/r6-canary-demo-fixes` candidate adds three narrow fixes:

1. `80b657b` projects only the browser-safe BFF answer, citation, and bounded
   trace fields instead of forwarding internal response fields.
2. `b0f76d8` extends the fixed pre-retrieval refusal policy to the accepted
   protected-prompt and private-secret synonym families.
3. `5f505b0` makes Memos wait for AI Service health in the Agent Compose overlay
   while keeping AI Service and Qdrant off host-published ports.

On Windows, the candidate passes Ruff, mypy over 64 production files, and 767
tests with 88.6% branch coverage and the 88.0% fail-under threshold. The same
resource-bounded canary browser acceptance proves a safe real BFF response
body, normal cited answer, original and synonym refusal before retrieval,
disablement, Compose readiness, zero AI/Qdrant host ports, and exact cleanup.
These are local candidate facts, not Linux or clean-checkout GitHub CI evidence.

## Remaining problems

- The three canary fixes have not been pushed, reviewed, merged to `main`, or
  verified by clean-checkout Linux CI.
- Legacy insight/template/summary panels are not yet migrated to Memos BFF or
  hidden in Agent-overlay mode.
- The deterministic Provider answer is useful for acceptance but is not a
  polished user-facing synthesis, and refusal currently shares the generic
  empty-result presentation.
- Authoritative oldest-pending outbox lag, cross-process rebuild state, and a
  dedicated reconciliation owner are still missing; these states must not be
  inferred.
- Multi-instance deployment still requires encrypted transport and shared
  atomic replay/capability storage.
- The Docker build context remains larger and more failure-prone than desired;
  startup readiness is fixed, but build-transfer efficiency is separate work.

## Authorization and next stage

1. Separately authorize publishing `codex/r6-canary-demo-fixes`, then verify
   required clean-checkout GitHub CI on the exact remote head.
2. After review, separately authorize merging those fixes to `main` and verify
   post-merge required CI.
3. Separately authorize an R6 tag, release notes, image/artifact, and release
   publication. Passing CI does not authorize release operations.
4. Only after R6 release closure, perform the bilingual R7-I0 definition gate
   before coding: outcome, scope, acceptance, rollback, privacy/data flow,
   approval boundaries, bounded planning, durable run state, recovery, and a
   fixed multi-tool task set.

Real user data, external Providers, public AI ports, and multi-instance use are
not authorized by any of the evidence above.
