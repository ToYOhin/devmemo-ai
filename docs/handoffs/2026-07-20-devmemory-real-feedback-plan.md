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
4. Use a new, non-sensitive Bug Report. Evidence may contain only safe title/summary, source references, statuses, aggregate counts, and the participant's own feedback; do not record raw Memo content, IDs, Webhook payloads, secrets, or chunks.

## Execution steps

1. The participant captures one Bug Report in the Memos UI. Record only a safe source label and the visible creation outcome.
2. Let the existing product path produce or query Insights. If no Insight appears, record that blocker and stop: do not synthesize AI records or call private storage directly.
3. The participant reviews the visible Insight. The current authorization permits one accepted or rejected action; record its visible version/status. If independent candidates make both actions meaningful, request new confirmation before a second state change.
4. Build the Context Pack from the current Memo and accepted Insight only. Use a deliberately small `max_chars` to observe the existing truncation explanation without adding a new budget contract.
5. With the participant's confirmation immediately before each state-changing step, verify revoke/delete linkage only on this test Memo. Rebuild the pack and record whether the revoked/deleted source is excluded.
6. Copy Markdown and JSON through the real Chrome UI. Verify only the safe output written by this test path; do not inspect unrelated clipboard content. Confirm no React error boundary appears after either copy.
7. Ask the participant four short questions: whether provenance is clear, whether review/revoke wording is clear, whether truncation is understandable, and whether the copied pack is useful. Record answers as concise paraphrases, not raw Memo text.

## Stop conditions

- No participant consent or no stable authenticated session: stop without mutation and retain the current incomplete evidence.
- No generated Insight or a database/session mismatch: record the observable blocker; do not seed SQLite or manufacture a review state.
- A browser/API error, copy failure, or unexpected deletion behavior: stop at that point, retain only safe evidence, and do not call the overall path a pass.

## 2026-07-20 execution result

The authorized test Bug Report was created and saved through the authenticated UI, but the post-capture lifecycle aggregate remained `memo_insights=0` with only one pre-existing processed webhook event. The detail page showed the Context Pack entry, yet no Insight was visible or persisted. Per the stop condition, no review, pack generation/budget action, copy, delete/revoke, or feedback interview was performed. The safe evidence record is `docs/handoffs/2026-07-20-devmemory-feedback-capture-blocked.md`; do not retry by creating another Memo.

## Evidence and acceptance

Create a new dated handoff only after the real path. It must distinguish completed, failed, and untested steps; include test/health commands actually run; and state that this is product feedback rather than public-chunk rollout proof. The path passes only when a real participant completes the available steps and the recorded feedback is attributable to the visible safe UI state.
