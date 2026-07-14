# 下一阶段 Prompt：Phase 9 DevMemory Loop

~~~text
继续 H:\DevMemoAI 的 DevMemo AI 项目，不要从零设计。

协作模式：单 Agent。只使用 H:\DevMemoAI 主工作树；不要启动 Terra/Luna，不要同时操作 project4 下的其他 worktree。默认快速推进；只有用户明确要求时才 push。

先读取：
1. docs/handoffs/2026-07-14-single-agent-handoff.md
2. docs/PROJECT_STATUS.md
3. docs/HANDOFF.md 顶部当前阶段
4. docs/roadmap.md 的 Phase 8/9
5. docs/DECISIONS.md 的 ADR-034/035/036
6. 本文件
7. git status --short --branch 与 git log --oneline -8

产品方向：
- DevMemo AI 不继续堆叠通用 RAG 功能，下一步做“DevMemory Loop”：捕获 Memo → 提取开发事实/决策/行动 → 人工确认 → 时间线/关联 → 生成可复制的开发上下文包。
- 这是一条区别于 Memos 快速记录、Khoj 通用个人 AI、AnythingLLM 工作区 RAG 的开发者记忆路线；重点是可解释、可撤销、可追溯，而不是自动替用户修改原文。

当前事实：
- Phase 5f/5g 已完成独立 Qdrant chunk collection、内部 ChunkRetrievalService、真实 Qdrant persistence smoke。
- Phase 6/7 已决定公共 chat 保持完整 Memo Citation，并形成未实现的 public chunk API proposal。
- Phase 8 public chunk API implementation gate 仍 pending approval；没有明确批准时，不实现 `POST /api/ai/v1/chunks/search`，不新增运行时 flag，不改变公共 chat。
- 默认 deterministic + memory；FastEmbed/Qdrant 只在 adapters；AI 数据存 AI Service 自有 SQLite；Memos 核心数据库不改。

本阶段目标：完成一个可回滚的“AI Inbox / Decision Ledger”垂直切片，不实现公共 chunk API：
1. 先定义 provider-neutral `MemoInsight` contract：`insight_id`、`memo_id`、`insight_type`（fact/decision/action/bug）、`title`、`summary`、`confidence`、`status`（pending/accepted/rejected）、`source_refs`、`created_at`、`updated_at`。原始 content 只作为服务端派生输入，不进入公共 citation。
2. 用现有 parser、SummaryResponse 和 deterministic provider 实现最小提取器：Code Snippet 产生技术事实/行动候选，Bug Report 产生问题/根因/修复候选，plain Memo 只产生显式可判断的事实候选；不做自由发挥式知识图谱。
3. 在 AI Service 自有 SQLite 增加兼容表 `memo_insights`，支持同一 Memo/同一 insight 类型的幂等 upsert、人工 approve/reject 和审计时间；不写回 Memos 原文，不启动后台 worker。
4. 增加内部 HTTP contract：只允许本地产品边界使用的 `GET /api/ai/insights/{memo_id}`、`POST /api/ai/insights/preview` 和显式状态变更 endpoint。preview 不落库；approve/reject 必须带 insight_id 和当前版本，拒绝过期更新。
5. 在现有 Memo 详情页增加一个轻量 AI Inbox 卡片：展示候选类型、置信度、来源 Memo、状态和 approve/reject；失败、空状态、窄屏必须可用。不要增加聊天 UI，不要暴露 chunk content，不要改公共 chat citation。
6. 预留下一切片的 Context Pack，但本阶段只写 contract/fixture：输入 question + 已确认 insight/memo IDs，输出带来源的 bounded Markdown/JSON；不要实现跨 Memo 自动 agent、外部网页或 MCP。

创新验收标准：
- 用户可以把“一个 Bug Report”从原始笔记变成可审核的 Decision Ledger 卡片，而不是只得到一次性摘要。
- 同一条知识可以被 reject/accept，状态可追踪；重新生成不会产生不可控重复。
- 任何 AI 派生卡片都能回到 source_refs；删除/撤销只影响 AI 派生数据，不破坏原始 Memo。
- deterministic + memory 离线路径完成全流程；切换 OpenAI/Ollama 不改变 contract。

禁止：
- 不实现 public chunk API，不修改 `/api/ai/chat`、CitationResponse、`retrieved_count`、完整 Memo `memo-v1` 或 chunk collection。
- 不修改 Memos server/store/proto/web 核心；优先只改 ai-service、`web/src/features/ai` 和文档。
- 不引入 Neo4j、Redis、Celery、LangChain、LlamaIndex、Prometheus、新默认依赖或常驻 worker；不执行 docker compose down -v，不删除 collection/volume。
- 不把第三方项目源码复制进仓库；Khoj/Logseq 的 AGPL、Outline 的 BSL、AFFiNE 的许可证边界必须留在参考层。

验证顺序：
- 先写 contract fixture 和 AI Service tests，再实现 SQLite/route，再接入 UI。
- cd ai-service; .\.venv\Scripts\python.exe -m pytest -q tests
- powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\verify-devmemo.ps1
- docker compose config --quiet
- cd web; pnpm test; pnpm exec tsc --noEmit --skipLibCheck; pnpm build; pnpm lint
- 如涉及 Qdrant/lifecycle，运行 deterministic chunk smoke；默认路径仍必须 deterministic + memory。
- git diff --check

完成条件：
- AI Inbox/Decision Ledger contract、数据库幂等、过期状态保护、approve/reject 和详情页卡片均有测试。
- 公共 chat、完整 Memo collection、默认配置和 Phase 8 pending approval 事实没有回归。
- 更新 docs/PROJECT_STATUS.md、docs/CHANGELOG_AI.md、docs/HANDOFF.md、docs/roadmap.md；形成清晰 commit，不自动 push。
- 最终报告真实测试结果、截图/手动路径、未验证项、边界和下一个 Context Pack Prompt。
~~~
