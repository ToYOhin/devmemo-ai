# Phase 10 DevMemory feedback observation

Date: 2026-07-20

## Chosen route and scope

This is Phase 10 route B: a read-only observation of one existing local Bug Report in the authenticated Memos product. It is not a public-chunk rollout, does not repeat the in-process gateway contract smoke, and leaves `AI_PUBLIC_CHUNK_RETRIEVAL=false`.

## What was actually observed

- A logged-in Chrome session displayed an existing local Bug Report capture with a safe, user-visible summary about Context Pack clipboard acceptance.
- The Memos API correctly rejected an unauthenticated `auth/me` request with `401`; no raw API bypass was used.
- Compose was running and AI Service health returned the deterministic provider.
- `python -m scripts.devmemory_lifecycle_report` opened the configured AI SQLite database read-only and reported zero `memo_insights` records and one processed webhook event. The report contains only aggregates.
- A subsequent read-only Chrome recheck rendered `/inbox` correctly with its expected empty Inbox state. The earlier retained Memo body was a transient/stale observation, not a reproducible route-rendering defect.
- No durable accepted/rejected Insight state could be re-observed because the configured read-only AI SQLite aggregate still reported zero `memo_insights` records.

## Deliberately not claimed

- No human participant feedback was collected.
- No fresh Capture -> Insight -> Review -> Context Pack lifecycle was completed.
- No accept/reject, delete/revoke, budget truncation, Markdown/JSON copy, or post-copy UI state was re-verified in this observation.
- No Memo, Insight, database record, collection, volume, flag, secret, or public API was changed.

The earlier Phase 9f Chrome/Windows clipboard evidence remains historical acceptance evidence only; it is not substituted for this missing feedback loop. The local gateway contract smoke also remains contract/fake evidence only, not deployment proof.

## Focused evidence

- `tests/test_memo_insights.py`, `tests/test_context_pack_builder.py`, `tests/test_context_pack_golden.py`, and `tests/test_lifecycle_report.py`: `15 passed`.
- Memos unauthenticated `GET /api/v1/auth/me`: `401`.
- AI Service full suite and `scripts/verify-devmemo.ps1`: `187 passed` with one existing Starlette/httpx deprecation warning; `docker compose config --quiet` passed.
- Fresh Web test/build/lint were intentionally not run after the documentation-only change because the user requested avoiding further CPU-heavy work. Standalone strict `pnpm exec tsc --noEmit` again showed the known 13 dependency declaration/`src/types/view.d.ts` errors; this slice did not change web code or dependencies.

## Next admissible slice

Use exactly one route: either a real trusted gateway deployment with Memos visibility mapping and rollback conditions, or a stable authenticated product session with a real human participant who can supply feedback through Capture -> Insight -> Review -> Context Pack. Keep the public-chunk flag disabled until the real gateway conditions are met.
