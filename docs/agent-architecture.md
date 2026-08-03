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
> all-or-nothing projection with an in-memory fake. R5-I7 adds an unwired real
> SQLite current-authority reader with temporary-database parity and race proofs.
> R5-I8 adds an unwired process-local authority capability issuer/resolver with
> a bounded in-memory registry and synthetic concurrency proof. R5-I9 adds an
> unwired single-host transport composition with a dedicated process-local request
> replay store and synthetic call-order/concurrency proof. R5-I10 adds an
> unregistered single-host `net/http` handler/client contract with strict HTTP
> projection, fixed five-second timeout, and in-memory/fake-transport proof.
> R5-I11A adds strict, disabled-by-default Go/Python runtime configuration for
> a dedicated current/previous rehydration keyring and one AI-side Memos origin.
> R5-I11B adds fixed-order matching-key verification and opt-in registration on
> the existing Memos listener. R5-I11C adds an opt-in Python HTTP client owned by
> the AI Service lifespan, with deterministic transport close. R5-I12 issues a
> Memos-owned authority capability from the authenticated BFF path and carries
> only its opaque ref inside the signed delegation. R5-I13 adds injected durable
> candidate-to-rehydration orchestration with snapshot recheck and request-memory
> materialization. R5-I14 adds a content-free vector/lifecycle adapter, a ledger-
> owned active-generation revision, authorized UID query pushdown, and strict
> default-disabled lifespan ownership. R5-I15 makes the verified answer Agent
> select that owned orchestrator under the same opt-in, with no legacy fallback,
> and proves the disposable synthetic single-host product path. R5-I16 records
> the completion audit and authorization checklist. The authorized post-I16
> lifecycle slice now connects SQLite mutation/outbox delivery, the existing
> internal AI listener, generation activation, and Qdrant-derived state. Two
> disposable authenticated-browser runs completed the private/public visibility,
> update/delete, restart, rollback, and exact-cleanup matrix. R5 is complete only
> for this default-disabled single-host scope.

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
20. **Real single-host SQLite current-authority reader — complete, unwired.**
   R5-I7 derives caller identity only from Memos' internal authentication
   context, reuses the shared Memo visibility scope, and reads the current
   normal caller, bounded requested UIDs, comment relation, complete content,
   and latest A4 source event through one read-only SQLite snapshot. A latest
   delete, unknown version, stale document, ineligible Memo, missing row, or
   any concurrent database commit fails the entire response. The adapter is
   not registered with HTTP or runtime and has no real-data or multi-instance
   claim.
21. **Process-local Memos authority capability — complete, unwired.** R5-I8
   issues only from Memos authentication context plus a Memos-owned bounded
   complete-Memo UID scope. A fixed-capacity, expiring in-memory registry binds
   three independent opaque tokens to one private caller/scope record and
   atomically consumes an exact bounded rehydration subset at most once. Fake
   clock/token/scope tests cover auth provenance, UID bounds, expiry, capacity,
   collision, mismatch, restart invalidation, and concurrent consume. It adds
   no route/client, replay wiring, runtime configuration, persistence, real
   data, or multi-instance claim.
22. **Single-host rehydration composition — complete, unwired.** R5-I9 fixes
   the pure Go order from R5-I5 verification through a dedicated bounded
   request replay store, R5-I8 single consume, server-owned auth-context
   restoration, one reader-factory/reader call, R5-I6 projection, exact JSON,
   and R5-I5 response signing. Synthetic tests cover independent nonce and
   capability single-use, scope/binding/token rejection, fixed signed failure,
   concurrent duplicate handling, and new-store invalidation. It registers no
   HTTP route/client and adds no runtime secret/configuration, timer, retry,
   persistence, real data, or multi-instance claim.
23. **Disabled single-host HTTP adapter — complete, unwired.** R5-I10 adds an
   unregistered standard-library handler and client around R5-I9. The handler
   accepts only the exact internal POST envelope, projects unverified input as
   a content-free non-cacheable 404, and maps only exact signed 200/503 results.
   The client fixes a five-second timeout, makes one injected RoundTripper call,
   closes bounded bodies, authenticates the exact response before parsing, and
   leaves response replay with the AI-side R5-I4 boundary. Tests use only
   recorders, in-memory handler calls, and fake transports. No route, listener,
   environment/config field, runtime secret source, real socket, or Agent runtime
   integration is added.
24. **Dedicated rehydration runtime configuration — complete, unwired.**
   R5-I11A adds matching Go/Python environment contracts that remain secret-free
   while disabled and require the primary Agent flag before opt-in. An enabled
   runtime requires one canonical unpadded base64url 32-byte current secret, an
   optional distinct previous secret, strict separation from the answer-
   delegation secret, and one credential-free HTTP(S) Memos origin on the AI
   side. Pure settings tests add no key generation, route/client construction,
   listener, timer, persistence, or real secret.
25. **Dormant Memos rehydration registration — complete, opt-in.** R5-I11B
   constructs current and optional previous compositions over one shared
   process-local capability registry and request replay store. The handler tries
   current then previous and signs every verified response with the request-
   matching key. Only explicit opt-in registers the exact internal POST on the
   existing Echo server; disabled startup registers nothing. The runtime owns
   no listener, goroutine, timer, transport, or closeable resource.
26. **AI-side rehydration client lifespan — complete, disconnected.** R5-I11C
   creates the Python client only during an enabled AI Service lifespan and
   clears/closes it on shutdown. Its injected async transport has zero retries;
   the client fixes a five-second timeout, rejects redirects and non-exact
   response envelopes, bounds streamed bodies, verifies before parsing, and
   owns one process-local response replay store. The object is only exposed on
   `app.state` and is not called by `EvidenceAnswerAgent` or any endpoint.
27. **Authenticated capability delegation bridge — complete, disconnected.**
   R5-I12 makes the enabled Memos runtime derive the caller and exact visible
   complete-Memo UID scope once, issue one opaque capability for a nonempty
   scope, and add only its ref to the already signed internal answer request.
   An empty current scope produces no capability and preserves normal no-context
   behavior. The browser request and safe response contain no authority ref;
   disabled mode retains the prior memory delegation body.
28. **Durable rehydration orchestration — complete, unselected.** R5-I13 accepts
   only verified delegation, a content-free candidate repository, and the I11C
   client protocol. It filters candidates before one client call, rereads the
   current snapshot token, materializes reverified documents only in request
   memory, and projects the existing authorized result. Empty scopes/candidates
   make no call; every mismatch/failure is content-free and has no fallback.
29. **Content-free durable runtime selection — complete, disconnected.** R5-I14
   makes the A4 SQLite ledger own an active rebuild generation and monotonic
   snapshot revision, changing the opaque token in the same transaction as each
   lifecycle transition. A vector adapter pushes the exact authorized Memo UID
   set into ranking, accepts only strict `memo-v1` sequence/hash/generation
   metadata, joins applied ledger state, and rejects duplicate, malformed,
   content-bearing, stale, deleted, quarantined, or racing results. The existing
   rehydration opt-in constructs the repository/orchestrator in lifespan state
   only for memo-mode Qdrant selection; disabled startup constructs nothing.
   Neither `EvidenceAnswerAgent` nor an endpoint selects it yet.
30. **Durable answer-path selection — complete, opt-in.** R5-I15 gives
   `EvidenceAnswerAgent` one optional async durable retrieval dependency. The
   internal endpoint injects only the orchestrator already owned by the current
   app lifespan and only under the existing rehydration flag; missing ownership
   or any durable failure maps to the existing safe 503 without memory fallback.
   Disabled mode keeps the prior memory retrieval path byte-for-byte. Durable
   evidence becomes controlled Agent citations using only the server-owned Memo
   UID, source sequence, and `memo-v1`; vector or rehydration metadata cannot
   supply title, tags, visibility, or citation fields. A temporary SQLite,
   in-memory vector, fake-client proof reaches an answered trace with no network.
31. **Single-host lifecycle activation — complete, opt-in.** Memos SQLite CRUD
   now writes and dispatches the authoritative outbox under a dedicated flag.
   The existing AI listener verifies the lifecycle-only HMAC, applies the
   content-free ledger/Qdrant transition, and activates an exact generation only
   after manifest reconciliation. Startup rebuild is bounded and fail closed;
   no new listener, host port, automatic retry worker, or default enablement is
   introduced.
32. **Disposable real-runtime acceptance — complete for the R5 boundary.** Two
   local Compose projects using deterministic providers, temporary accounts and
   data, SQLite Memos, and local Qdrant proved same-origin BFF answers, owned
   private and other-user public inclusion, other-user private exclusion,
   update/delete convergence, restart reconciliation, safe rollback, and exact
   cleanup. This does not authorize real data, an external Provider, cross-host
   transport, shared replay state, or multi-instance operation.

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

R5-I7 supplies the first real reader implementation, scoped deliberately to
SQLite and still unwired. Its constructor obtains caller ID only from the
Memos authentication context; the R5 request and opaque binding cannot carry
or override identity or visibility. It shares the exact authenticated
visibility scope used by `ListMemos`, then opens one read-only transaction on a
dedicated SQLite connection. The transaction verifies the caller is still a
normal user and uses a bounded requested-UID CTE to select only normal,
noncomment, nonblank, currently visible Memos. Each selected Memo must join its
latest outbox event, which must remain a `memo-v1` upsert whose stored source
document equals the current Memos body. Memos content is the returned body;
outbox metadata cannot authorize visibility, identity, or citation.

The reader checks SQLite `data_version` before and after the transaction. Any
commit during the read—including content update, delete, or visibility change—
invalidates the whole snapshot. R5-I6 still owns exact UID, sequence, hash,
version, request-order, and response projection checks. Temporary SQLite tests
cover visibility parity, comment/archive/blank/tombstone rejection, missing or
inconsistent source state, concurrent changes, and fixed errors. This proves
only the existing SQLite schema and single-host process. R5-I7 itself does not
prove MySQL/PostgreSQL parity or add a capability issuer, route/client,
HMAC/replay wiring, runtime configuration, real data, or multi-instance support.

R5-I8 supplies the missing process-local capability boundary without wiring it
to R5-I7 or transport. Issuance accepts only Memos authentication context; it
has no caller, owner, visibility, query, request, or UID-scope parameter. A
Memos-private scope source must return the same current caller plus a unique,
nonempty set of at most 1,000 complete-Memo UIDs using the R5-I1 matcher. The
registry derives an authority reference, authenticated-context token, and
authority token from independent token-source values and binds them to one
private entry. Only the authority reference is intended for a later signed
rehydration request; caller identity, the full UID scope, and the other tokens
have no JSON projection.

The registry has a constructor-fixed capacity and TTL capped at 60 seconds. It
uses an injected clock, lazy expiry, no timer, and a per-registry monotonic
derivation sequence so recycled capacity cannot alias an older capability in
the same process. Consume holds one lock across lookup, private token-index
binding checks, and deletion. Exactly one concurrent caller can receive the
Memos-private resolution containing a fresh server auth context, the original
UID scope, the unchanged two-field R5-I6 binding, and its authority token.
Selections must be a unique one-to-ten-item subset of that original scope before
any future R5-I7 call. Unknown, expired, malformed, over-capacity, mismatched,
duplicate, out-of-scope, clock, token, scope-source, or concurrency failure maps
only to `authorized_retrieval_unavailable` and returns no partial binding.

This is deliberately a single-process, request-local proof. Process restart or
a new registry invalidates every prior entry. R5-I8 does not reuse the R5-I4
nonce stores and does not implement HTTP, HMAC/replay runtime composition,
answer runtime selection, configuration, secrets, persistence, database access,
networking, or real data. A shared atomic capability/replay store and encrypted
transport remain mandatory before any multi-instance use.

R5-I9 composes those boundaries without registering a runtime. Its constructor
requires an explicitly supplied scoped secret, request age of at most 60
seconds, clock, dedicated fixed-capacity request replay store, R5-I8 registry,
and reader factory. Verification of the R5-I5 HMAC, freshness, and exact body
precedes nonce consumption; nonce consumption precedes capability lookup;
capability resolution is rechecked for exact private token binding and a
bounded authorized UID subset before it reconstructs a fresh Memos auth
context. Only that context, the two-field R5-I6 binding, and the authority token
reach the reader factory. The factory and reader are each called at most once.

The request replay store and capability registry are different process-local
types with independent capacity and lifecycle. A concurrent duplicate nonce
allows at most one call past replay; changing the nonce does not make a consumed
capability reusable. A new replay store forgets old nonces while a new
capability registry rejects old authority references, which is an explicit
restart boundary rather than a durability claim. The future client policy
remains a five-second timeout with automatic retry disabled; no client or timer
exists in this slice.

An unauthenticated or malformed request is rejected before replay with the
fixed local error and no response projection, because it supplies no trusted
snapshot token for the response HMAC. Once a request is verified, replay,
capability, binding, reader, or schema failure produces only the exact signed
`503 authorized_retrieval_unavailable` body. If response signing itself fails,
the composition returns no projection rather than emitting an unsigned body.
Success is only an exact signed R5-I6 `200` response. Caller identity, full UID
scope, authenticated-context token, authority reference, and raw failures have
no response or observability projection.

R5-I10 wraps that composition in dormant standard-library HTTP objects without
registering a route or opening a listener. The handler requires exact
`POST /internal/ai/agent/evidence/rehydrate`, one value for each request HMAC
header, exact `application/json`, a known non-chunked body length from 1 byte to
32 KiB, one JSON value, and a successfully closed request body before entering
R5-I9. Any pre-verification rejection is a bodyless, unsigned, non-cacheable
404. Verified success or downstream failure maps only the exact body, status,
four response HMAC headers, JSON content type, and `Cache-Control: no-store`.

The dormant client accepts only constructor-injected base URL, scoped secret,
clock, and `RoundTripper`. It fixes `http.Client.Timeout` at five seconds,
disables redirect following, performs one POST without retry, bounds and closes
the response body, rejects duplicate, cacheable, identity, or debug response
headers, and verifies freshness, request nonce, snapshot token, status, body,
and response HMAC before exact parsing. Client response replay remains solely
the AI-side R5-I4 store; the Go handler does not add a second client replay
store. Request contexts reach the restored server auth context and cancellation
fails closed.

R5-I10 contains no route registration, listener, environment variable, config
field, runtime secret source, rotation/overlap policy, port, volume, migration,
persistence, real network access, answer-path import, real Store access, or real
data. Runtime secret sourcing and rotation, shutdown ownership, Docker/browser
end-to-end proof, and AI runtime selection require later explicit authorization.
Encrypted transport and shared atomic replay/capability storage remain mandatory
before multi-instance use.

R5-I11A establishes a third, purpose-scoped secret domain instead of reusing
the Memos session secret or `AI_AGENT_INTERNAL_SECRET`. The deployment boundary
injects `AI_AGENT_REHYDRATION_SECRET_CURRENT` and an optional
`AI_AGENT_REHYDRATION_SECRET_PREVIOUS` into both processes; neither service
creates, distributes, stores, logs, or projects them. Both contracts discard
the supplied values while `AI_AGENT_REHYDRATION_ENABLED=false`. Enabling
rehydration also requires `AI_AGENT_ENABLED=true`; malformed, duplicate, or
delegation-secret-equal values fail startup validation. The AI contract also
requires exactly one credential-free HTTP(S) origin in
`AI_AGENT_REHYDRATION_MEMOS_URL`.

The keyring is startup-fixed, capped at current plus previous, and has no timer
or dynamic reload. R5-I11B verifies requests in fixed current-then-previous
order and keeps both compositions on the same process-local capability and
request-replay stores. A verified success or failure is signed only by the key
that authenticated its request. Explicit opt-in registers the exact POST on the
existing Memos Echo instance; disabled mode has no route. The Memos server owns
the handler lifetime, while the runtime adds no listener, port, goroutine,
timer, transport, or shutdown hook. The AI client has separate lifespan ownership.

R5-I11C constructs the Python client only inside the FastAPI lifespan when the
rehydration flag is enabled. Production injects `AsyncHTTPTransport(retries=0)`;
tests inject an in-memory transport. Each call prepares one signed POST, uses a
fixed five-second timeout without redirects or retry, streams and bounds the
response, requires exact signed 200/503 headers, then verifies and consumes the
existing process-local response replay entry before parsing. Shutdown always
closes the owned client/transport and clears `app.state`. Disabled lifespan does
not construct a transport. The client remains disconnected from the answer
Agent and durable retrieval selection.

R5-I12 extends the private Memos-to-AI delegation with one optional opaque
`memos_authority_ref`. When rehydration is enabled, the BFF asks the same
process-local registry for the Memos-authenticated current visible UID scope and
its capability in one operation, then delegates that exact UID copy plus the
ref under the existing answer HMAC. Empty scope delegates no ref; registry or
scope failure maps to the existing safe BFF failure. The field is never accepted
from or returned to the browser. Python verifies its 32-64-character opaque
shape but does not yet call the lifespan client.

R5-I13 composes the existing R5 domain contracts without selecting a runtime
adapter. A verified delegation becomes an authorized query; content-free
candidates are filtered before one rehydration request. Only a successful exact
response proceeds to a fresh repository snapshot-token read and the existing
materialization cross-check. Any client failure, changed snapshot, partial or
mismatched response fails as `authorized retrieval unavailable`, never loading
derived raw content. Empty authorized/candidate scopes return empty without a
client call. No endpoint or `EvidenceAnswerAgent` uses this orchestrator yet.

R5-I14 binds that orchestrator to the production vector and lifecycle
boundaries without persisting Memo content. The A4 SQLite ledger stores only a
single active generation and monotonic revision beside its existing derived
state; reserve, complete, and fail transitions advance the revision in the same
transaction. The repository embeds the question, pushes the exact authorized
UID set into in-memory or Qdrant ranking, and joins each content-free result to
the ledger. It accepts only current-generation `memo-v1` metadata whose sequence
and hash match an applied upsert. Missing, duplicate, unauthorized, stale,
deleted, quarantined, content-bearing, or concurrently changing state fails
closed. The existing `AI_AGENT_REHYDRATION_ENABLED` opt-in owns the repository
and orchestrator in FastAPI lifespan state only when memo-mode Qdrant is
selected. The memory default is unchanged, and the answer Agent remains
disconnected until R5-I15.

R5-I15 connects the already-owned orchestrator without adding another client,
repository, ledger, transport, route, or configuration flag. Delegation is
verified before the Agent calls the optional async retrieval dependency. The
durable result supplies request-memory context, while its server-owned citation
is projected into the existing Agent schema with controlled empty title/tags,
an identity derived only from `memo-v1`, Memo UID, and source sequence, and no
rehydration/vector metadata. Empty durable evidence preserves no-context and
does not call the Provider. Missing runtime ownership, missing authority,
rehydration failure, snapshot race, malformed result, or projection failure
maps to the existing retrieval-unavailable 503 and never falls back to memory.
The earlier product-path proof uses a temporary ledger, in-memory vectors,
synthetic delegation, and a fake rehydration client. The later authorized
single-host acceptance additionally exercised the production SQLite/HTTP/Qdrant
objects with disposable data while preserving the same fail-closed contract.

## A4 local RAG lifecycle contract

This section defines the lifecycle contract used only by the explicit
single-host opt-in. The generic Memos Webhook path is not the A4 transport: its
Memos-side dispatch uses
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

Rollback first disables lifecycle and rehydration. It then restores
`AI_VECTOR_STORE=memory`, or disables the complete Agent with
`AI_AGENT_ENABLED=false`; it does not change Memos data or visibility. Revert
the lifecycle consumer or provider configuration, discard the suspect derived
generation, and rebuild from Memos before re-enabling. A scope leak, stale
resurrection, or raw-content exposure requires immediate disablement and
derived-index quarantine. A delete is recovered only by restoring the
authoritative Memo through the normal Memos backup policy and then reindexing,
never by copying content back from AI state.

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
6. **Complete for disposable single-host SQLite:** the authorized opt-in runtime
   connected mutation/outbox dispatch, the existing authenticated listener,
   generation activation, complete-Memo Qdrant state, restart reconciliation,
   headed-browser authorization, rollback, and exact cleanup.
7. Only after separate explicit approval, run an opt-in migration/rebuild
   against real Memos data with backup, rollback, and post-run deletion
   verification.

### Chunk and Qdrant gates

A4 still does not enable chunk retrieval. R5 permits complete-Memo Qdrant Agent
retrieval only under the explicit, default-disabled single-host lifecycle and
rehydration flags; Memos remains the current visibility and content authority.
Chunk retrieval still requires its own version and collection, stable
delete/tombstone rules, offline evaluation, reviewed migration gates, and the
same Memos authority check before context assembly. `search_memos` continues to
accept only complete `memo-v1` evidence.

### R6 evaluation contract

R6-I1 defines separate, provider-neutral `agent-evaluation-case-v1` and
`agent-evaluation-result-v1` contracts. Cases are explicitly classified as
synthetic and carry only a bounded question plus opaque visible, expected, and
forbidden evidence IDs. Results are content-free: they carry the observed
answer state, retrieved and cited evidence IDs, an allowlisted failure category,
and bounded latency, but no answer text, prompt, context, trace payload, Memo
content, identity mapping, Provider output, or secret.

R6-I2 adds `agent-evaluation-corpus-v1` with 64 static synthetic cases, eight
per required category. Its parser enforces 50-100 unique cases, exact declared
category counts, at least two cases per category, and an explicit synthetic
marker in every question. `agent-evaluation-thresholds-v1` binds the corpus and
result versions and declares separate gates for Recall@5, MRR, citation
precision, groundedness, refusal accuracy, scope-leak count, and p95 latency.
Each gate has an exact unit, direction, legal range, boundary, and applicable
categories; no aggregate score field exists.

R6-I3 adds a pure runner over already parsed corpus, threshold, and result
objects. It requires exactly one result per corpus case and rejects missing,
duplicate, unknown, or wrong-type results. Recall@5 and reciprocal rank exclude
cases with no expected evidence; citation precision and groundedness apply to
answer cases; refusal accuracy applies to no-answer/refusal cases; scope leaks
are counted from forbidden IDs or an explicit safe failure flag; p95 latency
uses nearest-rank selection. The five ratio metrics are macro-averaged across
their applicable cases, while scope leaks are summed. The runner never calls
retrieval or a Provider.

`agent-evaluation-report-v1` contains only bound contract versions, case count,
aggregate metric values and gates, overall pass/fail, and every failed case ID
with allowlisted categories. It contains no question, answer, evidence content,
Memo, prompt, context, trace, identity mapping, Provider output, or secret. Test
reports use supplied synthetic results only and are not product benchmark,
Provider-quality, runtime-latency, or cost evidence.

### R6 content-free observability contract

R6-I4A defines the provider-neutral `agent-observability-v1` contract without
selecting it in any runtime path. Events allow only a fixed component,
operation, and outcome combination. Metrics separately allow request count,
tool and Provider latency, outbox lag, retry and quarantine counts, rebuild
state, and reconciliation state, with fixed units, ranges, and state values.
Unknown fields, arbitrary labels, identity and request IDs, raw errors, content,
and generation IDs fail closed.

The dormant in-memory adapter accepts only already validated contract objects.
Its capacity is fixed at construction, bounded to 1-4096 samples, and overflow
evicts the oldest item. Snapshots are immutable copies. The adapter has no
persistence, timer, thread, background task, exporter, network transport, or
runtime configuration. No endpoint, Agent, retrieval, Provider, lifecycle,
rebuild, or reconciliation caller records samples yet, so these tests are
contract evidence rather than operational observability evidence. R6-I4B must
review and explicitly authorize any minimal runtime instrumentation and its
default, ownership, cardinality, and rollback boundaries.

#### R6-I4B reviewed runtime matrix

R6-I4B changes no runtime code. It fixes the following ownership and sequencing
before any caller is authorized:

| Disposition | Owner and exact point | Allowlisted emission and frequency | Timing boundary | Missing/failure behavior | Test and rollback |
| --- | --- | --- | --- | --- | --- |
| Implemented by R6-I4C | AI Service `answer_delegated_agent_request`, after the existing Agent-enabled gate | One `request_count=1` metric and one `answer` event per handler invocation; only `success`, `no_context`, `invalid`, or `unavailable` | None; this slice adds no latency claim | Missing recorder is a no-op; eviction or record failure cannot alter the existing response/status | Fake and raising recorders preserve success/no-context/400/401/500/502/503 projections; rollback removes lifespan ownership and endpoint injection, with no data cleanup |
| Deferred | `EvidenceAnswerAgent._run`, around the selected memory or durable retrieval branch | One `search_memos` event and one `tool_latency_ms` metric per valid search | Injected monotonic clock immediately before retrieval through safe citation/context assembly | No recorder is a no-op; observer failure cannot change retrieval | Fake clock/recorder must cover both retrieval modes, no-context, invalid input, and unavailable mapping |
| Deferred | `EvidenceAnswerAgent._answer`, only around an actual non-deterministic Provider call | One `provider_call` event and one `provider_latency_ms` metric per actual call; deterministic/no-context paths emit neither | Injected monotonic clock immediately before `generate` through parse/validation | Observer failure cannot change Provider failure mapping | Fake clock/provider must prove success, invalid result, timeout, and unavailable mapping |
| Deferred to a Go-owned design | Memos `memoLifecycleSourceRuntime` and `MemoLifecycleOutboxStore` | Outbox outcome, lag, retry, and quarantine/exhaustion projections only from authoritative Go state | Source-owned UTC timestamps and store transaction boundaries; never Python wall time | No Python adapter, new transport, or per-event label | A separate Go contract/adapter must define whether exhausted means quarantined and add an authoritative oldest-pending-lag read |
| Deferred | Memos rebuild preparation plus AI `MemoLifecycleRuntime.activate` | Fixed rebuild state only after one reviewed cross-process state machine exists | State transitions, not inferred elapsed time | Partial activation cannot be projected as complete | Fake Memos client/store and AI ledger tests must prove pending/active/complete/failed transitions and rollback |
| Rejected until an authority exists | Reconciliation | No emission: there is no dedicated reconciliation owner or persisted status today | Not applicable | Never infer `synced`/`degraded` from raw errors or arbitrary mismatches | Define and review an authoritative state machine before instrumentation |

R6-I4C makes the existing AI lifespan own exactly one
`BoundedInMemoryObservabilityAdapter(256)` only while the existing Agent opt-in
is enabled, expose it through `app.state`, inject it into the internal answer
handler, and clear the reference during shutdown. It adds no flag, environment
variable, endpoint, exporter, persistence, thread, timer, or background task.
The recorder sees only fixed contract objects and must never receive request
bodies, result content, exceptions, IDs, or dynamic labels. Recording is
best-effort per fixed sample: a missing or raising recorder cannot change the
existing answer, status, body, or unexpected exception. TestClient proofs cover
answered, no-context, 400, 401, 500, 502, 503, disabled ownership, shutdown,
and recorder failure. No snapshot reader or operational exporter exists, so
this is in-process emission evidence, not operator-facing observability.

#### R6-I4E retrieval timing boundary

R6-I4E implements the retrieval-only boundary reviewed in R6-I4D. It adds two
keyword-only dependencies to `EvidenceAnswerAgent`: the existing recorder
protocol and a `Callable[[], float]` monotonic clock. Existing constructors keep
both as `None`; only the enabled internal answer handler injects its
lifespan-owned recorder and `time.monotonic`. The adapter never owns a clock.

| Path | Fixed outcome | Exact timing boundary | Existing behavior that must remain | Required fake proof |
| --- | --- | --- | --- | --- |
| Delegation verification or `SearchMemosToolCall` construction fails | No retrieval sample | Before timing starts | Existing delegation/request failure mapping | Clock and recorder remain untouched |
| Memory retrieval returns safe non-empty/empty evidence | `success` / `no_context` | Start immediately before the selected memory branch; stop after `_safe_citation`, context, and protected-fragment assignment | Exactly one authorized search; Provider remains after the stop point | Fixed clock yields one `tool_latency_ms` and one `search_memos` event |
| Memory retrieval raises `RetrievalInputError` | `invalid` | Same start; stop before re-raising | Original exception and endpoint 400 mapping | No fallback or Provider call |
| Memory retrieval is unavailable or safe assembly raises unexpectedly | `unavailable` | Same start; stop before the original failure escapes | Existing unavailable mapping or unexpected exception is unchanged | Recorder failure cannot replace the retrieval failure |
| Durable retrieval returns safe non-empty/empty evidence | `success` / `no_context` | Start immediately before the selected durable branch; stop after `_safe_durable_citation`, context, and protected-fragment assignment | One durable call, no legacy fallback | Same metric/event shape as memory retrieval |
| Durable retrieval fails, returns the wrong type, or fails safe assembly | `unavailable` | Same start; stop before the existing `RetrievalUnavailableError` mapping escapes | Existing fail-closed mapping and no Provider call | No raw durable failure is retained |
| Provider or response serialization later succeeds/fails | Does not change the completed retrieval outcome | Outside the retrieval interval | Retrieval success remains distinct from Provider outcome | Clock is called exactly twice before Provider execution |

The implemented wrapper starts only after the signed request and tool call are
valid, surrounds the existing branch without moving its logic, derives the
outcome from that branch, reads the stop clock before recording, and then lets
the current `_run` flow continue. Missing recorder/clock, a raising clock, a
boolean/non-numeric/non-finite clock value, negative elapsed time, or elapsed
time above the contract's 600,000 ms maximum emits neither retrieval sample.
It must not substitute zero or a capped value. A raising recorder independently
attempts the fixed metric and event but cannot change retrieval or answer
behavior. No question, context, citation, Memo/request/user/generation ID,
exception, branch name, or dynamic label reaches either sample.

The R6-I4E implementation is limited to the observability helper, the optional
keyword-only dependencies and shared try/finally boundary in
`EvidenceAnswerAgent._run`, and injection of the current lifespan recorder plus
`time.monotonic` by the internal answer handler. Pure/fake tests cover clock
validation, memory/durable success, no-context, invalid/unavailable failures,
Provider exclusion, missing/raising dependencies, and compatible constructors.
Rollback removes those optional dependencies and the retrieval wrapper; R6-I4C
answer samples remain and no persistent cleanup is required. Provider timing
and all Go-owned lifecycle metrics remain separate and unwired.

#### R6-I4F reviewed Provider timing boundary

R6-I4F changes no runtime code. The reviewed owner is the configured-Provider
branch of `EvidenceAnswerAgent._answer`; the deterministic fallback performs no
Provider call and must emit no Provider sample. A later minimal implementation
may reuse the Agent's optional recorder and monotonic clock without adding a
second clock owner or changing existing constructors.

| Path | Fixed Provider outcome | Exact timing boundary | Answer behavior that must remain | Required fake proof |
| --- | --- | --- | --- | --- |
| Deterministic fallback | No Provider sample | No interval | Existing fallback and citations | Clock and recorder are untouched |
| `generate` returns a result with string text | `success` | Immediately before `generate`; stop after the result envelope/text check | Parsing, grounding validation, and response construction remain after the stop | Nested clock order is retrieval start/stop, then Provider start/stop |
| `generate` returns an invalid result envelope/text | `invalid` | Same start; stop before the existing contract failure is mapped | Existing `invalid_grounded_answer` mapping | No prompt/result content or raw error is recorded |
| `generate` raises, including timeout or cancellation | `unavailable` | Same start; stop before the original failure mapping or cancellation escapes | Existing fixed error mapping; cancellation is re-raised | Clock/recorder failure cannot replace the Provider failure |
| Grounded-answer parse or validation fails after valid text | Completed Provider outcome remains `success` | Outside the Provider interval | Existing Agent Provider error and answer outcome remain unchanged | Provider success and answer unavailable can coexist |

The candidate uses the same whole-pair discard rules as retrieval timing:
missing dependencies, raising/boolean/non-numeric/non-finite clock values,
negative elapsed time, or elapsed time above 600,000 ms emit neither sample.
Recording happens after the stop read and independently attempts the fixed
`provider_latency_ms` metric and `provider_call` event. No Provider/model name,
prompt, result text, exception, request/Memo/user/generation ID, or dynamic label
is retained.

The minimal first batch is one helper plus one inner try/finally around the
configured `generate` call and result-envelope check. Post-Provider parsing,
grounding validation, token/cost metrics, Provider-specific labels, streaming,
retries, and all Go-owned observability are deferred. Reader/exporter,
persistence, settings, network calls, and real Provider execution are rejected
from this slice. Rollback removes only the helper and inner boundary; answer and
retrieval samples remain unchanged. Wiring requires explicit authorization.

## Future work excluded from this proposal

Write tools require separately reviewed authentication and visibility mapping,
explicit user confirmation, idempotency, audit and rollback semantics, rate
limits, and threat modelling. They are not implied by the read-only Agent.
