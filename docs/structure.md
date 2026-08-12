# DevMemo AI 项目结构与边界

更新时间：2026-08-12

## 顶层目录

```text
repository-root/
├── cmd/                         # Memos Go 启动入口
├── server/                      # Memos HTTP/Connect/API 层
├── store/                       # Memos 数据存储与迁移边界
├── internal/                    # Memos 内部服务、Markdown、Webhook 等模块
├── proto/                       # Memos API/Store Proto 与生成代码
├── web/                         # Memos React + TypeScript 前端
│   └── src/features/ai/         # DevMemo AI 前端 feature：API、hooks、模板、摘要、Inbox、Context Pack
├── ai-service/                  # 独立 FastAPI AI 旁路服务
├── contracts/                   # 跨语言 provider-neutral fixtures（Context Pack、Agent、lifecycle、grounded answer）
├── integrations/                # 上游/部署集成脚本与配置
├── scripts/                     # Windows 验证、安装、Compose 辅助脚本
├── docs/                        # 可公开的架构、API、路线、决策与运维文档
├── docker-compose.yml           # Memos、AI Service、Qdrant、Ollama 编排
├── docker-compose.local-webhook.yml # 仅受控本地开发允许私网 Webhook 的显式 override
├── NOTICE                        # 上游 Memos 与 DevMemo AI 的许可/归属说明
├── UPSTREAM.md                   # 下游维护、同步与非官方关系说明
└── graphify-out/                # 本地忽略的结构图产物，不属于运行时源码
```

本地 Agent 状态、交接和下一阶段操作说明位于 Git 忽略的仓库本地目录或操作系统临时目录，
不属于公开仓库结构，也不得随代码提交或推送。公开文档只记录可复现的产品、架构和验证事实。

DevMemo AI `v0.2.0` 已从默认分支精确提交 `eddaa602537cda1adc27c0cd1d8c58b40c8e503b`
发布。该 release 固化当前默认关闭、显式 opt-in 的单机 Agent/lifecycle 边界，不构成真实数据、
外部 Provider、公开 AI 端口或多实例生产部署证明。

R7-I0 双语 AgentRun definition gate 已通过 PR #8 合并；R7-I1 的 provider-neutral frozen AgentRun
contract、脱敏 fixture 与定向测试已通过 PR #9 合并于
`0358fb120fd539a97d67b04c47787df0fa72c9ff`。R7-I2 随后通过 PR #10 把 legacy 浏览器 AI 路径统一到
same-origin Memos BFF，并合并于 `39068613b387d1154b7f7e4bf9d32fc230b3ed39`。R7-I3 新增独立、
single-host、derived-only 的 SQLite AgentRun persistence adapter 与临时数据库恢复/事务测试；该 adapter
仍 dormant/unwired，不新增 route、worker、runner、runtime、UI 或产品 artifact 路径。

## Memos 核心边界

## 对外文档与部署边界

根目录的 `README.md`、`README.zh-CN.md`、`README_AI.md`、`README_AI.zh-CN.md`、`CONTRIBUTING.md`、`SUPPORT.md`、`GOVERNANCE.md`、`CODE_OF_CONDUCT.md`、`SECURITY.md`、`NOTICE` 与 `UPSTREAM.md` 共同描述 DevMemo AI 的非官方下游身份、部署方式、帮助/贡献入口和安全报告边界。`docs/operations.md` 与 `docs/operations.zh-CN.md` 记录备份、恢复与升级边界。默认 `docker-compose.yml` 不放行私网 Webhook；`docker-compose.local-webhook.yml` 只能由本机受控开发显式叠加，不能作为公共或多用户部署配置。

```text
cmd/server/store/internal/proto
  -> Memos Go backend
  -> Webhook: memo.created / memo.updated / memo.deleted
  -> web React frontend
```

Memos 仍是 Memo 原始内容、标签、搜索和用户权限的事实来源。Memos BFF 在实验性 Agent
启用时计算调用者可见范围。默认关闭的单机 lifecycle 路径已把 Memo mutation、SQLite outbox、
认证 internal AI listener、generation activation 与 Qdrant 派生状态接通；只有显式 runtime flag
选择它，默认 Compose 不会启动该路径。AI 派生状态不写回 Memo 业务表，`proto/` 与通用前端
数据层也不承担 AI 派生状态。

## Web AI feature 结构

```text
web/src/features/ai/
├── api.ts                 # AI Service URL、insight/template/summary 请求
├── hooks.ts               # React Query 读取与状态变更 hooks
├── AiMemoInsights.tsx     # Memo 详情页 AI Inbox：pending/accepted/rejected 审核
├── AiMemoContextPack.tsx  # Phase 9d-11：内存 preview/copy、显式来源、预算摘要、复制状态与无障碍反馈
├── contextPack.ts         # Phase 9b contract 的 Web provider-neutral adapter
├── AiMemoEvidenceAnswer.tsx # 实验性只读 Agent 入口；提交前不发请求
├── AiMemoTemplate.tsx     # 结构化 Memo 模板展示
└── AiMemoSummary.tsx      # bounded summary 展示
```

当前问题：AI Inbox 是详情页内嵌 feature，不是全局 Inbox；Context Pack 的 Python builder 与 Web adapter 仍是两份实现，但已通过 `contracts/context-pack-v1.json` 的 Markdown/compact JSON golden 做字节级对齐，后续任何语义变更都必须扩展该 fixture。Phase 11 只在组件层读取既有 pack 的 items/sources/markdown 长度并维护瞬时复制反馈，不改变 builder contract 或持久化边界。`graphify-out` 的历史图仍会把 “Inbox” 解析为 Memos `store/inbox.go`，且未收录近期 AI feature；结构判断应以源码与本文档为准，图谱重建是后续维护项。

### Web strict 类型兼容边界

`web/src/types/compat/` 只为已安装 package 的公开消费面提供 TypeScript 解析映射；`strict-dependency-compat.d.ts` 补齐缺失的 type-fest utilities 与 React Leaflet deep context，`leaflet-markercluster.d.ts` 只声明当前 MarkerCluster 组件需要的 Leaflet plugin 类型。这些文件不参与运行时打包替换；production build 继续使用 `node_modules` 中的 JavaScript。未来依赖升级若修复对应声明，应先用 strict tsc 和 build 证明后再删除相应 bridge，不得长期同时维护重复来源。

Phase 13 已把 `web/package.json` 的 `lint` 固定为 `tsc --noEmit && biome check src`。因此 Web 日常门禁现在与独立 strict TypeScript 使用相同的声明检查范围；这只改变开发验证，不改变 Vite runtime resolution、前端行为或任一服务边界。

## AI Service 目录

```text
ai-service/
├── main.py                         # FastAPI 路由、Webhook 兼容边界、组合入口
├── settings.py                     # 环境变量配置校验
├── database.py                     # AI 自有 SQLite：ai_notes、templates、outbox、chunk state
├── embedding.py                    # 旧 list-based embedding 兼容入口
├── rag.py                          # 旧 RAG 兼容入口
├── llm.py                          # deterministic/OpenAI/Ollama LLM adapter 入口
├── lifecycle_report.py              # 本地只读 AI SQLite 生命周期聚合
├── app/
│   ├── domain/
│   │   ├── embeddings.py            # EmbeddingProvider/VectorStore/VectorRecord 契约
│   │   ├── memo_chunking.py         # MemoChunk、稳定 ID、memo-chunk-v1
│   │   ├── models.py                # CodeSnippet、BugReport、ParsedMemo
│   │   ├── retrieval.py             # Citation、RetrievalResult 等 provider-neutral 类型
│   │   ├── retrieval_evaluation.py  # 离线评估输入/结果类型
│   │   ├── memo_insight.py          # AI Inbox/Decision Ledger contract
│   │   ├── context_pack.py          # context-pack-v1 contract 与 JSON 输出
│   │   ├── agent.py                 # search_memos-only Agent 请求/结果契约
│   │   ├── agent_run.py             # R7 contract-only run/step/event/approval/artifact 校验
│   │   ├── agent_evaluation.py      # R6 sanitized case/corpus/threshold/result contract
│   │   ├── agent_evaluation_report.py # content-free benchmark report contract
│   │   ├── agent_lifecycle.py       # A4 lifecycle event/ack/state machine
│   │   ├── agent_observability.py   # 固定低基数、无正文 observability contract
│   │   ├── grounded_answer.py       # 严格 Provider answer/citation reference 契约
│   │   ├── durable_authorized_retrieval.py # R5 两阶段授权 candidate/materialization 契约
│   │   └── evidence_rehydration.py  # R5 当前 Memos authority 正文 rehydration 契约
│   ├── services/
│   │   ├── content_parser.py        # Markdown 模板解析
│   │   ├── embedding_service.py     # provider -> vector record -> store 编排
│   │   ├── embedding_factory.py     # memory/Qdrant 与 deterministic/FastEmbed 组合根
│   │   ├── memo_indexing.py          # 完整 Memo memo-v1 索引边界
│   │   ├── retrieval_service.py     # query embedding -> search -> context/citations
│   │   ├── chunk_retrieval.py       # 内部 memo-chunk-v1 retrieval contract
│   │   ├── retrieval_evaluator.py   # Recall@K/首个相关结果离线评估
│   │   ├── offline_chunk_index.py   # 独立 chunk 试验索引
│   │   ├── chunk_lifecycle.py       # 显式 chunk Webhook create/update/delete 编排
│   │   ├── public_chunk_retrieval.py # public-chunk-v1 authorization/dedupe/redaction projection
│   │   ├── agent_delegation.py      # answer HMAC purpose/path 与严格 delegated body
│   │   ├── evidence_answer_agent.py # 授权检索、Provider 校验与安全回答编排
│   │   ├── agent_refusal_policy.py  # retrieval 前的固定拒绝策略
│   │   ├── agent_evaluation_runner.py # deterministic content-free metrics runner
│   │   ├── agent_evaluation_harness.py # 64-case product-core offline harness
│   │   ├── agent_observability_runtime.py # 可选进程内 recorder 与固定 sample helper
│   │   ├── agent_lifecycle_processor.py # dormant ledger/vector lifecycle processor
│   │   ├── agent_lifecycle_runtime.py # 默认关闭的 lifecycle composition/runtime
│   │   ├── agent_lifecycle_transport.py # lifecycle HMAC、replay 与 in-process transport
│   │   ├── durable_authorized_retrieval.py # R5 candidate/materialization service
│   │   ├── evidence_rehydration_transport.py # R5 request/response HMAC 与 process-local replay 证明
│   │   ├── webhook_security.py      # Webhook HMAC-SHA256
│   │   ├── ops_security.py          # ops token 与错误脱敏
│   │   ├── memo_insights.py         # deterministic insight 提取与稳定 ID
│   │   └── context_pack.py          # 显式来源的 bounded pack builder
│   └── adapters/
│       ├── embedding.py             # deterministic embedding
│       ├── fastembed_embedding.py   # 可选 FastEmbed，第三方类型只在此处
│       ├── vector_store.py          # InMemoryVectorStore
│       ├── qdrant_vector_store.py   # 可选 Qdrant adapter
│       ├── chunk_state.py            # InMemory/SQLite chunk 状态 adapter
│       ├── agent_lifecycle_ledger.py # dormant AI SQLite lifecycle ledger
│       ├── agent_run_store.py        # dormant derived-only AgentRun SQLite persistence
│       └── disposable_sqlite_authorized_retrieval.py # R5 仅测试的临时 SQLite parity adapter
├── scripts/public_chunk_gateway_contract_smoke.py # local trusted-gateway contract evidence only
├── scripts/smoke_qdrant.py          # 显式真实 Qdrant smoke
├── scripts/devmemory_lifecycle_report.py # local-only read-only diagnostic CLI
└── tests/                           # AI Service unit/contract/API 测试
```

## Provider 与存储边界

```text
AiSettings.from_env
  -> build_embedding_service
  -> EmbeddingProvider
       ├── deterministic (default, 8 dimensions)
       └── FastEmbed (optional, 384 dimensions by default)
  -> VectorStore
       ├── InMemoryVectorStore (default, low CPU/offline)
       └── QdrantVectorStore (explicit AI_VECTOR_STORE=qdrant)
```

`app/domain/` 和 provider-neutral service 不依赖 FastAPI、FastEmbed、qdrant-client、httpx 或
sqlite3 类型。第三方 SDK 只在 adapter；SQLite 只在根数据库层、`chunk_state.py`、dormant
`agent_lifecycle_ledger.py` 与 dormant `agent_run_store.py` adapter。AgentRun store 只保存无正文的派生
run/step/event/approval/artifact metadata 与 `storage_ref`，不保存 Provider prompt、Memo 正文或 secret，
也不成为 Memo/source authority。

## Evidence Answer Agent 与 lifecycle 边界

浏览器只访问 Memos 的 `POST /api/ai/agent/answer`。Memos 负责认证、可见范围与短时委托；
AI Service 的固定 internal path 只执行 `search_memos`，并用严格 grounded-answer parser
验证非 deterministic Provider 输出。citation 由服务端已授权证据映射，公开响应不包含原始
Memo、prompt/context、embedding、身份、可见范围或 secret。

`contracts/memo-lifecycle-v1.json`、Memos-owned SQLite outbox、AI SQLite ledger 与认证 transport
已在默认关闭的单机 opt-in 下组成 source-owned lifecycle。Go 只在权威 store transition 成功后记录
固定 delivery/retry/quarantine sample；记录失败不能改变 outbox 结果。outbox lag、rebuild observability
和 reconciliation 仍缺各自权威状态接口，禁止从异常或计数推断。

R5 durable authorized retrieval 分布在 AI Service 的 `durable_authorized_retrieval.py`、
`durable_rehydration_orchestrator.py`、`evidence_rehydration.py`、HTTP client/runtime adapter，以及 Go
`internal/aiagent/evidence_rehydration_*` authority/transport 与 Memos API composition。跨语言 fixture 位于
`contracts/memo-evidence-rehydration-v1.json` 和
`contracts/memo-evidence-rehydration-transport-v1.json`。启用 rehydration opt-in 时，Agent 只选择
lifespan-owned durable orchestrator，不回退到 memory；disabled 时仍保持原 memory retrieval。

R6 在这条产品路径外增加离线工程证据：64 个完全 synthetic case、七项预声明 threshold、pure runner、
真实 deterministic retrieval/Agent core harness、fixed pre-retrieval refusal，以及 answer/retrieval/Provider/
lifecycle 的无正文固定 sample。它们不等于真实 Provider、Docker、浏览器、CI 或 release 证据。

## 默认完整 Memo 索引

```text
POST /api/ai/embed 或 AI_INDEX_MODE=memo
  -> MemoIndexDocument.from_memo
  -> index_version=memo-v1 / index_mode=memo
  -> EmbeddingService.embed_memo
  -> complete Memo VectorStore
  -> RetrievalService / POST /api/ai/chat
```

默认一个完整 Memo 对应一个稳定 `memo-*` embedding ID。`POST /api/ai/chat` 默认检索这一索引，公共 citations 去除内部 `content` 字段。

## 可选 chunk Webhook 索引

```text
AI_INDEX_ON_WEBHOOK=true
  + AI_INDEX_MODE=chunk
  -> chunk_memo
  -> memo-chunk-v1 / index_mode=chunk / stable chunk IDs
  -> ChunkLifecycleCoordinator
  -> AI_VECTOR_STORE=qdrant 且 AI_INDEX_MODE=chunk
       -> 独立 QdrantVectorStore（QDRANT_CHUNK_COLLECTION）
     否则
       -> 独立 InMemoryVectorStore
  -> AI SQLite memo_chunk_index_state
  -> create/update upsert + stale delete
  -> delete/empty content registered chunk delete
  -> ChunkRetrievalService -> ChunkRetrievalResult（内部，不接公共 chat）
```

chunk lifecycle 使用独立 VectorStore，避免 chunk 向量污染完整 Memo 的 chat 检索。`ChunkRetrievalService` 只接受 `memo-chunk-v1`/`memo_chunk` 元数据，把 `content` 留在服务端 context，返回显式 chunk citation。`GET /api/ai/index/chunk-health` 只读所选独立 store 和 `memo_chunk_index_state` 统计。显式 `AI_INDEX_MODE=chunk` + `AI_VECTOR_STORE=qdrant` 时使用 `QDRANT_CHUNK_COLLECTION`，默认 chunk 路径仍使用 memory；失败仍返回 Webhook `code=0` 和 `index_status=failed`。

## Webhook 与可靠性边界

```text
raw request
  -> optional AI_WEBHOOK_SECRET HMAC check
  -> eventId/body SHA-256 idempotent webhook_events outbox
  -> summary/template persistence
  -> optional memo/chunk index lifecycle
  -> processed/failed + bounded attempts
  -> explicit retry / alerts / retention preview / approved cleanup audit
```

默认不启动 worker、Redis、Celery 或自动重试。运维 API 可由 `AI_OPS_TOKEN` 保护；公开响应不返回原始 Webhook payload。

## 前端 AI feature 边界

```text
web/src/features/ai/
├── api.ts             # same-origin Memos AI BFF client
├── hooks.ts           # React Query hooks
├── AiMemoTemplate.tsx # Code Snippet/Bug Report 展示与复制
└── AiMemoSummary.tsx  # 摘要读取、生成与反馈
```

Evidence Answer 与 legacy template/summary/insight 面板都只访问 same-origin Memos BFF，不把身份、
可见 UID、delegation secret 或 AI Service 地址交给浏览器。legacy BFF 仅在显式 Agent opt-in 下注册，
逐 Memo 复用 Memos visibility；summary 正文由服务端 store 读取，响应按固定字段投影。
前端不访问 SQLite，AI 功能不可用时 Memo Markdown、标签、搜索和编辑流程继续正常运行。

## 当前推进路线与问题

1. **保持 R7 contract 与 persistence 边界：** 已具备 provider-neutral contract、deterministic sanitized
   fixture，以及 dormant single-host SQLite persistence；恢复对象必须重新经过 frozen domain validator，
   每个 checkpoint 单事务提交，timeline append-only，approval 首次有效 decision 原子消费。
2. **下一步实现 bounded runner/runtime：** 浏览器 AI 路径已统一到 Memos BFF；继续保持 AI Service 不发布
   宿主端口，在独立切片中组合有界执行、恢复与 fail-closed authority recheck，不在 persistence adapter
   中隐式启动 worker 或 background job。
3. **再拆分 BFF 与体验：** bounded runtime 稳定后，依次独立评审 AgentRun BFF、run/approval/timeline UI，
   每一步都保留默认关闭、fail-closed 与可回滚边界。
4. **最后讨论真实环境：** 真实 Provider、真实用户数据与多实例需分别完成隐私、备份恢复、加密 transport、
   shared atomic replay/capability storage 证明后才能进入。
5. **保持未解决问题显式：** refusal 展示仍偏通用；lifecycle lag、跨进程 rebuild authority 与 dedicated
   reconciliation owner 尚不完整；Docker build-context 传输效率仍是独立工程问题。
6. **隔离本地协作材料：** 本地状态、临时交接、报告、截图与生成的结构产物必须保持 Git 忽略；公共文档
   只保留可复现的产品事实。

## Compose 与持久化

```text
docker compose up -d
  ├── memos       -> memos-data
  ├── ai-service  -> ai-data + ai-model-cache
  ├── qdrant      -> qdrant-data
  └── ollama      -> ollama-data
```

默认 `AI_PROVIDER=deterministic`、`AI_EMBEDDING_PROVIDER=deterministic`、`AI_VECTOR_STORE=memory`、`AI_INDEX_ON_WEBHOOK=false`、`AI_INDEX_MODE=memo`，不会因模型下载、Qdrant 或 Ollama 增加日常 CPU/网络负担。默认 Compose 只启动 Memos (`0.75` CPU) 和 AI Service (`0.25` CPU)，Qdrant/Ollama 必须通过 profile 显式启动。Qdrant 配置同时保留完整 Memo collection 和独立 chunk collection 名称。

## 迁移与升级规则

1. Memos 核心继续跟随官方 upstream；AI 功能优先使用旁路 HTTP/Webhook 和 AI 自有 SQLite。
2. 新增 provider 通过 adapter 和可选 requirements 接入，不把 SDK 类型带入 domain。
3. 新索引模式必须通过 `index_version`/`index_mode` 隔离，可回滚且不覆盖既有 embedding ID。
4. 默认路径保持 deterministic + memory；真实 FastEmbed/Qdrant 只在显式配置或 smoke 中启用。
5. 修改目录、模块边界、API 或数据模型后同步 `docs/structure.md`、`docs/api.md`、`docs/architecture.md` 和 `docs/DECISIONS.md`。
