# DevMemo AI 项目状态

更新时间：2026-07-14

## 当前阶段

Phase 0、Phase 1、Phase 2、Phase 2b、Phase 2c、Phase 2d、Phase 3a、Phase 3b、Phase 3c、Phase 3d、Phase 3e、Phase 3f、Phase 3g、Phase 4、Phase 4b、Phase 4c、Phase 4d、Phase 4e、Phase 4f、Phase 4g、Phase 5a、Phase 5b、Phase 5c、Phase 5d、Phase 5e 已完成。当前阶段为 Phase 5f：Qdrant chunk 持久化与显式 chunk 检索，collection/config contract 已完成，composition 尚未接入。

## 当前事实

- 工作区：H:\DevMemoAI
- 分支：codex/devmemo-ai-mvp
- 协作模式：单 Agent；只使用主工作树，`project4` 下的 Terra/Luna worktree 暂不参与开发
- Memos 基线：v0.29.1
- Go：G:\Go；Go 工作区和缓存：G:\GoWorkspace
- AI Service：FastAPI，默认 deterministic provider
- AI 数据：AI Service 自有 SQLite；不修改 Memos 数据库
- 默认向量存储：InMemoryVectorStore
- 可选向量存储：QdrantVectorStore
- 可选 embedding：FastEmbedEmbeddingProvider，默认不启用、不加载模型；本机已安装依赖用于 smoke
- 索引健康接口：GET `/api/ai/index/health`，默认 memory 路径不连接 Qdrant
- RAG 接口：POST `/api/ai/chat`，当前检索完整 Memo 并返回引用；默认 deterministic + memory 可离线运行
- 检索质量：内部 `RetrievalEvaluator` 提供离线 Recall@K/首个相关结果评估，不改变 chat API
- Chunking 边界：provider-neutral `MemoChunk` 使用 `memo-chunk-v1`/`chunk` metadata；通过显式 `AI_INDEX_MODE=chunk` 接入 Webhook 生命周期，默认不启用
- Chunk 离线评估：`OfflineChunkIndex` 复用 deterministic + memory 与 `RetrievalEvaluator`，可对照完整 Memo 基线，不改变公共 chat API
- Chunk 生命周期：`AI_INDEX_MODE=chunk` 显式启用 `ChunkLifecycleCoordinator`；默认 `memo-v1` 不变，AI SQLite 只持久化 chunk ID 状态
- Chunk store 隔离：当前 chunk Webhook 使用独立 InMemoryVectorStore，不污染完整 Memo chat 检索；Qdrant chunk collection 留到后续阶段
- Phase 5f collection contract：`QDRANT_CHUNK_COLLECTION` 默认 `devmemo_memo_chunks`，必须与完整 Memo `QDRANT_COLLECTION` 不同；当前尚未接入 chunk composition
- Chunk health：GET `/api/ai/index/chunk-health` 返回 `memo-chunk-v1`、点数、已登记 Memo/chunk 数量和 SQLite/memory 状态
- Webhook 安全：可选 `AI_WEBHOOK_SECRET` + `X-DevMemo-Signature: sha256=<hex>` HMAC 校验
- Webhook outbox：GET `/api/ai/ops/outbox` 读取状态，POST retry 显式有限重试，默认不启动 worker
- Ops 安全：可选 `AI_OPS_TOKEN` 保护运维 API；公开响应不返回原始 payload，错误摘要最多 240 字符
- Outbox 运维：retention preview 只读，alerts 提供失败/耗尽摘要；清理必须显式确认并写入审计，不自动删除或主动推送
- 文档同步：2026-07-14 已按实际仓库目录刷新 README、架构、API、开发、OSS 采用和结构边界文档；本次同时完成 Phase 5f collection/config contract 与 Compose 透传

## Phase 4 已完成

- 新增 provider-neutral `RetrievalService`：问题 embedding -> VectorStore.search -> 结构化 citations/context。
- 当前以一个完整 Memo 为一个检索单元；索引派生 metadata 保存原文供上下文组装，API 引用会剥离内部 `content` 字段。
- 新增 POST `/api/ai/chat`，接收 `question` 和 `limit`，返回 `answer`、`citations`、`provider`、`retrieved_count`。
- deterministic provider 返回可复现的引用式离线答案；OpenAI/Ollama 复用现有 LLM adapter。
- 空知识库返回明确空结果；非法 limit 返回 422；检索不可用返回 503；LLM 失败返回 502。

## Phase 4b 已完成

- 新增 provider-neutral `app/services/webhook_security.py`，使用标准库 HMAC-SHA256 校验原始 Webhook body。
- `AI_WEBHOOK_SECRET` 未配置时保持兼容放行；显式配置后缺失、错误或篡改签名返回 401。
- 签名校验位于 Webhook 业务处理前，不改变有效请求和默认 `code=0` 契约；未修改 Memos API、数据库或 Proto。
- Docker Compose 暴露空默认的 `AI_WEBHOOK_SECRET`/`AI_OPS_TOKEN` 配置，不增加默认 CPU、网络或模型负担。

## Phase 4c 已完成

- AI Service SQLite 新增兼容 `webhook_events` 表，记录 `event_id`、`event_type`、`payload`、`status`、`attempts`、`last_error`、`created_at`、`updated_at`。
- Webhook 优先入队；显式 `eventId` 使用原值，没有 eventId 时使用原始 body SHA-256 派生稳定 ID。
- 重复 event ID 不重复执行摘要、模板或索引；业务异常记录 `failed`，仍返回 `code=0`。
- 新增 GET `/api/ai/ops/outbox?status=&limit=` 运维读取 API；不引入后台 worker、Redis、Celery 或新依赖。

## Phase 4d 已完成

- `webhook_events` 通过兼容 SQLite 补列增加 `max_attempts`，默认总尝试上限为 3；旧表和旧数据保留。
- 新增 POST `/api/ai/ops/outbox/{event_id}/retry`，仅允许 `failed` 事件；重试准备在 SQLite 事务中原子切换为 `pending`。
- 重试成功转为 `processed` 并清除 `last_error`；再次失败保持 `failed` 并递增 `attempts`；达到上限返回 409。
- GET outbox 增加 `by_status` 和最多 5 条 `recent_errors`，不引入后台 worker、定时任务、外部队列或观测依赖。

## Phase 4e 已完成

- 新增可选 `AI_OPS_TOKEN` 和 `X-DevMemo-Ops-Token`，配置后保护 outbox GET/retry POST；未配置时保持本地开发兼容。
- 公开 outbox item 移除原始 Webhook payload；SQLite 内部 payload 保留，不影响 retry 编排。
- `last_error` 和最近错误摘要归一化为单行并截断到 240 字符；认证失败返回 401。
- 未引入认证服务、Redis、Prometheus、后台 worker 或前端运维 UI。

## Phase 4f 已完成

- 新增 GET `/api/ai/ops/outbox/retention-preview`，按 `updated_at` 预览超过阈值的 `processed/failed` 终态事件；默认 30 天、最多 100 条，只读不删除。
- 新增 GET `/api/ai/ops/alerts`，返回 `failed_count`、`exhausted_count` 和最多 5 条 warning/critical 摘要；继续受 `AI_OPS_TOKEN` 保护。
- alerts/preview 均不返回 payload、secret 或未截断错误；不启动 worker、不推送外部告警、不修改任何 Qdrant/AI volume。

## Phase 4g 已完成

- retention preview 返回固定 `cutoff`、`preview_limit` 和 `candidate_ids`，供后续批准请求绑定。
- 新增 POST `/api/ai/ops/outbox/retention-cleanup`；默认 `dry_run=true`，只有 `confirm=true` 且 `dry_run=false` 才执行。
- 清理在 SQLite 事务中重新校验完整 preview 集合、cutoff 和 `processed/failed` 终态；pending、集合外 ID 或数据变化整批拒绝。
- 新增 `webhook_cleanup_audits` 和 GET `/api/ai/ops/outbox/cleanup-audits`；记录 approval_id、actor 摘要、cutoff、候选数、删除数和执行时间，不保存 ops secret。
- 相同 approval_id 的重复执行幂等返回；清理只处理 AI Service 自有 webhook_events，不触碰 Memos、ai_notes、memo_templates、原始 Markdown 或 Qdrant volume。

## Phase 5a 已完成

- 选择离线检索评估作为最小切片，暂不改变当前“一整个 Memo 一个向量”的索引契约。
- 新增 provider-neutral `RetrievalEvaluationCase`、`RetrievalEvaluationResult` 和 `RetrievalEvaluator`。
- 支持 Recall@K、命中 Memo ID、首个相关结果排名和批量评估；不连接网络、不依赖 FastEmbed/Qdrant SDK。
- deterministic + memory 实际检索契约和评估器均有 unit/contract tests；未新增公共 API。

## Phase 5b 已完成

- 新增 provider-neutral `MemoChunk` 和 `chunk_memo`，按 Markdown 换行边界或固定字符上限切分，并保留源 Markdown 字符序列。
- 稳定 chunk ID 使用 Memo ID、`index_version` 和 chunk position；同一位置更新可复用 ID，缩短内容时可显式计算 stale IDs 删除。
- metadata 明确包含 `source_type=memo_chunk`、`index_mode=chunk`、`index_version=memo-chunk-v1`、chunk 序号/总数和派生 content。
- 覆盖空内容、超长内容、更新、删除、重复 ID、metadata 复制和非法参数；没有接入 Webhook、Qdrant、FastEmbed 或默认 Compose。

## Phase 5c 已完成

- 新增 provider-neutral `OfflineChunkIndex`，使用 chunk ID 作为试验索引 embedding ID，复用现有 VectorStore 和 RetrievalService。
- chunk citation 明确保留 `memo_id`、`chunk_id`、`chunk_index`、`index_version` 和服务端上下文；公共 `POST /api/ai/chat` 契约未改变。
- 支持完整 Memo 与 chunk 试验索引使用同一 `RetrievalEvaluator` 做 Recall@K/首个命中排名对照；仅访问 deterministic + memory，不下载模型或连接 Qdrant。
- 覆盖 upsert、更新后的显式 stale chunk delete、重复/空 chunk 和 citation/context contract；未接入默认 Webhook 或生产索引。

## Phase 5d 已完成

- 新增 provider-neutral `ChunkLifecycleCoordinator`，支持 chunk create/update/delete；更新先 upsert 当前 chunk，再删除同一 `memo-chunk-v1` 版本的旧尾部 chunk。
- 新增 AI Service 自有 SQLite `memo_chunk_index_state`，只记录 `memo_id`、`index_version`、`chunk_ids` 和更新时间，用于进程重启后的生命周期清理；不保存或替代原始 Markdown。
- 新增 `AI_INDEX_MODE=memo|chunk`，默认 `memo`；只有同时开启 `AI_INDEX_ON_WEBHOOK=true` 和 `AI_INDEX_MODE=chunk` 时 Webhook 才使用 chunk 路径。
- chunk Webhook 覆盖 create/update/delete、空内容清理、eventId 幂等和失败降级；完整 Memo `memo-v1`、`POST /api/ai/chat`、Webhook `code=0` 和默认 Compose 契约保持不变。
- chunk lifecycle 当前只验证 deterministic/provider-neutral + 独立 memory store；未把 chunk 向量接入 Qdrant，也未改变公共 chat 的完整 Memo 检索源。

## Phase 5e 已完成

- 新增 provider-neutral `ChunkIndexStateStats` 和 `ChunkIndexHealth`，同时观测 chunk VectorStore 点数与 SQLite 登记的 Memo/chunk 数量。
- 新增只读 GET `/api/ai/index/chunk-health`，显式返回 `index_mode=chunk`、`index_version=memo-chunk-v1`、provider、dimension、point_count、tracked_memos、tracked_chunks、state_backend 和降级 detail。
- health 不触发索引、不扫描原始 Markdown、不改变完整 Memo `GET /api/ai/index/health` 或 `POST /api/ai/chat`；SQLite 状态损坏/不可用会返回 `status=degraded`，不静默报告 ready。
- 覆盖空状态、create/update/delete 后计数、版本隔离、SQLite 重启读取和 HTTP contract；默认 deterministic + memory、不访问网络。

## Phase 3c 已完成

- 新增 `FastEmbedEmbeddingProvider`，只在 adapter 内导入 `fastembed.TextEmbedding`。
- 新增 `requirements-fastembed.txt`，固定 `fastembed==0.8.0`；默认 requirements 不增加模型/ONNX 网络依赖。
- 增加 `AI_EMBEDDING_PROVIDER=deterministic|fastembed`、`AI_FASTEMBED_MODEL` 和 `AI_FASTEMBED_DIMENSION`。
- 默认仍使用 8 维 deterministic provider；显式 fastembed 模式检查模型输出维度并与 VectorStore 维度匹配。
- 新增 `MemoIndexDocument`/`index_memo` 索引边界；当前一个完整 Memo 对应一个向量，chunking 延后。
- POST `/api/ai/embed` 保持响应契约，新增索引 metadata：`source_type=memo`、`index_version=memo-v1`。

## Phase 3d 已完成

- 新增 `AI_INDEX_ON_WEBHOOK`，默认 `false`，Compose 默认不触发向量索引。
- 开启后，Memo created/updated 通过 `MemoIndexDocument` 做稳定 ID 幂等 upsert。
- deleted 事件按 Memo UID 删除对应向量；缺少 UID 时安全返回 `index_status=skipped`。
- 索引失败不会阻断摘要、模板持久化或 Webhook `code=0` 响应，返回 `index_status=failed`。
- Webhook 非空 Memo 返回 `index_status=indexed|skipped|failed`；删除返回 `deleted|skipped|failed`。

## Phase 3e 已完成

- Docker Desktop Linux Engine 已启动，Compose Qdrant 服务在 `http://127.0.0.1:6333` 正常响应。
- 在 ai-service 虚拟环境安装 `qdrant-client==1.18.0`；Qdrant Server smoke 使用 `qdrant/qdrant:latest`，当前服务端返回 1.18.2。
- 真实验证了 collection 创建、384 维 FastEmbed 向量 upsert、`query_points` search、payload 映射和 delete。
- FastEmbed + Qdrant smoke 返回 `fastembed-1` 最近结果，删除后该向量不再可检索；临时 collection 已清理。
- 新增 `ai-service/scripts/smoke_qdrant.py`，默认 FastEmbed，可切换 deterministic，使用模块方式运行。
- 安装 qdrant-client 后，缺失可选依赖测试改为通过模块注入模拟，不依赖卸载本机包。

## Phase 3f 已完成

- Compose 为 AI Service 增加可选 `/app/model-cache` volume；`AI_FASTEMBED_CACHE_DIR` 可配置 FastEmbed 模型缓存目录。
- Compose 默认设置缓存目录为 `/app/model-cache`，但 provider 默认仍为 deterministic，因此不会日常下载或加载模型。
- Qdrant 数据 volume `devmemoai_qdrant-data` 确认挂载到 `/qdrant/storage`，没有执行 `down -v` 或删除 volume。
- 使用 `devmemo_phase3f_persistence_20260713` 临时 collection 写入 `persist-1`，执行 `docker compose restart qdrant` 后仍能检索到同一 embedding_id、memo_id 和 metadata；验证后已清理临时 collection。
- FastEmbed 可选缓存目录 smoke 已通过，`H:\DevMemoAI\ai-service\model-cache` 约 64.07 MB，并在 `HF_HUB_OFFLINE=1` 下成功加载 384 维模型。
- 首次直接迁移下载曾因 Hugging Face 代理 `RemoteProtocolError` 中断，未将网络问题伪装成代码成功；复用已验证本地缓存后完成离线验证。

## Phase 3g 已完成

- 新增只读 `GET /api/ai/index/health`，返回 provider、available、dimension、status、collection、point_count 和 detail。
- InMemoryVectorStore 本地返回 `ready`，不会连接 Qdrant；QdrantVectorStore 将 SDK 查询异常转换为 `available=false、status=unavailable`。
- FastEmbed 模型初始化错误现在包含 cache_dir 和修复提示，缓存损坏不被伪装为成功。
- Qdrant `latest` 已固定到已验证的 Server 1.18.2 镜像 digest `sha256:75eab8c4...`。
- 增加 Qdrant health、不可用降级、FastEmbed cache 错误和 API contract tests；未修改 Memos 核心。

## Phase 3b 已完成

- 新增 QdrantVectorStore adapter，实现现有 VectorStore Protocol 的 upsert、query_points search、delete。
- Qdrant point 使用稳定 UUID 映射，原始 embedding_id、memo_id 和 metadata 保存在 payload。
- 增加维度、collection、payload 和 optional dependency 错误边界。
- 新增 requirements-qdrant.txt，固定 qdrant-client 1.18.0；默认 requirements 不增加网络依赖。
- 新增 AI_VECTOR_STORE=memory|qdrant 配置，默认 memory。
- AI 容器不再 depends_on Qdrant/Ollama，默认启动不依赖外部 AI/向量服务。
- Qdrant fake client contract tests 不访问网络。

## 验证状态

~~~text
AI Service full pytest             144 passed
FastEmbed fake/model tests          6 passed
Provider/index targeted tests      13 passed
frontend full tests                131 passed
frontend TypeScript/build          PASS
Go full test -p 2 ./...            PASS
verify-devmemo.ps1                 PASS / DEVMEMO_VERIFY_OK
docker compose config              PASS
Qdrant FastEmbed smoke             PASS / collection upsert search delete
Qdrant volume restart              PASS / collection and point recovered
FastEmbed cache-dir smoke           PASS / offline 384-dim load
Qdrant health smoke                PASS / green collection status
Index health contract tests         PASS / memory and degraded qdrant
git diff --check                   PASS
pnpm lint                          PASS
~~~

## 网络与环境证据

- 当前 ai-service 虚拟环境已安装 qdrant-client 1.18.0 和 fastembed 0.8.0；FastEmbed 模型缓存约 64.07 MB。
- Docker Desktop Linux Engine 已运行；Qdrant 服务端返回 1.18.2。
- FastEmbed 真实模型下载/推理、FastEmbed+Webhook create/update/delete smoke 和 FastEmbed+Qdrant collection/upsert/search/delete smoke 均已通过。
- fastembed 和 qdrant-client 的版本、许可证、维护风险和替换边界记录在 docs/DECISIONS.md。

## 已知未完成项

- 当前默认 memory 索引为进程内存，服务重启后不保留。
- Compose Qdrant volume 重启持久化已验证；FastEmbed 可选缓存目录已验证，默认 Compose 仍不加载模型。
- Qdrant health API、不可用降级和 FastEmbed 缓存损坏错误边界已验证；镜像已固定到已验证 digest。
- Webhook 默认不触发向量索引；开启 `AI_INDEX_ON_WEBHOOK=true` 后才会触发。
- FastEmbed smoke：首次加载约 23.48 秒，单条 embedding 约 0.06 秒，返回 384 维；项目缓存目录约 64.07 MB。
- 当前 RAG 只检索完整 Memo，默认 memory 为进程内存；服务重启后不保留索引。
- Phase 5e 已增加 chunk health/status；Phase 5f 已完成独立 collection/config 与 fake contract，Qdrant chunk composition、真实 health 和 chunk-aware 公共检索仍未接入，chunk 仍未替换公共 `POST /api/ai/chat` 的完整 Memo 检索。
- 当前 outbox 提供显式有限重试、基础状态计数、ops token、保留预览、告警轮询和显式清理审计；没有自动 worker、主动告警推送或定时清理。
- 全量 pnpm lint 已在上一阶段通过；本阶段未修改前端源码。

## 下一步

执行 docs/prompts/NEXT_STAGE_PROMPT.md，使用单 Agent 开始 Phase 5f Qdrant chunk 持久化与显式 chunk 检索。
