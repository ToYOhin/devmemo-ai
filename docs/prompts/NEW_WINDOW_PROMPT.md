# 新窗口启动 Prompt

~~~text
继续 H:\DevMemoAI 的 DevMemo AI 项目，不要从零设计。

第一步读取：
1. docs/PROJECT_STATUS.md
2. docs/HANDOFF.md
3. docs/roadmap.md
4. docs/structure.md
5. docs/DOC_UPDATE_POLICY.md
6. docs/DECISIONS.md
7. docs/api.md
8. docs/prompts/NEXT_STAGE_PROMPT.md

然后执行：
Set-Location H:\DevMemoAI
git status --short --branch
git log --oneline -8
 .\scripts\verify-devmemo.ps1

当前协作模式：单 Agent。只在 `H:\DevMemoAI` 主工作树推进；不要启动 Terra/Luna，不要同时操作 `project4` 下的其他 worktree。每次只完成一个最小垂直切片，先测试后扩大范围，最终由当前 Agent 更新文档、提交 commit；只有用户明确要求时才 push。

先阅读交接快照：`docs/handoffs/2026-07-14-single-agent-handoff.md`。

当前默认阶段是 Phase 5f：Qdrant chunk 持久化与显式 chunk 检索。Phase 4/4b/4c/4d/4e/4f/4g/5a/5b/5c/5d/5e 的 RAG、HMAC、outbox、显式有限重试、ops 安全、保留预览、告警轮询、显式清理批准、审计、离线检索评估、纯函数 chunking、OfflineChunkIndex、显式 chunk 生命周期和 chunk health 已经完成，必须保持：
- 默认 deterministic + memory，低 CPU、无网络依赖。
- FastEmbed/Qdrant 只进入 adapters，不进入 domain/service。
- 当前默认生产路径一个完整 Memo 对应一个向量；只有 `AI_INDEX_ON_WEBHOOK=true` + `AI_INDEX_MODE=chunk` 才启用 `ChunkLifecycleCoordinator`，并通过 `memo-chunk-v1` 与 `memo-v1` 隔离；RAG `/api/ai/chat` 已完成，但不加入 rerank 或前端聊天 UI。
- `GET /api/ai/index/chunk-health` 只读统计 isolated chunk store 与 SQLite state；当前 chunk store 仍是 memory，Qdrant chunk collection 尚未接入。
- 原文只作为索引派生上下文，公共 citations 不返回内部 `content` 字段。
- Webhook HMAC 只有显式配置 `AI_WEBHOOK_SECRET` 才启用，默认保持旧 `code=0` 行为。
- Webhook outbox 只做 SQLite 幂等记录、有限显式 retry 和基础状态查询，默认不启动 worker 或自动重试。
- Ops API 可选 `AI_OPS_TOKEN`；配置后使用 `X-DevMemo-Ops-Token`，公开响应不返回原始 payload。
- Retention preview 只读；alerts 只读轮询，不主动推送、不自动删除、不修改 Qdrant/AI volume。
- 每个小步骤先测试；完成后更新状态、变更、交接和下一阶段 Prompt。
- 不使用多 Agent 并行；不要把同一接口拆给多个窗口重复实现。
- 最终报告真实测试结果、未验证项、网络阻塞证据、commit 和下一个 Prompt。

如 Docker Desktop、Qdrant 和 Go 缓存可用，再运行：
.\scripts\verify-devmemo.ps1 -FullBackend
~~~
