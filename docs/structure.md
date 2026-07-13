# DevMemo AI 项目结构与边界

更新时间：2026-07-14

## 顶层目录

```text
H:\DevMemoAI/
├── cmd/                         # Memos Go 启动入口
├── server/                      # Memos HTTP/Connect/API 层
├── store/                       # Memos 数据存储与迁移边界
├── internal/                    # Memos 内部服务、Markdown、Webhook 等模块
├── proto/                       # Memos API/Store Proto 与生成代码
├── web/                         # Memos React + TypeScript 前端
│   └── src/features/ai/         # DevMemo AI 前端 feature：API、hooks、模板、摘要
├── ai-service/                  # 独立 FastAPI AI 旁路服务
├── integrations/                # 上游/部署集成脚本与配置
├── scripts/                     # Windows 验证、安装、Compose 辅助脚本
├── docs/                        # 架构、API、路线、决策、交接和下一阶段 Prompt
├── docker-compose.yml           # Memos、AI Service、Qdrant、Ollama 编排
└── graphify-out/                # 本地忽略的结构图产物，不属于运行时源码
```

## Memos 核心边界

```text
cmd/server/store/internal/proto
  -> Memos Go backend
  -> Webhook: memo.created / memo.updated / memo.deleted
  -> web React frontend
```

Memos 仍是 Memo 原始内容、标签、搜索和用户权限的事实来源。本项目不把 AI 字段写入 Memos 数据库，也不修改 `server/`、`store/`、`proto/` 或通用前端数据层来承载 AI 派生状态。

## AI Service 目录

```text
ai-service/
├── main.py                         # FastAPI 路由、Webhook 兼容边界、组合入口
├── settings.py                     # 环境变量配置校验
├── database.py                     # AI 自有 SQLite：ai_notes、templates、outbox、chunk state
├── embedding.py                    # 旧 list-based embedding 兼容入口
├── rag.py                          # 旧 RAG 兼容入口
├── llm.py                          # deterministic/OpenAI/Ollama LLM adapter 入口
├── app/
│   ├── domain/
│   │   ├── embeddings.py            # EmbeddingProvider/VectorStore/VectorRecord 契约
│   │   ├── memo_chunking.py         # MemoChunk、稳定 ID、memo-chunk-v1
│   │   ├── models.py                # CodeSnippet、BugReport、ParsedMemo
│   │   ├── retrieval.py             # Citation、RetrievalResult 等 provider-neutral 类型
│   │   └── retrieval_evaluation.py  # 离线评估输入/结果类型
│   ├── services/
│   │   ├── content_parser.py        # Markdown 模板解析
│   │   ├── embedding_service.py     # provider -> vector record -> store 编排
│   │   ├── embedding_factory.py     # memory/Qdrant 与 deterministic/FastEmbed 组合根
│   │   ├── memo_indexing.py          # 完整 Memo memo-v1 索引边界
│   │   ├── retrieval_service.py     # query embedding -> search -> context/citations
│   │   ├── retrieval_evaluator.py   # Recall@K/首个相关结果离线评估
│   │   ├── offline_chunk_index.py   # 独立 chunk 试验索引
│   │   ├── chunk_lifecycle.py       # 显式 chunk Webhook create/update/delete 编排
│   │   ├── webhook_security.py      # Webhook HMAC-SHA256
│   │   └── ops_security.py          # ops token 与错误脱敏
│   └── adapters/
│       ├── embedding.py             # deterministic embedding
│       ├── fastembed_embedding.py   # 可选 FastEmbed，第三方类型只在此处
│       ├── vector_store.py          # InMemoryVectorStore
│       ├── qdrant_vector_store.py   # 可选 Qdrant adapter
│       └── chunk_state.py            # InMemory/SQLite chunk 状态 adapter
├── scripts/smoke_qdrant.py          # 显式真实 Qdrant smoke
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

`app/domain/` 和 provider-neutral service 不依赖 FastAPI、FastEmbed、qdrant-client、httpx 或 sqlite3 类型。第三方 SDK 只在 adapter，SQLite 只在根数据库层和 `chunk_state.py` adapter。

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
  -> 独立 InMemoryVectorStore
  -> AI SQLite memo_chunk_index_state
  -> create/update upsert + stale delete
  -> delete/empty content registered chunk delete
```

chunk lifecycle 使用独立 VectorStore，避免 chunk 向量污染完整 Memo 的 chat 检索。`GET /api/ai/index/chunk-health` 只读独立 store 和 `memo_chunk_index_state` 统计。当前阶段没有把 chunk store 接入 Qdrant；Qdrant chunk collection 是后续显式扩展。失败仍返回 Webhook `code=0` 和 `index_status=failed`。

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

默认 `AI_PROVIDER=deterministic`、`AI_EMBEDDING_PROVIDER=deterministic`、`AI_VECTOR_STORE=memory`、`AI_INDEX_ON_WEBHOOK=false`、`AI_INDEX_MODE=memo`，不会因模型下载、Qdrant 或 Ollama 增加日常 CPU/网络负担。

## 迁移与升级规则

1. Memos 核心继续跟随官方 upstream；AI 功能优先使用旁路 HTTP/Webhook 和 AI 自有 SQLite。
2. 新增 provider 通过 adapter 和可选 requirements 接入，不把 SDK 类型带入 domain。
3. 新索引模式必须通过 `index_version`/`index_mode` 隔离，可回滚且不覆盖既有 embedding ID。
4. 默认路径保持 deterministic + memory；真实 FastEmbed/Qdrant 只在显式配置或 smoke 中启用。
5. 修改目录、模块边界、API 或数据模型后同步 `docs/structure.md`、`docs/api.md`、`docs/architecture.md` 和 `docs/DECISIONS.md`。
