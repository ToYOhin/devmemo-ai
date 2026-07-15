# 下一阶段 Prompt：Phase 9c Context Pack integration gate

~~~text
继续 H:\DevMemoAI 的 DevMemo AI 项目，不要从零设计。

协作模式：单 Agent。只使用 H:\DevMemoAI 主工作树；不要启动 Terra/Luna，不要同时操作 project4 下的其他 worktree。默认快速推进；只有用户明确要求时才 push。

先读取：
1. docs/handoffs/2026-07-14-single-agent-handoff.md
2. docs/PROJECT_STATUS.md
3. docs/HANDOFF.md 顶部当前阶段
4. docs/roadmap.md 的 Phase 8/9
5. docs/DECISIONS.md 的 ADR-035/036/037/038
6. 本文件
7. git status --short --branch 与 git log --oneline -8

当前事实：
- Phase 9a 已完成 AI Inbox/Decision Ledger：`MemoInsight`、SQLite 幂等和版本化 approve/reject、详情页卡片均已落地。
- Phase 9b 已完成 `context-pack-v1` provider-neutral contract/fixture 和纯函数 `build_context_pack`；只消费显式 Memo/accepted insight IDs，输出 bounded Markdown/JSON 与 sources。
- Phase 8 public chunk API implementation gate 仍 pending approval；不实现 `POST /api/ai/v1/chunks/search`，不修改 `/api/ai/chat`、完整 Memo `memo-v1` 或 chunk collection。
- 默认 deterministic + memory；不从 SQLite/Qdrant 自动发现 Context Pack 内容；Memos 核心数据库不改；不启动 Agent、worker、网页搜索或 MCP。

本阶段目标：做 Context Pack 的产品集成闸门，不默认新增公共 HTTP 行为：
1. 评审并记录唯一产品入口：Memo 详情页 AI Inbox 的“复制 Context Pack”、命令面板或独立内部页面；没有明确选择时停留在 ADR/fixture，不猜测 UI。
2. 明确权限与撤销：只有当前用户可见 Memo、accepted insight 才能进入；rejected/pending、删除 Memo、过期版本和撤销后的 insight 必须被排除；原始 content、Webhook payload、secret 和 chunk content 不显示。
3. 明确交互 contract：question 输入、Memo/insight 选择、max_chars/max_items、Markdown/JSON 复制、sources 展示、截断提示、失败/空态/窄屏行为。
4. 若产品入口已获明确批准，只实现一个最小内部 preview/copy 垂直切片；优先复用 Phase 9b builder 和现有 AI Inbox，不新增公共 chunk API，不接 Qdrant，不做跨 Memo 自动发现。
5. 若没有明确产品入口批准，只补 ADR/API proposal 和 contract tests，不修改运行时 UI/API；形成下一次可执行的批准条件。

禁止：
- 不实现 public chunk API，不修改 `/api/ai/chat`、CitationResponse、`retrieved_count`、完整 Memo/chunk collection。
- 不修改 Memos server/store/proto/web 核心，不新增 Redis/Celery/Neo4j/LangChain/LlamaIndex/Prometheus/常驻 worker。
- 不把 Context Pack 变成自动 Agent；不读取外部网页、MCP 或未显式选择的 Memo/insight。

验证顺序：
- 先读 ADR-038 和 Phase 9b tests；若只有文档变更，先跑相关 AI tests。
- 如实现 UI，再先跑相关 web tests，再跑：
  cd ai-service; .\.venv\Scripts\python.exe -m pytest -q tests
  powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\verify-devmemo.ps1
  docker compose config --quiet
  cd web; pnpm test; pnpm exec tsc --noEmit --skipLibCheck; pnpm build; pnpm lint
- git diff --check

完成条件：
- 明确记录 Context Pack 的产品入口、权限、撤销、复制和失败边界；没有批准就保持 proposal-only。
- 若实现内部 UI，必须有空/失败/窄屏、来源追溯和不暴露原文的测试；Phase 9a/9b、公共 chat 和 Phase 8 gate 无回归。
- 更新 docs/PROJECT_STATUS.md、docs/CHANGELOG_AI.md、docs/HANDOFF.md、docs/roadmap.md、docs/api.md、docs/DECISIONS.md 和本 Prompt；形成清晰 commit，不自动 push。
- 最终报告真实测试结果、产品入口决策、截图/手动路径、未验证项、边界和下一阶段批准条件。
~~~
