# R6 Completion Audit

R6 is implemented through the sanitized evaluation, fixed refusal, and
content-free observability slices and is published on the feature branch with
clean-checkout CI evidence, but it is not release-complete. This record
separates current evidence from gates that still require release authority.

## Current project shape

- The Go Memos core owns authentication, Memo visibility, source mutations,
  lifecycle outbox state, the same-origin Agent BFF, and the safe response
  projection.
- The FastAPI AI Service owns provider-neutral Agent contracts, deterministic
  and optional Provider/vector adapters, derived SQLite/Qdrant state, durable
  rehydration, the fixed refusal policy, offline evaluation, and bounded
  in-memory observations.
- The React Web feature calls the Memos BFF for Evidence Answer. Legacy
  insight/template/summary panels still use the optional direct AI client and
  remain a separate compatibility decision.
- Cross-language fixtures live in `contracts/`; public design and operations
  evidence lives in `docs/`. Local Agent status, prompts, handoffs, and generated
  architecture graphs are ignored and are not release artifacts.

## Verified evidence

- The strict 64-case synthetic corpus and seven versioned thresholds run through
  the real deterministic in-memory retrieval and Agent core. All cases and
  thresholds pass after the fixed pre-retrieval refusal contract.
- Python, Go, and Web exact parsers agree on answered, no-context, and fixed
  refusal projections; unknown or mixed trace shapes fail closed.
- AI answer count/outcome, retrieval latency/outcome, and configured Provider
  latency/outcome are emitted only under existing Agent ownership. Go lifecycle
  outcome/retry/quarantine samples derive only from persisted outbox transitions.
- Focused Python, Go, Web, TypeScript, formatting, content-leak, credential, and
  local-path checks pass for the changed slices.
- The Python engineering gate is pinned with hash-locked Ruff 0.16.1, mypy
  1.20.2, and coverage.py 7.15.3. On Windows, Ruff passes the explicit AI
  source/test scope, mypy passes 64 production source files, and all 764 tests
  pass with 88.6% branch coverage against an 88.0% fail-under baseline.
- A disposable Windows Docker/Qdrant/headed-browser run against the current
  checkout used one synthetic account and Memo with the deterministic Provider.
  It proved one same-origin cited answer, the fixed pre-retrieval refusal with
  no citations, explicit disabled-state UI, zero AI/Qdrant host ports, and exact
  cleanup of containers, network, volumes, acceptance images, browser state,
  temporary build context, credentials, data, and the Memos host listener.
  Qdrant telemetry was disabled before the accepted run. The same browser run
  reconfirmed that legacy direct-AI panels still fail while port 8000 remains
  intentionally unpublished.
- Draft PR #3 at feature-branch head `30a275d` passes clean-checkout GitHub CI:
  AI Service Tests run `30908048004`, Backend Tests run `30908048498`, Frontend
  Tests run `30908047993`, Proto Linter run `30908048511`, and CodeQL run
  `30908042878`. This is feature-branch/PR evidence, not default-branch release
  evidence.

## Not yet complete

1. **Release gate:** no reviewed default-branch merge, R6 tag, release notes,
   image, or release artifact exists. README must not claim a released R6 state.

## Authorization sequence

After review, separately authorize merge/default-branch publication, tag, and
release. Passing PR CI does not authorize any of those actions.

R7 must not be invented or implemented while these R6 gates remain open. Once
R6 closes, define R7 outcome, scope, acceptance, rollback, privacy/data-flow
impact, and authorization gates in both roadmap languages before coding.

Outbox lag remains blocked on an authoritative oldest-pending query. Rebuild
observability remains blocked on a reviewed cross-process state authority, and
reconciliation remains blocked until it has a dedicated owner. These metrics
must not be inferred to make R6 appear complete.
