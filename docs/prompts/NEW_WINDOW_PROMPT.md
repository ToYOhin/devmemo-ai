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

当前默认阶段是 Phase 4b：索引可靠性与 Webhook 运维边界。Phase 4 RAG 最小切片已经完成，必须保持：
- 默认 deterministic + memory，低 CPU、无网络依赖。
- FastEmbed/Qdrant 只进入 adapters，不进入 domain/service。
- 当前一个完整 Memo 对应一个向量；RAG `/api/ai/chat` 已完成，但不加入 chunk、rerank 或前端聊天 UI。
- 原文只作为索引派生上下文，公共 citations 不返回内部 `content` 字段。
- 每个小步骤先测试；完成后更新状态、变更、交接和下一阶段 Prompt。
- 最终报告真实测试结果、未验证项、网络阻塞证据、commit 和下一个 Prompt。

如 Docker Desktop、Qdrant 和 Go 缓存可用，再运行：
.\scripts\verify-devmemo.ps1 -FullBackend
~~~
