# Phase 10 route B: real DevMemory feedback plan

Date: 2026-07-20

## Objective

Complete exactly one real Bug Report path with a present, consenting participant:

`Capture -> Insight -> Review -> Context Pack -> human feedback`

This is not gateway rollout work. Keep `AI_PUBLIC_CHUNK_RETRIEVAL=false` and do not modify public chat, Memos core, collections, volumes, or browser-held secrets.

## Preconditions

1. Use the `H:\DevMemoAI` main worktree and one authenticated local Memos session.
2. Confirm Compose and AI Service health, then run the read-only lifecycle report before the activity. It must be clear which configured AI SQLite database is being observed.
3. The real participant has authorized creating one non-sensitive test Bug Report and one Insight accept or reject action. Delete/revoke remains a separate action-time confirmation. Do not use an API call to bypass Memos authentication.
4. Reuse the existing non-sensitive Bug Report; do not create another. Evidence may contain only safe title/summary, source references, statuses, aggregate counts, and the participant's own feedback; do not record raw Memo content, IDs, Webhook payloads, secrets, or chunks.

## Execution steps

1. Do not repeat Capture, review, budget, or copy actions: their technical evidence already exists for this Memo.
2. Show the participant the already-visible safe Context Pack state in a stable authenticated session; do not inspect raw Memo content, unrelated clipboard data, or private storage.
3. Ask the participant four short questions: whether provenance is clear, whether the accepted-review outcome is trustworthy, whether the `64`-character truncation is useful, and whether Markdown/JSON copy matches expectation. Record answers as concise paraphrases, not raw Memo text.
4. Do not perform revoke/delete in this feedback slice. Those lifecycle actions already have separate technical coverage and are not needed to obtain the four answers.

## Stop conditions

- No participant consent or no stable authenticated session: stop without mutation and retain the current incomplete evidence.
- No generated Insight or a database/session mismatch: record the observable blocker; do not seed SQLite or manufacture a review state.
- A browser/API error, copy failure, or unexpected deletion behavior: stop at that point, retain only safe evidence, and do not call the overall path a pass.

## 2026-07-20 execution result

The later local-webhook correction completed the existing Memo's real Capture -> persisted Insight -> accepted Review path. A fresh same-profile Chrome tab then confirmed accepted-safe Context Pack content, `max_chars=64` truncation, and real Windows system-clipboard Markdown/JSON copy without console or React errors. The earlier `memo_insights=0` observation was a host-path mistake; use the Compose-mounted read-only lifecycle command described in the rollout handoff. The real participant then supplied all four concise feedback answers: sources were clear, the accepted review was trustworthy, the `64`-character budget was useful, and copy matched expectation.

## Evidence and acceptance

The dated completion record is `docs/handoffs/2026-07-20-devmemory-real-feedback-evidence.md`. It distinguishes completed and intentionally untested steps, and states that this is product feedback rather than public-chunk rollout proof. The available route-B path now passes because a real participant completed the available steps and the feedback is attributable to the visible safe UI state.
