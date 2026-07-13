# 下一阶段 Prompt：Phase 5e chunk 检索与可观测性收敛

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
- Phase 4 RAG、Webhook HMAC、SQLite outbox、有限 retry、ops token、告警、显式清理批准和审计。
- Phase 5a 离线 RetrievalEvaluator；Phase 5b provider-neutral MemoChunk；Phase 5c OfflineChunkIndex 对照。
- Phase 5d ChunkLifecycleCoordinator：显式 `AI_INDEX_ON_WEBHOOK=true` + `AI_INDEX_MODE=chunk` 时支持 create/update/delete、stale chunk 清理、空内容清理和 SQLite 状态持久化。
- 默认完整 Memo `memo-v1`、默认 deterministic + memory、Webhook `code=0`、公共 `POST /api/ai/chat` citation 契约保持不变。
- Phase 5d chunk Webhook 使用独立 InMemoryVectorStore；Qdrant chunk collection 尚未接入，避免 chunk 污染完整 Memo chat 检索。
- AI Service 当前测试为 142 passed；前端 131 tests、TypeScript/build、pnpm lint 和 Docker Compose config 已通过。
- 项目结构文档已按实际目录同步；继续以 `docs/structure.md` 的模块边界为准。

当前目标：实现 Phase 5e 的“chunk 检索与可观测性收敛”最小可验证切片。

本次只做：
1. 先检查 `ChunkLifecycleCoordinator`、`OfflineChunkIndex`、`RetrievalService`、`RetrievalEvaluator`、Webhook `index_status` 和 `/api/ai/index/health` 边界。
2. 选择一个最小切片：优先增加 provider-neutral chunk index health/status 统计，或增加显式 chunk 检索的离线/contract API；不要同时做 rerank 和混合检索。
3. 如果增加 HTTP 能力，必须显式声明 `index_mode`/`index_version`，默认仍返回完整 Memo 语义；不要直接改变公共 `/api/ai/chat` citations。
4. 覆盖 chunk create/update/delete 后的点数、状态缺失、版本隔离、失败降级和重启后的 SQLite 状态；默认测试不访问网络。
5. 真实 Qdrant/FastEmbed 仅作为显式 smoke；不要把它们变成默认启动依赖。

不要做：
- 不修改 Memos server/store/proto/web 核心。
- 不改变默认 `AI_INDEX_ON_WEBHOOK=false`、`AI_INDEX_MODE=memo`、Webhook `code=0`、AI_OPS_TOKEN、清理批准/审计和现有完整 Memo chat 契约。
- 不加入 rerank、BM25、混合检索、流式输出、聊天 UI、LangChain/LlamaIndex、Redis/Celery/Prometheus 或新的默认依赖。
- 不删除现有完整 Memo 向量、chunk 向量、AI SQLite 数据、Qdrant volume 或原始 Markdown。

实现要求：
- provider-neutral domain/service 不得导入 FastAPI、FastEmbed、qdrant-client、httpx 或 sqlite3 类型。
- chunk 与完整 Memo 必须继续由 `memo-chunk-v1`/`chunk` 和 `memo-v1`/`memo` 隔离。
- 失败时不得静默删除完整 Memo 索引；Webhook 继续返回 `code=0` 并给出可观测的 `index_status`。
- 每一步先测试，保持 deterministic + memory 的低 CPU 离线路径。

验证命令：
- powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\verify-devmemo.ps1
- cd ai-service; .\.venv\Scripts\python.exe -m pytest -q tests
- docker compose config --quiet
- cd web; pnpm lint
- cd web; pnpm test
- cd web; pnpm exec tsc --noEmit --skipLibCheck
- cd web; pnpm build
- git diff --check
- 如 Docker Desktop/Qdrant/Go 环境可用，再运行 .\scripts\verify-devmemo.ps1 -FullBackend

完成条件：
- 选定的 Phase 5e 小切片有清晰 provider-neutral 边界和 contract tests。
- AI Service、前端、TypeScript/build、pnpm lint、Go 全量和 Docker 配置真实结果被记录。
- 更新 docs/PROJECT_STATUS.md、docs/CHANGELOG_AI.md、docs/HANDOFF.md、docs/roadmap.md、docs/api.md、docs/structure.md、docs/DECISIONS.md。
- 更新本文件和 docs/prompts/NEW_WINDOW_PROMPT.md 的默认阶段描述。
- 形成独立 commit，报告真实验证结果、未验证项、阻塞证据和下一阶段 Prompt。

停止条件：
- 需要修改 Memos 核心 API、数据库或 Proto 时先停下报告影响。
- 需要默认启动外部服务、下载模型或删除现有向量才能继续时，保留 deterministic + memory 方案并报告。
- 如果新的 chunk 检索能力无法与完整 Memo citation 共存，停留在离线评估/health 边界，不替换公共 chat 契约。
~~~
