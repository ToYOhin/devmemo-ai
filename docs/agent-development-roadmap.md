# DevMemo Agent Development Roadmap

> Status date: 2026-08-03
>
> Product direction: a local-first, permission-aware RAG Agent for developer
> memory.
>
> Current delivery state: A0-A3, the A4 lifecycle design, R1/A4-I1 pure
> lifecycle contracts, the SQLite-only A4-I2 source-outbox transaction proof,
> the dormant A4-I3 derived-ledger/fake-vector recovery proof, A4-I4
> authenticated transport contracts, and the A4-I5 synthetic disposable
> lifecycle integration proof are complete on the Agent feature branch. R4-I1
> adds strict provider-neutral grounded-answer result contracts, and R4-I2
> safely integrates them using synthetic evidence and fake Provider results.
> R4-I3 adds a disposable local Provider compatibility smoke. R5-I1 adds an
> unwired, fake-verified durable authorized-retrieval contract, and R5-I2 adds
> an unwired disposable SQLite repository-adapter parity proof. R5-I3 selects
> authenticated current-authority Memos rehydration and request-memory-only
> content retention through a pure design contract and synthetic fixture.
> R5-I4 adds an unwired in-process proof for domain-separated request/response
> HMAC, freshness, exact parsing, and bounded process-local replay. R5-I5 adds
> unwired Go/Python canonical and exact-payload parity against the shared fixture.
> R5-I6 adds the unwired pure Go current-authority reader contract and in-memory
> all-or-nothing parity proof. R5-I7 adds the unwired real single-host SQLite
> current-authority reader and temporary-database parity proof. R5-I8 adds the
> unwired process-local authority capability issuer/resolver and bounded registry
> proof. R5-I9 adds the unwired single-host transport composition and dedicated
> process-local request-replay proof. R5-I10 adds an unregistered single-host
> HTTP handler/client contract with strict projection, fixed five-second timeout,
> and recorder/fake-transport proof. R5-I11A adds strict, disabled-by-default
> Go/Python configuration for a dedicated current/previous rehydration keyring
> and one AI-side Memos origin. R5-I11B adds fixed-order matching-key handling
> and opt-in registration on the existing Memos listener. R5-I11C adds the
> AI-side Python HTTP client and deterministic lifespan shutdown. No new
> listener, Agent answer-path wiring, or production-ready durable answer path is
> implemented.

This document is the delivery authority for the Agent product line. The
historical phase log in `docs/roadmap.md` remains useful for the broader DevMemo
AI project, while this roadmap defines what is still required before the Agent
can be presented as a complete, resume-ready project.

## Product contract

DevMemo Agent answers questions from Memos that the current caller is already
allowed to read. It is intentionally a bounded Agent, not a general autonomous
assistant:

- Memos is the sole source of truth for Memo content, identity, lifecycle, and
  visibility.
- The browser communicates only with the same-origin authenticated Memos BFF.
- The Agent has one read-only tool, `search_memos`, and retrieves only complete
  `memo-v1` records that survive the pre-context visibility filter.
- The AI Service may keep only disposable, rebuildable derived state. It must
  not become a second permissions or Memo-content database.
- Answers expose only validated answer text, citations, controlled metadata,
  and content-free trace data.
- Agent enablement, indexing, and any real-data migration remain explicit
  opt-ins with documented rollback paths.

The target portfolio story is therefore specific: **a secure local RAG Agent
with source-owned lifecycle delivery, permission-aware retrieval, grounded
answers, measurable quality, and reproducible recovery**.

## Current strengths

- The Memos BFF owns authentication and resolves visibility before delegation.
- Short-lived HMAC delegation prevents the browser from choosing identity or
  scope.
- The AI Service applies the UID and `memo-v1` filter before assembling model
  context.
- The Agent exposes one bounded tool and a strict response projection.
- The optional local overlay keeps the AI Service off host-published ports and
  leaves the default Compose path disabled.
- A disposable Provider smoke has covered success, empty retrieval, and safe
  Provider failure mapping without persisting real Memo data.
- The A4 design defines a Memos-owned outbox, ordered idempotency, tombstones,
  quarantine, retry, rebuild, observability, and rollback boundaries.

## Gaps that block a complete Agent project

| Priority | Gap | Current impact | Exit criterion |
| --- | --- | --- | --- |
| P0 | Authorized Agent retrieval works only with the in-memory complete-Memo runtime | R5-I11C now provides the opt-in Memos route and owned Python client lifespan, but no capability issuance or durable runtime selection connects them to the answer path; process-local replay/capability state also remains single-instance only | Connect the reviewed single-host durable runtime selection without changing defaults; require shared atomic state before multi-instance use |
| P0 | A4 is not connected to a runtime lifecycle path | Contract, SQLite outbox, derived-ledger recovery, authenticated transport, and disposable integration proofs exist, but no lifecycle route, dispatcher, or production consumer invokes them | Separately review and authorize a single-host runtime route/client/dispatcher; require shared replay storage before any multi-instance claim |
| P1 | AI browser paths are split | Evidence Answer uses the BFF, while legacy Insights and Context Pack still expect direct AI Service access and fail in Agent-overlay mode | Move supported reads through authenticated Memos BFF projections or hide unsupported legacy panels; never publish port 8000 as the fix |
| P1 | Evaluation is synthetic and too small | Retrieval and safety claims are not supported by a representative, repeatable benchmark | Publish a sanitized evaluation set, thresholds, failure categories, and a reproducible report |
| P1 | Observability is request-local | Operators cannot inspect latency, retry backlog, stale/quarantined records, or rebuild progress without risking content exposure | Add content-free metrics and spans with explicit field allowlists and cardinality limits |
| P1 | AI Service boundaries are concentrated in large modules and Python quality gates are limited | Changes to routing, storage, and Agent behavior are harder to review safely | Extract domain/service boundaries as touched and add lint, type, coverage, and focused integration gates |
| P1 | The Agent exists only on a feature branch with no public demonstration | Reviewers cannot reproduce the full product claim from the default branch or a release | Merge through review, publish a tagged release, architecture/threat-model docs, evaluation results, and a short reproducible demo |

## Delivery rules

Every stage below follows the same rules:

1. Implement the smallest contract-first slice and keep safe defaults
   unchanged.
2. Use temporary databases, synthetic records, and disposable vector stores
   until a later stage explicitly authorizes real-data migration.
3. Verify both the success path and the fail-closed path before wiring the next
   runtime layer.
4. Record a rollback procedure and content-free operational evidence.
5. Do not claim completion from unit tests alone when the milestone requires a
   process restart, store rebuild, authenticated browser path, or release.

## Milestones

### R0 — Product baseline and authoritative roadmap

**Outcome:** the repository describes one coherent Agent product, its current
limits, and a reviewable order of delivery.

Acceptance:

- This roadmap and the Agent architecture contract agree on authority,
  persistence, retrieval, and safe-output boundaries.
- Historical project phases remain intact; Agent completion is not implied by
  the completed A0-A4 design record.
- The next implementation slice is narrow enough to run without a database,
  network, Provider, or real Memo.

Rollback: documentation-only; revert the roadmap links if the product direction
changes.

### R1 — Pure lifecycle contracts (A4-I1)

**Status:** implemented and unit-verified without runtime wiring.

**Outcome:** executable domain rules exist before storage or transport is
introduced.

Scope:

- Provider-neutral event and acknowledgement types for
  `memo.index.requested.v1`, `memo.reindex.requested.v1`, and
  `memo.delete.requested.v1`.
- Strict validation of event identity, `source_sequence`, `memo-v1`, operation,
  reason, timestamps, and index/reindex document requirements.
- A pure transition function covering new, duplicate, stale, same-sequence
  conflict, interrupted applying/failed retry, higher-sequence supersession,
  delete tombstone, and retrieval quarantine.
- A safe acknowledgement/error projection that cannot contain raw Memo text,
  document hash, prompt, context, embedding, identity, visibility, or secret.

Acceptance:

- Table-driven unit tests cover every transition and invalid input class.
- Identical replay is idempotent; same-sequence mismatch is quarantined; stale
  events cannot revive an older vector; accepted unfinished changes are not
  retrievable.
- Tests require no route, database, network, vector adapter, or real data.

Rollback: remove the isolated domain module and tests; no runtime or stored
state is affected.

### R2 — Reliable source outbox and derived-state ledger (A4-I2/I3/I4)

**Status:** A4-I2 has an SQLite schema, explicit dormant adapter, and temporary-
database transaction proof. A4-I3 adds a separately constructed AI SQLite
ledger and an unwired processor/fake-vector test boundary that prove durable
reservation, duplicate/stale/conflict decisions, two crash-replay points,
idempotent tombstone deletion, safe failure codes, and retrieval quarantine.
A4-I4 adds a lifecycle-only HMAC purpose/path/header set, timestamp/nonce/body-
digest binding, a bounded process-local replay store, exact event/acknowledgement
parsers, safe error mapping, a Go signer/ack parser, and an in-process Python
client/handler contract. Existing Memo CRUD and AI routes call none of these.
MySQL/PostgreSQL adapters, a lifecycle route/dispatcher, and runtime wiring are
not started.

**Outcome:** source changes and derived-index intent cannot silently diverge.

Scope:

- A Memos-owned outbox written in the same database transaction as the source
  lifecycle change.
- Monotonic per-Memo `source_sequence`, delete tombstones, bounded explicit
  retry, acknowledgement, and audited retention.
- An AI-side derived-state ledger that reserves a transition before vector
  mutation and stores no raw Memo snapshot.
- A separately authenticated lifecycle transport; it must not reuse browser
  authority or broaden the existing answer delegation.

Acceptance:

- Temporary-database tests prove source mutation/outbox atomicity and rollback.
- Consumer tests prove duplicate delivery, reordering, crash-after-reservation,
  crash-after-vector-write, retry, supersession, and delete convergence.
- Failed or unfinished accepted events quarantine the affected record from
  retrieval.
- Logs, acknowledgements, metrics, and error summaries pass redaction tests.

Rollback: disable lifecycle dispatch, stop consumption, discard derived ledger
and vectors, then rebuild from Memos after the implementation is corrected.
No real-data wiring is authorized by this milestone alone.

### R3 — Disposable end-to-end lifecycle and recovery proof

**Status:** implemented and test-verified by A4-I5 without runtime wiring.

**Outcome:** durable local RAG behavior is demonstrated without touching a
user's real Memos or volumes.

Scope:

- Compose or process-level tests using synthetic Memos, temporary databases,
  and disposable vector collections.
- Create, update, archive/ineligible transition, delete, restart, retry, and
  full rebuild-generation scenarios.
- Reconciliation checks between Memos high-water marks, ledger state, and
  vector counts.

Acceptance:

- Restart does not lose acknowledged index state.
- Update replaces rather than duplicates evidence; delete becomes
  non-retrievable before acknowledgement; rebuild swaps generations only after
  validation.
- A forced Provider/store outage produces bounded retries and recoverable
  status without leaking payloads.
- The entire proof can be destroyed and rerun from documented commands.

Rollback: stop the disposable stack and delete only its pre-identified
temporary databases and vector collections.

### R4 — Grounded Provider answers

**Status:** R4-I1 strict parsing and R4-I2 safe runtime integration are complete.
Authorized Provider context uses opaque evidence references; validated answers
resolve only to server-owned citations. Empty retrieval and deterministic output
remain unchanged. R4-I3 verified exact output, fail-closed malformed output,
empty-retrieval skipping, and bounded endpoint failure with synthetic evidence
and a disposable local Provider. This remains a single-model compatibility
proof, not a quality benchmark.

**Outcome:** configured Providers can produce useful answers without weakening
the safe response boundary.

Scope:

- A versioned structured answer schema with bounded text and citation IDs.
- Validation that every citation maps to the authorized retrieved set and that
  no Provider-supplied metadata bypasses server-owned citation projection.
- Deterministic handling for empty context, malformed output, unknown
  citations, Provider timeout/failure, and suspected context echo.
- Prompt-injection and hostile-Memo fixtures that try to override tools,
  identity, visibility, output fields, and system instructions.

Acceptance:

- Provider text is returned only after schema, length, citation, and redaction
  validation.
- Unknown citations, raw context echoes, and extra fields fail closed.
- Empty retrieval never calls the Provider; safe 502/503 mappings remain.
- Deterministic tests plus one disposable local Provider smoke cover success
  and each failure class.

Rollback: select the deterministic finalizer or disable the Agent; no source
data change is required.

### R5 — Durable authorized retrieval and product-path unification

**Status:** R5-I1 is implemented and fake-verified. R5-I2 binds that protocol to
an explicitly disposable SQLite adapter and proves reopen parity, UID/limit
pushdown plus service-side re-intersection, consistent candidate/ledger reads,
snapshot invalidation between phases, lifecycle rejection before document
loading, duplicate/inconsistent-row rejection, and fixed failure mapping. The
adapter stores only synthetic `tmp_path` data and is not a production content-
persistence design. Existing `EvidenceAnswerAgent`, `RetrievalService`,
VectorStore construction, Memo CRUD, and lifecycle runtime paths do not import
or call it. R5-I3 selects Memos current-authority, all-or-nothing rehydration
with request-memory-only content retention; it rejects persistent AI-side
complete-Memo content and persistent hybrid caching for the durable Agent path.
Its exact contract and synthetic fixture bind selection sequence/hash/version
to the derived snapshot token and a request-local opaque Memos authority
reference, then fail closed on authority or revision changes.
R5-I4 adds a distinct request and response HMAC contract, strict timestamps,
body digests, exact parsing, a single-call in-process authority handler, fixed
signed failures, and bounded process-local request/client replay stores. The
shared fixture and pure tests cover tampering, replay, timeout, partial output,
and selection mismatch. No HTTP adapter, route, repository, runtime secret, or
real data is added; HMAC is not claimed as cross-host confidentiality.
R5-I5 adds a Go verifier for that exact request and a response signer/parser
that matches the shared Python fixture byte-for-byte. It rechecks all bounded
request and response fields, rejects duplicate or invalid nested JSON, and
projects every failure as `authorized_retrieval_unavailable`. It deliberately
adds no Go replay store, authority lookup, route/client, runtime configuration,
network, persistence, or real data.
R5-I6 adds a pure Go current-authority reader protocol. It accepts only the
verified request and an opaque Memos-internal authenticated-context binding,
then requires one atomic snapshot to re-confirm exact UID correspondence,
current visibility, complete/normal/current state, sequence, hash, `memo-v1`,
snapshot revision, and authority token. An in-memory fake proves request-owned
selection ordering, exact R5-I3 response projection, and all-or-nothing failure
for update/delete, partial, duplicate, stale, mixed-snapshot, and adapter errors.
No real Store, visibility resolver, HTTP, HMAC/replay wiring, runtime config,
persistence, network, or real data is added.
R5-I7 binds that protocol to the real single-host SQLite Store boundary without
registering a route or runtime. Caller identity comes only from Memos' internal
authentication context; the reader rechecks the normal caller row and uses the
same visibility scope as `ListMemos`. A bounded UID CTE reads normal, noncomment,
nonblank Memos and each Memo's latest A4 source event in one read-only snapshot.
Only a current `memo-v1` upsert whose source document equals current Memos content
is returned; R5-I6 then rechecks sequence, hash, version, UID correspondence, and
response order. SQLite `data_version` brackets the transaction, so any concurrent
commit during the read rejects the whole result. Temporary SQLite tests cover
visibility parity, update/delete/visibility races, lifecycle/source mismatch,
schema/transaction failure, and content-free errors. This is SQLite-only parity,
not MySQL/PostgreSQL, HTTP, real-data, or multi-instance proof.
R5-I8 adds an unwired process-local issuer/resolver. Issuance derives caller
identity only from Memos authentication context and accepts no caller-controlled
scope; an injected Memos-owned source must return the same current caller and a
unique, nonempty, R5-I1-matching scope of at most 1,000 complete-Memo UIDs. A
constructor-fixed capacity and TTL of at most 60 seconds bound the no-timer
registry. Three independently sourced opaque tokens bind one private entry;
only the authority reference is intended for a later signed request. Consume
atomically checks the private token indexes and a unique one-to-ten-item request
subset, deletes the entry, and returns only a Memos-private auth context, exact
original UID scope, unchanged R5-I6 binding, and authority token. Synthetic
tests cover expiry, capacity, collision, mismatch, restart invalidation, fixed
failure projection, and one-success concurrent consume. No HTTP, replay-store
reuse, runtime configuration, persistence, database, network, or real data is
added; multi-instance use still requires encrypted transport and shared atomic
capability/replay storage.
R5-I9 adds an unwired pure Go composition. It explicitly injects the scoped
secret, bounded request age, clock, a dedicated fixed-capacity request replay
store, the R5-I8 registry, and a reader factory. R5-I5 verification precedes
nonce consumption; nonce consumption precedes capability resolution; the
private caller/scope/binding/token resolution is revalidated before a fresh
server auth context reaches the one-call reader factory and R5-I6 projection.
Verified downstream failures become only an exact R5-I5-signed 503; unverified
requests and signing failures return no response projection and the same fixed
local error. The request replay and capability stores remain independent and
process-local, the future client timeout remains five seconds, and automatic
retry remains disabled. Synthetic tests cover exact signed success, verification
order, nonce and capability single-use, UID scope, binding/token mismatch,
reader one-call, fixed signed failure, concurrent duplicate handling, and
new-store invalidation. No HTTP route/client, runtime secret source, timer,
configuration, persistence, database/network access, or real data is added.
R5-I10 adds an unregistered standard-library HTTP adapter around that
composition. Its handler accepts only the exact internal POST path, one value
for each HMAC request header, exact JSON content type, a known non-chunked body
up to 32 KiB, one JSON value, and a successfully closed body. Pre-verification
rejection is a bodyless unsigned non-cacheable 404; verified results map only
exact signed 200/503 status, body, and response headers. The client uses only a
constructor-injected base URL, scoped secret, clock, and RoundTripper, fixes a
five-second timeout, disables redirects and retry, closes a bounded response,
and authenticates freshness, nonce, snapshot token, status, and body before
exact parsing. Client replay remains the AI R5-I4 boundary. Recorder, in-memory
handler, and fake-transport tests add no registration, listener, environment or
config field, runtime secret lifecycle, real socket, Store access, or real data.
R5-I11A adds matching disabled-by-default Go/Python configuration contracts.
Opt-in requires the primary Agent flag, a canonical unpadded base64url 32-byte
current secret, an optional distinct previous secret, strict separation from
the answer-delegation secret, and one credential-free HTTP(S) Memos origin on
the AI side. Disabled settings retain no supplied secret or URL. The deployment
boundary injects values into each process; neither service creates, distributes,
persists, logs, or projects them. The startup-fixed two-key contract adds no
route/client, timer, dynamic reload, real secret, network, or data.
R5-I11B constructs current and optional previous compositions over the same
process-local capability registry and request replay store. The HTTP handler
tries current then previous and signs verified success/failure only with the
matching request key. Explicit opt-in registers the exact internal POST on the
existing Memos Echo server; disabled startup adds no route. The runtime creates
no listener, port, goroutine, timer, transport, closeable resource, or shutdown
hook, and registration performs no Store read.
R5-I11C adds an async Python client created only by the enabled FastAPI lifespan.
It receives an injected zero-retry transport, fixes a five-second timeout,
disables redirects, performs one exact signed POST, closes a bounded streamed
response, verifies exact signed 200/503 before parsing, and owns one process-
local response replay store. Shutdown closes the owned client/transport and
clears `app.state`; disabled mode creates none. No endpoint or answer Agent uses
the client yet.

**Outcome:** the same permission boundary works with durable retrieval and the
browser has one supported AI access pattern.

Scope:

- Connect `search_memos` to the reviewed durable complete-Memo index only after
  R2-R4 pass.
- Preserve Memos visibility resolution and the AI pre-context `memo-v1` filter
  for every store adapter.
- Re-confirm current visibility and complete-Memo eligibility in Memos before
  an all-or-nothing rehydration response; retain returned content only in
  request memory and recheck the derived snapshot before materialization.
- Route supported legacy AI reads through authenticated Memos BFF contracts, or
  hide panels that are unavailable in Agent mode.
- Add an explicit, backed-up, opt-in migration/runbook before any real Memo
  derived state is written.

Acceptance:

- Cross-user and private/public visibility tests show zero unauthorized
  citations and zero unauthorized context assembly.
- No browser request targets the AI Service and no AI host port is published.
- Store parity tests produce equivalent authorized results for memory and the
  selected durable adapter within documented tolerances.
- A real-data opt-in requires separate authorization, backup verification, dry
  run, rollback command, and post-run reconciliation.

Rollback: disable durable retrieval, revert to the disabled/deterministic path,
discard rebuildable derived state, and retain Memos unchanged.

### R6 — Evaluation, observability, engineering gates, and release

**Outcome:** quality, security, and operability claims are measurable and the
project is independently reproducible.

Scope:

- A sanitized 50-100 question corpus covering lookup, synthesis, no-answer,
  conflicting evidence, visibility boundaries, deletion, stale state, and
  prompt injection.
- Retrieval metrics such as Recall@5 and MRR, plus citation precision,
  groundedness/faithfulness, refusal accuracy, scope-leak count, latency, and
  Provider/token cost where applicable.
- Content-free traces and metrics for request outcome, tool latency, Provider
  latency, outbox lag, retry counts, quarantine counts, rebuild generation, and
  reconciliation status.
- Python lint/type/coverage gates, focused Go/Web checks, disposable lifecycle
  integration tests, and authenticated browser verification.
- Public-facing README material, architecture and threat-model diagrams,
  benchmark method/results, a short demo, and a tagged release from reviewed
  default-branch code.

Acceptance:

- Thresholds are versioned before benchmark execution; failures are published,
  not hidden by aggregate scores.
- Observability uses allowlisted low-cardinality metadata and never records Memo
  text, query text, prompt, context, embedding, secret, identity mapping, or
  full trace payload.
- CI reproduces unit, integration, security, and build checks from a clean
  checkout.
- The release runbook proves install, opt-in enablement, one cited answer,
  update/delete convergence, restart recovery, disablement, and cleanup.

Rollback: disable the Agent and lifecycle dispatcher, preserve Memos, remove
only derived collections/ledgers according to the release runbook, and rebuild
after correction.

## Resume-ready definition of done

The project should be described as a completed Agent project only when all of
the following are evidenced from reviewed code:

- A real local Provider returns a schema-validated grounded answer whose
  citations all belong to the caller-visible evidence set.
- Source-owned create/update/delete events converge idempotently through
  restart, retry, and full rebuild without stale retrieval.
- Security tests cover visibility isolation, forged delegation, prompt
  injection, context echo, unknown citations, deletion, and log/trace
  redaction.
- A versioned evaluation report includes the dataset method, thresholds,
  retrieval/answer/safety metrics, latency, limitations, and failed cases.
- A new reviewer can start the project, run the disposable proof, use the
  authenticated browser flow, and clean it up from documented commands.
- The implementation is present on the default branch or a tagged release;
  README claims match that released state.

Until these gates pass, accurate wording is **"implemented secure Agent
boundary with a designed local RAG lifecycle"**, not **"production-ready
autonomous Agent"**.

## Deferred ideas

The following are intentionally deferred because they add breadth before the
single-Agent read path is reliable:

- MCP, multi-Agent orchestration, browser automation, web search, write tools,
  autonomous background jobs, and persistent Agent memory;
- chunk-based or public Qdrant Agent retrieval;
- remote/multi-tenant deployment and a general plugin framework;
- model routing, self-reflection loops, and unbounded tool planning.

They may be reconsidered only after R6 and with a new threat model, data-flow
review, and explicit authorization.

## Next authorization gate

R5-I11C has completed the Python HTTP client/replay lifespan and deterministic
transport shutdown while remaining disconnected from `EvidenceAnswerAgent` and
all endpoints. The next narrow R5 gate is single-host durable runtime selection:
issue the Memos-owned capability from the authenticated answer path, call the
owned Python client only for the reviewed durable adapter, and retain existing
memory/default behavior. It must be separately verified without Compose defaults,
real data, or multi-instance claims. Real browser/Docker acceptance remains a
later explicit runtime authorization gate after this answer path is connected.
Docker/browser proof remains later; encrypted transport and shared atomic
replay/capability storage remain mandatory before multi-instance use.
