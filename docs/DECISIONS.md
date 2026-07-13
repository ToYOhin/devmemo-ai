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
