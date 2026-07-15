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

## Phase 5f：Qdrant chunk 持久化与显式 chunk 检索（已完成）

当前最小切片已完成：

1. 增加 `QDRANT_CHUNK_COLLECTION`，默认 `devmemo_memo_chunks`，并通过 Compose 透传。
2. 配置层拒绝空 chunk collection 名称，且拒绝复用完整 Memo 的 `QDRANT_COLLECTION`。
3. fake Qdrant contract 明确校验独立 collection 的维度和 Cosine distance；chunk 版本继续使用 `memo-chunk-v1`，完整 Memo 继续使用 `memo-v1`。
4. 组合根已接入 chunk store 选择：仅 `AI_INDEX_MODE=chunk` + `AI_VECTOR_STORE=qdrant` 使用独立 Qdrant collection，其他路径继续使用独立 memory store。
5. chunk coordinator 的 health 已自然读取所选 VectorStore；默认 deterministic + memory、Webhook 和 `/api/ai/chat` 不变。
6. 新增 `ChunkRetrievalService`、`ChunkCitation` 和 `ChunkRetrievalResult`；严格校验 `memo_id`、`chunk_id`、`chunk_index`、`index_version` 与 chunk source metadata，原文只留在服务端 context。
7. `ai-service/scripts/smoke_qdrant.py --mode chunk` 覆盖 Qdrant health、upsert/search、重新连接后的 point_count/检索持久性、chunk contract 和 delete；默认临时 collection 自动清理。

验证：AI Service 聚焦测试 24 passed；Docker/Qdrant deterministic chunk smoke 返回 `QDRANT_CHUNK_SMOKE_OK`，初始/重连 point_count=2，删除后为 1，临时 collection 已清理；不改变公共 `/api/ai/chat`。

## Phase 5g：Qdrant chunk rollout gate（已完成）

1. Docker Desktop/Qdrant 恢复后，deterministic chunk smoke 返回 `QDRANT_CHUNK_SMOKE_OK`；health、upsert/search、重新连接后的 point_count/检索持久性、内部 contract 和 delete 均通过，临时 collection 已清理。
2. 完整门禁通过：AI Service 153 passed；前端 131 passed；TypeScript、build、lint、Compose config 和 Go `go test -p 2 ./...` 通过；Qdrant Server 1.18.2。
3. rollout 结论：chunk retrieval 保持内部边界，不接入公共 `/api/ai/chat`，不替换完整 Memo collection。

下一阶段：Phase 6 public chunk retrieval compatibility decision；先评估公共响应、引用排序和迁移/回滚契约，再决定是否实现外部接入。

## Phase 6：public chunk retrieval compatibility decision（已完成）

1. 对比现有 `POST /api/ai/chat` 的完整 Memo `CitationResponse` 与内部 `ChunkCitation`，确认 `embedding_id`、`retrieved_count`、同 Memo 多结果、排序和上下文预算不能无版本替换。
2. 决定不增加隐式 chunk mode、不修改公共 chat citation、不新增未定义的公共 chunk endpoint；继续保留内部 `ChunkRetrievalService` 和只读 chunk health。
3. 未来公开 chunk retrieval 前必须先定义 versioned API、chunk citation schema、Memo 去重/排序、content 脱敏和迁移/回滚 contract tests。

验证：现有 `test_chat_api_retrieves_memo_and_returns_citations` 保持公共完整 Memo citation 契约；AI Service 全量 153 passed，未修改运行时代码。

下一阶段：Phase 7 public chunk API proposal；仅在获得明确版本化公共契约后实现，不自动扩大现有 chat。

## Phase 7：public chunk API proposal（已完成提案，未实现）

1. 提出独立 `POST /api/ai/v1/chunks/search` / `public-chunk-v1`，不复用或修改现有 `POST /api/ai/chat`。
2. 定义请求 `question`/`limit`、固定 `memo-chunk-v1`、脱敏 chunk citation、同 Memo 只保留最高分 chunk、确定性排序和 `422/503` 错误边界。
3. 定义默认关闭的 `AI_PUBLIC_CHUNK_RETRIEVAL=false`、网关认证/ Memo 权限前提、离线双路径评估、灰度与仅关闭 flag 的回滚；本阶段不新增 HTTP 路由。

验证：提案文档与现有 `test_chat_api_retrieves_memo_and_returns_citations` 对齐；运行时代码未修改，公共 chat 默认行为保持不变。

下一阶段：Phase 8 public chunk API implementation gate；只有获得明确产品/兼容批准后才实现提案 endpoint。

## Phase 8：public chunk API implementation gate（pending approval）

当前只收到阶段名称，没有明确产品/兼容批准。根据 ADR-035，本阶段不实现 `POST /api/ai/v1/chunks/search`，不新增公共路由或运行时 feature flag，不启动灰度，不改变现有 chat、memo-v1 collection 或 chunk collection。收到明确批准并接受 ADR-034 的版本化字段、去重、脱敏、认证和回滚条件后，才进入实现切片。

## Phase 9：DevMemory Loop / AI Inbox 与 Decision Ledger（9a/9b 已完成）

Phase 9a 不依赖 Phase 8 public chunk API 的批准，已在现有 AI Service 边界内完成第一个可回滚垂直切片：

1. `MemoInsight` contract 已固定：事实、决策、行动和 Bug 候选统一携带来源、置信度、版本和 pending/accepted/rejected 生命周期。
2. 复用现有内容解析器和 deterministic 路径，新增 `memo_insights` SQLite 幂等表；语义变化会重置 pending，过期状态更新被拒绝；不写回 Memos 原文。
3. 新增 preview/查询/状态变更内部 API 和 Memo 详情页 AI Inbox 卡片；用户可确认/拒绝 AI 派生内容，原始 content 不进入响应。
4. Context Pack v1 已定义纯函数 builder/fixture：只消费显式已确认 Memo/insight，限制来源、字数和输出格式；不做 agent、网页搜索或 MCP。

验证事实：AI Service 174 passed；Context Pack 定向 12 passed；Phase 9a 前端 136 passed、TypeScript/build/lint 和真实 Compose API smoke 已通过；Playwright 截图 artifact 为 `devmemo-phase9-ai-inbox.png`。

Phase 9b contract 事实：`context-pack-v1` 只接受显式 `memo_ids`/`insight_ids`；只允许 accepted insight；同 Memo/source 去重；insight 按 confidence 降序、updated_at 降序、稳定 ID 升序；Markdown 严格受 `max_chars` 约束，超限返回 `truncated` 与原因；JSON 与 Markdown 共享同一 items/sources。

差异化判断：Memos 擅长快速捕获，Khoj 擅长个人 AI/语义搜索/自动化，AnythingLLM 擅长 workspace RAG/agents，AFFiNE 擅长文档-画布-表格工作区，Logseq 擅长本地知识图谱，Outline 擅长协作知识库。DevMemo AI 应聚焦“开发记忆的可审核生命周期”：把 Bug、决策、代码片段和上下文变成可撤销、可追溯的工程资产，而不是复制任一项目的完整平台。

## Phase 9c：Context Pack integration gate（proposal-only 已完成）

本阶段没有收到明确产品入口批准，因此只完成集成评审，不修改运行时 UI/API。推荐唯一入口为 Memo 详情页 AI Inbox 的“复制 Context Pack”：默认当前 Memo，跨 Memo 必须显式选择；命令面板和独立页面暂不采用。

集成 contract：只有当前用户可见 Memo 与 accepted insight 可进入；pending/rejected、删除 Memo、撤销 insight、过期版本和不可见来源必须排除。Markdown 是主复制格式，JSON 可选；必须展示 question、sources、截断原因、空/失败/窄屏状态；不显示 raw content、Webhook payload、secret 或 chunk content，pack 不落库。

Phase 8 public chunk API 继续 pending approval，默认 deterministic + memory、公共 chat 完整 Memo 语义、完整 Memo/chunk collection 和所有第三方参考边界均不变。下一切片为 Phase 9d internal preview/copy approval gate：只有入口批准后才实现最小 UI 垂直切片。

## Phase 9d：Context Pack internal preview/copy 已完成

用户已明确批准 Memo 详情页 AI Inbox 的内部入口。本切片复用 `context-pack-v1` 的显式来源与 bounded 输出语义，在 `web/src/features/ai/` 内生成临时 pack：默认当前 Memo + accepted insights，来源可取消选择，其他 Memo 不自动发现。

UI 提供 question、`max_chars`/`max_items`、Markdown preview/主复制、JSON 复制、sources、截断提示，以及 empty、AI 查询 failure、clipboard failure 和窄屏布局。只消费安全 title/summary/source_refs，不展示 raw content、Webhook payload、secret 或 chunk content；不写 SQLite，不新增公共 HTTP，不连接 Qdrant，不启动 worker/Agent。

验证：Web 定向 7 passed；全量 33 files / 143 passed；TypeScript、build、lint 通过；Playwright 已完成登录、approve、复制、预算截断和 390px 窄屏手动路径。下一阶段处理 canonical fixture、权限感知的跨 Memo 显式选择、删除/撤销联动，不改变公共 chat 或 Phase 8 gate。
