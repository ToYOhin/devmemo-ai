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

## Phase 4c：outbox、重试与观测

下一阶段评估 AI Service 自有 SQLite outbox、有限重试和最小运行指标；保持默认 Compose deterministic + memory，不把外部服务变成启动依赖。
