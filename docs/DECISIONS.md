# DevMemo AI 决策记录

## ADR-001：保留 Memos upstream 边界

Memos cmd/server/store/proto/web 视为 upstream；AI 通过独立 HTTP Service 和 Webhook 接入。

## ADR-002：MVP 使用 AI Service 自有 SQLite

ai_notes 和 memo_templates 由 ai-service 管理并按 memo_id upsert，Qdrant 留到 RAG 阶段。

## ADR-003：LLM 使用 provider adapter

deterministic、OpenAI、Ollama 实现放在 adapter 层，业务逻辑依赖 provider-neutral 结果。

## ADR-004：Phase 3 先接口后真实基础设施

先定义 embedding/vector store 接口和 fake 测试，再接入 FastEmbed/Qdrant。

## ADR-005：每个切片产生下一阶段 Prompt

PROJECT_STATUS、CHANGELOG_AI、HANDOFF、NEXT_STAGE_PROMPT 是固定交付物，验证事实必须刷新。

## ADR-006：模板失败回退 plain Memo

模板解析失败不阻断普通 Memo 保存、Markdown、标签和搜索。

## ADR-007：结构化模板由 AI Service SQLite 管理

memo_templates 按 memo_id 唯一 upsert，保留 kind、payload、raw_content、created_at、updated_at。

## ADR-008：VITE_AI_SERVICE_URL 是前端安全开关

React 只在显式配置时启用 AI query；404、非法响应和网络错误局部降级。AI_CORS_ORIGINS 默认 localhost:3001，Phase 2d 支持 GET/POST。

## ADR-009：Windows 使用低并发验证

Go 使用 G:\Go；验证默认使用 GOMAXPROCS=2 和 go test -p 2 ./...；Docker 服务设置 CPU 上限。

## ADR-010：摘要由 AI Service HTTP 边界负责

ai_notes 通过 GET /api/ai/notes/{memo_id} 读取，生成继续通过 POST /api/ai/summarize，React 不直接连接 SQLite。

## ADR-011：Phase 3a 默认 deterministic/in-memory

Phase 3a 使用固定 8 维 deterministic provider 和 InMemoryVectorStore，作为低 CPU、可重复的 contract 实现。

## ADR-012：Qdrant 作为可选 Apache-2.0 adapter

qdrant-client 固定为 1.18.0，放在 requirements-qdrant.txt，不进入默认 requirements。PyPI 标记其许可证为 Apache-2.0，官方仓库和文档持续维护；SDK 类型只允许出现在 qdrant_vector_store.py。当前本机已安装该可选依赖，并完成 Qdrant collection/upsert/search/delete 真实 smoke；默认 Compose 仍不依赖它。

真实验证：Qdrant Server 1.18.2、FastEmbed 384 维、Cosine collection、payload 映射、删除行为和 volume 重启恢复均已验证。

## ADR-013：FastEmbed 作为可选 Apache-2.0 provider

FastEmbed 由 Qdrant 维护，固定为 `fastembed==0.8.0`，放在 `requirements-fastembed.txt`，不进入默认 requirements。官方文档使用 `TextEmbedding(...).embed(...)` 生成向量，并说明初始化会准备模型；默认模型 `BAAI/bge-small-en-v1.5` 输出 384 维。FastEmbed 使用 ONNX Runtime、模型权重仍可能产生下载和 CPU/磁盘成本，因此仅在 `AI_EMBEDDING_PROVIDER=fastembed` 时加载。SDK 类型只允许出现在 `app/adapters/fastembed_embedding.py`；如果后续需要替换模型或 provider，只替换该 adapter 和 composition 配置。当前本机已安装该可选依赖并完成真实 smoke。

依据：[FastEmbed 官方文档](https://qdrant.github.io/fastembed/)、[FastEmbed PyPI 0.8.0](https://pypi.org/project/fastembed/0.8.0/)、[FastEmbed GitHub](https://github.com/qdrant/fastembed)。本机已完成真实 smoke：384 维模型首次加载约 23.48 秒，单条推理约 0.06 秒；显式项目缓存目录约 64.07 MB，并已通过离线加载验证。

## ADR-014：Webhook 向量索引默认关闭且失败降级

`AI_INDEX_ON_WEBHOOK` 默认 `false`，避免历史 Webhook 在未准备好模型或 VectorStore 时增加 CPU、网络和延迟。显式开启后，AI Service 使用稳定 embedding_id 对 create/update 做 upsert，对 delete 做删除；任何索引异常只返回 `index_status=failed`，不阻断已有摘要、模板和 `code=0` Webhook 契约。

## ADR-015：Qdrant volume 与 FastEmbed 缓存显式持久化

Qdrant 只通过 Compose named volume `qdrant-data:/qdrant/storage` 持久化派生向量索引；运维验证使用 `docker compose restart qdrant`，禁止用 `down -v` 作为测试步骤。Phase 3f 已验证 collection、point、memo_id 和 metadata 在重启后恢复。

FastEmbed 通过可选 `AI_FASTEMBED_CACHE_DIR` 指定模型缓存目录。Compose 提供 `ai-model-cache:/app/model-cache`，但默认 provider 仍为 deterministic，不会触发模型下载或推理。缓存是生成物，不进入 Git；如果缓存损坏，运维应清理并重新准备模型，不改变默认启动路径。

## ADR-016：索引健康检查保持 provider-neutral 且显式降级

`GET /api/ai/index/health` 只读取当前 VectorStore 状态。memory adapter 不访问网络；Qdrant adapter 在 collection 查询失败时返回 `available=false、status=unavailable`，不把第三方 SDK 类型泄漏到 domain 或 API 通用层。显式 qdrant 模式在启动时无法连接仍抛出 `QdrantAdapterError`，避免静默写入错误索引。

Qdrant Compose 镜像固定为本机验证过的 Server 1.18.2 digest：`qdrant/qdrant:latest@sha256:75eab8c4ba42096724fdcfde8b4de0b5713d529dde32f285a1f86fdcb2c9e50c`。不升级其他服务，不删除现有 volume。

## ADR-017：完整 Memo 原文作为索引派生上下文

Phase 4 需要让检索结果能够形成可回答的上下文，因此 `MemoIndexDocument` 将当前完整 Memo 原文写入向量 metadata 的内部 `content` 字段。它是可重建的派生数据，不修改 Memos 或 AI Service SQLite；`POST /api/ai/chat` 生成 citations 时会剥离该字段，避免把原文重复放进公共引用 metadata。后续 chunking 或独立文档存储可以替换这一边界。

## ADR-018：Phase 4 先采用 deterministic 引用式答案

默认 `POST /api/ai/chat` 使用 deterministic provider 生成可复现的引用式答案，不需要 API key、模型下载或外部服务。OpenAI/Ollama 继续通过现有 LLM adapter 接入；检索失败返回 503，LLM 失败返回 502。Phase 4 不引入 LangChain/LlamaIndex、chunk、rerank 或前端聊天 UI。

## ADR-019：Webhook HMAC 作为可选安全门

Phase 4b 使用标准库 HMAC-SHA256 校验原始 Webhook body。`AI_WEBHOOK_SECRET` 为空时不启用校验，保持既有客户端和 `code=0` 处理契约；显式配置后要求 `X-DevMemo-Signature: sha256=<hex>`，缺失、格式错误或内容篡改返回 401。签名 helper 位于 AI Service service 层，不修改 Memos 核心 API、数据库、Proto，也不引入第三方依赖。后续 outbox/重试仍需单独设计。

## ADR-020：AI Service SQLite Outbox 先做幂等记录，不启动 Worker

Phase 4c 在 AI Service 自有 SQLite 新增 `webhook_events`，以唯一 `event_id` 记录 Webhook payload、处理状态、attempts 和 last_error。显式 eventId 优先使用；缺失时由原始 body SHA-256 派生。重复事件直接返回 duplicate，不重复触发摘要、模板或索引；业务异常记录 failed 但保持 `code=0`。当前只提供 GET 运维读取 API，不引入常驻 worker、Redis、Celery、外部队列或无限重试；显式有上限的重试留到 Phase 4d。

## ADR-021：Phase 4d 只提供有上限的显式重试与 SQLite 观测

Phase 4d 在现有 `webhook_events` 上通过兼容 `ALTER TABLE` 补充 `max_attempts`，默认总尝试次数为 3；首次 Webhook 处理和最多两次显式重试共用该上限。`POST /api/ai/ops/outbox/{event_id}/retry` 只允许 `failed` 事件，并在数据库事务中先将事件原子置为 `pending`，避免同一事件被两个显式请求同时领取。成功转为 `processed` 并清除 `last_error`，失败继续保持 `failed` 并递增 `attempts`。

观测只扩展现有 outbox GET，返回按状态计数和最多 5 条最近错误摘要。不启动 worker、定时任务、Redis、Celery、Prometheus 或其他运行时依赖；默认 Compose deterministic + memory 和 Memos Webhook `code=0` 契约保持不变。

## ADR-022：Ops API 使用可选令牌并最小化公开错误数据

Phase 4e 使用标准库 `hmac.compare_digest` 校验可选环境变量 `AI_OPS_TOKEN`，请求头为 `X-DevMemo-Ops-Token`。未配置令牌时保持本地开发兼容；配置后 GET outbox 和 retry POST 的缺失/错误令牌返回 401。Webhook HMAC 使用独立的 `AI_WEBHOOK_SECRET`，两者不混用。

公开 outbox item 不再返回原始 Webhook payload；payload 仍保存在 AI Service SQLite，retry 只在服务内部读取。`last_error` 和最近错误摘要在 HTTP 响应中归一化为单行并截断到 240 字符，保留 event_id、状态、attempts 和 max_attempts 供排障。该切片不引入认证服务、Redis、Prometheus 或常驻 worker。

## ADR-023：Phase 4f 只读保留预览与告警轮询

Phase 4f 不执行默认数据删除，只提供受 `AI_OPS_TOKEN` 保护的 `GET /api/ai/ops/outbox/retention-preview`。候选以 `updated_at` 作为不活跃截止时间，仅包含 `processed` 和 `failed` 终态，排除 `pending`；默认 30 天、最多 100 条，接口不会修改 SQLite。未来若增加清理，必须另设显式批准/审计契约。

新增 `GET /api/ai/ops/alerts` 作为外部监控的只读轮询接口，返回失败数、达到 max_attempts 的耗尽数和最多 5 条 warning/critical 摘要，不主动推送、不引入 Prometheus、Redis、Celery 或后台 worker。公开响应继续不返回 payload、secret 或未截断错误。

## ADR-024：Phase 4g 清理必须显式批准并审计

Phase 4g 使用两步式清理：retention preview 返回 `cutoff`、`preview_limit` 和 `candidate_ids`；清理请求默认 `dry_run=true`，只有同时设置 `dry_run=false` 和 `confirm=true` 才允许执行。执行在 SQLite `BEGIN IMMEDIATE` 事务内重新计算同一 preview 集合，并校验 `processed/failed` 终态、cutoff 和 candidate 集合；pending、集合外 ID 或数据变化会整批拒绝。

清理只删除 AI Service 自有 `webhook_events` 派生记录，不触碰 Memos 数据库、`ai_notes`、`memo_templates`、原始 Markdown、Qdrant 或 AI volume。`webhook_cleanup_audits` 保存 approval_id、actor SHA-256 摘要、cutoff、preview_limit、候选数量、删除数量和执行时间；相同 approval_id 的重复请求幂等返回，且不保存 ops secret。当前不引入 worker、定时任务、外部队列、Prometheus 或前端运维 UI。

## ADR-025：Phase 5a 先做离线检索评估，不直接切换 Chunking

当前索引以完整 Memo 为一个向量，embedding_id、Webhook upsert/delete 和 citations 都依赖这一边界。Phase 5a 先新增 provider-neutral `RetrievalEvaluationCase`、`RetrievalEvaluationResult` 和 `RetrievalEvaluator`，测量 Recall@K、相关 Memo 命中和首个相关结果排名；评估器复用 `RetrievalService`，不依赖 FastAPI、FastEmbed、Qdrant 或外部网络。

在离线评估集证明当前检索基线前，不替换现有完整 Memo 索引。后续 Phase 5b 才定义 chunk 文档、稳定 chunk ID、index_version 和生命周期兼容策略；默认 deterministic + memory、Memos 核心和现有 chat API 保持不变。

## ADR-026：Phase 5b 只定义可回滚的 Memo chunking 边界

Phase 5b 使用 provider-neutral `MemoChunk` 和纯函数 `chunk_memo`，按换行边界或固定字符上限切分，并保持 chunk 内容拼接后等于原始 Markdown。chunk metadata 使用独立的 `index_version=memo-chunk-v1` 和 `index_mode=chunk`；稳定 ID 由 Memo ID、版本和位置派生，不包含内容 hash，因此同一位置更新可以复用 ID，内容缩短时可以显式删除旧尾部 ID。

该切片不接入 Webhook、EmbeddingService、VectorStore、Qdrant、FastEmbed 或 `POST /api/ai/chat`，也不修改 Memos/AI SQLite。现有完整 Memo `memo-v1` 生产索引继续作为唯一默认路径，后续必须先通过离线 chunk 评估再考虑显式试验索引。

## ADR-027：Phase 5c 使用独立 OfflineChunkIndex 做检索对照

Phase 5c 新增 `OfflineChunkIndex`，仅在 deterministic + memory 测试路径中将 `MemoChunk.chunk_id` 作为 embedding ID 写入 VectorStore，再复用 `RetrievalService` 和 Phase 5a `RetrievalEvaluator`。这样可以验证 chunk citation metadata、上下文和 Recall@K 对照，同时不改变 `EmbeddingService` 的 Memo 级稳定 ID 或 `delete_memo` 契约。

chunk 试验更新必须先 upsert 当前 chunk，再由调用方显式提交旧尾部 chunk 的 delete；重复 ID、空内容和 metadata 不一致在 helper 边界拒绝或归一化。该 helper 不接入 Webhook、Qdrant、FastEmbed、Compose 或公共 HTTP API，后续 Phase 5d 才评估显式 opt-in 生命周期。

## ADR-028：Phase 5d 允许显式 chunk Webhook 生命周期，但默认不切换

在用户要求放宽 Phase 5d 约束后，将 chunk 生命周期接入 AI Service Webhook，但通过 `AI_INDEX_MODE=chunk` 和既有 `AI_INDEX_ON_WEBHOOK=true` 双重 opt-in；默认仍是完整 Memo `memo-v1`，不修改 Memos 核心或公共 `POST /api/ai/chat` citation 响应。`ChunkLifecycleCoordinator` 先 upsert 当前 chunk，再删除同一 `memo-chunk-v1` 版本登记的 stale ID，避免更新失败时先删除可用索引。

生命周期需要跨进程知道旧 chunk ID，因此 AI Service 自有 SQLite 新增 `memo_chunk_index_state`。该表只保存 Memo ID、index version、chunk ID JSON 和时间戳，不保存原始 Markdown；状态缺失时不扫描 VectorStore，也不猜测删除其他版本。chunk coordinator 在本阶段使用独立 InMemoryVectorStore，避免 chunk 向量进入完整 Memo 的 chat 检索源；Qdrant chunk collection 留到后续显式边界。默认 Compose 仍 deterministic + memory，Qdrant/FastEmbed 只有已有显式配置才参与。Webhook 失败仍保持 `code=0`，通过 `index_status=failed` 暴露降级。

## ADR-029：Phase 5e 用只读 chunk health 收敛可观测边界

Phase 5e 选择 GET `/api/ai/index/chunk-health`，而不是改变公共 chat 或新增 chunk 查询语义。`ChunkIndexHealth` 合并独立 chunk VectorStore 的点数和 `ChunkIndexStateStore` 的登记计数，并显式返回 `index_mode=chunk`、`index_version=memo-chunk-v1`。状态异常只产生 `degraded`，不触发重建、删除、网络连接或默认模式切换。

SQLite adapter 负责把损坏/不可读状态转换为 bounded detail；domain/service 只使用标准 dataclass/Protocol。Qdrant chunk collection 和 chunk-aware public retrieval 留到 Phase 5f，避免在完整 Memo citation 契约尚未扩展前混合两种索引。

## ADR-030：默认使用单 Agent 推进

DevMemo AI 后续默认只使用 `H:\DevMemoAI` 主工作树和一个 Agent 推进。原因是当前阶段以 provider-neutral 边界、Qdrant collection 隔离、公共 chat citation 兼容和完整验证为主；多个 Agent 同时修改相邻接口会增加重复上下文、token 消耗、Git 冲突和集成验证成本。

单 Agent 仍按 contract-first、实现、测试、显式 smoke、文档、独立 commit 的小步顺序推进。`project4` 下已建立的 Terra/Luna worktree 不删除，但标记为历史/回滚参考，除非用户重新授权，不启动并行开发。

## ADR-031：Phase 5f 为 chunk 预留独立 Qdrant collection

完整 Memo 继续使用 `QDRANT_COLLECTION`/`memo-v1`。Phase 5f 的 chunk 路径预留 `QDRANT_CHUNK_COLLECTION`，默认 `devmemo_memo_chunks`，并在配置边界拒绝空名称或与完整 Memo collection 重合；chunk metadata 继续使用 `memo-chunk-v1`/`index_mode=chunk`。Qdrant collection 使用当前 provider dimension 和 Cosine distance，避免 chunk 向量污染完整 Memo 检索。

本决策已落地 collection/config contract、fake adapter 验证和 composition：只有显式 `AI_INDEX_MODE=chunk` + `AI_VECTOR_STORE=qdrant` 才选择独立 Qdrant chunk store，其他 chunk 路径使用独立 memory。真实 Qdrant health/persistence smoke 由显式 smoke 脚本验证；默认 deterministic + memory、Webhook `code=0`、完整 Memo `POST /api/ai/chat` 和既有 collection/volume 均保持不变。

## ADR-032：内部 chunk retrieval 与公共 Memo citation 分离

Phase 5f 增加独立的 `ChunkRetrievalService`，复用 query embedding 和 VectorStore search，但不复用公共 `Citation` 作为 chunk API。内部 `ChunkCitation` 固定携带 `memo_id`、稳定 `chunk_id`、`chunk_index` 和 `memo-chunk-v1`，并严格拒绝缺失、错误版本或混入完整 Memo 的 metadata。原文 `content` 仅用于服务端 context 组装，不出现在 citation metadata；公共 `POST /api/ai/chat` 继续检索完整 Memo。

这样可以先验证 Qdrant chunk collection 的 health、重新连接持久性和删除生命周期，再决定是否扩大公共检索语义；错误不会静默回退到完整 Memo collection。
