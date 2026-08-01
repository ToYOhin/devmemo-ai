# Evidence Answer Agent

> Status: the A1 local-first, read-only backend is implemented and locally
> runtime-verified. A2 adds an explicit experimental Web entry, A3 completed a
> controlled local Provider smoke, and A4 now defines the local RAG lifecycle
> contract. A4-I1 implements its pure event, acknowledgement, and state-machine
> rules. A4-I2 adds an SQLite-only dormant source-outbox adapter and temporary-
> database transaction proof. A4-I3 adds a dormant AI derived-ledger adapter and
> fake-vector crash-recovery proof. A4-I4 adds authenticated lifecycle transport
> contracts without a route or dispatcher. A4-I5 adds a synthetic disposable
> outbox-to-ledger integration proof with restart, retry, tombstone,
> reconciliation, and rebuild-generation coverage. The feature remains disabled
> by default. No runtime lifecycle wiring, automatic indexing, remote deployment,
> or general-public availability is delivered.

Delivery order, current gaps, acceptance gates, and the resume-ready definition
of done are maintained in [DevMemo Agent Development Roadmap](agent-development-roadmap.md).
This architecture document remains the authority for security and data-flow
contracts; the roadmap must not relax them.

## Purpose

DevMemo AI proposes a small, inspectable Agent path for answering a developer
question from already indexed Memos. The Agent must first retrieve evidence
through one bounded tool, then produce a cited answer. Its execution trace must
show control flow without exposing the underlying memo content.

This proposal deliberately starts smaller than a general-purpose autonomous
agent. It is designed to preserve the project's local-first, reviewable, and
low-resource defaults.

## Implemented A1 boundary

- The Memos-authenticated BFF at `POST /api/ai/agent/answer` accepts only a
  question and a bounded limit. It never accepts browser-supplied identity,
  visible Memo UIDs, tool selection, prompt overrides, or Memo content.
- Memos resolves the caller's complete-Memo visibility using its existing
  authorization rules, then delegates the UID capability to the AI Service
  using a short-lived HMAC request for a fixed internal path.
- The AI Service verifies that delegation before filtering `memo-v1` retrieval
  results and before assembling any internal context. The sole tool is
  `search_memos`; the safe response projection permits only answer, citations,
  controlled metadata, and a sanitized trace.
- The explicit `docker-compose.agent.yml` local overlay is required to enable
  the feature. It keeps the AI Service off host-published ports. The default
  Compose path remains Agent-disabled.

Targeted Go and AI tests, Compose validation, isolated health checks, and an
authenticated local BFF check have verified this boundary. The latter returned
only a caller-visible citation and a two-step sanitized trace; a known
non-visible Memo was excluded before context assembly. This is local runtime
evidence, not a multi-instance or public-network deployment claim.

## Scope

The first version, `evidence-answer-agent-v1`, has one read-only tool:
`search_memos(question, limit)`.

```text
question
  -> EvidenceAnswerAgent
  -> search_memos
  -> RetrievalService over the complete-Memo index
  -> bounded internal context and sanitized citations
  -> configured LLM provider or deterministic finalizer
  -> answer, citations, and sanitized trace
```

The tool must call the existing `RetrievalService`; it is not a mock or a
separate data store. The Agent is a new API path and must not change the
behaviour or contract of `POST /api/ai/chat`.

## Boundaries

- Memos remains the source of truth for Memos, identities, and permissions.
- The AI Service remains a sidecar for AI-derived state only. The first Agent
  version stores neither sessions nor execution traces.
- Only the complete-Memo `memo-v1` retrieval path is in scope. The Agent does
  not use public chunk retrieval, chunk content, or a new Qdrant path.
- The default is disabled: `AI_AGENT_ENABLED=false`.
- Existing safe defaults remain unchanged: deterministic provider, memory
  vector store, `AI_INDEX_ON_WEBHOOK=false`, `AI_INDEX_MODE=memo`, and
  `AI_PUBLIC_CHUNK_RETRIEVAL=false`.
- The first version has no write tools, background worker, recursive loop,
  MCP integration, browser access, queue, or Agent framework dependency.
- HTTP responses and traces must never expose raw Memo content, webhook
  payloads, embeddings, prompts, secrets, or chunk content.

## Implemented BFF contract

The endpoint and payload below are implemented for the explicit local Agent
mode. The browser reaches Memos only; the AI Service's corresponding endpoint
is internal and accepts a signed delegation request only.

```http
POST /api/ai/agent/answer
```

```json
{
  "question": "Why did the Docker port mapping fail?",
  "limit": 5
}
```

`question` is required. `limit` is constrained to 1–10 and is passed to the
single retrieval tool. The endpoint accepts no arbitrary tool name, URL, prompt
override, raw Memo content, or conversation history.

```json
{
  "answer": "The port mapping was corrected in the Compose configuration [1].",
  "citations": [
    {
      "memo_id": "memo-42",
      "embedding_id": "memo-42",
      "score": 0.9,
      "metadata": {"title": "Docker ports"}
    }
  ],
  "provider": "deterministic",
  "retrieved_count": 1,
  "agent_version": "evidence-answer-agent-v1",
  "trace": {
    "terminal_state": "answered",
    "steps": [
      {"index": 1, "kind": "tool", "name": "search_memos", "status": "completed", "result_count": 1},
      {"index": 2, "kind": "final", "name": "answer_from_evidence", "status": "completed"}
    ]
  }
}
```

The trace contains only sequence, action name, status, and result count. An
empty index terminates with `no_context` after retrieval and must not call the
LLM provider.

## Delivery status

1. **Contract and feature gate — complete.** Strict `AI_AGENT_ENABLED`
   parsing and provider-neutral Agent domain types have serialization tests.
2. **Read-only evidence Agent and authenticated BFF — complete.** The
   `EvidenceAnswerAgent`, signed internal route, Memos BFF, visibility filter,
   and targeted integration tests are in place.
3. **Explicit experimental UI — complete.** The Memo-detail entry is clearly
   labelled and sends no request until the user opens it and submits a question.
   It calls the same-origin Memos BFF with only `question` and `limit`, then
   strictly parses and renders only the safe answer, citations, and sanitized
   step status. It does not expose the AI Service directly or persist a result.
4. **Controlled provider smoke — complete.** A disposable local-only runtime
   verified the existing signed internal path with an opt-in Provider, including
   successful evidence-backed completion, no-context Provider bypass, and the
   safe 502 Provider-failure mapping. It used no host-published AI port, no
   persistent data, and no change to the default Compose configuration.
5. **Local RAG lifecycle contract — design complete.** The Memos-owned event,
   retry, idempotency, rebuild, observability, and rollback rules below are the
   review baseline for later implementation. No runtime wiring or persistent
   real-Memo derived data is authorized by this design slice.
6. **Pure lifecycle contracts — complete.** Provider-neutral event and
   acknowledgement types, immutable replay checks, sequence/idempotency
   decisions, tombstones, and fail-closed retrieval eligibility are covered by
   shared fixtures and pure unit tests. No route, database, transport, vector
   adapter, Compose change, or real data is involved.
7. **Memos-owned outbox transaction proof — complete for SQLite.** A dormant
   schema and explicit adapter allocate Memos source sequences and atomically
   pair synthetic create/update/archive/delete mutations with index/reindex/
   delete events. Temporary-database tests cover commit, rollback, tombstones,
   shared fixtures, incremental migration, and the three-attempt bound. Existing
   Memo CRUD paths do not call the adapter; no transport or automatic indexing
   is enabled, and MySQL/PostgreSQL adapters are not implemented.
8. **AI derived-ledger recovery proof — complete, unwired.** A separately
   constructed SQLite adapter persists only event identity, fingerprint,
   sequence, operation/hash, tombstone, status, bounded error code, and
   last-applied metadata. A fake-vector processor test boundary proves
   reserve-before-mutation, duplicate/stale/conflict handling, both crash replay
   points, stable upsert, idempotent delete, and fail-closed retrieval. No route,
   transport, Provider, Qdrant adapter, worker, default, or real-data path calls it.
9. **Authenticated lifecycle transport contracts — complete, unwired.** A
   lifecycle-only HMAC purpose, fixed path, and distinct headers bind method,
   timestamp, nonce, and exact body digest. Python verifies a bounded replay
   window and exact A4 event/acknowledgement projections; Go produces the same
   fixture signature and strictly parses content-free acknowledgements. An
   in-process client/handler maps authentication, validation, ledger, and vector
   failures without raw details. No HTTP route, client, dispatcher, worker,
   runtime secret/configuration, default, or real-data path is added.
10. **Synthetic disposable lifecycle integration proof — complete, test-only.**
   A process-local harness uses the real SQLite outbox migration, synthetic
   source mutations, temporary AI ledger/vector databases, lifecycle-only HMAC,
   and a fake stable vector writer. Tests cover ordered create/update/archive/
   delete convergence, four interruption points, retry/exhaustion, stale
   resurrection protection, content-free reconciliation, and rebuild-generation
   validation. No route, dispatcher, worker, Compose change, Provider/Qdrant
   call, runtime default, or real Memo is involved. The nonce replay store proves
   only a single-process contract; shared multi-instance replay storage remains
   a later runtime gate.

## Acceptance criteria for the first Agent path

- The Agent is disabled by default and has a clear disabled response.
- A TestClient integration test indexes a complete Memo through
  `POST /api/ai/embed`, calls the Agent endpoint, and observes a completed
  `search_memos` trace step, a citation, and a cited deterministic answer.
- Empty retrieval does not call the provider.
- Retrieval failures return 503 and provider failures return 502 without
  exposing prompts, context, raw exception data, or content.
- Citations and traces do not contain a `content` field.
- Existing chat tests remain unchanged and pass.
- The explicit Web entry remains opt-in: it sends no request before an open and
  submit action, calls the same-origin Memos BFF only, and renders a reduced
  answer, citation, and trace projection.

## A4 local RAG lifecycle contract

This section is an implementation contract, not an enabled feature. The current
generic Memos Webhook path is not the A4 transport: its Memos-side dispatch uses
a bounded in-process queue that can drop work, while the existing AI-side
`webhook_events` table proves only receipt at the consumer. It also stores the
received payload for legacy retry. A4 requires Memos to own the durable delivery
record and requires the AI lifecycle consumer to persist no raw Memo snapshot.

### Authority and persistence boundary

- Memos owns the canonical Memo, its identity, normal/archived/deleted state,
  comment relationship, and current visibility. A lifecycle event is a command
  to rebuild derived state; it is never a second source of truth.
- Memos writes each lifecycle event to a durable Memos-owned outbox in the same
  database transaction as the source mutation. A delete cannot commit without
  its tombstone event, and an event cannot describe a mutation that rolled back.
  After acknowledgement, an audited retention rule may remove the raw snapshot
  from the outbox while retaining bounded delivery metadata.
- The AI Service may persist only rebuildable state: stable vector IDs and
  vectors, `memo_uid`, `index_version`, the highest accepted and last applied
  source sequences, document hash, operation, rebuild generation, status, and
  bounded timestamps or error summaries. It must not persist the raw Memo
  snapshot, identity, visibility mapping, prompt, context, secret, or Agent
  trace.
- The raw complete-Memo snapshot may exist only in the authenticated internal
  request and process memory long enough to derive the vector. It must not be
  written to the AI lifecycle ledger, logs, metrics, traces, or ops responses.
- The existing answer delegation HMAC, Memos visibility resolver, and
  pre-context `memo-v1` filter remain unchanged. Lifecycle transport
  authentication is a separate implementation gate and must not widen or reuse
  browser authority.

### Versioned event envelope

Memos produces exactly three A4 event types:

| Event type | Meaning | Snapshot |
| --- | --- | --- |
| `memo.index.requested.v1` | First eligible representation | Complete current `memo-v1` document |
| `memo.reindex.requested.v1` | Eligible representation changed or an operator requested repair | Complete current `memo-v1` document |
| `memo.delete.requested.v1` | Memo was deleted or became ineligible | Tombstone only; no content |

Every event contains an opaque immutable `event_id`, `memo_uid`, a
Memos-generated monotonically increasing `source_sequence`, `index_version`
fixed to `memo-v1`, `occurred_at`, and a controlled `reason`. Index/reindex also
contains a complete normalized document and its SHA-256 `document_hash`; delete
contains no document. Visibility and user identity are never event fields.
Unknown event types, fields, index versions, missing hashes, or mismatched hashes
are rejected before embedding.

`source_sequence` is allocated by Memos in the source transaction and is the
ordering token; user-settable timestamps are not revisions. Retries reuse the
same event ID, sequence, and immutable payload. A newly requested reindex always
gets a new event ID and higher sequence, even when its document hash is
unchanged.

Delivery is at-least-once and source-sequenced per Memo. After the Memos
transaction commits, an initial delivery may be attempted without making the
Memo mutation depend on AI availability. Failure leaves the outbox row
retryable. Memos must attempt pending rows in source order, but an older failed
event must not block a newer reindex or delete; the sequence guard makes the
older retry stale after the newer event is accepted. The first implementation
provides only bounded, explicit operator retry: one initial attempt plus at
most two retries. It adds no background worker or automatic indexing default.

### AI consumer state machine and idempotency

The AI consumer compares an event with the persisted highest-accepted and
last-applied state for the same `memo_uid` and `index_version` before using
content:

- a lower sequence is acknowledged as `stale` and cannot change the vector;
- the same applied event ID, sequence, operation, and hash is acknowledged as
  `duplicate`; the same `applying` or `failed` event resumes its idempotent
  operation;
- the same sequence with conflicting identity, operation, or hash is a hard
  contract error and remains retry-visible;
- a higher sequence is first reserved durably as `applying`, immediately making
  every older vector for that Memo ineligible for retrieval; it then applies an
  upsert or idempotent delete, records the last-applied state, and acknowledges
  `applied`;
- an embedding/store or finalization failure is `failed`; it retains the
  accepted sequence for safe retry, does not advance the last-applied sequence,
  keeps older vectors retrieval-ineligible, and never returns raw exception or
  Memo data.

The complete-Memo vector ID remains the stable hash-derived ID already used by
`EmbeddingService`. Repeated upsert replaces that one record; repeated delete is
a successful no-op. The derived ledger reserves the event before vector
mutation and finalizes it afterwards. A crash between those steps safely
repeats the same stable upsert or delete; failure to reserve performs no vector
mutation. Each vector carries the applied source sequence and document hash,
and retrieval accepts it only when both match an `applied` ledger row. A delete
records a derived tombstone sequence even when no vector was present,
preventing an older delayed upsert from resurrecting content.

The internal acknowledgement is a strict projection of `event_id`,
`memo_uid`, `source_sequence`, `index_version`, `status` (`applied`,
`duplicate`, `stale`, or `failed`), `operation`, and an optional bounded error
code. It contains no document, hash, provider output, prompt, context, embedding,
visibility, identity, or secret.

### Default `memo-v1` policy

- One normal, non-comment Memo with non-blank Markdown maps to one complete
  `memo-v1` vector. The stable Memo UID is the identity; no chunk is eligible.
- Create emits index. A change to content or indexed metadata emits reindex.
  Restoring an archived Memo to normal also emits reindex. An explicit repair
  action reads a fresh canonical snapshot from Memos and emits reindex; the
  browser never supplies the snapshot.
- Delete, archive, transition to a comment, or transition to blank content emits
  delete. These rules also remove legacy entries for comments or other
  ineligible records during rebuild.
- Visibility-only changes do not copy visibility into the index and do not
  authorize retrieval. The existing Memos resolver computes the caller's fresh
  normal complete-Memo UID capability on every answer, and the AI Service still
  filters before context assembly.
- `AI_INDEX_ON_WEBHOOK=false`, `AI_INDEX_MODE=memo`, the memory vector store,
  deterministic providers, and `AI_AGENT_ENABLED=false` remain the defaults.

### Rebuild, recovery, and deletion propagation

A single-Memo repair is an explicit reindex event. A full rebuild is an
operator-approved, Memos-driven operation with a unique `rebuild_generation`:

1. keep the Agent disabled or pause answer traffic;
2. capture a Memos outbox high-water sequence and canonical eligible-Memo count;
3. create an empty derived generation and replay fresh `memo-v1` snapshots from
   Memos, never from the old vector store or AI ledger;
4. consume through the captured high-water point, then apply later queued
   events in sequence;
5. compare eligible count, indexed-state count, high-water sequence, and a
   manifest digest derived from Memo UID plus document hash;
6. activate the new generation only when all checks pass, then retain or discard
   the old derived generation according to the reviewed retention policy.

This generation swap removes orphaned vectors without treating a vector-store
scan as authority. A Memos restore is verified first; the AI index is then
discarded and rebuilt from that restored source. Restoring only AI-derived state
must never resurrect a deleted Memo. No real volume deletion or rebuild is part
of A4 design acceptance.

### Observability and operational gates

Memos-owned ops state exposes event ID, type, sequence, status, attempts,
bounded last error, timestamps, pending/failed/exhausted counts, oldest pending
age, and the produced/acknowledged high-water marks. AI-owned ops state exposes
applied/duplicate/stale/failed counts, last applied sequence, index version,
generation, provider/store health, indexed-state/vector counts, and bounded
errors. Both sides correlate by event ID and expose no payload or Memo content.

An index may be called synchronized only when pending, failed, and exhausted
counts are zero; the acknowledged high-water mark reaches the captured source
high-water mark; store health and provider dimension match `memo-v1`; and the
eligible count and manifest digest match. Any failed or exhausted event, a
growing/aged backlog, count or digest mismatch, wrong version/dimension, stale
delete, content-bearing ops output, or citation outside the Memos-provided scope
blocks rollout and raises an operator-visible degraded state.

Rollback first disables `AI_AGENT_ENABLED` and pauses lifecycle delivery; it
does not change Memos data or visibility. Revert the lifecycle consumer or
provider configuration, discard the suspect derived generation, and rebuild
from Memos before re-enabling. A scope leak, stale resurrection, or raw-content
exposure requires immediate disablement and derived-index quarantine. A delete
is recovered only by restoring the authoritative Memo through the normal Memos
backup policy and then reindexing, never by copying content back from AI state.

### Minimum implementation and validation plan

Each later step requires separate authorization before runtime or real-data
effects:

1. **Complete:** provider-neutral event/acknowledgement fixtures and pure
   state-machine tests cover duplicate, stale, conflict, retry, tombstone,
   quarantine, and redaction cases. They add no route, database, transport,
   Compose, or default change.
2. **Complete for SQLite:** a dormant Memos outbox schema and explicit adapter
   use temporary databases to prove create/update/archive/delete atomicity,
   per-Memo ordering, tombstones, bounded attempts, and explicit failure
   recording without a worker. Runtime CRUD integration and other database
   adapters remain separate gates.
3. **Complete:** add an AI derived lifecycle ledger and fake vector-store
   integration tests. They prove stable upsert, idempotent delete, reservation-
   and vector-finalize crash replay, tombstone protection, safe error redaction,
   retrieval quarantine, and no raw snapshot persistence. Runtime construction
   remains a separate gate.
4. **Complete:** add separately authenticated lifecycle transport contract tests.
   They prove exact request/acknowledgement projections, domain-separated HMAC,
   timestamp/nonce/body-digest binding, bounded replay-window enforcement, and
   safe failure mapping without a route, dispatcher, worker, or existing CRUD
   integration. Multi-instance replay storage remains a later runtime gate.
5. **Complete:** a synthetic, disposable process-level integration proof uses
   temporary stores only. It proves ordered outbox-to-ledger convergence,
   backlog/high-water/count/digest projections, four interruption points,
   bounded retry/exhaustion, tombstone protection, and rebuild-generation
   validation. Existing default/port/browser boundaries remain unchanged and
   are rechecked separately; no runtime endpoint is introduced.
6. Only after explicit approval, run an opt-in local migration/rebuild against
   real Memos data with backup, rollback, and post-run deletion verification.

### Chunk and Qdrant gates

A4 does not enable chunk or Qdrant Agent retrieval. That route remains blocked
until the complete-Memo lifecycle has durable Memos-owned delivery, demonstrated
delete/retry/rebuild behavior, scope-safe observability, and a tested rollback;
chunk has a separate version and collection plus stable delete/tombstone rules;
offline evaluation and dual-path migration meet reviewed quality gates; and a
trusted Memos gateway enforces current visibility before context assembly. The
`search_memos` Agent continues to accept only complete `memo-v1` evidence.

## Future work excluded from this proposal

Write tools require separately reviewed authentication and visibility mapping,
explicit user confirmation, idempotency, audit and rollback semantics, rate
limits, and threat modelling. They are not implied by the read-only Agent.
