# DevMemo AI API

## Phase 9f local lifecycle diagnostic (no HTTP API)

Run locally from `ai-service`:

```powershell
.\.venv\Scripts\python.exe -m scripts.devmemory_lifecycle_report
```

Optional `--database <path>` selects an AI Service SQLite file. The command opens the file through SQLite `mode=ro` and returns only aggregate `ai_notes`, `memo_templates`, `memo_insights`, `memo_chunk_index_state`, insight status/version range, and webhook-event status counts. It does not create, migrate, or modify a database; it omits memo IDs, raw content, raw webhook payloads, chunk content, and secrets. This is a local development diagnostic, not a public HTTP endpoint.

## Manual UI integration notes (2026-07-14)

- The default local CORS allowlist includes both `http://localhost:3001` and `http://127.0.0.1:3001`.
- `POST /api/ai/summarize` persists an explicit Code Snippet or Bug Report template when `memo_id` is present. The response includes `memo_type` and optional `template_id`; plain Memos do not create templates.

Base URL：http://localhost:8000

## Frontend configuration

VITE_AI_SERVICE_URL 控制前端 AI feature。AI_CORS_ORIGINS 默认允许 http://localhost:3001，Phase 2d 起允许 GET/POST。

## Vector store configuration

- AI_VECTOR_STORE=memory：默认低 CPU、无网络依赖的 InMemoryVectorStore。
- AI_VECTOR_STORE=qdrant：显式启用 QdrantVectorStore，需要安装 requirements-qdrant.txt。
- QDRANT_URL：默认 http://localhost:6333；Compose 默认使用 http://qdrant:6333。
- QDRANT_COLLECTION：默认 devmemo_memos。
- QDRANT_CHUNK_COLLECTION：默认 devmemo_memo_chunks；必须与 QDRANT_COLLECTION 不同，用于显式 chunk Qdrant store。
- QDRANT_API_KEY：可选，写入环境变量，不写入仓库。

## Embedding provider configuration

- AI_EMBEDDING_PROVIDER=deterministic：默认 8 维、低 CPU、无模型下载。
- AI_EMBEDDING_PROVIDER=fastembed：显式启用可选 FastEmbed provider，需要先安装 `ai-service/requirements-fastembed.txt`。
- AI_FASTEMBED_MODEL：默认 `BAAI/bge-small-en-v1.5`。
- AI_FASTEMBED_DIMENSION：默认 `384`；更换模型时必须与模型输出维度一致。
- AI_FASTEMBED_CACHE_DIR：可选模型缓存目录；Compose 默认 `/app/model-cache`，由 `ai-model-cache` volume 持久化。
- FastEmbed 初始化会触发模型准备/下载；因此不属于默认启动路径。
- AI_INDEX_ON_WEBHOOK=false：默认关闭 Webhook 向量索引；设为 `true` 后 create/update/delete 才编排向量生命周期。
- AI_INDEX_MODE=memo：默认使用完整 Memo `memo-v1`；只有显式设置为 `chunk` 且同时开启 `AI_INDEX_ON_WEBHOOK=true` 时，Webhook 才使用 `memo-chunk-v1` 生命周期。
- AI_WEBHOOK_SECRET：可选 Webhook HMAC secret；为空时保持兼容放行，配置后请求必须携带 `X-DevMemo-Signature: sha256=<hex>`。
- AI_OPS_TOKEN：可选 ops API 访问令牌；为空时保持本地兼容，配置后 `/api/ai/ops/outbox` 的 GET 和 retry POST 必须携带 `X-DevMemo-Ops-Token`。

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

接收 `memo_id`、`title`、`content`、`tags`，生成并 upsert `ai_notes`。当内容显式声明 Code Snippet 或 Bug Report 且提供 `memo_id` 时，同时 upsert `memo_templates`；响应返回 `summary`、`keywords`、`category`、`suggested_tags`、`provider`、`ai_note_id`、`created_at`、`memo_type` 和可选 `template_id`。

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

默认索引 metadata 会补充 `source_type=memo`、`index_mode=memo` 和 `index_version=memo-v1`。`POST /api/ai/embed` 仍是完整 Memo API；chunk Webhook 生命周期使用独立的 `memo-chunk-v1` 路径，不改变该 API 响应。

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

## Phase 5a internal evaluation boundary

Phase 5a adds no public HTTP endpoint. `RetrievalEvaluationCase` and `RetrievalEvaluator` run offline against the existing `RetrievalService`, reporting Recall@K and first relevant rank without changing the `POST /api/ai/chat` response. Phase 5b adds the separate pure-function chunking boundary; Phase 5c evaluates chunk retrieval offline.

## Phase 5b internal chunking boundary

Phase 5b adds no public HTTP endpoint and does not change `POST /api/ai/embed`, Webhook or `POST /api/ai/chat`. `MemoChunk`/`chunk_memo` are provider-neutral pure functions: empty/whitespace content produces no chunks; chunk content preserves the original Markdown character sequence; metadata uses `source_type=memo_chunk`, `index_mode=chunk` and `index_version=memo-chunk-v1`. Stable IDs are derived from Memo ID, version and position. The default production index remains `source_type=memo`/`memo-v1`; Phase 5d adds a separate explicit chunk Webhook path.

## Phase 5c internal chunk retrieval evaluation

Phase 5c adds no public HTTP endpoint. `OfflineChunkIndex` uses the existing deterministic provider, InMemoryVectorStore and RetrievalService to build a separate in-memory trial index; `RetrievalEvaluator` can compare it with the complete Memo baseline using Recall@K and first relevant rank. Trial citations expose `memo_id`, `chunk_id`, `chunk_index` and `index_version` through internal metadata, while chunk content is used only for server-side context assembly. Webhook indexing and `POST /api/ai/chat` remain complete-Memo contracts.

## Phase 5d optional chunk lifecycle

When `AI_INDEX_ON_WEBHOOK=true` and `AI_INDEX_MODE=chunk`, create/update events return `index_mode=chunk`, `index_version=memo-chunk-v1`, `chunk_count` and `deleted_chunk_count`. The coordinator upserts current chunks before deleting stale IDs registered for the same Memo and version. Delete events remove all registered chunk IDs. Empty content removes registered chunks without storing an empty vector.

The AI-owned SQLite table `memo_chunk_index_state` stores only the Memo ID, version, chunk IDs and timestamp needed for lifecycle bookkeeping. Missing state is treated as “no known chunks” and never triggers a broad vector-store scan. In this phase chunk vectors use a separate in-memory store, so they cannot contaminate the complete-Memo chat index; a Qdrant chunk collection is a later opt-in boundary. Chunk failures are reported as `index_status=failed` while the Webhook still returns `code=0`. The default `AI_INDEX_MODE=memo` path keeps `memo-v1` IDs and the public complete-Memo `POST /api/ai/chat` response unchanged.

## GET /api/ai/index/chunk-health

Read-only health for the explicit chunk lifecycle index. It always declares `index_mode=chunk` and `index_version=memo-chunk-v1`; it does not enable chunk indexing or change the complete-Memo index.

~~~json
{
  "index_mode": "chunk",
  "index_version": "memo-chunk-v1",
  "provider": "memory",
  "available": true,
  "status": "ready",
  "dimension": 8,
  "point_count": 2,
  "tracked_memos": 1,
  "tracked_chunks": 2,
  "state_backend": "sqlite",
  "detail": null
}
~~~

`point_count` comes from the isolated chunk VectorStore; `tracked_memos` and `tracked_chunks` come from `memo_chunk_index_state`. If either store is unavailable or malformed, the endpoint returns `available=false` and `status=degraded` with a bounded detail string. It never returns original Markdown or chunk payloads.

## Phase 5f collection/config boundary

The complete-Memo Qdrant collection remains `QDRANT_COLLECTION`/`memo-v1`. When `AI_INDEX_MODE=chunk` and `AI_VECTOR_STORE=qdrant`, the chunk lifecycle uses the separate `QDRANT_CHUNK_COLLECTION`/`memo-chunk-v1` boundary with the provider dimension and Cosine distance. Other chunk paths use an isolated in-memory store. The configuration rejects an empty chunk collection name or reuse of the complete-Memo collection; chunk health reports the selected store without changing public complete-Memo chat.

## Internal chunk retrieval contract

`ChunkRetrievalService` is an internal provider-neutral service and is not a public HTTP endpoint. It returns `ChunkRetrievalResult(context, citations)` where every `ChunkCitation` contains `memo_id`, stable `chunk_id`, non-negative `chunk_index`, `index_version=memo-chunk-v1`, score and sanitized metadata. It accepts only `source_type=memo_chunk` and `index_mode=chunk`; malformed or mixed-version metadata raises a retrieval-unavailable error. Chunk `content` is used only to assemble server-side context and is removed from citation metadata. Public `POST /api/ai/chat` continues to use the complete-Memo `Citation` contract.

## Phase 6 public chunk retrieval compatibility decision

Phase 6 keeps chunk retrieval internal. The existing `POST /api/ai/chat` response treats `embedding_id` as a complete-Memo identity and `retrieved_count` as the number of complete-Memo results. A direct switch to chunk IDs would create multiple citations for one Memo, change counts/order/context budgeting, and break clients that consume the current citation shape. There is no implicit chunk mode and no public chunk endpoint in this phase.

Any future public chunk API must use an explicit versioned endpoint or response contract and define chunk citation fields, same-Memo deduplication, ordering, context limits, content redaction, migration and rollback before implementation. `ChunkRetrievalService` and `/api/ai/index/chunk-health` remain the internal/operations boundary.

## Phase 9a internal MemoInsight contract

The AI Inbox is an internal product-boundary API, not a public chunk retrieval API. `MemoInsight` contains `insight_id`, `memo_id`, `insight_type` (`fact`, `decision`, `action`, or `bug`), `title`, bounded `summary`, `confidence`, `status` (`pending`, `accepted`, or `rejected`), `source_refs`, `version`, `created_at`, and `updated_at`. Raw Memo content is only an input to derivation and is not returned in this contract.

- `POST /api/ai/insights/preview` derives candidates from `{memo_id, title, content, summary}` without writing SQLite state.
- `GET /api/ai/insights/{memo_id}` reads persisted candidates; optional `status` filters the lifecycle state.
- `POST /api/ai/insights/{insight_id}/status` accepts `{status, version}`. The current version is required; stale updates return `409` and do not overwrite a newer decision.

The summarization path persists deterministic candidates for an explicit `memo_id`. Upsert identity is `(memo_id, insight_type)`; unchanged candidates retain review status, while changed semantic fields reset to `pending` and increment `version`. These routes do not modify Memos storage, `/api/ai/chat`, complete-Memo citations, or either vector collection.

## Phase 9b internal Context Pack contract

Context Pack v1 is a pure provider-neutral builder and fixture, not an HTTP route. `ContextPackRequest` contains a non-empty `question`, explicit `memo_ids`, explicit `insight_ids`, `max_chars` (64–20,000) and `max_items` (1–50). An insight is eligible only when its status is `accepted` and its parent Memo ID is also explicitly selected. Unknown IDs, pending/rejected insights and implicit expansion are rejected.

`build_context_pack(request, memos, insights)` returns `ContextPackResponse` with `pack_version=context-pack-v1`, bounded `markdown`, structured `items`, unique `sources`, `truncated` and `truncation_reason`. Memo title/summary and insight title/summary/source_refs are the only content inputs; raw Markdown, Webhook payloads, secrets and chunk content are not accepted by the contract. Items are deterministic: Memo IDs are sorted, then insights use confidence descending, updated_at descending and stable insight ID ascending. `max_chars` bounds the Markdown body without partial item blocks; JSON serialization uses the same items and sources through `to_json()`.

## Phase 9c Context Pack integration proposal（已批准并完成 9d UI）

The approved product entry is a `Context Pack` panel inside the existing Memo detail AI Inbox. It keeps provenance next to the reviewed insight and defaults to the current Memo. The current minimal slice does not load a cross-Memo picker, so it cannot implicitly expand to other Memos; a future cross-Memo flow must use explicit IDs and visibility checks. No public HTTP route is added.

The implemented internal interaction accepts a question, current Memo/accepted insight selection, `max_chars`, and `max_items`; offers Markdown as the primary copy format and JSON as an optional format; and shows sources, truncation reason, empty state, AI query failure, clipboard failure, and narrow-screen behavior. Authorization remains at the Memos product boundary: deleted/inaccessible Memo requests surface failure, while pending/rejected/revoked/stale insights are excluded from the eligible list. The pack is ephemeral and never exposes raw content, Webhook payloads, secrets, or chunk content. The browser adapter mirrors the Phase 9b Python builder contract because no HTTP route is permitted in this slice.

## Phase 9e Context Pack permission/deletion linkage

The shared test input is `contracts/context-pack-v1.json`; it is not a runtime data source. The Memo detail panel obtains additional candidates only from the current user's visible Memos returned by the existing Memos API. The current Memo is selected by default; every additional Memo requires an explicit checkbox. No raw Memo `content` is passed to the builder. Additional insight queries reuse `aiInsightKeys.detail(memo_id)` and only `accepted` records are eligible. A deleted or inaccessible current Memo surfaces the existing failure state; a selected additional Memo that disappears or whose insight query fails is excluded and shown as unavailable.

`rejected` is the current insight revoke state. `POST /api/ai/insights/{insight_id}/status` still requires the current `version`, increments it on success, and returns `409` for stale updates. React Query invalidation removes revoked insights from the Context Pack candidate set. Existing Memos deleted Webhook handling also deletes AI-owned `ai_notes`, `memo_templates`, and `memo_insights`; it does not delete Memos data, raw Markdown, public chat citations, or Qdrant volumes. Context Pack remains in-memory and adds no public route or persistence.

## Phase 7 public chunk API proposal（未实现）

This is a reviewable proposal only. It does not add a route or change the existing chat API.

Proposed endpoint: `POST /api/ai/v1/chunks/search` with `api_version=public-chunk-v1`.

Request:

~~~json
{
  "question": "Docker port mapping",
  "limit": 5
}
~~~

`question` is required and non-empty; `limit` is 1–10 and defaults to 5. The server always selects `index_version=memo-chunk-v1`; clients cannot select arbitrary index versions.

Proposed response:

~~~json
{
  "api_version": "public-chunk-v1",
  "index_version": "memo-chunk-v1",
  "provider": "deterministic",
  "chunks": [
    {
      "memo_id": "memo-42",
      "chunk_id": "memo-chunk-v1:memo-42:0000",
      "chunk_index": 0,
      "score": 0.912345,
      "metadata": {"title": "Docker ports", "source_type": "memo_chunk"}
    }
  ],
  "retrieved_count": 1
}
~~~

The default contract keeps only the highest-scoring chunk per Memo. Results sort by score descending, then `memo_id`, `chunk_index`, and `chunk_id` ascending. `retrieved_count` counts deduplicated chunks. Metadata is an allowlist and never contains `content`, raw Markdown, Webhook payloads, secrets, or internal storage fields.

Proposed errors: invalid question/limit → 422; disabled, unavailable, or degraded chunk store → 503. Public exposure requires gateway authentication and Memo-level authorization; the current local-compatible AI Service auth boundary is not multi-tenant authorization. Default `AI_PUBLIC_CHUNK_RETRIEVAL=false`; the endpoint is not implemented until product/API compatibility approval. Migration requires offline dual-path evaluation and feature-flagged canary; rollback disables the flag/route without touching `memo-v1`, the chunk collection, or volumes.

## GET /api/ai/ops/outbox

读取 AI Service 自有 SQLite 中最近的 Webhook outbox 状态，不会启动重试 worker。

- `status`：可选 `pending|processed|failed`
- `limit`：可选 1–100，默认 50

未配置 `AI_OPS_TOKEN` 时可直接读取；配置后必须携带 `X-DevMemo-Ops-Token`，缺失或错误返回 401。返回 `items`、`count`、`by_status`、`exhausted_count` 和最多 5 条 `recent_errors`。公开 item 只包含 `event_id`、`event_type`、`status`、`attempts`、`max_attempts`、`last_error`、`created_at` 和 `updated_at`，不返回原始 Webhook `payload`。`last_error` 和 `recent_errors.last_error` 为单行、最多 240 字符的摘要。重复 `eventId` 不重复处理；无显式 eventId 时服务使用原始 body hash 作为稳定 ID。Webhook 业务失败仍返回 `code=0`，并可通过该 API 查看 `failed` 状态。

## POST /api/ai/ops/outbox/{event_id}/retry

显式重试一个 `failed` Webhook 事件。配置 `AI_OPS_TOKEN` 后必须携带 `X-DevMemo-Ops-Token`；不会启动后台 worker；默认每个事件最多处理 3 次（首次处理加最多 2 次重试），上限保存在 AI Service 自有 SQLite 的 `max_attempts` 字段中。

- 仅 `failed` 事件可重试；`processed`、`pending` 或不存在的事件分别返回 409/404。
- 成功返回 `code=0`、`outbox_status=processed`；失败仍返回 `code=0` 并递增 `attempts`。
- 达到 `max_attempts` 后返回 409，错误信息为 `webhook retry limit reached`。
- 这是运维边界 API，不改变 Memos Webhook 原有 `code=0` 契约，也不引入队列或常驻进程。

## GET /api/ai/ops/outbox/retention-preview

只读预览长期未更新的终态 outbox 事件，不执行删除。默认 `older_than_days=30`，范围 1–3650；`limit` 默认 100，范围 1–100。返回本次预览固定的 `cutoff`、`preview_limit` 和 `candidate_ids`；只包含 `processed`/`failed`，不会把 `pending` 事件列为清理候选。配置 `AI_OPS_TOKEN` 后同样需要 `X-DevMemo-Ops-Token`。

## POST /api/ai/ops/outbox/retention-cleanup

执行 retention 清理前必须先调用 preview。请求至少包含 preview 返回的 `cutoff`、`preview_limit`、`candidate_ids` 和唯一 `approval_id`。

- 默认 `dry_run=true`，只返回 `executed=false`，不会删除数据。
- 只有同时设置 `dry_run=false` 和 `confirm=true` 才会执行。
- 服务会在 SQLite 事务中再次校验 cutoff、状态和完整 preview candidate 集合；pending、集合外 ID、集合发生变化时整批返回 409。
- `X-DevMemo-Ops-Actor` 可选，只保存 SHA-256 摘要，不保存 ops secret。
- 相同 `approval_id` 重复提交相同请求是幂等 replay，不会重复删除；同一 approval_id 改变参数返回 409。

## GET /api/ai/ops/outbox/cleanup-audits

读取清理执行审计，受 `AI_OPS_TOKEN` 保护。返回 `approval_id`、`actor_digest`、`cutoff`、`preview_limit`、候选数量、删除数量和执行时间；不返回 payload、Memo 原文或 ops secret。

## GET /api/ai/ops/alerts

供外部监控轮询的只读 JSON 摘要，受 `AI_OPS_TOKEN` 保护。返回 `has_alert`、`failed_count`、`exhausted_count`、`alert_count` 和最多 5 条 `alerts`；每条 alert 只包含事件 ID、attempts、max_attempts、更新时间、脱敏错误摘要和 `warning|critical` 严重级别，不返回 payload 或 secret。Phase 4f 不主动推送外部告警。

## GET /api/ai/templates/{memo_id}

读取 Code Snippet 或 Bug Report 派生模板，找不到返回 404；raw_content 保留原始 Markdown。

## POST /api/integrations/memos/webhook

接收 Memos memo.created、memo.updated 和 memo.deleted webhook。可选顶层 `eventId` 用于幂等；删除、空内容和非法模板事件保持 code=0；结构化模板写入 AI Service 自有 memo_templates。开启 `AI_INDEX_ON_WEBHOOK` 后返回 `index_status=indexed|skipped|failed|deleted`，索引失败不阻断 Webhook。默认 `AI_INDEX_MODE=memo` 使用完整 Memo；显式 `AI_INDEX_MODE=chunk` 时返回 chunk 数量、版本和旧 chunk 删除数量，且生命周期状态仅写入 AI Service 自有 SQLite。

配置 `AI_WEBHOOK_SECRET` 后，服务使用原始 request body 计算 HMAC-SHA256，并通过 `hmac.compare_digest` 校验 `X-DevMemo-Signature`。签名缺失、格式错误或不匹配返回 401；未配置 secret 时不改变既有 Webhook 行为。

## Operational smoke

真实 Qdrant smoke 命令：

~~~powershell
Set-Location H:\DevMemoAI\ai-service
.\.venv\Scripts\python.exe -m scripts.smoke_qdrant
~~~

脚本默认使用 FastEmbed 384 维模型，创建临时 collection 后验证 upsert/search/delete 并清理；`--provider deterministic` 可跳过模型加载，`--mode chunk` 额外验证 chunk metadata、health、重新连接后的持久性和内部 retrieval contract。`--cache-dir` 或 `AI_FASTEMBED_CACHE_DIR` 可指定缓存目录；显式传入 `--collection` 时默认保留 collection，只有加 `--delete-collection` 才清理。

## Planned APIs

- FastEmbed provider/index pipeline：Phase 3c 已完成；Webhook 索引生命周期：Phase 3d 已完成；Qdrant 真实 smoke：Phase 3e 已完成；Qdrant 重启持久化和缓存治理：Phase 3f 已完成；索引健康与故障边界：Phase 3g 已完成。
- POST `/api/ai/chat`：Phase 4 已完成最小检索/引用问答；outbox 显式重试、基础观测、ops API 安全、保留预览、告警轮询和清理审计已在 Phase 4d/4e/4f/4g 完成；Phase 5a/5b/5c/5d/5e 离线评估、chunk 边界、可选生命周期和 health 已完成，Phase 5f 已完成独立 Qdrant composition、内部 chunk retrieval contract 和 smoke 脚本，尚未把 chunk retrieval 接入公共 chat。
