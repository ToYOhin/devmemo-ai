# DevMemo AI 当前交接

## 2026-07-13 Phase 4e

Phase 4e 已完成运维 API 安全与数据暴露边界：

- 可选 `AI_OPS_TOKEN` 通过 `X-DevMemo-Ops-Token` 保护 outbox GET 和 retry POST；未配置时保持本地兼容，错误令牌返回 401。
- 公开 outbox item 不返回原始 Webhook payload；SQLite 内部 payload 保留，retry 行为不变。
- `last_error` 和 `recent_errors` 摘要统一为单行、最多 240 字符；没有新增认证服务、Prometheus、worker 或队列。
- AI Service 全量 102 passed；下一步执行 `docs/prompts/NEXT_STAGE_PROMPT.md` 的 Phase 4f。

## 2026-07-13 Phase 4d

Phase 4d 已完成显式有限重试与最小观测：

- `webhook_events` 兼容增加 `max_attempts`，默认每个事件最多 3 次总尝试，旧表和旧数据保留。
- 新增 `POST /api/ai/ops/outbox/{event_id}/retry`，只允许 `failed` 事件；达到上限返回 409。
- 重试成功清除 `last_error` 并转为 `processed`；重试失败仍返回 `code=0`，记录新的 attempts/error。
- GET outbox 增加 `by_status` 和最多 5 条 `recent_errors`；没有启动 worker、定时任务或外部队列。
- AI Service 全量 100 passed；下一步执行 `docs/prompts/NEXT_STAGE_PROMPT.md` 的 Phase 4e。

## 2026-07-13 Phase 4c

Phase 4c 已完成 AI Service SQLite outbox 最小切片：

- `webhook_events` 以唯一 `event_id` 保存 event type、payload、pending/processed/failed、attempts 和 last_error。
- Webhook 优先入队；显式 `eventId` 优先，没有时使用原始 body hash；重复事件不重复执行旧业务流程。
- 处理异常仍返回 `code=0`，状态可通过 GET `/api/ai/ops/outbox` 查询。
- 没有启动 worker、自动重试或引入 Redis/Celery；下一阶段只做有上限的显式重试和最小观测。
- AI Service 全量 95 passed；Go、前端、TypeScript/build、Compose config 已通过。

## 2026-07-13 Phase 4b

Phase 4b 已完成可选 Webhook HMAC 最小切片：

- `app/services/webhook_security.py` 使用标准库 HMAC-SHA256 签名原始 body。
- `AI_WEBHOOK_SECRET` 为空时兼容旧客户端；配置后要求 `X-DevMemo-Signature: sha256=<hex>`，无效签名返回 401。
- 未修改 Memos 核心、SQLite schema、Qdrant、LLM 或前端；默认 Compose CPU/网络行为不变。
- HMAC/API 定向测试和 AI Service 全量 95 passed；Go、前端、TypeScript/build、Compose config 也已通过。

## 2026-07-13 Phase 4

Phase 4 RAG 最小切片已完成，新增 commit：

- `b9902a8`：provider-neutral retrieval service、完整 Memo 派生上下文和 retrieval tests。
- 当前工作区已接入 `POST /api/ai/chat`，本轮最终提交会同时包含 chat API、测试和真相源文档。

当前实现：

- `app/domain/retrieval.py` 只包含 Citation、RetrievalResult 和 provider-neutral 错误类型。
- `app/services/retrieval_service.py` 执行问题 embedding、VectorStore.search、引用和上下文组装，limit 范围为 1–10。
- `MemoIndexDocument` 将完整 Memo 原文保存为内部 `content` metadata；API citations 不返回该字段。
- `POST /api/ai/chat` 默认 deterministic + memory 离线运行；空库 200，检索不可用 503，LLM 失败 502。
- 当前 AI Service 全量测试为 79 passed；Phase 4 不包含 chunk、rerank 或前端聊天 UI。

Phase 4b、4c、4d 已在顶部交接记录；后续以 `docs/prompts/NEXT_STAGE_PROMPT.md` 为准。

## 2026-07-13 Phase 3g

Phase 3c/3d 已完成，代码 commits：

- c699400：FastEmbed adapter 和 fake/model contract tests
- 57732f9：AI_EMBEDDING_PROVIDER 配置、可选 requirements 和 Compose 环境变量
- 0c0d2cb：MemoIndexDocument/index_memo 索引边界
- 4a58e56：可选 Webhook 索引生命周期、稳定 upsert/delete 和失败降级
- 1f1f055：qdrant-client 安装后的测试兼容、真实 smoke 脚本和 Phase 3e 文档
- Phase 3f：Qdrant volume 重启验证、FastEmbed 缓存目录配置和文档同步
- Phase 3g：索引 health API、Qdrant 降级状态、FastEmbed 缓存错误提示和 Qdrant 镜像 digest 固定

## 继续工作前

~~~powershell
Set-Location H:\DevMemoAI
git status --short --branch
git log --oneline -8
.\scripts\verify-devmemo.ps1
~~~

## 当前实现

- app/adapters/qdrant_vector_store.py 只在显式 qdrant 模式下懒加载 qdrant-client。
- Qdrant adapter 使用 collection、VectorParams、PointStruct、PointIdsList 和 query_points。
- point payload 保存 embedding_id、memo_id、metadata；外部 VectorStore 类型不依赖 SDK。
- app/settings.py 读取 AI_VECTOR_STORE、QDRANT_URL、QDRANT_COLLECTION、QDRANT_API_KEY。
- app/services/embedding_factory.py 默认返回 deterministic + memory；qdrant 模式显式构造 QdrantVectorStore。
- docker-compose.yml 的 AI Service 不再依赖 qdrant/ollama 启动；默认环境为 memory。
- qdrant-client 固定在 requirements-qdrant.txt，不放入默认 requirements.txt。
- fastembed 固定在 requirements-fastembed.txt，不放入默认 requirements.txt；默认 deterministic 不下载模型。
- FastEmbed 默认模型配置为 `BAAI/bge-small-en-v1.5`、384 维；显式更换模型时必须同步 `AI_FASTEMBED_DIMENSION`。
- `POST /api/ai/embed` 当前通过 `MemoIndexDocument` 索引完整 Memo，并写入 `source_type=memo`、`index_version=memo-v1` metadata；没有 chunking。
- `AI_INDEX_ON_WEBHOOK=false` 是安全默认；开启后 Webhook 返回 `index_status`，并执行 created/updated upsert、deleted delete。
- `AI_FASTEMBED_CACHE_DIR` 是可选缓存目录；Compose 显式映射 `/app/model-cache` 到 `ai-model-cache` named volume。
- `GET /api/ai/index/health` 是只读状态接口；memory 返回本地 ready，Qdrant 返回 collection status，查询失败返回 unavailable。
- Compose Qdrant 镜像固定为已验证的 `latest@sha256:75eab8c4...`，服务端版本为 1.18.2。

## 真实环境验证

本机已安装 `qdrant-client==1.18.0`，Docker Desktop Linux Engine 已启动，Qdrant 服务端为 1.18.2。使用 `python -m scripts.smoke_qdrant` 已完成真实 FastEmbed 384 维 collection/upsert/search/delete smoke，临时 collection 已清理。FastEmbed+Webhook create/update/delete smoke 也已通过。默认 Compose 仍为 deterministic + memory。

Phase 3f 持久化验证：`devmemoai_qdrant-data` 挂载到 `/qdrant/storage`；临时 collection `devmemo_phase3f_persistence_20260713` 在 `docker compose restart qdrant` 后恢复，`persist-1`、`memo-persist-1` 和 `phase3f` metadata 均保留。验证后已清理 collection，未删除 volume。

缓存验证：`AI_FASTEMBED_CACHE_DIR=H:\DevMemoAI\ai-service\model-cache` 的 64.07 MB 缓存可在 `HF_HUB_OFFLINE=1` 下加载。直接从网络迁移时曾收到 Hugging Face `RemoteProtocolError`，因此使用已有成功缓存完成本地离线验证。

Phase 3g 验证：默认 memory 的 `/api/ai/index/health` 返回 ready；真实 Qdrant 临时 collection 返回 green；Qdrant fake offline health 返回 unavailable；FastEmbed 初始化失败包含 cache_dir 和修复提示。AI Service 66 tests 通过。

可重复命令：

~~~powershell
Set-Location H:\DevMemoAI\ai-service
.\.venv\Scripts\python.exe -m scripts.smoke_qdrant
~~~

该脚本默认一次性加载 FastEmbed；低 CPU 日常路径仍使用 Compose 的 deterministic + memory。可用 `--provider deterministic` 做无模型下载的 Qdrant adapter smoke。

前端全量测试、TypeScript 和 build 通过；`pnpm lint` 报告 377 个仓库既有 Biome CRLF 诊断，本轮未格式化无关文件。

## 下一阶段

使用 docs/prompts/NEXT_STAGE_PROMPT.md，执行 Phase 4f Outbox 保留与告警导出边界。
