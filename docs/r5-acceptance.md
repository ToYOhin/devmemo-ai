# R5 Acceptance Record

R5 is complete for the explicitly bounded, default-disabled single-host scope.
The lifecycle dispatcher, rebuild-generation activation, durable retrieval, and
same-origin Agent path are implemented and have passed disposable Docker,
Qdrant, SQLite Memos, and authenticated headed-browser acceptance. This is not
a real-data, multi-instance, cross-host, or external-Provider claim.

## Evidence matrix

| Requirement | Status | Direct evidence and limit |
| --- | --- | --- |
| Unauthorized context and citations remain zero | Verified (runtime and tests) | Two temporary users proved that an owned private Memo is cited, another user's private Memo returns 404 and never appears in citations, and another user's public Memo is visible and cited. Existing Go/Python tests retain the same visibility matrix. |
| The supported Agent browser path uses only the same-origin Memos BFF | Verified (runtime, source, and tests) | Headed-browser network evidence showed `POST /api/ai/agent/answer` returning 200 with the safe projection. The Agent overlay published only Memos port 5230; AI Service and Qdrant remained container-internal. Legacy direct-AI panels still fail closed and are not part of the supported Agent path. |
| Browser Agent responses expose only the controlled projection | Verified (runtime and tests) | The authenticated response contained answer state, bounded citation fields, and execution trace only. It contained no raw Memo body, authority capability, vector metadata, Provider settings, secret, or internal transport data. |
| Memory and durable retrieval are equivalent within documented tolerance | Verified (synthetic and runtime) | Product tests prove answer state, retrieved count, Memo UID set, and `memo-v1` citation version parity. Runtime durable answers returned only current authorized Memo citations. Adapter-specific embedding IDs, scores, titles, and tags remain intentionally outside parity. |
| Durable failures never fall back to legacy/raw-content retrieval | Verified (tests and runtime rollback) | Missing ownership and durable failures remain safe 503 with no legacy fallback. Disabling rehydration while retaining lifecycle Qdrant points also failed safely; restoring the default memory store returned a 200 no-context result with zero citations. |
| Lifecycle dispatch and rebuild activation are operational | Verified (runtime and tests) | Default-disabled Memos mutation hooks delivered authenticated create/update/delete events to the existing AI listener. Startup prepared the authoritative SQLite outbox, replayed current synthetic Memos, and activated the configured generation with 204. |
| Update and delete converge without stale retrieval | Verified (runtime and tests) | An update advanced the lifecycle sequence and replaced the content-free document hash in the current generation. Delete produced an applied tombstone, removed every target generation point, and the deleted Memo did not reappear in a subsequent answer. |
| Restart reconciliation is operational | Verified (runtime) | Qdrant, AI Service, and Memos were restarted serially. Memos replayed the authoritative lifecycle state, activation returned 204, the deleted point remained absent, current points remained present, and the authenticated BFF answer still returned 200. |
| Disabled/default behavior and rollback remain safe | Verified (runtime, source, and tests) | Rehydration and lifecycle remain false by default. The runtime rollback set both false and restored `AI_VECTOR_STORE=memory`; the same authenticated browser received a no-context 200 with zero citations while Memos source data remained intact. Full Agent disable remains available with `AI_AGENT_ENABLED=false`. |
| Disposable cleanup is exact | Verified (runtime) | Both named disposable Compose projects were removed with their exact containers, networks, and four project volumes. Temporary accounts, Memos, secrets, Qdrant data, browser state, build contexts, generated frontend assets, and acceptance image tags were removed. No push, tag, or release occurred. |
| Real-data and multi-instance opt-in are safe to execute | Unverified and out of R5 scope | Real user data, MySQL/PostgreSQL, backup/restore execution, external Providers, shared atomic replay/capability state, cross-host encryption, and multi-instance operation require separate design and authorization. |

## Verified local gates

- Python targeted R5/A4/R4 regression: 417 passed, with one existing TestClient
  deprecation warning.
- Related Go Agent/BFF/SQLite tests and `go vet` passed.
- Web suite: 153 tests passed; the Evidence Answer API/component tests retain
  the same-origin BFF and delayed-request assertions.
- Docker Compose static configuration passed with the Agent and Qdrant
  profiles; runtime topology exposed only Memos port 5230.
- Python compile sanity, formatting, diff checks, source-wiring scans, and
  credential/local-path scans passed.

## Safe rollback

1. Set `AI_AGENT_LIFECYCLE_ENABLED=false` and
   `AI_AGENT_REHYDRATION_ENABLED=false`.
2. Restore `AI_VECTOR_STORE=memory`, or set `AI_AGENT_ENABLED=false` to disable
   the complete Agent path. Do not leave the legacy memory path pointed at
   lifecycle-only Qdrant records and describe the resulting safe 503 as parity.
3. Restart the single-host stack and verify a no-context response or the
   expected disabled response through the Memos BFF.
4. Keep Memos and its source database unchanged.
5. Delete only pre-identified rebuildable AI ledger/vector state after backup
   verification; never delete a broad or unresolved volume or path.
6. Re-enable only after a clean rebuild and reconciliation against Memos.

## Completion boundary

R5 proves a local, single-host, default-disabled Agent architecture with
Memos-owned authorization and lifecycle authority, Qdrant as rebuildable
derived state, deterministic disposable runtime acceptance, safe rollback, and
exact cleanup. The next work may proceed to R6. It must not reinterpret this
record as approval for real data, an external Provider, public AI ports,
multi-instance deployment, or cross-host plaintext transport.
