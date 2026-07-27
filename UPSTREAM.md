# Upstream relationship

DevMemo AI is a downstream project based on
[Memos](https://github.com/usememos/memos), initially pinned to upstream
`v0.29.1`.

## Ownership boundary

- Memos remains the authority for Memo data, users, and permissions.
- `ai-service/` owns only AI-derived SQLite state.
- DevMemo additions communicate with Memos through the existing HTTP and
  Webhook boundaries; they do not establish a second permissions system.

## Synchronizing upstream

1. Fetch and review one upstream tag at a time.
2. Read upstream migration and security notes before merging it.
3. Resolve conflicts without moving AI-derived state into Memos storage.
4. Run Go, Web, and AI Service checks after every merge.
5. Record the resulting baseline and compatibility notes in the release notes.

Generic fixes that are useful to Memos without the DevMemo AI product layer
should be proposed upstream. DevMemo-specific AI behavior, documentation, and
deployment policy are maintained here.
