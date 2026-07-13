# 下一阶段 Prompt：Phase 5c chunk 离线检索评估

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
- Phase 5a：provider-neutral 离线 RetrievalEvaluator，支持 Recall@K、相关 Memo 命中列表和首个相关结果排名。
- Phase 5b：provider-neutral MemoChunk、chunk_memo、稳定 chunk ID、memo-chunk-v1/index_mode metadata 和生命周期 contract；未接入生产索引。
- 当前 AI Service 测试为 129 passed；默认 Compose 仍 deterministic + memory，没有后台 worker 或外部队列。

当前目标：实现 Phase 5c 的“chunk 离线检索评估”最小可验证切片。

本次只做：
1. 先检查 MemoChunk、chunk_memo、MemoIndexDocument、EmbeddingService、VectorStore、RetrievalService 和 Phase 5a evaluator 契约。
2. 选择一个 provider-neutral 离线试验边界：用 deterministic + InMemoryVectorStore 构造 chunk 试验索引，并与完整 Memo 基线做 Recall@K/首个命中排名对照。
3. 如果现有 EmbeddingService 的 Memo 级稳定 ID 不适合 chunk 试验，增加独立的 offline chunk indexing helper；不要改变现有 Memo embedding_id 或 delete_memo 契约。
4. 评估 fixture 必须明确 chunk citation 的 memo_id、chunk_id、chunk_index、index_version 和原始内容上下文；公共 POST /api/ai/chat 仍只返回完整 Memo citation。
5. 只增加不访问网络的 unit/contract tests；不得把 chunk 试验接入默认 Webhook、Qdrant、FastEmbed、Compose 或生产 chat。

不要做：
- 不修改 Memos server/store/proto/web 核心。
- 不修改默认 AI_INDEX_ON_WEBHOOK 行为、完整 Memo memo-v1 索引或现有 embedding_id/delete_memo 契约。
- 不加入 rerank、混合检索、BM25、聊天 UI、流式输出或外部评估平台。
- 不引入 LangChain、LlamaIndex、Redis、Celery、Prometheus 或新的默认依赖。
- 不下载模型、访问外部服务、修改 Qdrant collection 或删除现有向量/AI SQLite 数据。

实现要求：
- provider-neutral domain/service 不得导入 FastAPI、FastEmbed、qdrant-client、httpx 或 sqlite3 类型。
- 保持 `memo-v1` 完整 Memo 索引与 `memo-chunk-v1` 试验索引显式隔离。
- 评估器复用 Phase 5a 指标，不新增公共 HTTP API；错误和空 fixture 有明确 contract。
- 每一步先测试，保持小 commit；如果 chunk 结果无法与完整 Memo citation 共存，停留在离线 fixture，不接入生产路径。

验证命令：
- powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\verify-devmemo.ps1
- cd ai-service; .\.venv\Scripts\python.exe -m pytest -q tests
- docker compose config --quiet
- cd web; pnpm test
- cd web; pnpm exec tsc --noEmit --skipLibCheck
- cd web; pnpm build
- git diff --check

完成条件：
- chunk 离线试验索引和完整 Memo 基线对照有清晰 provider-neutral 边界与 contract tests。
- Phase 5a evaluator 指标继续可用；默认完整 Memo 索引、RAG chat、Webhook、outbox、前端和 Docker 契约不回归。
- AI Service 测试、前端 131 tests、Go 全量和 Docker 配置真实结果被记录。
- 更新 docs/PROJECT_STATUS.md、docs/CHANGELOG_AI.md、docs/HANDOFF.md、docs/roadmap.md、docs/api.md、docs/structure.md、docs/DECISIONS.md。
- 更新本文件和 docs/prompts/NEW_WINDOW_PROMPT.md 的默认阶段描述。
- 形成独立 commit，报告真实验证结果、未验证项、阻塞证据和下一阶段 Prompt。

停止条件：
- 需要修改 Memos 核心 API、数据库或 Proto 时先停下报告影响。
- 需要生产 Webhook/Qdrant/FastEmbed 接入或删除既有向量才能继续时，保留 offline fixture 并报告，不扩大范围。
- 如果 chunk citation 无法与现有完整 Memo citation 契约清晰共存，不修改 POST /api/ai/chat。
~~~
