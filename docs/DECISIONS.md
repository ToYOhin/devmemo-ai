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

对外变更应同步更新适用的用户文档与变更记录，并如实说明验证范围。

## ADR-006：模板失败回退 plain Memo

模板解析失败不阻断普通 Memo 保存、Markdown、标签和搜索。

## ADR-007：结构化模板由 AI Service SQLite 管理

memo_templates 按 memo_id 唯一 upsert，保留 kind、payload、raw_content、created_at、updated_at。

## ADR-008：VITE_AI_SERVICE_URL 是前端安全开关

React 只在显式配置时启用 AI query；404、非法响应和网络错误局部降级。AI_CORS_ORIGINS 默认 localhost:3001，Phase 2d 支持 GET/POST。

## ADR-009：Windows 使用低并发验证

Windows 验证默认使用 `GOMAXPROCS=1` 和 `go test -p 1 ./...`；Go 工具链由 `PATH` 或
`DEVMEMO_GO` 解析，Docker 服务设置 CPU 上限。

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

## ADR-031：Phase 5f 为 chunk 预留独立 Qdrant collection

完整 Memo 继续使用 `QDRANT_COLLECTION`/`memo-v1`。Phase 5f 的 chunk 路径预留 `QDRANT_CHUNK_COLLECTION`，默认 `devmemo_memo_chunks`，并在配置边界拒绝空名称或与完整 Memo collection 重合；chunk metadata 继续使用 `memo-chunk-v1`/`index_mode=chunk`。Qdrant collection 使用当前 provider dimension 和 Cosine distance，避免 chunk 向量污染完整 Memo 检索。

本决策已落地 collection/config contract、fake adapter 验证和 composition：只有显式 `AI_INDEX_MODE=chunk` + `AI_VECTOR_STORE=qdrant` 才选择独立 Qdrant chunk store，其他 chunk 路径使用独立 memory。真实 Qdrant health/persistence smoke 由显式 smoke 脚本验证；默认 deterministic + memory、Webhook `code=0`、完整 Memo `POST /api/ai/chat` 和既有 collection/volume 均保持不变。

## ADR-032：内部 chunk retrieval 与公共 Memo citation 分离

Phase 5f 增加独立的 `ChunkRetrievalService`，复用 query embedding 和 VectorStore search，但不复用公共 `Citation` 作为 chunk API。内部 `ChunkCitation` 固定携带 `memo_id`、稳定 `chunk_id`、`chunk_index` 和 `memo-chunk-v1`，并严格拒绝缺失、错误版本或混入完整 Memo 的 metadata。原文 `content` 仅用于服务端 context 组装，不出现在 citation metadata；公共 `POST /api/ai/chat` 继续检索完整 Memo。

这样可以先验证 Qdrant chunk collection 的 health、重新连接持久性和删除生命周期，再决定是否扩大公共检索语义；错误不会静默回退到完整 Memo collection。

## ADR-033：Phase 6 保持 chunk retrieval 为内部 contract

Phase 6 对比了现有公共 `POST /api/ai/chat` 与内部 `ChunkRetrievalService` 的语义。当前公共 `CitationResponse` 使用 `memo_id`、完整 Memo 的 `embedding_id`、score 和脱敏 metadata；`retrieved_count` 表示完整 Memo 检索结果数量。内部 chunk 结果使用稳定 `chunk_id`、`chunk_index` 和 `memo-chunk-v1`。把 chunk 结果直接塞入现有字段会让同一 Memo 产生多个 citation、改变计数和排序，并破坏现有客户端对 `embedding_id` 的假设。

因此 Phase 6 决定：不增加 `POST /api/ai/chat` 的隐式 chunk mode，不把 `embedding_id` 改成 chunk ID，不新增未定义的公共 chunk endpoint。默认完整 Memo `memo-v1`、公共 citation schema、Webhook 默认行为和完整 Memo collection 继续保持不变；`ChunkRetrievalService` 与 `GET /api/ai/index/chunk-health` 作为内部/运维边界保留。

未来若要公开 chunk retrieval，必须先单独定义 versioned endpoint 或明确的请求/响应版本，并补齐 chunk citation schema、同 Memo 去重规则、排序/上下文预算、content 脱敏、迁移/回滚和双路径 contract tests。没有这些兼容性证据，不扩大公共 API。

## ADR-034：Phase 7 public chunk API proposal（仅提案，不实现）

提出未来独立 endpoint `POST /api/ai/v1/chunks/search`，响应版本固定为 `public-chunk-v1`。本 ADR 只定义可评审 contract，不新增路由、不改变现有 `POST /api/ai/chat`。

请求提案：`question` 为必填非空字符串，`limit` 范围 1–10、默认 5；服务固定检索 `memo-chunk-v1`，不允许客户端随意选择 index version。响应提案包含 `api_version`、`index_version`、`provider`、`chunks` 和 `retrieved_count`。每个 chunk citation 只包含 `memo_id`、`chunk_id`、`chunk_index`、`score` 和 allowlist metadata；不包含 `content`、原始 Markdown、Webhook payload、secret 或内部存储字段。

同一 Memo 默认只保留最高分 chunk；排序为 score 降序、`memo_id` 升序、`chunk_index` 升序、`chunk_id` 升序，保证结果可复现。`retrieved_count` 表示去重后的 chunk 数量，不复用现有 chat 的完整 Memo 计数语义。未来若需要同一 Memo 多 chunk，必须另行版本化，不在此 contract 中隐式扩展。

错误提案：question/limit 非法返回 422；chunk store 未启用、不可用或 health 为 degraded 返回 503；公共暴露必须由网关认证和 Memo 权限层保护，AI Service 本身不把当前本地兼容模式误当成多租户授权。默认 `AI_PUBLIC_CHUNK_RETRIEVAL=false`，关闭时不注册或不接受该 endpoint。

迁移/回滚：先以离线双路径评估确认 Recall、去重、排序和脱敏，再在独立 feature flag 下灰度；现有 chat 和 `memo-v1` collection 不迁移、不重写。回滚只需关闭 flag/路由，不删除 chunk collection 或 volume；`public-chunk-v1` 不复用旧 `CitationResponse` 字段语义。

## ADR-035：Phase 8 implementation gate 等待明确批准

Phase 8 的实现闸门要求明确的产品/兼容批准后，才能把 ADR-034 的提案变成公共 HTTP 路由。本轮只收到阶段名称，没有收到批准实现 `POST /api/ai/v1/chunks/search` 的授权，因此保持 gate pending approval。

在批准前不新增路由、不新增 `AI_PUBLIC_CHUNK_RETRIEVAL` 运行时行为、不改变公共 chat、不改完整 Memo collection，也不启动灰度。批准消息必须明确接受 `public-chunk-v1` 的字段、同 Memo 最高分去重、脱敏、认证前提和关闭 flag 回滚策略。

## ADR-036：Phase 9 先做可审核的 DevMemory Loop，不复制通用 AI 平台

Phase 9 的产品差异化目标是把 Memo 从一次性摘要升级为可审核的开发记忆资产：`MemoInsight` 以 fact/decision/action/bug 为类型，带有来源 Memo、置信度、pending/accepted/rejected 状态和可审计时间。AI 只提出候选，用户显式确认后才成为可复用的派生知识；原始 Memo 不被 AI 改写。

第一切片使用现有 parser、SummaryResponse、deterministic provider 和 AI Service SQLite，增加幂等 insight 状态与本地产品边界的 preview/approve/reject contract。它不依赖 public chunk API，不改变 `POST /api/ai/chat`、完整 Memo `memo-v1`、chunk collection 或默认 deterministic + memory。

该方向借鉴 Khoj 的个人 AI/语义搜索和自动化、AnythingLLM 的 workspace memory 与来源引用、AFFiNE 的知识工作区、Logseq 的本地知识图谱、Outline 的历史/协作意识，但不复制第三方源码。Khoj/Logseq 的 AGPL-3.0、Outline 的 BSL 1.1、AFFiNE 的仓库许可证边界均要求保持参考而非直接采用；任何新增依赖必须另做许可证、安全和维护评估。

未来 Context Pack 只能消费已确认 insight，并限制来源、字数和输出格式；不得默认引入 agent、网页搜索、MCP、图数据库、Redis、Celery 或常驻 worker。这样保留 local-first、可撤销和可回滚特性，同时形成区别于通用 RAG 的开发者工作流。

## ADR-037：Phase 9a 先落地可回滚 AI Inbox，不公开 chunk retrieval

Phase 9a 已按 ADR-036 实现首个垂直切片：`MemoInsight` 使用稳定的 `insight_id` 和 `(memo_id, insight_type)` 幂等身份；SQLite 保存版本和审计时间；preview 不落库；approve/reject 必须带当前版本，过期写入返回 409。deterministic 提取器只从现有 Code Snippet、Bug Report 和 plain Memo 生成有界候选，不做自由发挥式知识图谱。

Memo 详情页 AI Inbox 是本地产品边界，展示候选的类型、置信度、状态和 `source_refs`，不暴露原始 content。该切片不修改 Memos 核心、公共 `POST /api/ai/chat`、完整 Memo/chunk collection 或默认 `deterministic + memory`。Phase 8 public chunk API 仍保持 pending approval；下一步只定义消费已确认 insight 的 bounded Context Pack contract/fixture。

## ADR-038：Phase 9b Context Pack 先做纯 contract，不提前接入产品入口

Phase 9b 固定 `context-pack-v1` 为纯函数输出边界：请求必须显式携带 Memo/insight IDs，只有 accepted insight 可以进入；父 Memo 必须同时显式选择。builder 只读取安全的 Memo title/summary、insight title/summary 和 `source_refs`，通过稳定排序、唯一 source 和 `max_chars`/`max_items` 形成可复制 Markdown/JSON。

本阶段不新增 HTTP 路由、不从 SQLite 自动发现 ID、不读取 Qdrant、不连接公共 chat，也不实现 Agent。这样可以先评审 Context Pack 的产品入口、权限、撤销和用户确认体验，再决定 Phase 9c 是否接入内部 UI 或 CLI；Phase 8 public chunk API 继续 pending approval。

## ADR-039：Phase 9c Context Pack 入口保持 proposal-only，推荐 Memo 详情页复制

本阶段没有收到明确的产品入口批准，因此不新增运行时 UI/API。评审结论是推荐在现有 Memo 详情页 AI Inbox 内增加 `Copy Context Pack`，默认只包含当前 Memo；跨 Memo 选择必须显式完成。命令面板和独立页面暂不采用，因为它们会扩大权限、来源选择和空/失败态的产品边界。

未来内部入口必须满足：当前用户可见 Memo 权限、accepted insight 状态、显式 question/选择/预算、Markdown 主复制和 JSON 可选复制、sources/截断/空态/失败态/窄屏反馈。pending/rejected、删除 Memo、撤销 insight、过期版本和不可见来源必须排除；pack 不落库，不显示 raw content、Webhook payload、secret 或 chunk content。

当前决策是 proposal-only，等待产品明确批准后再执行 Phase 9d 最小 preview/copy UI slice。批准前不新增 HTTP endpoint、feature flag、SQLite 自动发现、Qdrant 读取或公共 chat 行为；Phase 8 public chunk API 继续 pending approval。

## ADR-040：Phase 9d 只在 Memo 详情页提供内存 Context Pack preview/copy

用户已明确批准 Memo 详情页 AI Inbox 作为唯一内部入口。实现默认选中当前 Memo 与 accepted insights，允许逐项取消 insight；当前 slice 不读取 Memo 列表，因此不提供跨 Memo 自动发现，未来跨 Memo 必须显式选择并通过当前用户可见性校验。

Web 端 `contextPack.ts` 镜像 Phase 9b Python `build_context_pack` 的 provider-neutral contract，在浏览器内生成 bounded Markdown/JSON。这样保留现有无 HTTP、无 Qdrant、无 worker 和不落 SQLite 的回滚边界；后续必须用共享 fixture 校验 Python/Web 的排序、预算和脱敏语义，避免双实现漂移。

空 accepted insight、用户清空来源、AI Service 查询失败、clipboard 失败和窄屏均有明确 UI 状态。pending/rejected/revoked/stale insight、删除或不可见 Memo、raw content、Webhook payload、secret 和 chunk content 不进入 pack。Phase 8 public chunk API 仍 pending approval，公共 chat 和完整 Memo collection 不变。

## ADR-041：Phase 9e 共享 Context Pack 输入并绑定 Memo 权限与派生状态生命周期

Phase 9e 采用根目录 `contracts/context-pack-v1.json` 作为 Python/Web 测试共同输入 fixture。它只包含安全的 Memo title/summary 与 insight 派生字段，不包含原始 Markdown、Webhook payload、secret 或 chunk content；生产代码继续在 AI Service 与浏览器分别执行 provider-neutral builder/adapter，不把测试 fixture 当运行时数据源。

Context Pack 的跨 Memo 选择必须来自 Memos 当前用户可见的 Memo 列表，并且每个额外 Memo 都需要用户显式勾选。默认仍只选择当前 Memo；额外 Memo 的 insight 通过同一 AI query key 查询，只有 accepted insight 可进入 pack，查询失败或 Memo 从可见列表消失时不得隐式扩展来源。这样把权限判断留在 Memos 产品边界，不在 AI Service 复制权限系统。

当前 reject 即 insight revoke：状态变更必须带当前 version，成功后递增版本并失效该 Memo 的查询缓存；Context Pack 的 accepted-only 过滤保证撤销不会继续输出。Memo deleted Webhook 无论索引是否启用都会清理 AI 自有 `ai_notes`、`memo_templates`、`memo_insights`，但不触碰 Memos 原文、Memos 数据库、公共 chat、完整/chunk collection 或 Qdrant volume。Context Pack 仍只在内存生成，不新增公共 HTTP、持久化审计、worker 或 Agent。

## ADR-042：Phase 9f 使用输出 golden 与本地只读生命周期诊断守住双实现边界

Python builder 与 Web adapter 继续独立，避免把浏览器 UI 与 AI Service 运行时耦合；根目录共享 fixture 因此从输入样例扩展为 expected Markdown 与 compact snake_case JSON golden output。两侧必须对同一 case 产生字节级一致结果，涵盖确定性排序、去重、accepted-only 过滤、预算截断与安全 source 输出。fixture 只用于测试，不作为生产运行时输入。

生命周期观测采用 `python -m scripts.devmemory_lifecycle_report` 本地只读 CLI，而不是新增 HTTP/telemetry API。它通过 SQLite `mode=ro` 汇总 AI Service 自有表的安全计数，不创建、迁移或写入数据库，且不输出 Memo ID、原文、chunk、Webhook payload 或 secret。该决策不改变 Memos 的权限/删除权威边界，不引入 worker、Prometheus 或新默认依赖。

## ADR-043：Phase 8 以网关签名可见范围实现受控 public-chunk-v1

用户已明确批准 public-chunk-v1 的鉴权、脱敏、去重和回滚契约。AI Service 实现独立 `POST /api/ai/v1/chunks/search`，但默认 `AI_PUBLIC_CHUNK_RETRIEVAL=false`。只有 flag 为 true 且 `AI_PUBLIC_CHUNK_SECRET` 非空时才处理请求；受信任网关必须使用该 secret 对精确 raw JSON body HMAC-SHA256，并在 body 中携带唯一 `visible_memo_ids`。AI Service 验证签名并将该集合强制用于结果过滤，不自行复制 Memos 用户/权限模型。

输出固定 `public-chunk-v1`、`memo-chunk-v1`，按 score desc、memo_id/chunk_index/chunk_id asc 排序，并只保留每个授权 Memo 的最高分 chunk。metadata 是 `source_type` 与可选 bounded title 的 allowlist，禁止 content、原始 Markdown、Webhook payload、secret 或内部字段。disabled/degraded 或缺 secret 返回 503，签名失败返回 401，scope/输入非法返回 422。回滚只关闭 flag，不迁移或删除 `memo-v1`、chunk collection/volume，也不修改 `/api/ai/chat`。

## ADR-044：Context Pack 复制优先保证系统剪贴板与 UI 稳定性

Context Pack 复制继续是浏览器内存中的本地交互，不新增 HTTP、SQLite 写入或外部依赖。实现优先在用户手势下使用 DOM copy，并仅在不可用时回退异步 Clipboard API；当两个能力都不可用时仍保留现有手动复制引导。复制状态不得通过会改变图标节点类型的瞬时替换破坏 React DOM 一致性。

该决策已由真实 Chrome/Windows 系统剪贴板验收覆盖 Markdown 与 JSON。它不改变 Context Pack 的脱敏来源、accepted-only、显式跨 Memo 选择、公共 chat、Memos 权限边界或 public-chunk-v1 rollout 条件。

## ADR-045：Phase 10 先记录本地 gateway contract evidence，不伪装为部署验收

Phase 10 的第一个切片使用 `python -m scripts.public_chunk_gateway_contract_smoke` 在进程内模拟受信任网关。它通过 exact raw-body HMAC 绑定 question、limit 和唯一 `visible_memo_ids`，并验证 disabled、missing/tampered signature、ambiguous scope、degraded store、授权去重及 metadata 脱敏。临时 secret 不输出，也不进入浏览器或部署配置。

该脚本使用 TestClient 和受控 fake chunk coordinator，不启动 HTTP 服务、不访问网络、不连接真实 Memos 权限层。因此它只能作为可重复的 contract/fake evidence，不能作为真实 gateway、用户可见范围映射、灰度流量或 flag rollback drill 的 pass。`AI_PUBLIC_CHUNK_RETRIEVAL=false` 继续是默认和唯一安全状态，直到真实受信任网关具有完整权限、兼容与回滚证据。

## ADR-046：Phase 10 人工反馈必须区分真实 Capture 与完整可复核生命周期

route B 可以使用真实、已登录的本地 Bug Report 作为 Capture 观察，但不能因为页面曾显示派生摘要就推断 accepted/rejected 持久化、用户反馈或 Context Pack 复制成功。当前已配置 AI SQLite 的只读 aggregate、路由实际视图和浏览器可见状态必须能共同支持该结论；若 aggregate 为零，只能记录未完成的观察。单次路由主体未刷新必须先以新的只读快照复核，不能直接升级为产品缺陷或阻塞。

这保持 Context Pack 的浏览器内存、accepted-only、脱敏来源与 Memos 权限权威边界不变。观察过程不允许绕过 Memos 登录、读取 raw content、修改 Memo/Insight 或把历史 Phase 9f 剪贴板验收重新表述为新的人工反馈；public chunk 继续默认关闭，直到 ADR-043 所需的真实网关证据存在。

真实反馈只能由在场且同意的参与者触发 review/revoke/delete/copy；无参与者或无 Insight 时应停止并如实记录。该过程不创建新运行时契约，也不授权 API 绕过、SQLite seed 或浏览器 secret 暴露。

当前参与者授权只覆盖一个非敏感测试 Memo 的创建与一次 Insight accept/reject；删除/撤销属于独立的行动时确认，不能由先前 review 授权推断。

该测试 Memo 已通过正常认证 UI 保存，但保存后的只读 aggregate 仍无 Insight，故本 ADR 的 stop condition 已触发：不从 Capture 推断 review、pack、copy 或用户反馈成功。后续只能先读取并诊断现有集成；不得创建第二条测试 Memo、seed SQLite 或绕过 Memos 权限来补齐状态。

## ADR-047：默认 Compose 路径以低 CPU 预算运行

Memos 与 AI Service 默认上限分别为 `0.75`/`0.25` CPU；Memos 的 `GOMAXPROCS`、验证脚本的 Go 并发及 AI 数值线程均固定为 `1`。这优先保证本地 capture/review/Context Pack 的响应，而不是最大吞吐量；如需更高性能，必须由使用者显式调整本地 Compose 配额。

Qdrant 与 Ollama 的资源成本不再属于默认启动路径，分别只能通过 `qdrant`、`ollama` Compose profile 显式启用。该决策不改变 deterministic + memory 默认、AI index opt-in、public chat、collection/volume 或 Phase 10 gateway/feedback 证据边界。

## ADR-048：本地私网 Memos Webhook 只用于真实集成证据，且规范化资源名

本地 Compose 中，Memos 以 `--allow-private-webhooks` 运行，允许当前已认证用户把其既有 webhook 指向 Docker 网络内的 AI Service。该开关只解决本机服务名解析到私有地址的部署限制；它不向浏览器公开任何 AI secret、不把客户端声明的 Memo ID 当授权，也不改变 Memos 作为 Memo/权限事实源。由于该开关放宽 Memos 对私有目标的限制，只能用于受控本地开发拓扑，不能据此声称生产网关 rollout 已通过。

Memos webhook 的当前 Memo 标识可为 `memos/<uid>`，而详情页 AI Inbox 使用终端 UID 查询。AI Service 在其派生状态边界将该单一资源名规范化为 UID，防止同一 Memo 形成两份 AI SQLite 状态；不读取或返回原文，且不改变 Memos 数据。该映射由 API 回归测试覆盖。

生命周期 CLI 仍保持只读、聚合、无 HTTP；运行 Compose 时必须在 AI Service 容器中执行，或明确传入 Compose 挂载的数据库文件。主机默认路径的空/旧 SQLite 不得作为线上容器状态或产品阻塞证据。该 ADR 不改变 `AI_PUBLIC_CHUNK_RETRIEVAL=false`、公共 `/api/ai/chat`、`memo-v1`、collection/volume 或 Context Pack 内存边界。

## ADR-049：Chrome 自动化证据与 Windows 剪贴板证据必须分层

Vite 重启后，接管长期 Chrome 用户标签可能超时；同一 profile 的新标签可继续验证已登录详情页和浏览器内存中的 Context Pack 状态。该恢复方式不改变登录、Memos 数据或 AI 派生状态，适合作为 UI 可见性与预算截断的证据。

自动化表面触发复制并不保证 Windows 系统剪贴板已被改写。若 host clipboard 未出现预期安全输出，必须记录为“自动化复制未验证”，不得把它当成产品回归，也不得把 UI 点击当成新的系统剪贴板 pass。Phase 10 已用真实 Chrome 指针点击及 host clipboard 复核确认 Markdown 与 JSON；此前自动化桥接不改写 clipboard 的观察仍只代表该工具路径。此决策不新增 Clipboard API、HTTP、SQLite 写入或外部依赖。

Phase 10 route B 的真实参与者随后确认来源清晰、accepted Review 可信、`64` 字符预算有用且复制符合预期。该反馈只评价已验证的安全 UI，不授权额外的 review、delete/revoke 或 public-chunk rollout。

## ADR-050：复制就绪反馈只描述当前浏览器内存中的 pack

Context Pack 在复制前直接显示当前输出的条目数、唯一来源数和 Markdown 字符数/预算，避免用户只凭截断标记判断 pack 是否适合粘贴。Markdown 与 JSON 使用相同的瞬时成功状态，并通过格式明确的 `role=status`/`aria-live=polite` 消息支持辅助技术。question、显式来源或预算变化并生成新 pack 后，旧 copied/manual/error 状态必须清除，因为它只对应上一份输出。

这些值全部来自现有浏览器内存 `context-pack-v1` 结果，不新增分析、权限推断、HTTP、SQLite、telemetry、Qdrant 或后台任务。安全字段、accepted-only、显式 Memo 选择、Python/Web golden、Memos 权限事实源与公共 chat 均不改变。

本切片的组件测试、全量 Web 测试、build 与项目 lint 已通过。真实 Chrome 插件连接成功，但当前 profile 的 Memos 登录态已失效且无浏览器保存凭据，因此没有进入详情页，也没有从 SQLite/token 存储绕过认证。Phase 10 的系统剪贴板证据仍是历史事实，但不能替代 Phase 11 的运行时验收。

## ADR-051：strict TypeScript 使用窄范围声明兼容层，不降低全局门禁

独立 strict TypeScript 的 15 项基线来自项目 callback 别名未进入编译，以及已安装第三方 package 的缺失 transitive declarations、ESM export assignment 和未导出 deep type path。项目 callback 改用明确 `() => void`；TanStack Query Devtools 与 goober 通过两个精确 TypeScript paths 暴露其实际消费的公开类型；Mermaid/type-fest、React Leaflet context 与 Leaflet MarkerCluster 通过窄范围声明补桥。

该兼容层只参与 TypeScript 类型解析，不替换 Vite 的运行时 package 解析，不引入或升级依赖，不修改 lockfile。禁止用全局 `skipLibCheck`、关闭 strict、宽泛 `any`、`@ts-ignore` 或删除检查来维持通过。依赖未来升级后，应在 strict tsc、定向测试和 production build 通过的前提下删除已经由上游修复的 bridge。

Phase 12 验证为 strict 0 errors、定向 `2/2`、Web `149/149`、build、项目 lint、Compose config 与 diff check 全部通过。Context Pack、Memos/AI 权限边界、API、数据库、public chat、collection/volume 和 `AI_PUBLIC_CHUNK_RETRIEVAL=false` 均未改变。

## ADR-052：Web lint 必须执行 strict TypeScript baseline

Phase 12 已在当前安装依赖下将独立 `tsc --noEmit` 收敛为 0 errors，因此 `web/package.json` 的日常 lint 不再保留 `--skipLibCheck`。`pnpm lint` 现在先运行 strict TypeScript，再执行 `biome check src`，使依赖声明回归在本地与 CI 风格门禁中立即可见。

该提升不修改 `tsconfig` strict 设置、runtime module resolution、依赖/lockfile 或 API。若未来依赖升级引入新的 declaration 错误，先检查是否能以精确、运行时无关的兼容声明修复；不得恢复全局 skip、关闭 strict、使用宽泛 `any` 或 `@ts-ignore` 来换取绿色门禁。

## ADR-053：开源发布默认安全部署、独立身份与 CI 命名空间

DevMemo AI 是基于 Memos 的非官方下游项目。发布说明必须同时保留上游版本/许可 NOTICE、明确的维护者与贡献/支持/行为准则入口，以及本项目自己的安全报告渠道；不得把上游 issue、资助、Docker Hub、GHCR 或安装资产误表述为 DevMemo AI 的发布入口。Go module import path 继续保留 `github.com/usememos/memos`，以避免为品牌改名扩大到上游核心代码和运行时行为。

默认 Compose 禁止 Memos 私网 Webhook 目标。只有受控本机开发需要访问 Docker service hostname 时，才可显式叠加 `docker-compose.local-webhook.yml`；公共或多用户部署不得使用该 override。该部署拆分不改变 Memos 权限事实源、AI 默认 deterministic + memory、Webhook/API/SQLite、Context Pack 或 `AI_PUBLIC_CHUNK_RETRIEVAL=false`。

CI 和发布资产使用 `devmemo-ai` 与 `ghcr.io/${github.repository_owner}/devmemo-ai` 命名空间，并对 AI Service 增加独立 pytest 与 Compose-config 检查。正式 release 仍必须先取得可用的发布凭据/包权限、私有漏洞报告通道、通过的既有后端 CI 以及真实仓库发布证据；任何一项缺失时都不得发布、推送稳定标签或把文档中的预期命名空间宣称为已发布资产。

## ADR-054：迁移 CI 使用固定兼容 fixture，linter 超时不得掩盖零问题结果

`store/test` 的迁移兼容测试不得使用浮动的 `neosmemo/memos:stable` 镜像。上游 stable 可在本项目未同步 schema migration 时前进，形成“当前代码尝试降级未来数据库”的无效失败。测试改用固定、可拉取的 `neosmemo/memos:0.26.2` fixture，并验证 SQLite schema 从 `0.26.5` 迁移到当前 `0.28.1` 后仍可写入数据。该 fixture 只用于测试，不改变默认 Compose 镜像、运行时升级策略或上游归属。

远端 golangci-lint 已在 `0 issues` 后因固定三分钟 timeout 失败，因此 action timeout 增至五分钟。它不放宽 lint 规则、跳过检查或改变 Go 编译/运行时。授权 push 后，完整 Store 驱动矩阵与真实 GitHub Actions 已通过；本机低 CPU 检查仍只证明固定 SQLite 迁移路径，不替代远端矩阵证据。

## ADR-055：GHCR 使用固定小写命名空间，RC 资产验证不等同于公开稳定发布

OCI repository 名称必须小写；GitHub owner 的展示大小写不能直接插入 GHCR repository reference。DevMemo AI 的 canary 与 release workflow 因此固定使用 `ghcr.io/toyohin/devmemo-ai`，而不依赖 `${{ github.repository_owner }}`。该变更只修复发布元数据，不改变 Go module、Memos 运行时、默认 Compose、AI provider、索引或 Context Pack 边界。

在真实 GitHub runner 上，修复后的 canary 已通过 amd64/arm64 build、manifest 合并与 registry inspect；`v0.1.0-rc.1` 作为 private prerelease 已生成六个原生资产、校验清单与多架构镜像。本机仅以低负载校验 Windows ZIP 的 SHA-256、解压和 `devmemo-ai.exe --help`；这不是完整安装、升级、运行时或公开用户验收。

RC 不能解除公开稳定发布的治理条件：仓库可见性、外部可用的私密漏洞报告渠道、维护者审阅与独立的稳定 tag/release 授权仍然必需。`RELEASE_PLEASE_TOKEN` 只用于可选的自动 proposal；缺失时 workflow 安全跳过，不能用个人 OAuth token 代替。当前本机 OAuth token 缺少 private Packages `read:packages`，直接 GHCR inspect 返回 403；runner-side inspect 成功是发布工作流证据，但不替代维护者需要时配置最小可轮换拉取凭据。

## ADR-056：公开仓库、GitHub Release 与 GHCR package 可见性分别验收

稳定 `v0.1.0` 已在 public 仓库发布，且 GitHub private vulnerability reporting 已启用；这两个状态不能自动改变独立 GHCR Container package 的 visibility。公开镜像发布的完成条件是未登录 Docker 客户端可以 inspect `ghcr.io/toyohin/devmemo-ai:stable` 并看到预期多架构 manifest，而不是仅在 GitHub runner 或认证会话中成功。

后续状态更新：Container package 已由具备 GitHub Packages 管理权限的维护者设为 public。
匿名 `docker buildx imagetools inspect ghcr.io/toyohin/devmemo-ai:stable` 已确认
linux/amd64、linux/arm64 与 linux/arm/v7 manifests。该发布状态不改变产品运行时默认值。

## ADR-057：R5 durable Agent 正文使用 Memos 当前权威 rehydration

R5-I3 为第一条 durable Agent 检索路径选择认证的 Memos 当前权威 rehydration，不在 AI 侧持久化完整
Memo 正文，也不引入持久 hybrid cache。R5 eligibility 选择后，独立 purpose/path 的未来服务端 transport
必须解析由 Memos 签发、AI 不解释且仅请求内使用的 opaque authority reference，重新确认当前 visibility
与完整 Memo eligibility，并以 all-or-nothing 精确 schema 返回正文；
AI 侧再校验 selection sequence/hash/version 与仍为当前值的 derived snapshot token。update、delete、
archive/comment/blank、tombstone、quarantine、旧 generation、部分响应或任何不一致均整体 fail closed。

完整正文只允许存在于认证请求的短时内存，不能进入 AI ledger、vector payload、日志、metrics、trace、
backup 或错误正文。Memos 继续拥有正文、身份、visibility、retention、加密、backup 与 restore；AI 派生
状态可丢弃并从 Memos 重建，不能成为第二事实源。最终 identity 仍来自 Memos-authority query，citation
仍由 R5 service 构造。所有故障只投影为 `authorized_retrieval_unavailable`。

此决策只约束新的 durable Agent 路径，不在本切片迁移或删除 ADR-017 所述旧完整 Memo vector metadata，
但旧 payload 不得作为 R5 的生产正文、可见性、身份或 citation authority。R5-I3 不实现 transport、route、
repository、runtime wiring、secret、Compose、database 或真实数据。下一授权最多证明单机认证 transport；
真实数据接入前必须完成 backup、dry run、rollback 与 reconciliation，多实例前必须增加跨宿主加密和共享
replay protection。

## ADR-058：rehydration request 与 response 使用独立 HMAC 和双向单进程 replay

R5-I4 将 `memo-evidence-rehydration-v1` 绑定到独立 transport version、固定 `POST` path 与
rehydration-only request purpose。request canonical form 包含 purpose、version、method/path、十进制
timestamp、nonce 和 exact body digest；验证在 exact JSON parsing 与 Memos authority callback 前完成，
并消费有界 process-local request replay entry。callback 最多执行一次，timeout、authority 或 schema
failure 只生成固定 `authorized_retrieval_unavailable`。

正文 response 使用不同的 response-only purpose 与 header namespace，canonical form 绑定 response
timestamp、原 request nonce、derived snapshot token、status 和 exact body digest。AI 侧必须先验签和检查
时效，再 exact parse、核对全部 selection reference/sequence/hash/version，并消费独立 client-side replay
entry。成功只允许 `200` exact R5-I3 response，失败只允许签名的 `503` 固定错误；response、错误和可观测
输出均不得包含 `memos_authority_ref`。契约固定未来 client timeout 为五秒且不自动重试，本切片只映射
合成 `TimeoutError`，不实现 HTTP timer。

两个 replay store 都明确只证明单进程；HMAC 只证明完整性和 scoped secret possession，不提供正文
保密性。本切片没有 route/client、runtime secret/config、database、repository、Compose、真实 Memo 或
runtime selection。跨宿主或多实例前必须增加加密 transport、shared replay storage、密钥轮换和独立
威胁评审；下一步仅允许证明 Memos Go 侧对共享 fixture 的跨语言 parity。

## ADR-059：Memos Go 侧先证明 rehydration transport parity，不接 authority 或 runtime

R5-I5 在 `internal/aiagent` 增加独立、未接线的 Go request verifier 与 response signer/parser。request
验签严格复现 R5-I4 的 purpose、transport version、固定 method/path、十进制 timestamp、nonce 与 exact
body digest；验签和 60 秒时效检查先于 exact nested JSON parsing。response 使用独立 purpose，签名前
必须通过 exact success 或固定 `503` parsing，并重新核对 derived snapshot token 与全部 selection
reference/sequence/hash/version。

共享 `memo-evidence-rehydration-transport-v1.json` 同时锁定 Python 与 Go canonical bytes。Go 侧对未知、
缺失、重复、部分、超限、非法 UTF-8、identity-bearing 或不一致 payload 只返回
`authorized_retrieval_unavailable`，不暴露正文、authority reference、secret、signature、digest 或原始错误。

本阶段不增加 Go replay store、Memos authority lookup、HTTP route/client、runtime secret/config、数据库、
网络或真实数据。Python R5-I4 的 process-local replay 证明保持不变；任何多实例使用仍需要 shared replay
storage 和加密 transport。下一步必须先用纯对象定义单机 Memos current-authority adapter 边界，再单独
授权实际 transport 与 runtime selection。

## ADR-060：Memos current-authority reader 先固定纯 Go 原子快照契约

R5-I6 在真实 Store 或 HTTP 接线前，先用 provider-neutral Go 对象固定 Memos-owned current-authority
reader 边界。输入只能是 R5-I5 已验签并 exact parse 的 `EvidenceRehydrationRequest` 与 Memos 内部 opaque
认证上下文绑定；绑定类型不包含 caller ID、owner 或 visibility 字段。`memos_authority_ref` 只做请求内
精确关联，不解码、不投影到响应，也不进入错误或可观测输出。

reader 每次只允许返回一个原子 snapshot。snapshot 与每个文档必须在 authority reference、认证上下文、
revision 和 authority token 上一致，并重新确认当前 visibility、complete Memo、normal row、current lifecycle、
非空正文、UID、source sequence、document hash 与 `memo-v1`。请求 UID 与文档必须精确一一对应；缺失、
多余、重复、unknown、archive/comment/blank/delete/tombstone、并发 update、stale 或混合 snapshot 全部
整体失败。成功响应按请求拥有的 selection reference 顺序构造，只包含 R5-I3 exact 字段，不包含 Memo UID、
identity、visibility、authority reference、citation 或 store metadata。所有失败固定为
`authorized_retrieval_unavailable`，不返回部分正文或原始错误。

本阶段的 reader 实现仅为测试内存 fake，因此只证明契约和 fail-closed projection，不证明真实 Store
transaction 原子性。真实 Memos Store reader、visibility resolver 接线、HTTP handler/client、HMAC/replay
运行时接线、secret/config、AI runtime selection、数据库、网络与真实数据均未加入，必须分别授权。

## ADR-061：首个真实 current-authority reader 限定为未接线的单机 SQLite snapshot

R5-I7 把 R5-I6 protocol 绑定到现有 Memos authentication context 与 SQLite Store，但不注册 HTTP route、
runtime factory 或 answer path。caller ID 只能由 `auth.GetUserID` 从 Memos 内部 context 取得；request、query、
derived metadata 与 opaque binding 都不能提供或覆盖 caller identity。reader 复用 `ListMemos` 的共享
visibility scope，并在 transaction 内重新确认 caller user row 仍为 normal。

reader 使用专用 SQLite connection 的只读 transaction。受限 requested-UID CTE 下推最多十个 UID，并在
同一 snapshot 中读取 Memo row、comment relation、正文，以及该 UID 按 outbox id 排序的最新 A4 source event。
只有 normal、非 comment、非空、当前可见的完整 Memo，以及最新 operation 为 upsert、version 为 `memo-v1`、
source document 等于当前 Memo 正文的记录才能返回。sequence/hash/version 与 UID 一一对应仍由 R5-I6 再次
验证；正文权威来自 `memo.content`，outbox 不能提供 visibility、identity 或 citation。

transaction 前后的 SQLite `PRAGMA data_version` 必须相同。任何其他 connection 在读取期间提交 update、delete、
archive、comment、blank 或 visibility 变化，都会使整批固定失败；这允许保守拒绝无关并发写，不能接受混合或
过期内容。open/schema/query/transaction/consistency failure 均只映射为
`authorized_retrieval_unavailable`，不包含正文、identity、visibility、authority ref、SQL 或原始异常。

该证明只使用临时 SQLite 和合成数据，不证明 MySQL/PostgreSQL、HTTP、真实数据或多实例。authority token
仍由未来单独授权的 Memos capability issuer 提供，reader 不签发 token。下一闸门应先定义 process-local、
有界、短时的 authority capability issuer/resolver，使 opaque authority reference 能安全恢复 Memos-owned
caller binding；之后才能分别授权 HTTP handler/client、HMAC/replay runtime 接线与 AI runtime selection。

## ADR-062：R5 authority capability 先限定为单进程、有界、短时且单次消费

R5-I8 在任何 HTTP 或 answer runtime 接线前，先定义 Memos-private capability issuer/resolver。签发入口只
接受 Memos 内部认证 context，并用 `auth.GetUserID` 派生 caller；接口不接收 caller ID、owner、visibility、
query、rehydration request 或任意 UID scope。一个尚未接线的 Memos-owned scope source 必须返回同一个
current caller，以及采用 R5-I1 UID matcher、非空、不重复且最多 1,000 个完整 Memo UID 的授权集合。unknown、
archived、binding mismatch、scope failure 或非法集合全部固定失败。

registry 的容量和 TTL 在构造时固定，TTL 上限为 60 秒；它只使用注入 clock 做惰性过期，不创建 timer。
每次签发从独立 token-source 值派生 `memos_authority_ref`、authenticated-context token 与 authority token，
并通过每个 registry 的独立 entropy 与单调序号避免同一进程回收容量后把旧 capability 解析为新 entry。
三个 token 必须 opaque、互异且精确绑定同一私有记录；只有 authority reference 预期进入未来签名 request。
caller、完整 UID scope、authenticated-context token 与 authority token 均不进入浏览器 schema、日志、错误或
可观测输出。

consume 在一把锁内完成过期清理、reference lookup、两个私有 token index 的一致性检查、selection 验证与
entry 删除。selection 必须是原始授权集合中唯一、1 至 10 项的有界子集；missing、extra、duplicate、unknown、
ref/token mismatch 或 malformed request 都在调用 R5-I7 前拒绝。并发 consume 最多一个成功；成功只返回
Memos-private resolution，用于未来恢复 server-owned auth context、精确原始 UID scope、未改变的两字段
`EvidenceAuthorityContextBinding` 与 authority token。失败不返回 caller、scope、token 或 partial binding，
并统一映射为 `authorized_retrieval_unavailable`。

本 registry 明确只证明 process-local request capability：进程重启或新 registry 会使旧 entry 失效，也不
复用 R5-I4 transport nonce store。R5-I8 没有 HTTP route/client、HMAC/replay runtime composition、运行时
secret/config、answer path、数据库、持久化、网络、Compose、Provider、Qdrant 或真实数据。下一闸门需单独
评审单机 handler/client 与 replay composition；多实例前必须提供 shared atomic capability/replay storage、
加密 transport、密钥轮换与独立威胁评审，AI runtime selection 仍需之后另行授权。

## ADR-063：R5 单机 transport composition 先保持未注册、单次且进程内

R5-I9 在任何 HTTP route/client 或 answer runtime 接线前，把既有边界组合为一个 Memos-private、未注册的
纯 Go service。构造函数只接受显式注入的 scoped secret、最多 60 秒的 request age、clock、专用有界
request replay store、R5-I8 capability registry 与 reader factory；没有环境变量、全局 singleton、timer、
自动 retry 或隐式 Store lookup。未来 client timeout 仍固定为五秒且 `auto_retry=false`，本阶段没有 network
timer 或 client。

调用顺序固定为 R5-I5 HMAC/freshness/exact parsing、专用 nonce consume、R5-I8 capability consume、私有
resolution 二次 scope/binding/token 校验、server-owned auth context 恢复、reader factory、R5-I6
all-or-nothing projection、exact JSON serialization 与 R5-I5 response-only signing。replay store 与 capability
registry 是两个不同类型、不同容量状态的 process-local 对象；同 nonce 的并发请求最多一个越过 replay，
同 capability 即使换 nonce 也最多一个进入 reader。reader factory 和 reader 每个请求都最多调用一次，caller、
完整 UID scope、authenticated-context token 与 authority token 均不能来自 request/header/browser/AI。

未通过 request 认证的输入没有可信 snapshot token，必须在 replay/capability 前以固定本地
`authorized retrieval unavailable` 和零 response projection 拒绝，不能伪造“已签名失败”。请求验证完成后，
replay、capability、scope、binding、reader 或 schema failure 只生成 exact、response-HMAC 签名的
`503 {"error_code":"authorized_retrieval_unavailable"}`；若 response signing 本身失败，则返回零 projection
与同一固定本地错误，绝不降级成未签名响应。成功只允许 exact signed `200` R5-I6 response。

该证明只覆盖单进程调用顺序、并发单次性与故障投影。新 replay store 清空 nonce history，新 capability
registry 使旧 authority reference 失效；二者都不主张 restart persistence 或 multi-instance safety。R5-I9
没有注册 `net/http`、实现 client、配置 runtime secret、接 `EvidenceAnswerAgent`/`RetrievalService`、访问真实
Store/网络/数据或改变 Compose/defaults。下一闸门必须单独评审 disabled single-host HTTP adapter 与 runtime
secret/timeout lifecycle；任何多实例使用前仍需加密 transport、shared atomic replay/capability storage、
密钥轮换与独立威胁评审，AI runtime selection 继续后置。

## ADR-064：R5 单机 HTTP adapter 保持未注册，并对未验证输入使用无正文 404

R5-I10 只在 R5-I9 composition 外增加 dormant 标准库 `net/http` handler/client 对象，不注册 route、不启动
listener、不绑定 port，也不读取环境变量或配置。handler 只接受精确
`POST /internal/ai/agent/evidence/rehydrate`、无 query/encoded path、四个 R5-I5 request header 各一个值、精确
`application/json`，以及 1 byte 至 32 KiB 的已知非 chunked body；有界读取、唯一 JSON value、body close 与
request context 均必须在进入 R5-I9 前 fail closed。query、cookie 或浏览器 header 不能补充 caller、scope、
UID、binding、authority token 或 secret。

未通过该 HTTP envelope 或 R5-I9 verification 的输入没有可信 snapshot token，因此统一投影为无正文、无
response HMAC 且 `Cache-Control: no-store` 的 404。不得伪造 signed failure，也不得回显 raw error、nonce、
authority reference、snapshot token 或 secret。R5-I9 返回的 exact signed 200/503 只允许逐字节映射 status、
body、四个 response HMAC header、`application/json` 与 `no-store`；不得增加 envelope、identity、visibility、
Memo UID、authority reference、debug header 或 cacheable response。

client constructor 只接受单一 base URL、scoped secret、clock 与 `RoundTripper`。其 `http.Client.Timeout` 固定为
五秒，禁止 redirect follow，不实现 automatic retry；每次调用只发送一次 exact POST。response body 必须有界
读取并成功关闭，response header 必须唯一且符合 allowlist，context cancellation 必须 fail closed。R5-I5 Go
transport 新增 response verifier，在解析正文前绑定 response freshness、request nonce、derived snapshot token、
status、exact body 与 response-only HMAC。client-side response replay 仍只属于 AI R5-I4 process-local store，
Go handler 不建立第二份 client replay store。

测试只使用 `httptest.ResponseRecorder`、内存 handler 调用、fake `RoundTripper`、合成 secret/capability/Memo UID
与 fake clock；没有建立真实 socket、访问 Store/网络/Provider/Qdrant/账号/Memo/volume 或真实数据。本阶段不
决定 runtime secret sourcing、rotation、双 secret overlap 或 shutdown ownership，也不证明 restart
persistence、cross-host confidentiality 或 multi-instance safety。R5-I11 必须单独评审这些 runtime lifecycle
与 dormant registration 决策；任何多实例使用前仍需加密 transport、shared atomic replay/capability storage、
密钥轮换与独立威胁评审，AI runtime selection 继续后置。

## ADR-065：R5 rehydration 使用独立、启动时固定且默认关闭的双 key 配置域

R5-I11A 不复用 Memos `APIV1Service.Secret` 或回答委托使用的 `AI_AGENT_INTERNAL_SECRET`。deployment boundary
负责生成并分别向 Memos 与 AI Service 进程注入一个 purpose-scoped
`AI_AGENT_REHYDRATION_SECRET_CURRENT`，以及 rotation overlap 期间可选的
`AI_AGENT_REHYDRATION_SECRET_PREVIOUS`；服务不得创建、通过 HTTP 分发、持久化、记录、trace 或投影这些值。
两个 secret 都必须是规范的无填充 base64url 32-byte 值，必须互不相同，也不得等于 delegation secret。

`AI_AGENT_REHYDRATION_ENABLED` 默认 false；关闭时 Go/Python settings 必须返回零值且不保留已经提供的 secret
或 URL。启用还要求 `AI_AGENT_ENABLED=true`，否则配置失败。AI 侧同时要求
`AI_AGENT_REHYDRATION_MEMOS_URL` 是不含 userinfo、query、fragment 或子路径的单一 HTTP(S) origin。配置非法
时 fail startup，不允许静默回退到不安全的共享 secret、默认 URL 或 enabled-but-partial runtime。

keyring 最多包含 current 与 previous，只在进程启动时构造；R5-I11A 不增加 timer、动态 reload、secret manager、
route、client、listener、port 或真实 secret。R5-I11B 必须按固定顺序验证 current/previous，并使用实际匹配的
request key 签 response，使 Memos 先接受新旧 key、AI 后切换 current 的轮换顺序可行。旧 key 只能在最后一个
旧请求的 60 秒 freshness 与五秒 client timeout 窗口后移除，保守运维等待为至少 90 秒。rollback 是关闭
rehydration flag 并重启；Memos 数据不变，process-local replay/capability 状态按既有边界失效。

R5-I11B 的 handler 仍由现有 Memos HTTP server 和 shutdown 管理，不增加 listener；R5-I11C 的实际 runtime
client 必须属于 Python AI Service lifespan，并在 shutdown 时关闭 transport。R5-I10 Go client 保持协议/测试
证明，不接入 Memos runtime。任何 Docker、浏览器、真实 Provider/账号/Memo/secret/data 或多实例主张继续需要
后续独立授权与证据。

## ADR-066：R5 dormant Memos runtime 共享单次状态并由现有 Echo server 托管

R5-I11B 不改变 R5-I9 单密钥 composition，而是在一个 HTTP handler 内固定按 current、previous 顺序尝试最多
两份 composition。两份 composition 必须共享同一个 process-local capability registry 与 request replay store；
因此 key rotation 不得制造第二个 capability 或 replay 域。第一个成功验签的 composition 继续完整处理请求，并用
同一个实际匹配 key 签 exact 200/503 response。current 已验签但后续 authority/read 失败时直接返回 current-key
signed 503，不允许再尝试 previous。两个 key 都无法认证时仍返回无正文、unsigned、`no-store` 404。

`AI_AGENT_REHYDRATION_ENABLED=false` 时不构造 runtime 且不注册 route。显式启用后，只在现有 Memos Echo
实例注册 exact internal POST；错误 method 由 Echo 返回 405。runtime 只持有 handler、共享 registry/replay 与
reader factory，注册期间不读取 Store。它不创建 listener、port、goroutine、timer、HTTP transport、closeable
resource 或 shutdown hook；生命周期自然属于现有 Memos HTTP server。配置还必须拒绝复用 `APIV1Service.Secret`。

该 route 目前保持 dormant：capability issuer 尚未接入回答路径，Python runtime client 也尚未创建。测试只使用
Echo/httptest、synthetic secret、fake authority/reader/clock 与进程内对象；没有启动 socket、访问真实 Store、
Provider、Qdrant、账号、Memo、volume、真实 secret/data 或外部网络。R5-I11C 单独负责 Python client lifespan
与 transport shutdown；`EvidenceAnswerAgent` 和 durable runtime selection 仍需后续窄切片。

## ADR-067：R5 Python rehydration client 只由 AI Service lifespan 创建和关闭

R5-I11C 使用独立 `EvidenceRehydrationHTTPClient`，不接入 R5-I10 的 Go client，也不创建第二个 service 或
listener。启用时 FastAPI lifespan 以 I11A 的 exact Memos origin 与 current key 构造 client；生产显式注入
`AsyncHTTPTransport(retries=0)`，测试只注入内存 transport。disabled lifespan 不构造 transport 或 client。
client 仅保存在 `app.state`，shutdown 必须清空 state 并 `aclose` owned client/transport。

每次调用只生成一个 request nonce、准备一次 exact signed POST，并使用固定五秒 timeout、`follow_redirects=false`
和零 automatic retry。response 只接受 exact 200/503、单值 JSON/no-store/HMAC headers 与有界非空 streamed body；
body 在任何 success/failure 路径关闭后才进入既有 response verifier/parser。client 生命周期内只拥有一份既有
`RehydrationReplayStore`，重启即失效；不得把 response replay 复制到 Memos handler 或持久化。

I11C 不把 client 注入 `EvidenceAnswerAgent`、endpoint、当前 `RetrievalService`、VectorStore factory、A4 lifecycle
或 Compose 默认值，也不发起真实网络请求。下一窄切片必须单独决定并验证 authenticated answer path 的
Memos-owned capability issuance 与 durable runtime selection；在此之前 route/client 均保持 opt-in dormant，
真实 Docker/浏览器验收仍受独立 runtime 授权闸门约束。
