# Evidence Answer Agent

> Status: the A1 local-first, read-only backend is implemented and locally
> runtime-verified. A2 adds an explicit experimental Web entry, while the
> feature remains disabled by default. No Agent persistence, remote deployment,
> or general-public availability is delivered.

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
4. **Controlled provider smoke — not started.** Optionally verify the same path with a
   locally configured provider. This is not a default Compose or CI requirement.

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

## Future work excluded from this proposal

Write tools require separately reviewed authentication and visibility mapping,
explicit user confirmation, idempotency, audit and rollback semantics, rate
limits, and threat modelling. They are not implied by the read-only Agent.
