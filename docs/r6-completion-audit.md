# R6 Completion Audit

R6 is locally implemented through the sanitized evaluation, fixed refusal, and
content-free observability slices, but it is not release-complete. This record
separates current evidence from gates that still require external tooling,
runtime authorization, CI publication, or release authority.

## Verified locally

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

## Not yet complete

1. **Python engineering gate:** the repository and current environment provide
   pytest but no ruff, mypy, coverage, or equivalent cached tool. The AI Service
   workflow runs tests only. A pinned dev-tool decision, dependency installation,
   baseline configuration, and locally verified CI commands are still required.
2. **Clean-checkout CI:** the R6 commits are local. GitHub workflows have not run
   against them, so Linux unit/integration/security/build reproducibility is not
   current evidence.
3. **R6 disposable browser proof:** R5 previously proved the lifecycle/browser
   product path, but the new refusal terminal, safe Go projection, and Web render
   have only unit/TestClient evidence. A disposable authenticated browser run
   must verify refusal, normal cited answer, disablement, and exact cleanup.
4. **Release gate:** no reviewed default-branch merge, R6 tag, release notes,
   image, or release artifact exists. README must not claim a released R6 state.

## Authorization sequence

Complete the remaining gates in this order:

1. authorize network-backed installation and lock/update of the selected Python
   lint/type/coverage tools;
2. authorize disposable Docker/Qdrant/temp-account/Memo/volume/secret and
   authenticated browser acceptance for the R6 delta;
3. authorize pushing the feature branch and verifying all required CI checks;
4. after review, separately authorize merge/default-branch publication, tag, and
   release.

Outbox lag remains blocked on an authoritative oldest-pending query. Rebuild
observability remains blocked on a reviewed cross-process state authority, and
reconciliation remains blocked until it has a dedicated owner. These metrics
must not be inferred to make R6 appear complete.
