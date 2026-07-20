# DevMemo AI Phase 10 接管交接

更新时间：2026-07-20

## 从这里开始

在 `H:\DevMemoAI` 主工作树继续；单 Agent，不启动 Terra/Luna，也不在其他 worktree 修改当前阶段。先运行：

```powershell
Set-Location H:\DevMemoAI
git status --short --branch
git log --oneline -8
.\scripts\verify-devmemo.ps1
```

再读取 `docs/PROJECT_STATUS.md`、`docs/HANDOFF.md` 顶部和 `docs/prompts/NEXT_STAGE_PROMPT.md`。使用 `rg -n` 定向读取路线、API、结构和 ADR；不要载入所有历史阶段。

## 当前架构

- `server/`、`store/`、`proto/`、`internal/`：Memos upstream 核心，原始 Memo 与权限的事实源；当前阶段不修改。
- `ai-service/app/domain` 与 `services`：provider-neutral AI contract/编排；`adapters` 才可接入 FastEmbed/Qdrant。
- `ai-service` SQLite：仅 AI 派生数据（insights、模板、outbox、chunk state）；不写回 Memos 原文。
- `web/src/features/ai`：AI Inbox 与 Context Pack 产品入口。Context Pack 仅在浏览器内存生成，只使用安全 title/summary/source refs 和 accepted insight。

## 已完成的关键事实

- 默认路径仍是 deterministic + memory，完整 Memo `memo-v1`；Qdrant chunk 使用独立 `memo-chunk-v1` collection，只有显式配置才启用。
- 公共 `/api/ai/chat` 未改变，继续检索完整 Memo；内部 chunk retrieval 与其 citation 语义隔离。
- `public-chunk-v1` 已实现为 `POST /api/ai/v1/chunks/search`，但 `AI_PUBLIC_CHUNK_RETRIEVAL=false` 默认关闭。只有可信网关的 raw-body HMAC 与唯一 `visible_memo_ids` 才构成授权范围；关闭 flag 即可回滚。
- DevMemory Loop 已有 `MemoInsight` 的 preview/query/版本化 approve/reject，accepted-only Context Pack、显式跨 Memo 选择、delete/revoke 联动、Python/Web golden parity 与只读 lifecycle report。
- Context Pack 真实 Chrome 验收已完成：Markdown 与 JSON 都写入 Windows 系统剪贴板，JSON 可解析、来源可追溯；复制后的 React error boundary 已修复。

## 最近验证

- Low-CPU baseline: Memos/AI Service default caps are `0.75`/`0.25` CPU, Go/Memos and AI numerical threads use one processor, and Qdrant/Ollama are explicit profiles. Docker inspection, Compose config, AI health, and serial verify (`187 passed`) confirmed the applied settings; see `docs/handoffs/2026-07-20-low-cpu-baseline.md`. `verify-devmemo.ps1 -FullBackend` now uses `go test -p 1`.
- Phase 10 route B now has real local delivery evidence. The current authenticated Memos user created one Docker-network AI Service webhook after Compose enabled Memos' `--allow-private-webhooks`; an ordinary UI update to the existing non-sensitive test Memo resulted in a processed event, one persisted Insight, and the authorized accepted review at version `2`.
- The earlier zero-Insight conclusion was a host-path diagnostic mistake: the host-default CLI did not inspect the Compose volume. Use `docker compose exec -T ai-service python -m scripts.devmemory_lifecycle_report` for the live safe aggregate; after the run it reported eight processed events. The detailed evidence is `docs/handoffs/2026-07-20-devmemory-feedback-webhook-evidence.md`.
- AI Service normalizes Memos' `memos/<uid>` webhook resource name to the terminal detail-route UID, preventing an orphaned AI-derived state. Its focused regression passes; no Memos core, public chat, collection/volume, or public-chunk behavior changed.
- This is a technical Capture → Insight → accepted Review result only. Browser control became unavailable after a Vite restart, so new Context Pack budget/copy proof, delete/revoke, and qualitative feedback remain unverified. Do not create another test Memo or fabricate those results.
- Vite now accepts `DEV_PROXY_SERVER` from ignored `.env.local` using `loadEnv`; copy `web/.env.example` for the local Compose addresses. Keep credentials and secrets out of that file.
- Fresh same-profile Chrome tab recovery has since confirmed the accepted Insight and `max_chars=64` Context Pack truncation with no console error. Automation clicks did not alter the Windows clipboard, so Markdown/JSON copy is still unverified rather than failed; see `docs/handoffs/2026-07-20-devmemory-context-pack-browser-evidence.md`.
- Phase 10 gateway contract evidence: `python -m scripts.public_chunk_gateway_contract_smoke` passed with disabled `503`, missing/tampered signature `401`, ambiguous scope `422`, degraded `503`, and authorized/redacted/deduplicated `200`; related public-chunk tests: `8 passed` with one existing Starlette/httpx deprecation warning.
- Full gate after this slice: AI Service `187 passed`; Web `33 files / 149 passed`, build, and project `pnpm lint` passed. Standalone strict `pnpm exec tsc --noEmit` is blocked by 13 existing dependency declaration and `src/types/view.d.ts` errors; this slice has no web/dependency changes and the project's `--skipLibCheck` lint type-check passed.
- The script is in-process TestClient + fake coordinator only: it starts no server, makes no network call, and outputs no temporary secret. It is not trusted-gateway/deployment/canary proof; the default flag remains off and real permission mapping plus rollback drill are unverified.
- AI Service 全量：186 passed（历史完整门禁，保留一个既有弃用警告）。
- Web：33 个测试文件 / 149 passed；TypeScript、lint 通过。
- Context Pack Chrome 验收：Markdown 512 字符，JSON 1,699 字符；两者均由 Windows `Get-Clipboard` 证实含预期来源。
- 近期只改 Web 复制兼容性和文档；未重跑后端完整门禁。提交前按改动范围重新验证。

## 下一步只选一个切片

1. Real controlled gateway rollout: only with an actual gateway, Memos visibility mapping, and rollback conditions, verify deployed raw-body HMAC, failures, dedupe, redaction, and flag rollback. The browser must never sign or hold the secret.
2. DevMemory 人工反馈：复用既有测试 Memo，在稳定登录态与真实参与者下完成尚未验证的 Context Pack 预算、Markdown/JSON 复制和四项简短反馈。不得为了补证据删除/撤销，也不得创建第二条 Memo。

不要同时推进两条；不增加 Agent、MCP、网页搜索、图数据库、Redis/Celery 或默认新依赖。

## 已知问题与边界

- Graphify 的历史图不包含近期 `AiMemoInsights`/`AiMemoContextPack`，并可能把 “Inbox” 指向 Memos `store/inbox.go`；先用源码与 `docs/structure.md`，图谱重建可作为独立维护切片。
- AI Inbox 仍是 Memo 详情页功能，不是全局 Inbox；Context Pack 双实现已由 golden 防漂移，但未来语义改动必须先更新共享 fixture。
- public-chunk-v1 没有真实可信网关/灰度证据前必须保持关闭；离线/contract 测试不是 rollout pass。

## 建议使用的 skills

- `graphify`：只在重建或查询更新后的结构图时使用。
- `incremental-implementation`：选择一个小切片并按测试先行推进。
- `code-review-and-quality`：在 gateway 或权限边界改动后复核。
- `handoff`：阶段结束时生成临时交接副本，同时同步本仓库的状态与 Prompt。
