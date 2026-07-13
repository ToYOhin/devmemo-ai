# 下一阶段 Prompt：Phase 5d 可选 chunk 索引生命周期

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
- Phase 5b：provider-neutral MemoChunk、chunk_memo、稳定 chunk ID、memo-chunk-v1/index_mode metadata 和生命周期 contract。
- Phase 5c：OfflineChunkIndex 使用 deterministic + memory 构造独立 chunk 试验索引，并与完整 Memo baseline 做离线 Recall@K 对照；不接入生产索引。
- 当前 AI Service 测试为 133 passed；默认 Compose 仍 deterministic + memory，没有后台 worker 或外部队列。

当前目标：实现 Phase 5d 的“可选 chunk 索引生命周期”最小可验证切片。

本次只做：
1. 先检查 MemoChunk、OfflineChunkIndex、MemoIndexDocument、EmbeddingService、VectorStore、Webhook create/update/delete、RetrievalService 和 Phase 5a evaluator 契约。
2. 选择一个显式 opt-in 的生命周期边界：建议新增 provider-neutral chunk lifecycle coordinator，或在 AI Service 内部增加明确的 `memo|chunk` 模式组合；默认仍使用完整 Memo `memo-v1`。
3. 覆盖 create/update/delete：当前 chunk 先 upsert；更新后显式删除旧尾部 chunk；删除 Memo 删除该版本全部 chunk；重复 webhook/event 不重复处理。
4. 明确 `index_version=memo-v1|memo-chunk-v1`、`index_mode=memo|chunk`、chunk citation 和失败降级契约；不要改变公共 POST `/api/ai/chat` 的完整 Memo citation 响应。
5. 只在 deterministic + memory 和不访问网络的 contract tests 中启用 chunk mode；如果要增加配置，默认必须为完整 Memo 且启动不依赖 Qdrant/FastEmbed。

不要做：
- 不修改 Memos server/store/proto/web 核心。
- 不改变默认 `AI_INDEX_ON_WEBHOOK=false`、Webhook `code=0`、AI_OPS_TOKEN、清理批准/审计或现有完整 Memo `memo-v1` 行为。
- 不接入默认 Qdrant/FastEmbed，不改变 Compose 默认 deterministic + memory，不删除既有向量、AI SQLite 数据或原始 Markdown。
- 不加入 rerank、混合检索、BM25、聊天 UI、流式输出或外部评估平台。
- 不引入 LangChain、LlamaIndex、Redis、Celery、Prometheus 或新的默认依赖。

实现要求：
- provider-neutral domain/service 不得导入 FastAPI、FastEmbed、qdrant-client、httpx 或 sqlite3 类型。
- 生产完整 Memo 与 chunk 试验必须通过 version/mode 显式隔离，能够安全回滚，不用覆盖同名 embedding ID。
- 失败时保留现有 Webhook code=0 降级和完整 Memo 读取；chunk mode 不可用时不得静默删除完整 Memo 索引。
- 每一步先测试，保持小 commit；先 fake/offline contract，再考虑真实 provider smoke。

验证命令：
- powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\verify-devmemo.ps1
- cd ai-service; .\.venv\Scripts\python.exe -m pytest -q tests
- docker compose config --quiet
- cd web; pnpm lint
- cd web; pnpm test
- cd web; pnpm exec tsc --noEmit --skipLibCheck
- cd web; pnpm build
- git diff --check

完成条件：
- chunk create/update/delete 生命周期、版本/模式隔离和失败降级有清晰 provider-neutral contract tests。
- 默认完整 Memo 索引、RAG chat、Webhook、outbox、前端和 Docker 契约不回归。
- AI Service 测试、前端 131 tests、TypeScript/build、Go 全量和 Docker 配置真实结果被记录。
- 更新 docs/PROJECT_STATUS.md、docs/CHANGELOG_AI.md、docs/HANDOFF.md、docs/roadmap.md、docs/api.md、docs/structure.md、docs/DECISIONS.md。
- 更新本文件和 docs/prompts/NEW_WINDOW_PROMPT.md 的默认阶段描述。
- 形成独立 commit，报告真实验证结果、未验证项、阻塞证据和下一阶段 Prompt。

停止条件：
- 需要修改 Memos 核心 API、数据库或 Proto 时先停下报告影响。
- 需要默认启动外部服务、下载模型或删除现有向量才能继续时，保留 deterministic + memory 方案并报告。
- chunk mode 无法与完整 Memo citation 或 Webhook code=0 共存时，停留在 OfflineChunkIndex，不接入生产生命周期。
~~~
