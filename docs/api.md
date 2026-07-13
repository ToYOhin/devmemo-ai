# DevMemo AI API

Base URL：http://localhost:8000

## Frontend configuration

VITE_AI_SERVICE_URL 控制前端 AI feature。AI_CORS_ORIGINS 默认允许 http://localhost:3001，Phase 2d 起允许 GET/POST。

## Vector store configuration

- AI_VECTOR_STORE=memory：默认低 CPU、无网络依赖的 InMemoryVectorStore。
- AI_VECTOR_STORE=qdrant：显式启用 QdrantVectorStore，需要安装 requirements-qdrant.txt。
- QDRANT_URL：默认 http://localhost:6333；Compose 默认使用 http://qdrant:6333。
- QDRANT_COLLECTION：默认 devmemo_memos。
- QDRANT_API_KEY：可选，写入环境变量，不写入仓库。

## Embedding provider configuration

- AI_EMBEDDING_PROVIDER=deterministic：默认 8 维、低 CPU、无模型下载。
- AI_EMBEDDING_PROVIDER=fastembed：显式启用可选 FastEmbed provider，需要先安装 `ai-service/requirements-fastembed.txt`。
- AI_FASTEMBED_MODEL：默认 `BAAI/bge-small-en-v1.5`。
- AI_FASTEMBED_DIMENSION：默认 `384`；更换模型时必须与模型输出维度一致。
- AI_FASTEMBED_CACHE_DIR：可选模型缓存目录；Compose 默认 `/app/model-cache`，由 `ai-model-cache` volume 持久化。
- FastEmbed 初始化会触发模型准备/下载；因此不属于默认启动路径。
- AI_INDEX_ON_WEBHOOK=false：默认关闭 Webhook 向量索引；设为 `true` 后 create/update/delete 才编排向量生命周期。
- AI_WEBHOOK_SECRET：可选 Webhook HMAC secret；为空时保持兼容放行，配置后请求必须携带 `X-DevMemo-Signature: sha256=<hex>`。

## GET /health

返回 service、status、provider。

## GET /api/ai/index/health

只读返回当前向量存储状态：

~~~json
{
  "provider": "memory",
  "available": true,
  "dimension": 8,
  "status": "ready",
  "collection": null,
  "point_count": 0,
  "detail": null
}
~~~

memory 模式不连接 Qdrant；qdrant 模式会读取 collection 状态。Qdrant 查询失败返回 `available=false`、`status=unavailable` 和 detail，不改变 Webhook 的 `code=0` 降级契约。显式 qdrant 模式在启动阶段无法连接时仍返回清晰的 `QdrantAdapterError`。

## POST /api/ai/summarize

接收 memo_id、title、content、tags，生成并 upsert ai_notes，返回 summary、keywords、category、suggested_tags、provider、ai_note_id、created_at。

## GET /api/ai/notes/{memo_id}

读取 AI Service 自有 SQLite 中的摘要；成功返回摘要元数据，找不到返回 404。

## POST /api/ai/embed

接收 memo_id、content、metadata，使用当前配置的 embedding/vector store 组合索引一个完整 Memo，并返回：

~~~json
{
  "embedding_id": "memo-...",
  "memo_id": "memo-42",
  "dimension": 8,
  "provider": "deterministic"
}
~~~

当前索引 metadata 会补充 `source_type=memo` 和 `index_version=memo-v1`。Phase 3c 不做 chunking、查询接口或 RAG。

memory 模式和 qdrant 模式共享同一 API contract。空输入、维度错误或非法请求返回 422。显式 FastEmbed 未安装/模型初始化失败时返回清晰的服务启动错误；默认 deterministic 不受影响。

## POST /api/ai/chat

接收 `question` 和可选 `limit`（默认 5，范围 1–10），对当前已索引的完整 Memo 执行 query embedding 和向量检索，再生成带引用的回答。

成功响应：

~~~json
{
  "answer": "根据知识库检索结果：...",
  "citations": [
    {
      "memo_id": "memo-42",
      "embedding_id": "memo-...",
      "score": 0.912345,
      "metadata": {"title": "Docker ports", "tags": ["docker"]}
    }
  ],
  "provider": "deterministic",
  "retrieved_count": 1
}
~~~

`citations` 不返回索引内部的 `content` 字段；完整 Memo 原文只用于服务端上下文组装。空知识库返回 200 和空 citations；非法 question/limit 返回 422；向量检索不可用返回 503；LLM provider 失败或空回答返回 502。

## GET /api/ai/ops/outbox

读取 AI Service 自有 SQLite 中最近的 Webhook outbox 状态，不会启动重试 worker。

- `status`：可选 `pending|processed|failed`
- `limit`：可选 1–100，默认 50

返回 `items`、`count`、`by_status` 和最多 5 条 `recent_errors`。每个 item 包含 `event_id`、`event_type`、结构化 `payload`、`status`、`attempts`、`max_attempts`、`last_error`、`created_at` 和 `updated_at`。重复 `eventId` 不重复处理；无显式 eventId 时服务使用原始 body hash 作为稳定 ID。Webhook 业务失败仍返回 `code=0`，并可通过该 API 查看 `failed` 状态。

## POST /api/ai/ops/outbox/{event_id}/retry

显式重试一个 `failed` Webhook 事件。不会启动后台 worker；默认每个事件最多处理 3 次（首次处理加最多 2 次重试），上限保存在 AI Service 自有 SQLite 的 `max_attempts` 字段中。

- 仅 `failed` 事件可重试；`processed`、`pending` 或不存在的事件分别返回 409/404。
- 成功返回 `code=0`、`outbox_status=processed`；失败仍返回 `code=0` 并递增 `attempts`。
- 达到 `max_attempts` 后返回 409，错误信息为 `webhook retry limit reached`。
- 这是运维边界 API，不改变 Memos Webhook 原有 `code=0` 契约，也不引入队列或常驻进程。

## GET /api/ai/templates/{memo_id}

读取 Code Snippet 或 Bug Report 派生模板，找不到返回 404；raw_content 保留原始 Markdown。

## POST /api/integrations/memos/webhook

接收 Memos memo.created、memo.updated 和 memo.deleted webhook。可选顶层 `eventId` 用于幂等；删除、空内容和非法模板事件保持 code=0；结构化模板写入 AI Service 自有 memo_templates。开启 `AI_INDEX_ON_WEBHOOK` 后返回 `index_status=indexed|skipped|failed|deleted`，索引失败不阻断 Webhook。

配置 `AI_WEBHOOK_SECRET` 后，服务使用原始 request body 计算 HMAC-SHA256，并通过 `hmac.compare_digest` 校验 `X-DevMemo-Signature`。签名缺失、格式错误或不匹配返回 401；未配置 secret 时不改变既有 Webhook 行为。

## Operational smoke

真实 Qdrant smoke 命令：

~~~powershell
Set-Location H:\DevMemoAI\ai-service
.\.venv\Scripts\python.exe -m scripts.smoke_qdrant
~~~

脚本默认使用 FastEmbed 384 维模型，创建临时 collection 后验证 upsert/search/delete 并清理；`--provider deterministic` 可跳过模型加载，`--cache-dir` 或 `AI_FASTEMBED_CACHE_DIR` 可指定缓存目录。

## Planned APIs

- FastEmbed provider/index pipeline：Phase 3c 已完成；Webhook 索引生命周期：Phase 3d 已完成；Qdrant 真实 smoke：Phase 3e 已完成；Qdrant 重启持久化和缓存治理：Phase 3f 已完成；索引健康与故障边界：Phase 3g 已完成。
- POST `/api/ai/chat`：Phase 4 已完成最小检索/引用问答；显式重试和基础 outbox 观测已在 Phase 4d 完成。
