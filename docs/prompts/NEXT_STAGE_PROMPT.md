# 下一阶段 Prompt：Phase 8 public chunk API implementation gate

~~~text
继续 H:\DevMemoAI 的 DevMemo AI 项目，不要从零设计。

协作模式：单 Agent。只使用 H:\DevMemoAI 主工作树；不要启动 Terra/Luna，不要同时操作 project4 下的其他 worktree。默认快速推进；只有用户明确要求时才 push。

先读取：
1. docs/handoffs/2026-07-14-single-agent-handoff.md
2. docs/PROJECT_STATUS.md
3. docs/HANDOFF.md 顶部当前阶段
4. 本文件
5. git status --short --branch 与 git log --oneline -8

当前事实：
- Phase 5f/5g 已完成：独立 QDRANT_CHUNK_COLLECTION、ChunkRetrievalService 内部 contract、真实 Qdrant smoke 和完整验证门禁均通过。
- Phase 6 已决定不改变现有 `POST /api/ai/chat`；Phase 7 已形成未实现的 public chunk API proposal：`POST /api/ai/v1/chunks/search` / `public-chunk-v1`。
- 提案固定 `memo-chunk-v1`，请求为 question + limit(1–10)，同 Memo 只保留最高分 chunk，按 score/memo_id/chunk_index/chunk_id 确定性排序，metadata 脱敏，不返回 content。
- 提案默认 `AI_PUBLIC_CHUNK_RETRIEVAL=false`，要求网关认证和 Memo 权限；错误为 422/503；迁移采用离线双路径评估、feature-flag 灰度和关闭 flag 回滚。
- 公共 `POST /api/ai/chat`、完整 Memo `memo-v1`、默认 deterministic + memory 继续不变。

本阶段目标：
1. 只有在获得明确产品/兼容批准后，才实现提案 endpoint；如果没有批准，继续停在 proposal，不新增公共 HTTP 行为。
2. 若获批准，先增加 contract fixture/tests，再实现独立 route/service，接入 explicit chunk store，不复用公共 chat 的 CitationResponse。
3. 运行时必须保持默认关闭、content 不出公共 response、完整 Memo chat 不回归，并具备禁用 flag 的回滚路径。

禁止修改：Memos server/store/proto/web 核心；默认 AI_INDEX_ON_WEBHOOK=false、AI_INDEX_MODE=memo、AI_VECTOR_STORE=memory；现有公共 chat citation 和完整 Memo collection；不执行 docker compose down -v，不删除 collection/volume，不加入 rerank/BM25/混合检索/聊天 UI/LangChain/LlamaIndex/Redis/Celery/Prometheus/新默认依赖，不创建并行 Agent。

验证顺序：
- 先运行相关 contract tests，再运行 `cd ai-service; .\.venv\Scripts\python.exe -m pytest -q tests`
- powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\verify-devmemo.ps1
- docker compose config --quiet
- 如涉及 Qdrant adapter/lifecycle，运行 deterministic chunk smoke
- 如环境允许，运行 `.\scripts\verify-devmemo.ps1 -FullBackend`；Go 全量可能需要较长时间
- git diff --check

完成条件：
- 未获批准时，明确记录 proposal 保持未实现；获批准时，形成独立实现 commit。
- 所有测试、未验证项、权限/脱敏和回滚事实写入 PROJECT_STATUS/HANDOFF/handoff/changelog。
- 不改变现有公共 chat 默认行为，不把内部 content 暴露到公共响应。
- 不 push；最终报告真实测试结果、未验证项、commit 和下一步。
~~~
