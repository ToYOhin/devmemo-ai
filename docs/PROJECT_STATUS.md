# DevMemo AI 项目状态

更新时间：2026-07-13

## 当前阶段

Phase 0、Phase 1、Phase 2、Phase 2b、Phase 2c、Phase 2d、Phase 3a、Phase 3b、Phase 3c、Phase 3d、Phase 3e、Phase 3f、Phase 3g、Phase 4 已完成。下一阶段为 Phase 4b：索引可靠性与 Webhook 运维边界。

## 当前事实

- 工作区：H:\DevMemoAI
- 分支：codex/devmemo-ai-mvp
- Memos 基线：v0.29.1
- Go：G:\Go；Go 工作区和缓存：G:\GoWorkspace
- AI Service：FastAPI，默认 deterministic provider
- AI 数据：AI Service 自有 SQLite；不修改 Memos 数据库
- 默认向量存储：InMemoryVectorStore
- 可选向量存储：QdrantVectorStore
- 可选 embedding：FastEmbedEmbeddingProvider，默认不启用、不加载模型；本机已安装依赖用于 smoke
- 索引健康接口：GET `/api/ai/index/health`，默认 memory 路径不连接 Qdrant
- RAG 接口：POST `/api/ai/chat`，当前检索完整 Memo 并返回引用；默认 deterministic + memory 可离线运行

## Phase 4 已完成

- 新增 provider-neutral `RetrievalService`：问题 embedding -> VectorStore.search -> 结构化 citations/context。
- 当前以一个完整 Memo 为一个检索单元；索引派生 metadata 保存原文供上下文组装，API 引用会剥离内部 `content` 字段。
- 新增 POST `/api/ai/chat`，接收 `question` 和 `limit`，返回 `answer`、`citations`、`provider`、`retrieved_count`。
- deterministic provider 返回可复现的引用式离线答案；OpenAI/Ollama 复用现有 LLM adapter。
- 空知识库返回明确空结果；非法 limit 返回 422；检索不可用返回 503；LLM 失败返回 502。

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
AI Service full pytest             79 passed
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
pnpm lint                          BLOCKED / 377 existing Biome CRLF diagnostics
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
- Phase 4b 尚未实现 Webhook 签名/HMAC、outbox、重试、限流和观测。
- Webhook 签名/HMAC、outbox、重试和观测尚未实现。
- 全量 pnpm lint 当前报告 377 个仓库既有 Biome CRLF 格式诊断；本轮未执行格式化修复，避免混入无关前端变更。

## 下一步

执行 docs/prompts/NEXT_STAGE_PROMPT.md，开始 Phase 4b 索引可靠性与 Webhook 运维边界。
