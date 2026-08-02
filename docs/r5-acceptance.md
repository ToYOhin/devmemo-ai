# R5 Acceptance Record

R5 code paths and the disposable synthetic product proof are complete. Real
single-host runtime acceptance is not complete: lifecycle dispatch and rebuild
generation activation are not connected, and Docker, authenticated browser,
live Qdrant/Memos, restart, and real-data operations require separate approval.

## Evidence matrix

| Requirement | Status | Direct evidence and limit |
| --- | --- | --- |
| Unauthorized context and citations remain zero | Verified (synthetic) | Go BFF/current-authority tests cover caller-owned private, other-user public, and other-user private Memos. Python durable retrieval tests intersect visibility before materialization and reject leaked candidates. No real multi-user browser run is claimed. |
| The supported Agent browser path uses only the same-origin Memos BFF | Verified (source and component tests) | The Web client posts only to `/api/ai/agent/answer`. The Agent Compose overlay removes the AI Service host port. Legacy panels are hidden when their separate `VITE_AI_SERVICE_URL` opt-in is absent. Web tests pass, but no headed browser was run for this R5 slice. |
| Memory and durable retrieval are equivalent within documented tolerance | Verified (synthetic) | The disposable product test proves the same answer state, retrieved count, Memo UID set, and `memo-v1` citation version. Adapter-specific embedding IDs, scores, titles, and tags are intentionally excluded from parity because durable citations do not trust vector or rehydration metadata. |
| Durable failures never fall back to legacy/raw-content retrieval | Verified (synthetic) | Agent and internal-route tests cover missing ownership and durable failure as the existing safe 503, with no memory or Provider call. Empty durable evidence remains no-context. |
| Disabled/default behavior and rollback remain safe | Verified (source and tests) | Rehydration is disabled by default. Disabled lifespan constructs no durable objects, the endpoint ignores durable state, and memory retrieval remains selected. Rollback is to disable rehydration/Agent and retain Memos. Runtime rollback has not been executed. |
| Lifecycle dispatch, rebuild activation, and restart reconciliation are operational | Contradicted by current source | `MemoLifecycleProcessor` and generation activation are used only by tests; there is no production dispatcher or rebuild activation entry point. A newly enabled real runtime therefore has no reviewed path to populate and activate its derived generation. |
| Live Qdrant/Memos and authenticated browser behavior are proven | Blocked by authorization | Current work forbids Docker, network, Qdrant, accounts, Memos, volumes, secrets, and browser actions. Synthetic tests cannot replace this evidence. |
| Real-data opt-in is safe to execute | Unverified | A real-data run requires explicit authorization, verified backups, a dry run, exact rollback targets, and post-run reconciliation. None was executed. |

## Verified local gates

- Python targeted R5/A4/R4 regression: 404 passed, with one existing TestClient
  deprecation warning.
- Go Agent/BFF/SQLite packages: targeted tests and `go vet` passed.
- Web suite: 153 tests passed; the Evidence Answer API/component tests assert the
  same-origin BFF path and delayed user-triggered request.
- Python compile sanity, diff checks, and credential/local-path/source-wiring
  scans passed.

These checks prove code and synthetic integration behavior only. They do not
prove a running container topology, browser authentication, real persistence,
or restart convergence.

## Safe rollback

1. Set `AI_AGENT_REHYDRATION_ENABLED=false` and restart the disposable stack.
2. If the complete Agent path must be disabled, also set
   `AI_AGENT_ENABLED=false`.
3. Keep Memos and its source database unchanged.
4. Delete only pre-identified rebuildable AI ledger/vector state after backup
   verification; never delete a broad or unresolved volume/path.
5. Re-enable only after a clean rebuild and reconciliation against Memos.

## Authorization required for real runtime acceptance

Approval must explicitly cover a disposable Compose topology, temporary
credentials and secrets, temporary accounts, synthetic Memos and visibility,
temporary volumes, local Qdrant, browser automation, restart, and cleanup.
Use the deterministic Provider unless a separate Provider authorization exists.

The authorized run must prove:

1. the browser signs in and calls only the same-origin Memos BFF;
2. an owned private Memo and another user's public Memo may be cited, while
   another user's private Memo never enters context or citations;
3. one answer returns controlled citations with no raw content in browser state;
4. update and delete converge without stale retrieval;
5. restart preserves or safely rebuilds derived state;
6. disabling rehydration returns to the memory/disabled path;
7. cleanup removes only the disposable derived resources and preserves Memos.

Until lifecycle activation exists and this authorized run passes, the accurate
status is: **R5 code and synthetic product path complete; real runtime acceptance
blocked by missing lifecycle wiring and runtime authorization.**
