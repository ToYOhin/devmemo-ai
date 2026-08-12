# DevMemo AI Service 指南

[English](README_AI.md)

本文说明与 Memos 配套的可选 AI Service。Memos 仍是 Memo 内容、身份和权限的事实来源；
AI Service 只保存派生摘要、模板、Insight、outbox 状态和可选索引状态。

## 默认配置

默认配置刻意保持离线优先和低资源：

```text
AI_PROVIDER=deterministic
AI_EMBEDDING_PROVIDER=deterministic
AI_VECTOR_STORE=memory
AI_INDEX_ON_WEBHOOK=false
AI_INDEX_MODE=memo
AI_PUBLIC_CHUNK_RETRIEVAL=false
AI_AGENT_ENABLED=false
```

默认只以温和 CPU 上限启动 Memos 与 AI Service。Qdrant 和 Ollama 都是显式 profile，常规
摘要、Insight 和浏览器内存中的 Context Pack 不依赖它们。

## 使用 Docker Compose 启动

```powershell
docker compose config --quiet
docker compose up -d --build
```

常用端点：

- Memos：<http://localhost:5230>
- AI Service health：<http://localhost:8000/health>
- 完整 Memo index health：<http://localhost:8000/api/ai/index/health>

部署、备份、恢复和升级步骤见 [docs/operations.zh-CN.md](docs/operations.zh-CN.md)。

## 可选 adapters

只在理解其运维成本和数据边界后再启动可选服务：

```powershell
docker compose --profile qdrant up -d qdrant
docker compose --profile ollama up -d ollama
```

- Qdrant 是可选的派生向量存储；完整 Memo 与 chunk 索引使用独立 collection。
- FastEmbed 是可选 CPU embedding provider，可能下载模型数据。
- Ollama 是可选本地模型运行时；Compose 固定到显式上游版本。

provider 配置应通过环境变量注入，不能提交到仓库：

- `AI_PROVIDER=deterministic|openai|deepseek|ollama`
- `OPENAI_API_KEY`、`OPENAI_MODEL`、`OPENAI_BASE_URL`
- `DEEPSEEK_API_KEY`、`DEEPSEEK_MODEL`、`DEEPSEEK_BASE_URL`
- `OLLAMA_BASE_URL`、`OLLAMA_MODEL`
- `AI_EMBEDDING_PROVIDER=deterministic|fastembed`
- `AI_VECTOR_STORE=memory|qdrant`

DeepSeek adapter 仅在显式选择时启用。它通过 OpenAI-compatible chat endpoint 使用固定的
非思考 JSON 模式、1,200 token 输出上限，并且只对 transport error、HTTP 408/429 或
服务端错误最多重试一次。默认模型为 `deepseek-v4-pro`；默认 Provider 仍是 deterministic。
在 Agent 路径使用外部 Provider 前，请先执行
[DeepSeek Provider 合成 smoke](docs/deepseek-provider-smoke.zh-CN.md) 中不会持久化凭据的步骤。

## Webhook 与公开检索边界

默认 Compose 阻止私网 Webhook 目标。`docker-compose.local-webhook.yml` 只适用于受控的
本地 Docker 开发拓扑，即 Memos 必须调用 `ai-service` 的情形；不得用于公网或多用户部署。

受控 `POST /api/ai/v1/chunks/search` 路由已实现，但默认关闭。只有具备真实 trusted gateway、
Memos visibility mapping、受控灰度和已验证回滚路径时，才可设置
`AI_PUBLIC_CHUNK_RETRIEVAL=true`。

## 实验性 Evidence Answer Agent

只读 Evidence Answer 默认关闭。显式配置后，浏览器只访问经过认证的 Memos BFF
`POST /api/ai/agent/answer`；Memos 计算当前调用者可见 Memo 范围，再用短时、purpose
隔离的 HMAC 请求委托给 AI Service。浏览器不会获得委托 secret，也不能自行提交可见范围。

旧 summary、template 与 insight 面板在保留既有 UI opt-in 时也只访问同源 Memos BFF。
`VITE_AI_SERVICE_URL` 的值只作为 build-time UI 门禁保留，不再作为浏览器请求目标。Memos 会认证
调用者、验证 Memo visibility、从自身 store 读取 summary 所需正文，并只投影 allowlist 内的 AI
响应；未显式启用本地 Agent overlay 时，这些路由仍不可用。

Agent 只有 `search_memos` 一个工具，并且只接受已授权的完整 Memo `memo-v1` 证据。
非 deterministic Provider 输出必须先通过严格的 `grounded-answer-result-v1` 契约，citation
再由服务端映射。公开结果只包含受限 answer、服务端 citation 字段和脱敏 trace，不包含原始
Memo、prompt/context、embedding、身份、可见性数据或 secret。

快速本地演示时，可以打开 Evidence Answer 面板并选择一个示例问题；点击示例只会填入表单，
仍需用户显式提交。结果区域会显示终态、每个已完成 Agent step 和受限引用，因此无需外部
Provider 也能直观展示 deterministic 只读 Agent 流程。

生命周期 event/outbox/ledger 当前仍是 dormant 契约和集成证明，尚未接入 Memo CRUD、
dispatcher、worker、自动索引、Qdrant 或默认 Compose。任何运行时 rollout 前应先阅读
[docs/agent-architecture.zh-CN.md](docs/agent-architecture.zh-CN.md) 和
[docs/agent-development-roadmap.zh-CN.md](docs/agent-development-roadmap.zh-CN.md)。

R5 已在默认关闭的单机范围内完成。授权 candidate 选择、当前权威正文 rehydration、internal
authenticated HTTP、Memos-owned lifecycle dispatch、generation-scoped Qdrant state、rebuild
activation 与无 fallback answer selection 已通过 disposable Docker 与认证浏览器验收，覆盖 visibility
隔离、update/delete、restart、rollback 和 cleanup。AI Service 与 Qdrant 仍不向宿主机发布端口。
真实数据、外部 Provider、跨主机 transport 与多实例仍是独立闸门。正文、身份、visibility 与 lifecycle
最终权威仍属于 Memos；详见 [R5 验收记录](docs/r5-acceptance.zh-CN.md)。

## 本地开发与验证

安装 Go、Node.js、pnpm 和 Python，并创建 `ai-service/.venv` 后运行：

```powershell
.\scripts\verify-devmemo.ps1
pnpm --dir web lint
pnpm --dir web test
pnpm --dir web build
```

验证脚本从 `PATH` 发现 Go，并从 `ai-service/.venv` 发现 Python。只有需要覆盖这些位置时，
才设置 `DEVMEMO_GO` 或 `DEVMEMO_PYTHON`。

容器构建安装带哈希锁定的 `ai-service/requirements.lock.txt`。修改
`ai-service/requirements.txt` 后，使用以下命令重新生成：

```powershell
uv pip compile ai-service/requirements.txt --generate-hashes --output-file ai-service/requirements.lock.txt
```

## API 与二次开发边界

接口契约与请求示例见 [docs/api.md](docs/api.md)。应将 Memos 核心修改与 AI 切片分开。
Context Pack 只能消费显式可见 Memo 与已接受 Insight，绝不暴露原始 Memo 内容、Webhook payload、
secret 或 chunk 内容。
