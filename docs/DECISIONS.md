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
