# DevMemo AI

[English](README.md)

DevMemo AI 是面向个人与小型团队的自托管开发知识库。它以 Memos 为基础，保留原始
Memo、用户身份和可见性权限的事实来源；独立的 FastAPI AI Service 只处理 AI 派生
状态，不建立第二套身份或权限系统。

项目适合将代码片段、故障记录、解决方案与技术决策沉淀为可追溯的开发知识，并在人工
审核后整理为可复制、长度受限的 Context Pack，供 IDE 或后续工具使用。

> **非官方下游项目。** DevMemo AI 不隶属于、未获 Memos 项目认可，也不由其提供
> 支持。上游基线、归属边界和署名见 [UPSTREAM.md](UPSTREAM.md) 与 [NOTICE](NOTICE)。

## 核心能力

- 使用 Memos 保存 Memo、用户与权限；AI 状态不会取代 Memos 的事实来源。
- 为代码片段和缺陷报告生成结构化模板与 AI 派生 insight。
- 在 Memo 详情页审核、接受或拒绝 insight，避免未经审核的 AI 内容进入工作上下文。
- 基于显式可见 Memo 与已接受 insight 生成 `context-pack-v1`；其中只包含安全的标题、
  摘要与来源引用，不包含原始 Memo 内容、Webhook payload、密钥或 chunk 内容。
- 默认采用 deterministic provider 与内存检索，适合低资源、离线优先的本地运行。
- FastEmbed、Qdrant、Ollama、Webhook 索引与公共 chunk retrieval 均为显式 opt-in，
  不作为默认行为。
- 通过 Memos BFF 提供实验性只读 Evidence Answer 入口；它默认关闭，只返回受限回答、
  服务端映射的引用和脱敏执行轨迹。

## 架构与数据边界

```text
Memos（Go + React）
  ├─ Memo 数据、用户与权限：事实来源
  └─ 显式 Webhook 集成
             │
             ▼
FastAPI AI Service
  ├─ 仅存储 AI 派生 SQLite 状态
  ├─ 模板、insight 与可选索引状态
  └─ provider/vector-store adapters
             │
             ▼
Memo 详情页
  ├─ AI insight 审核
  └─ 在浏览器内存中生成并复制 Context Pack
```

完整的目录与运行时边界见 [docs/structure.md](docs/structure.md)，接口契约见
[docs/api.md](docs/api.md)。实验性 Agent 的设计与剩余交付闸门分别见
[docs/agent-architecture.zh-CN.md](docs/agent-architecture.zh-CN.md) 和
[docs/agent-development-roadmap.zh-CN.md](docs/agent-development-roadmap.zh-CN.md)。sanitized evaluation 方法/结果与当前
完成闸门见 [docs/agent-evaluation-benchmark.zh-CN.md](docs/agent-evaluation-benchmark.zh-CN.md) 和
[docs/r6-completion-audit.zh-CN.md](docs/r6-completion-audit.zh-CN.md)。

## 快速开始

前提条件：已安装 Docker Desktop（含 Docker Compose）。

```powershell
git clone https://github.com/ToYOhin/devmemo-ai.git
Set-Location devmemo-ai
docker compose config
docker compose up -d --build
```

启动后访问：

- Memos：<http://localhost:5230>
- AI Service health：<http://localhost:8000/health>

也可直接拉取已公开的稳定镜像：

```powershell
docker pull ghcr.io/toyohin/devmemo-ai:stable
```

稳定镜像提供 `linux/amd64`、`linux/arm64` 与 `linux/arm/v7` manifests。可执行文件
请从 [GitHub Releases](https://github.com/ToYOhin/devmemo-ai/releases) 获取。

## 默认安全与资源策略

默认配置刻意保持轻量且保守：

```text
AI_INDEX_ON_WEBHOOK=false
AI_INDEX_MODE=memo
AI_VECTOR_STORE=memory
AI_PUBLIC_CHUNK_RETRIEVAL=false
AI_AGENT_ENABLED=false
```

- 默认 Compose 不允许私有网络 Webhook 目标。
- 默认堆栈只运行 Memos 与 AI Service，并采用温和的 CPU 预算。
- Qdrant 与 Ollama 只能通过显式 Compose profile 启动。
- 公共 chunk retrieval 保持关闭；它需要真实的 trusted gateway、Memos visibility
  mapping 以及可验证的关闭与回滚路径。
- Evidence Answer Agent 仍是显式启用的实验能力；R6 评审基线已发布于 `v0.2.0`。后续 R7
  切片已增加 frozen AgentRun contract、single-host derived-only SQLite persistence 与 bounded
  runtime，但 persistence/runtime 仍为 dormant，尚未接入 route、worker、产品 BFF 或 UI。
- DeepSeek adapter 只能通过显式配置启用，默认 Provider 仍为 deterministic。真实外部 endpoint
  smoke 只使用 synthetic evidence，不构成真实 Memo 或生产部署就绪证明。

如果在受控的本地 Docker 开发拓扑中，确实需要 Memos Webhook 指向 `ai-service`，请使用
[README_AI.md](README_AI.md) 中记录的 `docker-compose.local-webhook.yml` override。不要
将该 override 用于公网或多用户部署。

## 延伸阅读

[README_AI.zh-CN.md](README_AI.zh-CN.md) 说明 AI Service 配置与可选 adapters；
[docs/operations.zh-CN.md](docs/operations.zh-CN.md) 说明部署、备份、恢复与升级。欢迎按
[CONTRIBUTING.md](CONTRIBUTING.md) 参与贡献。

## 支持、安全与治理

- 使用与部署支持：[SUPPORT.md](SUPPORT.md)。
- 缺陷与功能建议：使用本仓库的 GitHub issue forms。
- 安全报告：遵循 [SECURITY.md](SECURITY.md)，不要在公开 issue 中披露漏洞细节。
- 治理、维护者职责与发布原则：[GOVERNANCE.md](GOVERNANCE.md)。
- 对于本项目未修改的 Memos 行为，请使用上游 [Memos](https://github.com/usememos/memos)
  的支持与 issue 渠道。

## 许可证

DevMemo AI 采用 [MIT License](LICENSE)。项目包含基于 Memos 的下游修改；上游归属与
许可说明保留在 [NOTICE](NOTICE) 与 [UPSTREAM.md](UPSTREAM.md) 中。
