# DevMemo AI 项目结构与边界

更新时间：2026-08-01

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
├── docs/                        # 架构、API、路线、决策、交接和下一阶段 Prompt
├── docker-compose.yml           # Memos、AI Service、Qdrant、Ollama 编排
├── docker-compose.local-webhook.yml # 仅受控本地开发允许私网 Webhook 的显式 override
├── NOTICE                        # 上游 Memos 与 DevMemo AI 的许可/归属说明
├── UPSTREAM.md                   # 下游维护、同步与非官方关系说明
└── graphify-out/                # 本地忽略的结构图产物，不属于运行时源码
```

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
启用时计算调用者可见范围；dormant lifecycle outbox adapter 位于 `store/`，但尚未接入
既有 Memo create/update/delete 路径。AI 派生状态不写回 Memo 业务表，`proto/` 与通用前端
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
│   │   ├── agent_lifecycle.py       # A4 lifecycle event/ack/state machine
│   │   └── grounded_answer.py       # 严格 Provider answer/citation reference 契约
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
│   │   ├── agent_lifecycle_processor.py # dormant ledger/vector lifecycle processor
│   │   ├── agent_lifecycle_transport.py # lifecycle HMAC、replay 与 in-process transport
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
│       └── agent_lifecycle_ledger.py # dormant AI SQLite lifecycle ledger
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
sqlite3 类型。第三方 SDK 只在 adapter；SQLite 只在根数据库层、`chunk_state.py` 和 dormant
`agent_lifecycle_ledger.py` adapter。

## Evidence Answer Agent 与 lifecycle 边界

浏览器只访问 Memos 的 `POST /api/ai/agent/answer`。Memos 负责认证、可见范围与短时委托；
AI Service 的固定 internal path 只执行 `search_memos`，并用严格 grounded-answer parser
验证非 deterministic Provider 输出。citation 由服务端已授权证据映射，公开响应不包含原始
Memo、prompt/context、embedding、身份、可见范围或 secret。

`contracts/memo-lifecycle-v1.json`、Memos-owned SQLite outbox、AI SQLite ledger、认证
transport 和一次性 integration proof 已存在，但都保持未接线。它们不会由当前 Memo CRUD、
AI route、dispatcher、worker、定时器、Qdrant 或默认 Compose 自动调用。

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
├── api.ts             # AI Service HTTP client
├── hooks.ts           # React Query hooks
├── AiMemoTemplate.tsx # Code Snippet/Bug Report 展示与复制
└── AiMemoSummary.tsx  # 摘要读取、生成与反馈
```

前端只访问 AI Service HTTP API，不访问 SQLite。未配置 `VITE_AI_SERVICE_URL`、AI Service 404 或网络失败时，Memo Markdown、标签、搜索和编辑流程继续正常运行。

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
