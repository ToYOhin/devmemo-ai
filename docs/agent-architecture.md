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
> reconciliation, and rebuild-generation coverage. R4-I1 adds a strict
> provider-neutral grounded-answer result contract, and R4-I2 integrates it into
> the non-deterministic answer path using only synthetic evidence and fake
> Provider tests. R4-I3 verifies that path with a disposable local Provider
> smoke. R5-I1 adds an unwired durable authorized-retrieval contract with a
> two-stage, content-free candidate boundary and fake repository proof. R5-I2
> adds an unwired disposable SQLite repository-adapter parity proof with
> reopen and snapshot-consistency coverage. R5-I3 selects current-authority
> Memos rehydration through a provider-neutral, unwired design contract; the AI
> side retains complete content only in request memory. R5-I4 proves the
> domain-separated request/response HMAC, freshness, exact parsing, and bounded
> process-local replay contract entirely in process. R5-I5 proves Go/Python
> canonical and exact-payload parity against the same synthetic fixture. R5-I6
> defines the pure Go current-authority reader boundary and proves its
> all-or-nothing projection with an in-memory fake. The feature remains
> disabled by default. No HTTP rehydration adapter, runtime lifecycle wiring,
> automatic indexing, remote deployment, or general-public availability is
> delivered.

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
11. **Strict grounded-answer result contract — complete.** A standalone
   domain parser accepts only a versioned bounded answer plus opaque
   `evidence-*` references. It rejects malformed/duplicate/extra fields,
   unknown, duplicate, direct, or excessive references, raw-context echoes, and
   Provider-supplied content or metadata. Final citations are mapped only from
   server-owned `AgentCitation` values; validation, timeout, and availability
   failures collapse to fixed content-free codes. R4-I2 now consumes this
   contract only through the guarded integration described below.
12. **Safe grounded-answer runtime integration — complete, fake-verified.**
   Authorized Agent retrieval now gives the Provider only `evidence-*` labels
   and raw authorized evidence, never Memo IDs, scores, or citation metadata.
   Non-deterministic output crosses the answer boundary only after the R4-I1
   parser, context-echo check, and server-owned citation resolution succeed.
   Empty retrieval and deterministic answers are unchanged; malformed output,
   timeout, and failure retain the existing bounded 502 projection. No real
   Provider, lifecycle runtime, Qdrant, Compose default, or real Memo was used.
13. **Disposable grounded-answer Provider smoke — complete.** An ephemeral
   no-volume, no-host-port container used synthetic complete-Memo evidence and
   the existing local Ollama Provider. The first non-exact result failed closed
   with the bounded 502 response; a prompt-only JSON-format clarification then
   produced an exact result whose validated answer and server-owned citation
   were returned. The same run proved empty retrieval made zero Provider calls
   and an unavailable endpoint returned the fixed 502 body. The container was
   removed and no runtime setting, model configuration, or data was persisted.
14. **Durable authorized-retrieval contract — complete, unwired.** R5-I1
   defines a bounded Memos-authority query, content-free candidate/ledger
   snapshot, second-stage complete-Memo materialization, request-local opaque
   evidence references, and a server-owned citation projection. A fake
   repository proves that visibility is intersected before document loading;
   only the current active generation whose `memo-v1` record matches an
   `applied` A4 ledger sequence and hash is eligible. Empty/unknown scope,
   pending/failed/delete state, stale sequence/hash, old or unknown generation,
   missing ledger, chunk version, duplicate/conflicting records, and repository
   failures all fail closed. The proof uses only synthetic in-memory records
   and does not modify the existing Agent or retrieval runtime.
15. **Disposable repository-adapter parity proof — complete, unwired.** R5-I2
   binds the R5-I1 boundary to one explicitly created temporary SQLite store.
   Candidate queries push down the Memos-authorized UID set and limit, while
   the service repeats the visibility intersection before document loading.
   Active generation, content-free candidate data, and A4 ledger state are read
   in one read transaction; a revision-backed opaque snapshot token prevents a
   later document load from mixing store generations. Reopen parity, lifecycle
   rejection, duplicate/inconsistent rows, and fixed repository failure mapping
   use only `tmp_path` and synthetic records. The adapter is test-only and is
   not a production content-persistence or rehydration design.
16. **Production content rehydration design contract — complete, unwired.**
   R5-I3 selects authenticated, current-authority Memos rehydration for the
   durable Agent path instead of persistent AI-side complete-Memo content or a
   persistent hybrid cache. Exact bounded request/response projections bind
   eligible candidate sequence, hash, version, and the R5 snapshot token; any
   update, delete, visibility loss, generation/revision switch, missing item,
   or inconsistent response fails as one content-free error. Complete content
   exists only in authenticated request memory. The shared fixture and pure
   tests add no transport, repository, route, runtime secret, database, or real
   data.
17. **Authenticated content-rehydration transport proof — complete, unwired.**
   R5-I4 binds the exact R5-I3 request to a rehydration-only method/path,
   transport version, timestamp, nonce, and body digest. A separate response
   HMAC binds status, response timestamp, original request nonce, derived
   snapshot token, and body digest before exact parsing. Bounded process-local
   request and response replay stores, a single-call fake authority handler,
   fixed signed failure projection, and a shared synthetic fixture cover
   tampering, expiry, replay, timeout, partial output, and authority mismatch.
   This is integrity/authentication proof only: it adds no HTTP adapter,
   runtime secret, persistence, remote confidentiality claim, or real data.
18. **Cross-language Memos transport parity — complete, unwired.** R5-I5 adds
   a provider-neutral Go verifier for the exact R5-I4 request plus a
   response-only signer/parser. The shared synthetic fixture fixes both HMAC
   canonical forms byte-for-byte; strict nested JSON parsing rejects duplicate,
   unknown, partial, oversized, invalid-UTF-8, identity-bearing, stale, or
   inconsistent payloads with one content-free error. The Go proof adds no
   route/client, replay store, authority lookup, runtime secret/configuration,
   persistence, network, or real data.
19. **Memos current-authority adapter contract — complete, unwired.** R5-I6
   accepts only an already verified `EvidenceRehydrationRequest` and an opaque
   Memos-internal authenticated-context binding. A one-call reader protocol must
   return one atomic snapshot whose authority reference, context binding,
   revision, authority token, current visibility, complete-Memo type, normal
   row state, current lifecycle state, sequence, hash, and `memo-v1` version all
   agree. Pure fake tests prove exact UID correspondence, request-owned
   selection ordering, no identity or visibility projection, and all-or-nothing
   rejection of update/delete, partial, duplicate, stale, mixed-snapshot, and
   adapter failures. No real Store, visibility resolver, route, replay, HMAC,
   runtime configuration, persistence, network, or data is connected.

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

## R4 grounded-answer result contract and integration

R4-I1 is a pure contract, not a runtime behavior change. An untrusted Provider
result contains exactly `version`, bounded `answer`, and one to ten opaque
`citation_refs`. References use server-issued `evidence-*` tokens and never
carry Memo IDs, scores, metadata, content, visibility, identity, prompt,
embedding, secret, or trace fields.

Validation resolves every reference against the already-retrieved server-owned
`AgentCitation` mapping. Unknown, duplicate, direct Memo, or excessive
references fail closed. Explicit protected context fragments are normalized and
checked for verbatim echoes before the answer can be projected. Contract,
timeout, and Provider failures map only to `invalid_grounded_answer`,
`provider_timeout`, or `provider_unavailable`; raw exceptions and Provider text
are not included.

R4-I2 connects this contract only to `EvidenceAnswerAgent`'s non-deterministic
path. Authorized retrieval replaces internal Memo IDs, scores, and metadata in
the Provider context with request-local `evidence-*` labels. The validated
answer may be returned, but each requested reference is resolved back to the
existing server-owned `AgentCitation`; Provider result fields never pass
through. Empty retrieval still skips the Provider, and the deterministic answer
is unchanged. Validation, timeout, and Provider failures continue through the
existing bounded 502 response.

R4-I3 additionally verified this integration with synthetic evidence and the
existing local Ollama Provider in a disposable container. The first response
that did not satisfy the exact JSON contract was rejected without detail. After
only clarifying the prompt's JSON-only format, a rerun returned a validated
answer with one server-owned citation. Empty retrieval made no Provider call,
and an unavailable endpoint retained the fixed 502 response. The smoke used no
volume or host port and left no container behind. This is a single-machine,
single-model compatibility proof, not a quality or production-readiness claim.
The retained content-free command summary is: success `200`, answer length `79`,
one server-owned citation, exact parser passed, opaque reference present,
identity/metadata absent from the prompt, empty retrieval `200` with zero
Provider calls, and unavailable endpoint `502` with the fixed body.

## R5 durable authorized retrieval and current-authority content rehydration

R5-I1 is a provider-neutral, unwired boundary. Its query carries a bounded,
duplicate-free set of complete-Memo UIDs supplied by Memos authority; an empty
set returns an empty result without touching a repository. The repository is
split into two phases: it first returns only ranked record identity,
generation, index version, sequence/hash, and joined A4 ledger state, then it
may load complete synthetic documents only for the records that survived the
Memos UID intersection and every lifecycle check. The service repeats the UID
intersection even when an adapter claims to have applied it.

A candidate is eligible only when its generation equals the current active
generation, its index version is exactly `memo-v1`, and `is_retrieval_eligible`
confirms that its source sequence and document hash match the latest `applied`
upsert with no active tombstone or failure quarantine. Missing, applying,
failed, deleted, stale, old/unknown-generation, chunk, duplicate, or internally
inconsistent derived records cannot cause document loading or context
assembly. Unknown authorized UIDs produce no evidence; malformed or duplicate
query UIDs are rejected by a fixed contract error.

Eligible documents receive request-local `evidence-*` references. Citation
identity is anchored back to the Memos-authority query and constructed by the
service from allowlisted fields, never from Provider output or arbitrary store
metadata. Safe observation exposes only the contract version, result count,
and opaque references. Repository, document,
or consistency failures collapse to `authorized_retrieval_unavailable` and do
not expose Memo text, question context, payload, embedding, identity,
visibility, secret, citation metadata, or raw exception data.

R5-I2 adds one reopenable, disposable SQLite implementation of the repository
protocol. It stores only synthetic proof data in a caller-supplied temporary
file. Candidate reads push down the authorized UID set and requested limit but
remain content-free. The active generation, candidate fields, and joined A4
ledger eligibility inputs are read under one read transaction. The returned
opaque snapshot token binds the subsequent document load to the same store
revision and active generation, so a generation switch or any adapter-owned
write between the two phases fails without returning a partial result.

Tests compare reopened SQLite results with the in-memory fake, including opaque
reference order, context order, and server-owned citations. They also prove
that unauthorized document keys are not loaded; pending, failed, quarantined,
stale, tombstoned, old/unknown-generation, missing-ledger, and chunk rows cause
zero document loads; duplicate or inconsistent candidate/document rows fail as
one fixed `authorized_retrieval_unavailable` result; and open, schema, query,
load, or transaction failures expose no raw details. The temporary schema has
no visibility, final identity, Provider citation metadata, prompt, embedding,
secret, or runtime configuration fields.

This SQLite document table remains a one-time test fixture and is not promoted
to production storage. R5-I3 instead selects **Memos current-authority
rehydration** for the first durable Agent path. Persistent AI-side complete-
Memo content and a persistent hybrid cache are rejected because either would
duplicate content retention, deletion, visibility, backup, and breach-response
obligations. This decision is scoped to the new durable Agent path: legacy
complete-Memo vector metadata described by ADR-017 is unchanged and is not a
production authority for R5.

After R5 selects eligible candidates, the AI side may create one bounded
`memo-evidence-rehydration-v1` request containing only a derived snapshot token
and a request-local opaque `memos_authority_ref` issued by Memos, plus each
server-created selection reference, Memo UID, source sequence, document hash,
and `memo-v1`. The AI side cannot interpret, persist, or log that reference. A
future Memos-owned handler must use a distinct internal path and authentication
purpose, resolve the reference server-side, re-confirm the caller's current visibility
and complete-Memo eligibility, and read all requested documents from one
atomic current-authority snapshot. The response echoes only selection
references plus exact content, sequence/hash/version, the derived snapshot
token, and an opaque Memos authority token. It is all-or-nothing: missing,
archived, comment, blank, deleted, unauthorized, duplicate, stale, or partially
failed items produce no content response.

The AI side must then verify the original authorized query, exact eligible
selection, response mapping, sequence/hash/version, and that the derived
snapshot token is still current before materialization. A concurrent update or
delete observed by Memos changes or removes the response and fails the old
selection; a derived revision or rebuild-generation switch invalidates the
token. Tombstones, pending/failed/conflict quarantine, old generations, and
`memo-chunk-v1` remain ineligible before rehydration. No derived candidate,
ledger, vector payload, browser, Provider, or response metadata can supply
final visibility, identity, content authority, or citation fields. Final
identity remains anchored to the Memos-authority query and citations remain
server-owned.

The authority reference and complete content are retained only for the request
lifetime and must not enter
the AI ledger, vector payload, logs, metrics, traces, backups, or error bodies.
Memos owns content encryption, access control, retention, backup, restore, and
source recovery. AI derived state is excluded from authoritative backup and
may be discarded and rebuilt from Memos; restore requires Memos backup
verification followed by derived reconciliation before activation. Every
contract, authentication, timeout, replay, partial-response, authority, or
adapter failure maps to `authorized_retrieval_unavailable` without raw Memo,
question, context, payload, embedding, identity, visibility, secret, SQL,
endpoint, or exception details.

R5-I4 proves that transport boundary without opening a network connection. The
request canonical form contains the rehydration-only purpose, transport
version, fixed `POST` path, decimal timestamp, nonce, and SHA-256 body digest.
Verification enforces a 60-second window, a 32 KiB request bound, exact JSON
without duplicate keys, and one process-local nonce consumption before the
authority callback. The callback runs at most once and must return the atomic
Memos current-authority snapshot; timeout, authority, or schema failure becomes
only a signed `503` body with `authorized_retrieval_unavailable`.

The response uses a separate response-only HMAC purpose and header namespace.
Its canonical form binds transport version, method/path, response timestamp,
original request nonce, derived snapshot token, status (`200` or `503`), and
the exact body digest. The AI-side parser verifies that signature and freshness
before exact JSON parsing, then rechecks every selection reference,
sequence/hash/version and consumes a separate client-side replay entry. The
contract fixes a five-second future client timeout and no automatic retry; the
in-process proof maps a synthetic `TimeoutError` but does not implement an HTTP
timer. Neither success nor failure responses contain `memos_authority_ref`.

Both replay stores are deliberately bounded and process-local. HMAC proves
integrity and peer possession of the scoped secret, not content
confidentiality. Cross-host or multi-instance use remains blocked until there
is encrypted transport, shared replay protection, key rotation, and a separate
threat review. A real-data opt-in additionally requires verified Memos backup,
explicit dry run, rollback, and post-run lifecycle/retrieval reconciliation.
`EvidenceAnswerAgent`, `RetrievalService`, VectorStore construction, A4 runtime
routes, Memo CRUD, dispatcher/worker paths, Qdrant, Compose, and real data
remain unchanged in R5-I5.

R5-I5 independently verifies the request signature in Go before exact parsing
and signs only an exact success or fixed `503` response under the response-only
purpose. The Go parser rechecks snapshot token and every selection reference,
sequence, hash, and version; it rejects response identity or authority-reference
fields. This is cross-language contract parity, not a Go replay implementation
or Memos authority adapter. The HTTP route/client, process-local replay wiring,
current-visibility authority lookup, runtime secret/configuration, and AI
runtime selection remain separate authorization gates.

R5-I6 defines the next Memos-owned boundary without implementing that lookup.
`EvidenceAuthorityContextBinding` contains only the opaque authority reference
and an opaque authenticated-context token; it has no caller ID, owner, or
visibility fields. `EvidenceCurrentAuthorityReader` is called once and must
return all requested complete Memos from one atomic current-authority snapshot.
Every document must be currently visible, complete, normal, non-tombstoned,
nonblank, and must exactly match the requested UID, source sequence, document
hash, and `memo-v1` version. Per-document revision and authority token seals
must match the snapshot-level seals, preventing rows from different reads from
being combined.

The response is assembled in request selection order and contains only the R5-I3
fields: selection reference, content, sequence, hash, version, derived snapshot
token, and opaque authority token. Memo UID, caller identity, visibility,
authority reference, citation metadata, and store metadata are not projected.
Any missing, extra, duplicate, unknown, archived, comment, blank, deleted,
tombstoned, changed, malformed, or mixed row returns only
`authorized_retrieval_unavailable`, with no partial content. This proof uses an
in-memory fake and does not prove real-store transaction atomicity. A real
Memos Store reader, HTTP handler/client, replay wiring, runtime secret/config,
and AI runtime selection all require separate authorization.

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
