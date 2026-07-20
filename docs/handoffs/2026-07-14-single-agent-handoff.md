# DevMemo AI 单 Agent 接管交接

更新时间：2026-07-20（Phase 9f golden parity 与本地只读诊断最小切片后更新）

## 当前工作模式

项目已从多 Agent 并行切回单 Agent 推进。后续新窗口只使用 `H:\DevMemoAI` 主工作树，不启动 Terra/Luna 并行执行，不在多个 worktree 同时修改同一阶段。

`C:\Users\HP\Documents\project4\devmemo-ai-workspace` 中的 Terra/Luna worktree 保留为历史和回滚参考，但不属于当前开发路径。

## 仓库状态

- 主目录：`H:\DevMemoAI`
- 分支：`codex/devmemo-ai-mvp`
- 当前 HEAD：以 `git log --oneline -8` 为准；本轮人工验收修复与文档已纳入当前交接，用户未提交的 Prompt 文件仍需保留
- GitHub remote：本轮只形成本地 commit，未经用户明确要求不 push；以远端分支和提交校验为准
- 工作区：保留用户已有的 `docs/prompts/NEW_WINDOW_PROMPT.md` 未提交修改
- Memos 基线：v0.29.1
- Go：`G:\Go`；工作区/缓存：`G:\GoWorkspace`

## 已完成能力

- Phase 1/2：AI 摘要、Code Snippet、Bug Report 模板和前端展示/复制。
- Phase 3a-3g：provider-neutral embedding/vector store、FastEmbed、Qdrant adapter、真实 smoke、volume 重启、缓存治理和 health/degraded 边界。
- Phase 4-4g：RAG 引用问答、Webhook HMAC、SQLite outbox、显式有限重试、ops token、告警、保留预览、显式清理批准和审计。
- Phase 5a：离线 RetrievalEvaluator。
- Phase 5b：MemoChunk、稳定 chunk ID、版本隔离。
- Phase 5c：OfflineChunkIndex 离线对照。
- Phase 5d：显式 chunk Webhook 生命周期和 SQLite 状态。
- Phase 5e：GET `/api/ai/index/chunk-health`，只读返回 chunk 点数、SQLite tracked 状态和 degraded 信息。

## 实际结构

- `cmd/`、`server/`、`store/`、`internal/`、`proto/`：Memos Go 核心，继续保持不修改。
- `web/src/features/ai/`：React AI API client、React Query hooks、模板和摘要 UI。
- `ai-service/app/domain/`：Embedding、VectorStore、MemoChunk、Retrieval 等 provider-neutral 类型。
- `ai-service/app/services/`：索引、检索、chunk lifecycle、Webhook security、评估和编排。
- `ai-service/app/adapters/`：deterministic/FastEmbed、memory/Qdrant、SQLite chunk state adapter。
- `ai-service/database.py`：AI Service 自有 SQLite，包含 ai_notes、memo_templates、outbox、chunk state 和 cleanup audit。
- `ai-service/main.py`：FastAPI HTTP/Webhook 边界；旧的 `embedding.py`、`rag.py` 仍保留兼容入口。
- `docs/`：状态、路线、API、结构、决策、交接和下一阶段 Prompt。

## 当前已完成与未完成

Phase 5f 代码切片、Phase 5g rollout gate、Phase 6 compatibility decision、Phase 7 public API proposal、Phase 9a AI Inbox、Phase 9b Context Pack contract、Phase 9c integration gate 和 Phase 9d UI 已完成；Phase 8 implementation gate 仍 pending approval：

- 已完成 collection/config 与 composition：`QDRANT_CHUNK_COLLECTION` 默认 `devmemo_memo_chunks`，仅 chunk + qdrant 显式组合时使用，其他路径仍是独立 memory。
- fake composition/health contract 已覆盖独立 collection、provider/status 传播和默认不连接 Qdrant。
- `ChunkRetrievalService`、`ChunkCitation`、`ChunkRetrievalResult` 已落地；严格校验 `memo-chunk-v1` metadata，原文仅用于服务端 context。
- `scripts/smoke_qdrant.py --mode chunk` 已覆盖 health、重新连接后的 point_count/检索持久性、内部 retrieval contract 和 delete。

1. 显式 Qdrant health/persistence smoke 已通过：启动 Docker Desktop/Qdrant 后运行 deterministic chunk smoke，返回 `QDRANT_CHUNK_SMOKE_OK`；初始/重连 point_count=2，删除后为 1，临时 collection 已清理。
2. 完整门禁已通过：AI Service 153 passed；前端 131 passed；TypeScript/build/lint、Compose config 和 Go `go test -p 2 ./...` 通过，`store/test` 用时 168.864s。
3. Phase 6 决定 chunk-aware retrieval 继续保持内部 contract，未替换或修改公共 `POST /api/ai/chat`。
4. Phase 7 只形成 `POST /api/ai/v1/chunks/search` / `public-chunk-v1` 提案，默认关闭、同 Memo 保留最高分 chunk、脱敏 metadata；未新增运行时代码或公共路由。
5. 当前没有明确产品/兼容批准，Phase 8 不实现 endpoint；批准前保持 proposal、公共 chat 和完整 Memo collection 不变。

6. Phase 9a 已新增 `MemoInsight` contract、deterministic 提取器、AI SQLite `memo_insights` 幂等表，以及 preview/查询/版本化 approve/reject API；语义变化重置 pending，过期版本返回 409。
7. Memo 详情页已接入 AI Inbox 卡片；真实 Compose API Bug Report smoke 生成 bug/action 并完成批准；Playwright 截图 artifact 为 `devmemo-phase9-ai-inbox.png`。
8. Phase 9a 验证：AI Service 162 passed；前端 136 passed；TypeScript/build/lint 和 Compose API smoke 通过。下一阶段只做 bounded Context Pack contract/fixture，不实现 agent、网页搜索或 MCP。

9. Phase 9b 已新增 `context-pack-v1` domain contract 和纯函数 `build_context_pack`；显式 Memo/insight 选择、accepted 状态、同 Memo/source 去重、确定性排序、Markdown 字符预算、JSON/Markdown 一致性均有测试。
10. Phase 9b 验证：定向 Context Pack 12 passed；AI Service 全量 174 passed，保留 1 个 Starlette/httpx 弃用警告；未新增 HTTP、Qdrant 或公共 chat 行为。

11. Phase 9c integration gate 已完成 proposal-only 评审：推荐 Memo 详情页 AI Inbox 的 `Copy Context Pack`，默认当前 Memo，跨 Memo 显式选择。
12. Phase 9d 已实现 `AiMemoContextPack` 与 Web `contextPack` adapter：question、预算、accepted 来源勾选、Markdown/JSON copy、sources、截断、empty/failure/copy-error 和窄屏布局；pack 只在内存生成，不新增 HTTP/SQLite/Qdrant/worker。
13. Phase 9d Web 定向 7 passed、全量 143 passed；TypeScript/build/lint 通过；Playwright 已登录并完成 approve insight、复制、`max_chars` 截断和 390px 窄屏，截图 artifact 为 `devmemo-phase9d-context-pack-desktop.png`、`devmemo-phase9d-context-pack-mobile.png`。
14. Phase 9e 已新增共享 `contracts/context-pack-v1.json`，Web 使用当前用户可见 Memo 列表提供显式跨 Memo 选择；默认仍只选当前 Memo，只有 accepted insight 进入 pack，额外查询失败显示不可用提示。
15. Phase 9e Memos deleted Webhook 已清理 AI 自有 `ai_notes`、`memo_templates`、`memo_insights`、`memo_chunk_index_state`；reject 是 revoke 语义，版本递增/查询失效后不会继续进入 pack；不触碰 Memos 原文、公共 chat、Qdrant volume。
16. 本轮人工验收修复了 canonical/raw Memo ID 重复来源、清空来源后无法重新勾选和删除联动遗漏；In-App Browser 禁用两种剪贴板 API，copy 仍需真实 Chrome 复验。
17. Phase 9f minimum slice completed: the shared fixture now includes expected Markdown and canonical compact snake_case JSON golden cases. Python and Web assert byte-for-byte output parity; the tests caught and fixed one Web trailing-newline mismatch.
18. `python -m scripts.devmemory_lifecycle_report` is a local read-only diagnostic over AI-owned SQLite aggregates. It uses SQLite `mode=ro`, creates no missing DB, has no HTTP/worker/telemetry behavior, and never prints IDs, raw content, webhook payloads, or secrets.

默认完整 Memo `memo-v1`、deterministic + memory、Webhook `code=0`、Memos 原有笔记/标签/搜索/编辑能力必须保持不变。

## 验证基线

```text
AI Service full pytest      179 passed
Context Pack focused pytest 12 passed
Frontend full tests          149 passed
pnpm lint                    PASS
TypeScript/build             PASS
Go full test -p 2 ./...      PASS
verify-devmemo.ps1           DEVMEMO_VERIFY_OK
docker compose config        PASS
git diff --check             PASS
Qdrant/FastEmbed smoke       PASS（历史显式 smoke）
```

## 单 Agent 接管步骤

1. 先读取本文件、`docs/PROJECT_STATUS.md`、`docs/HANDOFF.md` 顶部和 `docs/prompts/NEXT_STAGE_PROMPT.md`，恢复核心上下文。
2. 执行 `git status --short --branch` 和 `git log --oneline -8`。
3. 用 `rg -n` 从 roadmap/structure/DECISIONS/api/oss 文档中定向读取当前切片所需段落，不加载全部历史阶段。
4. 只选择一个最小垂直切片。
5. 先做 contract/adapter，再做 service/API，再做真实 smoke；每个阶段先测试。
6. 完成后更新 `PROJECT_STATUS`、`CHANGELOG_AI`、`HANDOFF`、`NEXT_STAGE_PROMPT`，必要时同步 API/结构/决策/路线文档。
7. 运行验证门禁，形成独立 commit；只有用户明确要求时再 push。

## 下一入口

直接复制 `docs/prompts/NEW_WINDOW_PROMPT.md` 到新窗口；继续保持 Phase 8 gate pending approval，再执行 `docs/prompts/NEXT_STAGE_PROMPT.md` 的 Phase 9f Context Pack lifecycle observation Prompt。
