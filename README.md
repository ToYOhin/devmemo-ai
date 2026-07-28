# DevMemo AI

[中文](#中文) · [English](#english)

## 中文

### 概述

DevMemo AI 是面向个人与小型团队的自托管开发知识库。它以 Memos 为基础，保留原始 Memo、用户身份和可见性权限的事实来源；独立的 FastAPI AI Service 只处理 AI 派生状态，不建立第二套身份或权限系统。

项目适合将代码片段、故障记录、解决方案与技术决策沉淀为可追溯的开发知识，并在人工审核后整理为可复制、长度受限的 Context Pack，供 IDE 或后续工具使用。

> **非官方下游项目。** DevMemo AI 不隶属于、未获 Memos 项目认可，也不由其提供支持。上游基线、归属边界和署名见 [UPSTREAM.md](UPSTREAM.md) 与 [NOTICE](NOTICE)。

### 核心能力

- 使用 Memos 保存 Memo、用户与权限；AI 不写入 Memos 原始数据存储。
- 为 Code Snippet 与 Bug Report 生成结构化模板和 AI 派生 insight。
- 在 Memo 详情页审核接受或拒绝 insight，避免未经审核的 AI 内容进入工作上下文。
- 基于显式可见 Memo 与已接受 insight 生成 `context-pack-v1`；只包含安全的 title、summary 和 source refs，不包含原始 Memo 内容、Webhook payload、secret 或 chunk 内容。
- 默认使用 deterministic provider 与内存检索，适合低资源、离线优先的本地运行。
- 将 FastEmbed、Qdrant、Ollama、Webhook 索引与公开 chunk retrieval 保持为显式 opt-in，而不是默认行为。

### 架构与数据边界

```text
Memos (Go + React)
  ├─ Memo data, users, and permissions: source of truth
  └─ explicit Webhook integration
             │
             ▼
FastAPI AI Service
  ├─ AI-derived SQLite state only
  ├─ templates, insights, and optional index state
  └─ provider/vector-store adapters
             │
             ▼
Memo detail view
  ├─ AI insights review
  └─ in-memory Context Pack generation and copy
```

完整目录与运行时边界见 [docs/structure.md](docs/structure.md)，接口契约见 [docs/api.md](docs/api.md)。

### 快速开始

前提条件：Docker Desktop（含 Docker Compose）。

```powershell
git clone https://github.com/ToYOhin/devmemo-ai.git
Set-Location devmemo-ai
docker compose config
docker compose up -d --build
```

启动后访问：

- Memos：<http://localhost:5230>
- AI Service health：<http://localhost:8000/health>

也可以直接拉取已公开的稳定镜像：

```powershell
docker pull ghcr.io/toyohin/devmemo-ai:stable
```

稳定镜像提供 `linux/amd64`、`linux/arm64` 和 `linux/arm/v7` manifest。可执行文件请从 [GitHub Releases](https://github.com/ToYOhin/devmemo-ai/releases) 获取。

### 默认安全与资源策略

默认配置刻意保持轻量且保守：

```text
AI_INDEX_ON_WEBHOOK=false
AI_INDEX_MODE=memo
AI_VECTOR_STORE=memory
AI_PUBLIC_CHUNK_RETRIEVAL=false
```

- 默认 Compose 不允许私网 Webhook 目标。
- 默认仅运行 Memos 与 AI Service，并采用低 CPU 预算。
- Qdrant 与 Ollama 只能通过显式 Compose profile 启动。
- 公共 chunk retrieval 仍保持关闭；它需要真实 trusted gateway、Memos visibility mapping 与可验证的关闭/回滚条件。

若在受控的本机 Docker 开发环境中明确需要 Memos Webhook 指向 `ai-service`，请使用 [README_AI.md](README_AI.md) 中的 `docker-compose.local-webhook.yml` override。不要将该 override 用于公网或多用户部署。

### 进一步了解

部署配置、可选 AI 适配器与本地 Webhook override 见 [README_AI.md](README_AI.md)。欢迎按照 [CONTRIBUTING.md](CONTRIBUTING.md) 参与贡献。

### 支持、安全与治理

- 使用问题和项目支持：见 [SUPPORT.md](SUPPORT.md)。
- 缺陷与功能建议：使用本仓库的 GitHub issue forms。
- 安全问题：遵循 [SECURITY.md](SECURITY.md)，不要在公开 issue 中披露漏洞细节。
- 治理、维护者职责与发布原则：见 [GOVERNANCE.md](GOVERNANCE.md)。
- 对于未被 DevMemo AI 修改的 Memos 行为，请使用上游 [Memos](https://github.com/usememos/memos) 的支持与 issue 渠道。

### 许可证

DevMemo AI 采用 [MIT License](LICENSE)。项目包含基于 Memos 的下游修改；上游归属与许可说明保留在 [NOTICE](NOTICE) 和 [UPSTREAM.md](UPSTREAM.md) 中。

## English

### Overview

DevMemo AI is a self-hosted developer knowledge base for individuals and small
teams. It is built on Memos, which remains the source of truth for original
Memo data, user identities, and visibility permissions. A separate FastAPI AI
Service stores AI-derived state only; it does not introduce a second identity
or authorization system.

Use DevMemo AI to capture code snippets, bug reports, solutions, and technical
decisions as traceable developer knowledge. After human review, accepted
insights can be compiled into bounded, copyable Context Packs for an IDE or a
subsequent tool.

> **Unofficial downstream project.** DevMemo AI is not affiliated with,
> endorsed by, or supported by the Memos project. Read [UPSTREAM.md](UPSTREAM.md)
> and [NOTICE](NOTICE) for the upstream baseline, ownership boundary, and
> attribution.

### Key capabilities

- Keep Memo data, users, and permissions in Memos; AI state never replaces the
  Memos source of truth.
- Generate structured templates and AI-derived insights for Code Snippets and
  Bug Reports.
- Review and accept or reject insights in the Memo detail view before they can
  contribute to a working context.
- Build `context-pack-v1` from explicitly visible Memos and accepted insights.
  It contains only safe titles, summaries, and source references—not raw Memo
  content, Webhook payloads, secrets, or chunk content.
- Run locally with deterministic providers and in-memory retrieval by default,
  with a low-resource, offline-first baseline.
- Keep FastEmbed, Qdrant, Ollama, Webhook indexing, and public chunk retrieval
  as explicit opt-ins rather than default behavior.

### Architecture and data boundaries

```text
Memos (Go + React)
  ├─ Memo data, users, and permissions: source of truth
  └─ explicit Webhook integration
             │
             ▼
FastAPI AI Service
  ├─ AI-derived SQLite state only
  ├─ templates, insights, and optional index state
  └─ provider/vector-store adapters
             │
             ▼
Memo detail view
  ├─ AI insights review
  └─ in-memory Context Pack generation and copy
```

See [docs/structure.md](docs/structure.md) for the repository and runtime
boundaries, and [docs/api.md](docs/api.md) for API contracts.

### Quick start

Prerequisite: Docker Desktop with Docker Compose.

```powershell
git clone https://github.com/ToYOhin/devmemo-ai.git
Set-Location devmemo-ai
docker compose config
docker compose up -d --build
```

After startup:

- Memos: <http://localhost:5230>
- AI Service health: <http://localhost:8000/health>

The published stable image is also available directly:

```powershell
docker pull ghcr.io/toyohin/devmemo-ai:stable
```

The stable image publishes `linux/amd64`, `linux/arm64`, and `linux/arm/v7`
manifests. Download native executables from [GitHub
Releases](https://github.com/ToYOhin/devmemo-ai/releases).

### Default security and resource posture

The default configuration is intentionally lightweight and conservative:

```text
AI_INDEX_ON_WEBHOOK=false
AI_INDEX_MODE=memo
AI_VECTOR_STORE=memory
AI_PUBLIC_CHUNK_RETRIEVAL=false
```

- Default Compose does not allow private-network Webhook targets.
- The default stack runs only Memos and the AI Service with modest CPU budgets.
- Qdrant and Ollama require explicit Compose profiles.
- Public chunk retrieval remains disabled. It requires a real trusted gateway,
  Memos visibility mapping, and a verified disable-and-rollback path.

For a controlled local Docker development topology where a Memos Webhook must
target `ai-service`, use the `docker-compose.local-webhook.yml` override
documented in [README_AI.md](README_AI.md). Do not use that override for a
public or multi-user deployment.

### Further reading

[README_AI.md](README_AI.md) documents deployment configuration, optional AI
adapters, and the local Webhook override. Contributions are welcome through
[CONTRIBUTING.md](CONTRIBUTING.md).

### Support, security, and governance

- Setup and usage support: [SUPPORT.md](SUPPORT.md).
- Bugs and feature requests: use this repository's GitHub issue forms.
- Security reports: follow [SECURITY.md](SECURITY.md); do not disclose
  vulnerabilities in public issues.
- Governance, maintainer responsibilities, and release expectations:
  [GOVERNANCE.md](GOVERNANCE.md).
- For Memos behavior unchanged by this project, use the upstream
  [Memos](https://github.com/usememos/memos) support and issue channels.

### License

DevMemo AI is distributed under the [MIT License](LICENSE). It contains
downstream changes based on Memos; upstream attribution and licensing details
are preserved in [NOTICE](NOTICE) and [UPSTREAM.md](UPSTREAM.md).
