# DevMemo AI 当前交接

## 2026-07-14 单 Agent 模式切换

## 2026-07-14 Phase 5f collection/config/composition

- 新增 `QDRANT_CHUNK_COLLECTION`，默认 `devmemo_memo_chunks`，并由 Compose 透传。
- 配置拒绝空 chunk collection 名称或与完整 Memo `QDRANT_COLLECTION` 重合；fake Qdrant contract 校验独立 collection 的维度和 Cosine distance。
- 组合根已接入 chunk store 选择：仅 `AI_INDEX_MODE=chunk` + `AI_VECTOR_STORE=qdrant` 使用 `QDRANT_CHUNK_COLLECTION`，其他路径继续使用独立 memory store。
- chunk health 读取所选 store；默认完整 Memo、Webhook `code=0` 和 `/api/ai/chat` 不变。
- AI Service 全量测试：150 passed；下一小步是内部 chunk retrieval contract 和显式 Qdrant smoke。

后续项目推进统一回到单 Agent：只使用 `H:\DevMemoAI` 主工作树，不启动 Terra/Luna 并行开发，不让多个 worktree 同时修改当前阶段。`project4` 下的多 Agent worktree 保留为历史/回滚参考，当前不作为开发入口。

详细接管快照见 [`docs/handoffs/2026-07-14-single-agent-handoff.md`](handoffs/2026-07-14-single-agent-handoff.md)。当前 HEAD 已包含本轮 isolated Qdrant chunk collection commit，本轮尚未 push；工作区仍保留用户已有的 `docs/prompts/NEW_WINDOW_PROMPT.md` 未提交修改。

下一窗口先读取该快照和本文件顶部 Phase 5f composition 事实，再执行 `docs/prompts/NEXT_STAGE_PROMPT.md` 的 retrieval/smoke 小步。

## 2026-07-14 Phase 5e

Phase 5e 已完成 chunk health/status 最小切片：

- 新增 `ChunkIndexStateStats`、`ChunkIndexHealth` 和 GET `/api/ai/index/chunk-health`，返回 `memo-chunk-v1`、向量点数、tracked Memo/chunk 数、state backend 和 degraded detail。
- health 只读，不触发索引、不读取原始 Markdown、不改变完整 Memo `/api/ai/index/health` 或 `/api/ai/chat`。
- 覆盖空状态、生命周期计数、版本隔离、SQLite 状态读取和 HTTP contract；AI Service 当前 144 passed。
- 下一阶段执行 `docs/prompts/NEXT_STAGE_PROMPT.md` 的 Phase 5f Qdrant chunk 持久化与显式 chunk 检索。

## 2026-07-14 文档与结构同步

- 已按实际仓库目录刷新 `docs/structure.md`：Memos Go/React 核心、`web/src/features/ai/`、AI Service domain/services/adapters、SQLite、Webhook 和 Compose 均已列出。
- 已同步 `README_AI.md`、`docs/architecture.md`、`docs/development.md`、`docs/api.md` 和 `docs/oss-adoption.md`，修正 Phase 3c 旧描述、不存在的 `.env.example` 命令和过期 lint 阻塞记录。
- 本次仅更新文档，没有修改运行时代码；沿用 Phase 5d 的 AI Service 142 passed、前端 131 passed、Go 全量和 build/lint 验证结果。

## 2026-07-14 Phase 5d

Phase 5d 已完成显式 chunk 索引生命周期：

- 新增 `ChunkLifecycleCoordinator`，`AI_INDEX_ON_WEBHOOK=true` 且 `AI_INDEX_MODE=chunk` 时处理 create/update/delete；默认仍使用完整 Memo `memo-v1`。
- 更新先 upsert 当前 `memo-chunk-v1` chunk，再删除旧尾部；空内容和删除事件清理已登记 chunk，eventId 重复事件继续由 outbox 幂等忽略。
- AI Service 自有 SQLite 新增 `memo_chunk_index_state`，记录版本和 chunk ID 列表，缺失状态不扫描向量库，不误删其他版本。
- chunk coordinator 使用独立 InMemoryVectorStore，避免 chunk 向量污染完整 Memo chat 检索；Qdrant chunk collection 尚未接入。
- chunk 失败保持 Webhook `code=0` 并返回 `index_status=failed`；公共 `POST /api/ai/chat` 完整 Memo citation 不变。
- AI Service 全量 142 passed；下一阶段执行 `docs/prompts/NEXT_STAGE_PROMPT.md` 的 Phase 5e chunk 检索与可观测性收敛。

## 2026-07-13 Phase 5c

Phase 5c 已完成 chunk 离线检索评估：

- 新增 `OfflineChunkIndex`，用现有 deterministic provider 和 InMemoryVectorStore 构造独立试验索引；chunk ID 作为 embedding ID。
- 复用 `RetrievalService` 和 Phase 5a `RetrievalEvaluator`，可将完整 Memo 与 chunk 结果按 Recall@K/首个命中排名对照。
- chunk citation metadata 明确包含 `memo_id`、`chunk_id`、`chunk_index`、`index_version`；服务端上下文仍保留 chunk 原文，公共 chat API 不变。
- 更新、重复 ID、空内容和显式 stale delete 有 contract tests；没有接入 Webhook、Qdrant、FastEmbed、Compose 或 Memos 核心。
- AI Service 全量 133 passed；下一阶段执行 `docs/prompts/NEXT_STAGE_PROMPT.md` 的 Phase 5d 可选 chunk 索引生命周期。

## 2026-07-13 Phase 5b

Phase 5b 已完成 Memo chunking 纯函数/内存边界：

- 新增 provider-neutral `MemoChunk` 与 `chunk_memo`，按换行边界和字符上限切分，拼接 chunk 内容可还原原始 Markdown。
- chunk ID 由 Memo ID、`index_version` 和位置稳定派生；metadata 使用 `memo-chunk-v1`/`index_mode=chunk`，与现有 `memo-v1` 完整 Memo 索引隔离。
- 更新时同位置复用 ID，内容缩短时通过旧 chunk 数量计算 stale IDs，供未来显式 delete；重复 ID 会在生命周期边界被拒绝。
- 本次没有接入 Webhook、Qdrant、FastEmbed、Compose 或 Memos 核心，也没有新增公共 HTTP API。
- AI Service 全量 129 passed；下一阶段执行 `docs/prompts/NEXT_STAGE_PROMPT.md` 的 Phase 5c chunk 离线检索评估。

## 2026-07-13 Phase 5a

Phase 5a 已完成离线检索质量评估边界：

- 选择离线评估而不是直接切换 chunking，保护当前完整 Memo 索引和 citation 契约。
- 新增 `RetrievalEvaluationCase`、`RetrievalEvaluationResult` 和 `RetrievalEvaluator`，支持 Recall@K、命中列表、首个相关结果排名和批量评估。
- 评估器只依赖 provider-neutral `RetrievalService`，默认 deterministic + memory 可离线运行，不访问 FastEmbed/Qdrant。
- 没有新增公共 API，没有修改 Memos 核心、Webhook、outbox、AI SQLite 或向量存储。
- AI Service 全量 116 passed；下一阶段执行 `docs/prompts/NEXT_STAGE_PROMPT.md` 的 Phase 5b Memo chunking 边界。

## 2026-07-13 Phase 4g

Phase 4g 已完成显式清理批准与审计边界：

- retention preview 返回 `cutoff`、`preview_limit` 和 `candidate_ids`，执行请求绑定同一预览集合。
- 新增 `POST /api/ai/ops/outbox/retention-cleanup`；默认 dry-run，必须 `confirm=true` 且 `dry_run=false` 才删除。
- SQLite 事务重新校验 cutoff、完整候选集合和终态；pending、越界 ID 或数据变化整批拒绝。
- 新增 cleanup audit 表和 `GET /api/ai/ops/outbox/cleanup-audits`；相同 approval_id 重复执行幂等，不保存 ops secret。
- 清理只作用于 AI Service 自有 webhook_events；AI Service 全量 108 passed。
- 下一阶段执行 `docs/prompts/NEXT_STAGE_PROMPT.md` 的 Phase 5 检索质量增强。

## 2026-07-13 Phase 4f

Phase 4f 已完成 Outbox 保留预览与告警轮询边界：

- 新增受 `AI_OPS_TOKEN` 保护的 retention preview，按 `updated_at` 预览 30 天以上未更新的 `processed/failed` 事件，不删除、不影响 `pending`。
- 新增受保护的 alerts JSON 摘要，返回失败数、耗尽重试数和最多 5 条 warning/critical 摘要，不推送外部服务。
- 公开接口不返回 payload、secret 或未截断错误；没有启动 worker、队列、Prometheus，也没有修改 volume。
- AI Service 全量 105 passed；下一步执行 `docs/prompts/NEXT_STAGE_PROMPT.md` 的 Phase 4g。

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

使用 docs/prompts/NEXT_STAGE_PROMPT.md，执行 Phase 5e chunk 检索与可观测性收敛。
