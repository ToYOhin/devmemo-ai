# 下一阶段 Prompt：Phase 7 public chunk API proposal

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
- Phase 5f/5g 已完成：独立 QDRANT_CHUNK_COLLECTION、ChunkRetrievalService 内部 contract、真实 Qdrant health/persistence smoke 和完整验证门禁均通过。
- Phase 6 已完成兼容性决策：公共 `POST /api/ai/chat` 继续使用完整 Memo `Citation`；`embedding_id`/`retrieved_count` 不改为 chunk 语义；不启用隐式 chunk mode，不新增未定义公共 chunk endpoint。
- 未来公开 chunk retrieval 必须先定义版本化 endpoint/response、chunk citation schema、同 Memo 去重、排序/上下文预算、content 脱敏、迁移/回滚和双路径 contract tests。
- 默认完整 Memo 是 memo-v1 + deterministic + memory；显式 chunk + qdrant 才使用独立 memo-chunk-v1 collection。

本阶段目标：
1. 只提出一个可评审的 public chunk API contract，不直接接入生产公共 chat。
2. 明确 endpoint/version、请求参数、响应字段、chunk citation 去重与排序、错误/降级、权限/敏感内容和 migration/rollback。
3. 若没有明确用户产品需求或兼容批准，停留在 ADR/API proposal 文档和 contract fixture，不新增公共 HTTP 行为。

允许修改：AI Service provider-neutral tests/services、contract fixtures、docs/PROJECT_STATUS.md、docs/CHANGELOG_AI.md、docs/HANDOFF.md、docs/handoffs/、docs/roadmap.md、docs/api.md、docs/structure.md、docs/DECISIONS.md 和本 Prompt。

禁止修改：Memos server/store/proto/web 核心；默认 AI_INDEX_ON_WEBHOOK=false、AI_INDEX_MODE=memo、AI_VECTOR_STORE=memory；现有公共 chat citation 和完整 Memo collection；不执行 docker compose down -v，不删除现有 collection 或 volume，不加入 rerank/BM25/混合检索/聊天 UI/LangChain/LlamaIndex/Redis/Celery/Prometheus/新默认依赖，不创建并行 Agent。

验证顺序：
- 如新增 contract fixture，先运行相关 AI tests，再运行 `cd ai-service; .\.venv\Scripts\python.exe -m pytest -q tests`
- powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\verify-devmemo.ps1
- docker compose config --quiet
- 如涉及 adapter/lifecycle，运行 deterministic chunk smoke
- 如环境允许，运行 `.\scripts\verify-devmemo.ps1 -FullBackend`；Go 全量可能需要较长时间
- git diff --check

完成条件：
- 形成可评审的 public chunk API proposal，或明确记录为什么继续等待产品/兼容批准。
- 不改变现有公共 chat 默认行为，不把内部 content 暴露到公共响应。
- 所有测试、未验证项和边界事实写入 PROJECT_STATUS/HANDOFF/handoff/changelog。
- 形成一个清晰 commit；不 push。
- 最终报告测试结果、未验证项、commit 和下一步。
~~~
