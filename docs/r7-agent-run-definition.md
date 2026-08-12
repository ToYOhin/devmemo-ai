# R7-I0 AgentRun Definition Gate

Status: R7-I0 is merged on `origin/main` at
`3dbddc3a6e8c17aeb90d35100137e436f2b7a4f7`. R7-I1 now has a local
contract-only Python implementation plus deterministic sanitized contract and
acceptance fixtures. This remains unwired: it adds no AgentRun persistence,
route, database migration, worker, runtime, UI, or feature default. It refines
the next gate in the
[Agent development roadmap](agent-development-roadmap.md).

## Outcome

Define a provider-neutral, bounded, resumable AgentRun contract that preserves
Memos authentication and visibility authority, produces evidence-linked report
artifacts, and fails closed when evidence or authority changes.

R7-I0 succeeds when the models, state machine, budgets, ownership, recovery,
approval boundaries, redacted timeline, acceptance fixtures, and rollback are
unambiguous in English and Chinese. R7-I1 locally implements those domain
validators and fixtures without implementing orchestration or side effects.

## Scope

- Define `AgentRun`, `AgentStep`, `RunEvent`, `ApprovalRequest`, and `Artifact`.
- Define legal run transitions and terminal behavior.
- Fix the first tool set to `search_memos`, `get_memo_evidence`, and
  `create_report_artifact`.
- Define bounded execution, idempotency, checkpoint, retry, resume, cancel, and
  process-restart semantics.
- Define source revision, visibility, approval, privacy, and audit behavior.
- Define deterministic acceptance fixtures for the later contract slice.

## Non-goals

R7-I1 does not implement Go, TypeScript, Proto, migrations, Compose,
environment variables, persistence, runtime wiring, background jobs, model routing, Memo
writes, external write tools, or a browser experience. It does not change
defaults, authentication, visibility, storage, ports, or current R6 behavior.

It does not claim real-Provider, real-user-data, browser-automation,
multi-instance, or production readiness.

## Threat model and invariants

The design assumes hostile Memo text, prompt injection, forged or replayed run
requests, stale source revisions, visibility changes during a run, duplicate
delivery, process interruption, expired or duplicated approval, Provider output
that invents citations, and attempts to extract protected prompts, secrets,
capabilities, embeddings, or another user's content.

The following invariants are mandatory:

1. Memos authenticates the user and computes visibility before retrieval.
2. Every evidence read is re-authorized against current Memos authority.
3. A run cannot broaden its original user, workspace, or source scope.
4. Only server-validated evidence references may enter an answer or artifact.
5. Missing evidence, stale authority, or ambiguous side effects fail closed.
6. Planning and tool execution are bounded; no recursive or unbounded planning.
7. Terminal runs are immutable except for append-only redacted audit metadata.

## Ownership and data flow

1. The browser submits an authenticated task to the same-origin Memos BFF and
   receives only a browser-safe run, timeline, approval, and artifact projection.
2. Memos owns identity, visibility, source Memo mutations, source revisions,
   lifecycle outbox state, current-authority checks, and capability issuance.
3. The Memos BFF fixes the authorized scope and delegates only that bounded,
   content-minimized scope to the AI Service. The browser never calls the AI
   Service directly.
4. The AI Service owns orchestration, provider-neutral run/step state, derived
   retrieval indexes, checkpoints, redacted events, and generated artifact
   bytes. All of these are derived and must be rebuildable or removable without
   mutating source Memos.
5. An `Artifact` is derived output, never source authority. Memos rechecks the
   requesting user's visibility before projecting artifact metadata or issuing
   a bounded download. An artifact cannot restore access to evidence that has
   become invisible.

## Provider-neutral data model

Identifiers are opaque server-generated values. Timestamps are UTC. Enumerated
types and reason codes are versioned contracts, not Provider-specific strings.

### AgentRun

| Field | Contract |
| --- | --- |
| `run_id` | Stable opaque identifier |
| `subject_id` | Authenticated Memos principal; never browser-selected |
| `scope_ref` | Memos-issued bounded source scope reference |
| `request_key` | Idempotency key scoped to subject and operation |
| `status` | One of the six states defined below |
| `budget` | Immutable accepted ceilings for steps, calls, and active time |
| `source_snapshot` | Content-free authority version/revision set |
| `created_at`, `updated_at` | UTC lifecycle timestamps |
| `terminal_reason` | Fixed safe code for terminal runs, otherwise absent |
| `last_event_seq` | Monotonic sequence of the committed timeline |

### AgentStep

| Field | Contract |
| --- | --- |
| `step_id`, `run_id`, `ordinal` | Stable identity and total run order |
| `kind` | `plan`, `tool`, `approval`, or `finalize` |
| `status` | `queued`, `running`, `succeeded`, `failed`, or `cancelled` |
| `tool_name` | Fixed tool name for tool steps; otherwise absent |
| `attempt` | Zero-based bounded attempt number |
| `input_digest` | Digest of normalized safe input, never raw content |
| `checkpoint_ref` | Last atomically committed step checkpoint |
| `started_at`, `finished_at` | UTC timing when applicable |
| `outcome_code` | Fixed content-free outcome code |

### RunEvent

| Field | Contract |
| --- | --- |
| `event_id`, `run_id`, `seq` | Stable identity and monotonic run order |
| `event_type`, `schema_version` | Fixed event contract and version |
| `step_id` | Related step when applicable |
| `safe_details` | Allowlisted content-free metadata only |
| `occurred_at` | Server timestamp |
| `prev_digest`, `event_digest` | Optional tamper-evident ordering fields |

### ApprovalRequest

| Field | Contract |
| --- | --- |
| `approval_id`, `run_id`, `step_id` | Stable approval identity |
| `action_type` | Versioned action class, never arbitrary executable text |
| `action_digest` | Digest binding the exact proposed action and arguments |
| `source_snapshot` | Authority revisions the proposal was based on |
| `requested_at`, `expires_at` | Explicit bounded approval window; no implicit default |
| `status` | `pending`, `approved`, `rejected`, `expired`, or `superseded` |
| `decided_by`, `decided_at` | Authenticated decision audit fields |

### Artifact

| Field | Contract |
| --- | --- |
| `artifact_id`, `run_id`, `step_id` | Stable derived-output identity |
| `kind`, `media_type`, `schema_version` | Allowlisted format contract |
| `storage_ref` | Server-only derived-object reference |
| `digest`, `size_bytes` | Integrity and size metadata |
| `evidence_refs` | Authorized Memo UID/revision references used to derive it |
| `created_at`, `expires_at` | Lifecycle and retention boundary |
| `status` | `available`, `revoked`, or `expired` |

## Run state machine

The only run states are `queued`, `running`, `waiting_approval`, `succeeded`,
`failed`, and `cancelled`.

| From | Legal transition | Trigger |
| --- | --- | --- |
| `queued` | `running` | A worker claims the run with its committed budget |
| `queued` | `cancelled` | An authorized cancel arrives before execution |
| `running` | `waiting_approval` | A future approval-gated action is fully bound and checkpointed |
| `running` | `succeeded` | Final output is validated and committed |
| `running` | `failed` | A fixed terminal failure or exhausted budget occurs |
| `running` | `cancelled` | An authorized cancel is observed at a safe boundary |
| `waiting_approval` | `running` | One valid, unexpired, current-authority approval is consumed |
| `waiting_approval` | `failed` | Rejection, expiry, stale authority, or invalid approval occurs |
| `waiting_approval` | `cancelled` | An authorized cancel is observed |

`succeeded`, `failed`, and `cancelled` are terminal. No transition reopens a
terminal run. Process restart is recovery within the persisted state, not a new
state or an implicit transition.

## Fixed first-stage tools

- `search_memos`: returns content-free ranked candidates inside the delegated
  scope; it cannot accept a browser-selected identity or expanded scope.
- `get_memo_evidence`: rechecks current authority and returns only exact,
  revision-bound evidence required for the current step.
- `create_report_artifact`: creates an idempotent derived report from validated
  evidence references; it does not create or modify a Memo.

No other tool is allowed in the first stage. All future Memo write tools remain
approval-gated and require a separate threat-model, schema, runtime, and product
review. R7-I0 defines no write tool and authorizes no side effect on source data.

## Execution budgets

The first contract ceiling is immutable per accepted run and is not a change to
current runtime defaults:

- at most 12 steps, including planning and finalization;
- at most 8 total tool calls and 1 retry for any tool step;
- at most 120 seconds of active execution, excluding `waiting_approval`;
- at most 30 seconds for one tool attempt;
- at most 3 artifacts and 1 MiB per artifact.

Reaching any ceiling produces a fixed, content-free failure code. A run cannot
extend its own budget, spawn another run to evade a ceiling, or continue
planning after the remaining budget cannot complete a valid next step.

## Idempotency, checkpoint, retry, resume, cancel, and restart

- Memos deduplicates creation by `(subject_id, request_key)` and returns the
  existing run for an identical request. A conflicting digest fails closed.
- Each tool attempt uses a stable key derived from run, step, attempt, tool, and
  normalized safe-input digest. `create_report_artifact` returns the same
  artifact for the same key.
- Run state, step outcome, artifact metadata, and the corresponding event are
  committed atomically at each checkpoint. Partial results are not projected.
- A retry is allowed only for a classified transient failure, within the one-
  retry ceiling, after rechecking cancellation, source revisions, and visibility.
- Resume begins from the last committed checkpoint. It never trusts uncommitted
  Provider output or tool output and never repeats an unknown side effect.
- Cancel is authenticated and idempotent. Workers check it before planning,
  before and after each tool call, before artifact commit, and before finalization.
- After process restart, `queued` runs may be claimed; `running` runs resume from
  their last checkpoint; `waiting_approval` runs remain paused until a valid
  decision or expiry. Terminal runs remain terminal.

## Complete redacted timeline

Every state transition, step start/end, tool attempt, retry, approval decision,
checkpoint, artifact lifecycle change, cancellation, and terminal outcome emits
one ordered `RunEvent`. Safe details may contain IDs, fixed reason codes, tool
names, counts, durations, source UID/revision references, digests, and artifact
metadata.

The timeline must never record raw prompts, raw Memo content, secrets, tokens,
internal capabilities, embeddings, Provider hidden reasoning, or unrestricted
tool arguments/results. Browser projection applies a stricter allowlist than
server audit storage. Error text is mapped to fixed safe codes.

## Approval and authority failures

- Approval is bound to one subject, run, step, action digest, and source
  snapshot. It cannot approve a modified action.
- Approval received after `expires_at` becomes `expired` and fails the run
  closed. The expiry is explicit when the request is created.
- The first valid approval decision is consumed atomically. Duplicate identical
  delivery is idempotent; a conflicting or already-consumed decision is rejected
  and recorded without executing the action again.
- A stale source revision invalidates the pending action and fails closed.
- A visibility change triggers current-authority recheck, revokes inaccessible
  evidence/artifact projection, and fails the active step. Cached access never
  overrides Memos authority.

## Acceptance fixtures

R7-I1 locally implements the deterministic, sanitized
`agent-run-contract-v1.json` and `agent-run-acceptance-v1.json` fixtures. The
targeted Python tests load them and drive the domain validators; they are not
runtime, persistence, UI, CI, external-Provider, real-data, or multi-instance
evidence.

The local R7-I1 fixtures cover these minimum cases. They define inputs, ordered
safe events, terminal state, tool-call count, evidence revisions, and
artifact/approval outcome.

| Fixture | Required result |
| --- | --- |
| `readonly_multistep_success` | Search, evidence read, and report creation succeed with valid citations |
| `no_evidence_termination` | Stops without Provider synthesis or artifact and returns a fixed no-evidence result |
| `safe_refusal` | Protected-prompt or secret request refuses before retrieval |
| `stale_revision` | Revision mismatch fails closed before evidence use or artifact commit |
| `visibility_change` | Mid-run access loss revokes projection and terminates safely |
| `waiting_approval_resume` | Contract-level future action pauses, consumes one valid approval, and resumes without implementing a write tool |
| `duplicate_retry` | Duplicate request/tool delivery remains idempotent and within budget |
| `cancel` | Authorized cancel reaches `cancelled` with no later tool or artifact commit |
| `restart_recovery` | Restart resumes exactly from the last checkpoint without duplicate side effects |

## Rollback

R7 remains disabled by default. R7-I1 adds no route, runtime selection, worker,
database migration, environment variable, persistence, or source-data mutation.
Rollback is reverting the local contract/fixture commits; existing R6 behavior
and data are unchanged.

## Unverified and separately authorized scope

This definition does not verify or authorize a real Provider, real user data,
browser automation, background autonomous jobs, multi-instance operation, or
external write tools. Encrypted transport, shared atomic replay/capability
storage, production retention, and operational ownership require separate
design and acceptance before any corresponding claim.
