# DevMemo AI

DevMemo AI 是基于 [Memos](https://github.com/usememos/memos) 的 AI 开发者知识库 MVP，用于记录代码、Bug、解决方案和技术知识，并在保存 Memo 后生成结构化总结。

## 当前 MVP

- 保留 Memos v0.29.1 的 Go 后端和 React/TypeScript 前端基线。
- 以旁路 `ai-service` 提供 FastAPI 总结服务，不重写 Memos 核心。
- 支持 deterministic 本地模式、OpenAI 和 Ollama 配置。
- 通过 Memos 用户 Webhook 接收 Memo 创建/更新事件。
- 将结果保存到 `ai_notes` SQLite 表。

当前仓库的上游前端已经是 React；“保留原有架构”按实际上游基线执行，不额外改造成 Vue。

## 架构

```text
Memos (Go + React)
       | user webhook: memo.created / memo.updated
       v
FastAPI ai-service ---> OpenAI / Ollama
       |
       +-------------> SQLite ai_notes
       +-------------> Qdrant (Phase 3)
```

详细说明见 [docs/architecture.md](docs/architecture.md)。

## Docker 部署

```powershell
Copy-Item ai-service/.env.example .env
docker compose config
docker compose up -d
```

访问：

- Memos: `http://localhost:5230`
- AI Service: `http://localhost:8000/health`
- Qdrant: `http://localhost:6333`

默认 `AI_PROVIDER=deterministic` 不需要密钥，适合先验证链路。使用 OpenAI 或 Ollama 时，在 `.env` 中切换提供商和模型。

在 Memos 中创建一个指向 `http://ai-service:8000/api/integrations/memos/webhook` 的用户 Webhook，保存或编辑 Memo 后即可触发总结。

## 本地开发

```powershell
python -m venv ai-service/.venv
ai-service/.venv/Scripts/python.exe -m pip install -r ai-service/requirements.txt
ai-service/.venv/Scripts/python.exe -m pytest -q ai-service/tests
ai-service/.venv/Scripts/python.exe -m uvicorn main:app --app-dir ai-service --reload --port 8000
```

Memos 上游构建需要 Go、Node.js 和 pnpm；本机当前没有 Go，因此本轮只验证旁路服务和 Compose 配置，未宣称 Memos 源码构建通过。

## API

当前接口与请求示例见 [docs/api.md](docs/api.md)。代码片段 Memo、Bug Report 模板、Embedding/Qdrant RAG、AI 问答和前端 AI 助手区域属于后续阶段。

## 二次开发

- `upstream` remote 指向官方 Memos，升级时先评估上游标签和迁移说明。
- AI 逻辑仅依赖 `ai-service` HTTP 合约，避免业务代码直接依赖具体 LLM SDK。
- 每个功能切片使用独立提交，Memos 原始模块只在明确需要时修改。
- 外部模型密钥只通过环境变量注入，不写入仓库。

路线与目录边界见 [docs/roadmap.md](docs/roadmap.md)、[docs/oss-adoption.md](docs/oss-adoption.md) 和 [docs/structure.md](docs/structure.md)。
