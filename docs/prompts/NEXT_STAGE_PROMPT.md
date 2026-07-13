# 下一阶段 Prompt：Phase 5f Qdrant chunk 持久化与显式 chunk 检索

~~~text
你正在继续 H:\DevMemoAI 的 DevMemo AI 项目。

协作模式：单 Agent。只使用 `H:\DevMemoAI` 主工作树；不要启动 Terra/Luna，不要同时操作 `project4` 下的其他 worktree。你负责分析、实现、测试、文档、commit 和最终报告。

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

另外读取：
- docs/handoffs/2026-07-14-single-agent-handoff.md

当前已完成：
- Phase 4 RAG、Webhook HMAC、SQLite outbox、有限 retry、ops token、告警、显式清理批准和审计。
- Phase 5a RetrievalEvaluator；Phase 5b MemoChunk；Phase 5c OfflineChunkIndex；Phase 5d ChunkLifecycleCoordinator。
- Phase 5e 新增 GET `/api/ai/index/chunk-health`，返回 chunk mode/version、VectorStore point_count、SQLite tracked_memos/tracked_chunks 和 degraded detail。
- 默认完整 Memo `memo-v1`、默认 deterministic + memory、Webhook `code=0`、公共 `POST /api/ai/chat` citation 契约保持不变。
- 当前 chunk Webhook 使用独立 InMemoryVectorStore；Qdrant chunk collection 尚未接入。
- AI Service 当前测试为 144 passed；前端 131 tests、TypeScript/build、pnpm lint、Go 全量和 Docker Compose config 已通过上一阶段验证。

当前目标：实现 Phase 5f 的“Qdrant chunk 持久化与显式 chunk 检索”最小可验证切片。

执行顺序：先完成 collection/config contract 和 fake tests，再接入 chunk composition，再完成内部 retrieval contract，最后进行显式 Qdrant smoke；任何一步失败先修复或记录阻塞，不跨步扩大范围。

本次只做：
1. 先检查 QdrantVectorStore、ChunkLifecycleCoordinator、chunk-health、AI_VECTOR_STORE/AI_INDEX_MODE 配置和现有完整 Memo collection 命名。
2. 为 chunk mode 设计独立 collection 名称/版本/维度/距离函数；不得复用或污染完整 Memo `devmemo_memos` collection。
3. 增加 provider-neutral chunk store composition：默认仍使用独立 memory；只有显式 `AI_INDEX_MODE=chunk` + `AI_VECTOR_STORE=qdrant` 才连接独立 Qdrant collection。
4. 让 chunk-health 在显式 Qdrant chunk 模式下读取真实 collection 状态；Qdrant 不可用时返回 degraded/明确错误，不影响默认 memory 和完整 Memo chat。
5. 增加最小显式 chunk retrieval contract（优先内部 service/测试边界；如增加 HTTP，必须声明 `index_mode=chunk` 和 `index_version=memo-chunk-v1`），不要直接改变公共 `/api/ai/chat` citations。
6. 覆盖 fake client contract、collection 隔离、create/update/delete、重启持久化 smoke；默认单元测试不得访问网络。

不要做：
- 不修改 Memos server/store/proto/web 核心。
- 不改变默认 `AI_INDEX_ON_WEBHOOK=false`、`AI_INDEX_MODE=memo`、`AI_VECTOR_STORE=memory`、Webhook `code=0`、AI_OPS_TOKEN、清理批准/审计和完整 Memo chat 契约。
- 不删除或重命名现有完整 Memo Qdrant collection，不执行 `docker compose down -v`，不删除用户 volume。
- 不加入 rerank、BM25、混合检索、流式输出、聊天 UI、LangChain/LlamaIndex、Redis/Celery/Prometheus 或新的默认依赖。
- 不创建新的并行 Agent，不把同一接口拆成多个竞争实现。

实现要求：
- provider-neutral domain/service 不得导入 FastAPI、FastEmbed、qdrant-client、httpx 或 sqlite3 类型。
- chunk 与完整 Memo 必须继续由 `memo-chunk-v1`/`chunk` 和 `memo-v1`/`memo` 隔离；collection 名称也必须隔离。
- Qdrant 模式必须显式失败或 degraded，不能静默回退到完整 Memo store，也不能静默删除既有向量。
- 先 fake/offline contract，再执行显式 deterministic Qdrant smoke；FastEmbed 只在已有缓存和明确需要时验证。

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
- 显式 Qdrant chunk smoke：使用临时 collection，验证后删除临时 collection，不删除 volume

完成条件：
- 独立 Qdrant chunk collection、配置、fake contract 和隔离测试通过。
- chunk-health 在 memory/Qdrant 显式模式下契约清晰；默认完整 Memo health/chat 不回归。
- AI Service、前端、TypeScript/build、pnpm lint、Go 全量、Docker 配置和真实 Qdrant smoke 结果被如实记录。
- 更新 docs/PROJECT_STATUS.md、docs/CHANGELOG_AI.md、docs/HANDOFF.md、docs/roadmap.md、docs/api.md、docs/structure.md、docs/DECISIONS.md。
- 更新本文件和 docs/prompts/NEW_WINDOW_PROMPT.md 的默认阶段描述。
- 形成独立 commit，报告真实验证结果、未验证项、阻塞证据和下一阶段 Prompt。

停止条件：
- 需要修改 Memos 核心 API、数据库或 Proto 时先停下报告影响。
- Qdrant collection/volume 兼容性不明确时，只保留 fake adapter contract，不修改现有 collection。
- 新 chunk retrieval 无法与完整 Memo citation 共存时，停留在内部 service/health 边界，不改变公共 `/api/ai/chat`。
~~~
