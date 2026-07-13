# DevMemo AI 单 Agent 接管交接

更新时间：2026-07-14

## 当前工作模式

项目已从多 Agent 并行切回单 Agent 推进。后续新窗口只使用 `H:\DevMemoAI` 主工作树，不启动 Terra/Luna 并行执行，不在多个 worktree 同时修改同一阶段。

`C:\Users\HP\Documents\project4\devmemo-ai-workspace` 中的 Terra/Luna worktree 保留为历史和回滚参考，但不属于当前开发路径。

## 仓库状态

- 主目录：`H:\DevMemoAI`
- 分支：`codex/devmemo-ai-mvp`
- 当前 HEAD：`3011431 feat(ai): add chunk index health contract`
- GitHub remote：`origin/codex/devmemo-ai-mvp` 已与本地同步
- 工作区：切换模式前已确认干净
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

## 当前未完成

Phase 5f 尚未完成：

1. Qdrant 独立 chunk collection 尚未接入 `ChunkLifecycleCoordinator`。
2. chunk-aware retrieval 尚未替换或修改公共 `POST /api/ai/chat`。
3. chunk citation 的公共 HTTP 契约尚未确定。

默认完整 Memo `memo-v1`、deterministic + memory、Webhook `code=0`、Memos 原有笔记/标签/搜索/编辑能力必须保持不变。

## 验证基线

```text
AI Service full pytest       144 passed
Frontend full tests          131 passed
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

直接复制 `docs/prompts/NEW_WINDOW_PROMPT.md` 到新窗口，或者执行 `docs/prompts/NEXT_STAGE_PROMPT.md` 的 Phase 5f 单 Agent Prompt。
