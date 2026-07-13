# 下一阶段 Prompt：Phase 5b Memo chunking 边界

将下面整段复制到新的 Codex 窗口或下一次任务中：

~~~text
你正在继续 H:\DevMemoAI 的 DevMemo AI 项目。

先读取以下真相源：
- docs/PROJECT_STATUS.md
- docs/HANDOFF.md
- docs/roadmap.md
- docs/structure.md
- docs/DOC_UPDATE_POLICY.md
- docs/DECISIONS.md
- docs/api.md
- docs/oss-adoption.md
- git status --short --branch
- git log --oneline -8

当前已完成：
- Phase 4 RAG：RetrievalService 和 POST /api/ai/chat，默认 deterministic + memory。
- Phase 4b/4c/4d/4e/4f/4g：Webhook HMAC、SQLite outbox、有限 retry、ops token、告警、显式清理批准和审计。
- Phase 5a：provider-neutral 离线 RetrievalEvaluator，支持 Recall@K、相关 Memo 命中列表和首个相关结果排名；不改变现有索引或 HTTP API。
- 当前 AI Service 测试为 116 passed；默认 Compose 仍 deterministic + memory，没有后台 worker 或外部队列。

当前目标：实现 Phase 5b 的“Memo chunking 边界”最小可验证切片。

本次只做：
1. 先检查 MemoIndexDocument、EmbeddingService、VectorStore、Webhook create/update/delete、RetrievalService 和 Phase 5a 评估契约。
2. 定义 provider-neutral `MemoChunk`/chunk document 和稳定 chunk ID；不先接真实模型或修改 Qdrant adapter。
3. 设计明确的 `index_version`/mode metadata，使完整 Memo 索引与 chunk 试验可以共存或安全回滚。
4. 只实现纯函数/内存边界和 unit/contract tests；默认不改变现有 `AI_INDEX_ON_WEBHOOK` 行为，不自动切换生产索引模式。
5. 评估更新、删除、空内容、超长内容、重复 chunk ID 和原始 Markdown 保留契约。

不要做：
- 不把 chunking 直接接入默认 Webhook、Compose、Qdrant 或 FastEmbed 生产路径。
- 不同时加入 rerank、混合检索、BM25、聊天 UI、流式输出或外部评估平台。
- 不修改 Memos server/store/proto/web 核心，不删除既有完整 Memo 向量或 AI SQLite 数据。
- 不引入 LangChain、LlamaIndex、Redis、Celery、Prometheus 或新的默认依赖。
- 不改变 Webhook code=0、AI_OPS_TOKEN、清理审批/审计和 `/api/ai/chat` 响应契约。

验证命令：
- powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\verify-devmemo.ps1
- cd ai-service; .\.venv\Scripts\python.exe -m pytest -q tests
- docker compose config --quiet
- cd web; pnpm test
- cd web; pnpm exec tsc --noEmit --skipLibCheck
- cd web; pnpm build
- git diff --check

完成条件：
- Memo chunk provider-neutral 边界、稳定 ID、metadata/version 和生命周期测试通过。
- 默认完整 Memo 索引、RAG chat、Webhook、outbox、前端和 Docker 契约不回归。
- 原有 AI Service 116 个测试、前端 131 个测试、Go 全量和 Docker 配置通过。
- 更新 docs/PROJECT_STATUS.md、docs/CHANGELOG_AI.md、docs/HANDOFF.md、docs/roadmap.md、docs/api.md、docs/structure.md、docs/DECISIONS.md。
- 更新本文件和 docs/prompts/NEW_WINDOW_PROMPT.md 的默认阶段描述。
- 形成独立 commit，报告真实验证结果、未验证项、阻塞证据和下一阶段 Prompt。

停止条件：
- 如果 chunking 无法与现有完整 Memo 索引共存，保留纯函数/评估边界，不接入生产路径。
- 需要修改 Memos 核心 API、数据库或 Proto 时先停下报告影响。
- 需要下载模型、访问外部服务或删除现有向量才能验证时，先保留 fake/offline 路线并记录证据。
~~~
