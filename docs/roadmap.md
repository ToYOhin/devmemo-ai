# DevMemo AI 二次开发路线

## 总原则

保持 Memos upstream，AI 通过 Webhook、HTTP API 和可替换 adapter 接入。每个阶段先做可回滚垂直切片，完成后更新状态、变更、交接和下一阶段 Prompt。

## Phase 0：开发基础

Go 位于 G:\Go，缓存/工作区位于 G:\GoWorkspace；Docker Desktop 负责本地 Compose 环境；Windows 低并发验证和 CPU 限制已完成。

## Phase 1：AI 摘要 MVP

Memo webhook -> AI provider -> ai_notes SQLite upsert。已支持 deterministic/OpenAI/Ollama provider 边界。

## Phase 2：开发者 Memo 模板

已完成 Code Snippet、Bug Report 解析、plain fallback、Webhook 返回、memo_templates 持久化和 React 展示/复制。

## Phase 2d：摘要读取与生成

已完成 ai_notes 兼容补列、GET 摘要 API、摘要展示、关键词/分类、生成/重新生成、React Query 刷新和 POST CORS。

## Phase 3a：Embedding provider/vector store 边界

已完成 provider-neutral contracts、8 维 deterministic provider、InMemoryVectorStore、稳定 embedding_id 和 POST /api/ai/embed。

## Phase 3b：可选 Qdrant adapter

已完成 QdrantVectorStore fake contract、payload 映射、collection/dimension 校验、optional requirements、AI_VECTOR_STORE 配置和 Compose 启动解耦。

验证：AI Service 42 passed；Qdrant fake 11 passed；前端 131 passed。

## Phase 3c：可选真实 embedding 与索引编排

已完成：

1. 新增可选 `FastEmbedEmbeddingProvider`，固定 `fastembed==0.8.0`，第三方类型只在 adapter。
2. 增加 `AI_EMBEDDING_PROVIDER`、模型名和维度配置；默认 deterministic，显式模式缺依赖/模型失败时报清晰错误。
3. 新增 `MemoIndexDocument`/`index_memo`；当前一整个 Memo 是一个索引单元，metadata 使用 `source_type` 和 `index_version`，不提前引入 chunk。
4. POST `/api/ai/embed` 保持原响应契约，并沿用 memory/qdrant VectorStore 组合。

验证：AI Service 54 passed；前端 131 passed；TypeScript/build、Compose config 和根验证通过。真实 FastEmbed/Qdrant 仍受本机依赖和 Docker engine 状态限制。

## Phase 3d：Memo 索引生命周期与 Webhook 可选编排

已完成：

1. 新增默认关闭的 `AI_INDEX_ON_WEBHOOK=false`。
2. create/update 复用 `MemoIndexDocument` 做稳定 embedding_id 幂等 upsert。
3. deleted 事件删除对应向量；缺少 UID 时安全跳过。
4. 索引失败降级为 `index_status=failed`，不阻断摘要、模板和 Webhook `code=0`。

验证：AI Service 60 passed；Go `GOMAXPROCS=2 go test -p 2 ./...` 通过；前端 131 passed；FastEmbed+Webhook 真实 smoke 通过。

## Phase 3e：Qdrant 真实 smoke

已完成：

1. Docker Desktop Linux Engine 恢复后安装 `requirements-qdrant.txt`，锁定 qdrant-client 1.18.0。
2. 使用 FastEmbed 384 维 provider + QdrantVectorStore 验证 collection 创建、upsert、search、payload 和 delete。
3. 新增 `ai-service/scripts/smoke_qdrant.py`，默认 FastEmbed，支持 deterministic 低负载 smoke；默认 Compose 配置未改变。
4. 修正可选依赖测试，使测试既能覆盖缺依赖边界，也能在依赖已安装时运行。

验证：AI Service 60 passed；FastEmbed+Qdrant 真实 smoke 通过；Go 全量测试、前端 131 tests、TypeScript/build 和 Compose config 继续通过。

## Phase 3f：Qdrant 持久化与模型缓存治理

已完成：

1. 验证 `devmemoai_qdrant-data` 挂载到 `/qdrant/storage`，Qdrant `docker compose restart qdrant` 后 collection、point、payload 可恢复。
2. 新增 `AI_FASTEMBED_CACHE_DIR`，FastEmbed adapter 只在显式配置时传入 `cache_dir`。
3. Compose 增加 `ai-model-cache:/app/model-cache`；默认 deterministic 不加载模型，低 CPU 默认保持不变。
4. 新增缓存目录配置/adapter 测试；项目缓存目录在离线模式下完成 384 维 FastEmbed smoke。

验证：AI Service 62 passed；Qdrant volume restart smoke 通过；FastEmbed cache-dir offline smoke 通过；Compose config 通过。

## Phase 3g：索引运行健康与故障边界

已完成：

1. 新增只读 `GET /api/ai/index/health`；memory 路径不连接 Qdrant，Qdrant 路径返回 collection status 和 point_count。
2. Qdrant health 异常转换为 `available=false、status=unavailable`；保留显式 qdrant 模式初始化失败的清晰 adapter 错误。
3. FastEmbed cache/model 初始化错误包含 cache_dir 和修复提示，并增加 contract tests。
4. Qdrant 镜像固定到已验证的 Server 1.18.2 digest，不升级其他服务。

验证：AI Service 66 passed；Qdrant health smoke、memory API health、offline/degraded adapter tests、Go 全量和前端 131 tests 通过。

## Phase 4：RAG 与引用问答

已完成最小切片：

1. `RetrievalService` 复用现有 EmbeddingProvider/VectorStore，执行 query embedding -> search -> context。
2. 新增 POST `/api/ai/chat`，返回 deterministic/OpenAI/Ollama provider 结果和结构化 Memo citations。
3. 当前一个完整 Memo 对应一个检索单元；不做 chunk、rerank、混合检索或外部网页。
4. 默认 deterministic + memory 可离线运行；Qdrant 只通过既有显式配置启用。

验证：AI Service 79 passed；Go `go test -p 2 ./...`、前端 131 tests、TypeScript/build、Compose config 和 deterministic Qdrant smoke 通过；`pnpm lint` 受 377 个既有 CRLF 诊断阻塞。

## Phase 4b：索引可靠性与 Webhook 运维边界

已完成最小切片：

1. 新增可选 Webhook HMAC-SHA256 签名验证，使用 `AI_WEBHOOK_SECRET` 和 `X-DevMemo-Signature`。
2. 默认未配置 secret 时保持旧 Webhook `code=0` 和业务处理兼容；显式配置后无效签名返回 401。
3. 签名逻辑独立于 FastAPI、Qdrant、LLM 和 Memos 核心，测试不访问网络。

验证：AI Service 90 passed；Go `go test -p 2 ./...`、前端 131 tests、TypeScript/build 和 Compose config 通过；`pnpm lint` 受 377 个既有 CRLF 诊断阻塞。

## Phase 4c：Outbox 与失败状态读取

已完成最小切片：

1. AI Service SQLite 新增 `webhook_events`，不修改 `ai_notes`、`memo_templates` 或 Memos 数据库。
2. Webhook 按显式 `eventId` 或原始 body hash 幂等入队，重复事件不重复执行。
3. 处理失败记录 `failed`、`attempts` 和 `last_error`，同时保持旧 `code=0` 响应契约。
4. 新增 GET `/api/ai/ops/outbox`，只读返回最近状态；不启动 worker 或外部队列。

验证：AI Service 95 passed；Go `go test -p 2 ./...`、前端 131 tests、TypeScript/build 和 Compose config 通过；`pnpm lint` 受既有 CRLF 诊断阻塞。

## Phase 4d：显式重试与最小观测

已完成最小切片：

1. 通过兼容 SQLite 补列为 `webhook_events` 增加 `max_attempts`，默认总尝试次数为 3，不删除旧表和数据。
2. 新增 `POST /api/ai/ops/outbox/{event_id}/retry`，只重试 `failed` 事件；成功转 `processed`，失败保持 `failed` 并记录最新错误。
3. 达到上限后返回 409，不执行无限重试；没有后台 worker、定时任务或外部队列。
4. 扩展 GET outbox 返回 `by_status` 和最多 5 条 `recent_errors`，作为最小观测契约。

验证：AI Service 100 passed；Go 全量、前端 131 tests、TypeScript/build 和 Compose config 通过。默认 Compose 仍为 deterministic + memory。

## Phase 4e：运维 API 安全与告警边界

已完成最小切片：

1. 新增可选 `AI_OPS_TOKEN`，配置后保护 outbox GET 和 retry POST；未配置时保持本地开发兼容。
2. 公开 outbox item 移除原始 Webhook payload；retry 仍从 AI Service SQLite 内部 payload 读取。
3. `last_error` 和 `recent_errors` 统一为单行、最多 240 字符摘要；认证失败返回 401。
4. 不引入认证服务、Prometheus、Redis、后台 worker、前端运维 UI 或新运行时依赖。

验证：AI Service 102 passed；Go 全量、前端 131 tests、TypeScript/build 和 Compose config 通过。

## Phase 4f：Outbox 保留与告警导出边界

已完成最小切片：

1. 新增受 `AI_OPS_TOKEN` 保护的 retention preview，按 `updated_at` 预览超过 30 天的 `processed/failed` 终态；不删除、不影响 `pending`。
2. 新增受保护的 `GET /api/ai/ops/alerts`，返回失败数、耗尽重试数和最多 5 条 warning/critical 摘要。
3. alerts 只供外部轮询，不主动推送；不引入 worker、队列、Prometheus 或新运行时依赖。

验证：AI Service 105 passed；Go 全量、前端 131 tests、TypeScript/build 和 Compose config 通过。

## Phase 4g：显式清理批准与审计边界

已完成：

1. retention preview 返回 `cutoff`、`preview_limit` 和 `candidate_ids`，清理请求必须绑定同一预览集合。
2. 新增 `POST /api/ai/ops/outbox/retention-cleanup`；默认 dry-run，只有 `confirm=true` 且 `dry_run=false` 才能执行。
3. SQLite 事务重新校验完整候选集合、cutoff 和 `processed/failed` 终态；pending、越界 ID 或数据变化整批拒绝。
4. 新增 `webhook_cleanup_audits` 和 `GET /api/ai/ops/outbox/cleanup-audits`；保存 approval_id、actor 摘要、cutoff、候选数、删除数和执行时间。
5. 相同 approval_id 重复请求幂等；清理只作用于 AI Service 自有 webhook_events，不触碰 Memos、ai_notes、memo_templates、原始 Markdown 或 Qdrant volume。

验证：AI Service 108 passed；Go 全量、前端 131 tests、TypeScript/build 和 Compose config 通过。

## Phase 5a：离线检索质量评估

已完成：

1. 选择离线评估作为第一步，避免直接改变完整 Memo 的索引、Webhook 生命周期和 citation 契约。
2. 新增 provider-neutral `RetrievalEvaluationCase`、`RetrievalEvaluationResult` 和 `RetrievalEvaluator`。
3. 支持 Recall@K、相关 Memo 命中列表、首个相关结果排名和批量案例；不访问网络、不加载模型、不连接 Qdrant。

验证：AI Service 116 passed；Go 全量、前端 131 tests、TypeScript/build 和 Compose config 通过。

## Phase 5b：Memo chunking 边界

已完成：

1. 新增 provider-neutral `MemoChunk` 与纯函数 `chunk_memo`，按换行边界和固定字符上限切分，保留原始 Markdown 字符序列。
2. 使用 `memo-chunk-v1`、`index_mode=chunk` 和基于 Memo/版本/位置的稳定 chunk ID；完整 Memo 的 `memo-v1` 索引继续独立存在。
3. 提供 `chunk_ids_for_memo` 和重复 ID 校验，覆盖更新、缩短内容后的 stale ID、空内容、超长内容和 metadata 复制契约。
4. 只实现纯函数/内存边界，没有改变 Webhook、Qdrant、FastEmbed、Compose、RAG chat 或 Memos 核心。

验证：AI Service 129 passed；Go 全量、前端 131 tests、TypeScript/build 和 Compose config 通过。

## Phase 5c：chunk 离线检索评估

已完成：

1. 新增 provider-neutral `OfflineChunkIndex`，使用 deterministic + memory 写入独立 chunk 试验索引。
2. 复用 `RetrievalService` 和 Phase 5a `RetrievalEvaluator`，对完整 Memo 与 chunk 结果做 Recall@K/首个相关结果排名对照。
3. chunk citation metadata 明确包含 Memo ID、chunk ID、chunk position、index version；上下文组装保留原始 chunk 内容，公共 chat API 不变。
4. 覆盖 upsert、显式 stale delete、重复/空 chunk 和 baseline 对照；不接入默认 Webhook、Qdrant、FastEmbed 或生产索引。

验证：AI Service 133 passed；Go 全量、前端 131 tests、TypeScript/build 和 Compose config 通过。

## Phase 5d：可选 chunk 索引生命周期

已完成：

1. 新增 provider-neutral `ChunkLifecycleCoordinator`，在 `AI_INDEX_MODE=chunk` 时编排 create/update/delete；默认 `AI_INDEX_MODE=memo` 继续走完整 Memo `memo-v1`。
2. 更新先 upsert 当前 `memo-chunk-v1` chunk，再删除同一 Memo/版本的 stale 尾部；空内容会清理已登记 chunk，删除事件清理全部已登记 chunk。
3. AI Service 自有 SQLite 新增 `memo_chunk_index_state`，只保存版本和 chunk ID 列表；缺失状态不做全库扫描，避免误删其他版本或 Memo。
4. Webhook chunk 路径保留 `eventId` 幂等、失败 `code=0` 降级和完整 Memo chat citation 契约；默认 Compose 仍 deterministic + memory。
5. chunk lifecycle 使用独立 InMemoryVectorStore 与完整 Memo 检索隔离；Qdrant chunk collection 作为后续显式扩展。

验证：AI Service 142 passed；Go 全量、前端 131 tests、TypeScript/build、pnpm lint 和 Compose config 通过。

## Phase 5e：chunk 检索与可观测性收敛

已完成：

1. 新增 `ChunkIndexStateStats` 和 `ChunkIndexHealth`，对照 VectorStore 点数与 AI SQLite 登记的 Memo/chunk 数量。
2. 新增 GET `/api/ai/index/chunk-health`，显式返回 `index_mode=chunk`、`index_version=memo-chunk-v1`、provider、dimension、point_count、tracked_memos、tracked_chunks、state_backend 和 detail。
3. SQLite 状态异常返回 degraded；health 只读，不改变完整 Memo index health、Webhook code=0 或公共 chat citation。
4. 覆盖空状态、create/update/delete 计数、版本隔离、SQLite 状态读取和 HTTP contract；默认 deterministic + memory。

验证：AI Service 144 passed；前端、Go、Docker 和完整验证门禁沿用 Phase 5d 已验证结果，最终提交前重新执行。

## Phase 5f：Qdrant chunk 持久化与显式 chunk 检索（下一阶段）

计划为 chunk 模式增加独立 Qdrant collection 或等价持久化边界，并设计显式 chunk 检索 contract；默认完整 Memo `memo-v1`、memory、Webhook 和 `/api/ai/chat` 不切换。
