# DevMemo AI 变更记录

## 2026-07-13

### Phase 4：RAG 检索与引用问答最小切片

- 新增 provider-neutral `RetrievalService`，按问题 embedding、向量搜索和完整 Memo 上下文组装执行检索。
- 新增 `POST /api/ai/chat`，返回答案、`memo_id`/`embedding_id`/`score`/metadata 引用、provider 和检索数量。
- 默认 deterministic + memory 支持无网络问答；空知识库、非法 limit、检索故障和 LLM 故障有明确契约。
- 原文仅作为索引派生上下文使用，公共 citations 不返回内部 `content` 字段；未引入 chunk/rerank 或前端聊天 UI。
- 验证：AI Service 79 passed；Go `go test -p 2 ./...`、Qdrant deterministic smoke、Compose config、前端 131 tests、TypeScript/build 均通过。
- `pnpm lint` 仍受仓库既有 377 个 Biome CRLF 诊断阻塞，本轮未格式化无关前端文件。

### Phase 3g：索引运行健康与故障边界

- 新增只读 `GET /api/ai/index/health`：memory 返回 ready，Qdrant 返回 collection status/point_count。
- Qdrant health 查询异常降级为 `available=false、status=unavailable`，不让默认 memory 路径连接 Qdrant。
- FastEmbed 初始化错误现在包含 cache_dir 和缓存修复提示。
- Qdrant 镜像固定到已验证的 Server 1.18.2 digest：`sha256:75eab8c4...`。
- 验证：AI Service 66 passed；真实 Qdrant health smoke 通过；Go 全量、前端 131 tests、TypeScript/build 通过。
- 未完成：RAG 检索、Memo chunk 和 `/api/ai/chat`，留到 Phase 4。

### Phase 3f：Qdrant 持久化与 FastEmbed 缓存治理

- Compose 为 AI Service 增加 `ai-model-cache:/app/model-cache`，并新增 `AI_FASTEMBED_CACHE_DIR`；默认 deterministic + memory 不加载模型。
- 验证 `devmemoai_qdrant-data` 挂载到 `/qdrant/storage`；`docker compose restart qdrant` 后 collection、point 和 payload 恢复成功。
- FastEmbed 384 维模型在 `H:\DevMemoAI\ai-service\model-cache` 离线加载成功，缓存约 64.07 MB。
- 首次直接迁移下载因 Hugging Face 代理 `RemoteProtocolError` 失败，随后复用已验证缓存完成离线 smoke；该环境限制已记录。
- AI Service：62 passed；Qdrant volume restart smoke：通过；Compose config：通过。
- 未完成：Qdrant health/故障降级边界和镜像版本固定评估，留到 Phase 3g。

### Phase 3e：Qdrant 真实 collection smoke

- Docker Desktop Linux Engine 已启动，Compose Qdrant 服务端返回 1.18.2。
- 安装可选 `qdrant-client==1.18.0`，不加入默认 requirements，Compose 默认仍为 deterministic + memory。
- 新增 `ai-service/scripts/smoke_qdrant.py`，验证真实 collection 创建、FastEmbed 384 维 upsert、search、payload 和 delete；临时 collection 已清理。
- FastEmbed+Qdrant 真实 smoke：通过；删除后目标向量不再出现在搜索结果中。
- AI Service 全量测试：60 passed；安装 qdrant-client 后的缺依赖契约测试通过模块注入模拟。
- 未完成：Qdrant volume 重启持久化和 FastEmbed 模型缓存持久化目录评估，留到 Phase 3f。

### Phase 3c：可选 FastEmbed Provider 与 Memo 索引边界

- 新增可选 `FastEmbedEmbeddingProvider`，第三方 SDK 只存在于 adapter。
- 新增 `AI_EMBEDDING_PROVIDER`、`AI_FASTEMBED_MODEL` 和 `AI_FASTEMBED_DIMENSION`；默认 deterministic、不下载模型。
- 新增 `requirements-fastembed.txt`，固定 fastembed 0.8.0。
- 新增 `MemoIndexDocument/index_memo`；当前一个完整 Memo 对应一个向量，补充 `source_type` 和 `index_version` metadata，不做 chunk/RAG。
- 验证：AI Service 54 passed；前端 131 passed；TypeScript/build、Compose config、根验证通过。
- FastEmbed 真实 smoke 已通过：首次加载约 23.48 秒，单条推理约 0.06 秒，384 维；模型缓存约 64.07 MB。
- 未验证：真实 Qdrant 网络路径，原因是 qdrant-client 未安装且 Docker Linux engine 未运行。
- Commits：c699400、57732f9、0c0d2cb。

### Phase 3d：Webhook 可选索引生命周期

- 新增 `AI_INDEX_ON_WEBHOOK=false`，默认不改变日常 CPU 和 Webhook 索引行为。
- 开启后支持 Memo create/update 稳定 upsert、delete 删除和 `index_status` 状态。
- 索引失败不会阻断摘要、模板持久化和 Webhook `code=0` 响应。
- 验证：AI Service 60 passed；Go 全量测试通过；前端 131 passed；FastEmbed+Webhook 真实 smoke 通过。
- 未验证：真实 Qdrant，因 qdrant-client 未安装且 Docker Linux engine 未运行。
- Commit：4a58e56。

### Phase 3b：可选 Qdrant VectorStore Adapter

- 新增 QdrantVectorStore，实现 VectorStore Protocol 的 upsert、query_points search、delete。
- 使用稳定 UUID 映射 Qdrant point，payload 保存 embedding_id、memo_id、metadata。
- 新增 requirements-qdrant.txt，固定 qdrant-client 1.18.0；默认 requirements 不增加网络依赖。
- 新增 AI_VECTOR_STORE=memory|qdrant，默认 memory。
- AI 容器不再依赖 Qdrant/Ollama 启动。
- fake adapter contract 通过；真实 Qdrant 因本机依赖和 Docker 引擎不可用暂未验证。
- Commits：ee0937c、99ad024。

### Phase 3a：Embedding Provider 与 Vector Store 边界

- 新增 provider-neutral contracts、8 维 deterministic provider、InMemoryVectorStore、EmbeddingService 和 POST /api/ai/embed。
- 验证：AI Service 34 passed；Phase 3a 定向 13 passed。

### Phase 2d：AI 摘要读取与生成 UI

- 新增 GET /api/ai/notes/{memo_id}、摘要展示和生成/重新生成。
- 验证：AI Service 21 passed；前端 131 passed；TypeScript/build 通过。

## 2026-07-12

### Phase 2c：模板展示与复制

- React 展示 Code/Bug 模板、highlight.js 高亮和 Clipboard API 反馈。

### Phase 2b：模板持久化

- memo_templates 按 memo_id 幂等 upsert，保留 raw_content。
