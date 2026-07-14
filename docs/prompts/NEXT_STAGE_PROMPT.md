# 下一阶段 Prompt：Phase 9b Context Pack contract

~~~text
继续 H:\DevMemoAI 的 DevMemo AI 项目，不要从零设计。

协作模式：单 Agent。只使用 H:\DevMemoAI 主工作树；不要启动 Terra/Luna，不要同时操作 project4 下的其他 worktree。默认快速推进；只有用户明确要求时才 push。

先读取：
1. docs/handoffs/2026-07-14-single-agent-handoff.md
2. docs/PROJECT_STATUS.md
3. docs/HANDOFF.md 顶部当前阶段
4. docs/roadmap.md 的 Phase 8/9
5. docs/DECISIONS.md 的 ADR-035/036/037
6. 本文件
7. git status --short --branch 与 git log --oneline -8

当前事实：
- Phase 9a 已完成：`MemoInsight` contract、deterministic 候选提取、AI SQLite 幂等表、preview/查询/版本化 approve/reject API 和 Memo 详情页 AI Inbox 均已落地。
- `MemoInsight` 只允许 `fact/decision/action/bug`；状态为 `pending/accepted/rejected`；稳定身份为 `insight_id` 与 `(memo_id, insight_type)`，过期状态写入返回 409。
- Phase 8 public chunk API implementation gate 仍 pending approval；不实现 `POST /api/ai/v1/chunks/search`，不修改 `/api/ai/chat`、完整 Memo `memo-v1` 或 chunk collection。
- 默认 deterministic + memory；AI 数据只在 AI Service 自有 SQLite；Memos 核心数据库不改；原始 content 不进入公共 citation 或 Context Pack 的来源字段。

本阶段目标：只完成 Context Pack 的 provider-neutral contract/fixture 和纯函数 builder，不接入公共 HTTP、Agent 或外部数据源：
1. 定义 `ContextPackRequest`：`question`、显式 `memo_ids`、显式已确认 `insight_ids`、`max_chars`/`max_items`；拒绝未知 ID、rejected/pending insight 和超出预算的隐式扩展。
2. 定义 `ContextPackResponse`：版本、question、bounded Markdown/JSON、按 Memo/insight 可追溯的 `sources`、截断原因和确定性排序；不带原始 Webhook、secret、chunk content 或未确认知识。
3. 实现纯函数 `build_context_pack`/fixture：只消费传入的已确认 insight 与安全的 Memo 标题/摘要；同一来源去重，按 confidence/updated_at/稳定 ID 确定性排序；超预算显式截断而不是悄悄放宽。
4. 增加 contract tests：空输入、未知 ID、pending/rejected、同 Memo 去重、字符预算、稳定输出、JSON/Markdown 一致性和 source_refs 可追溯。
5. 不新增生产 HTTP 路由；如需要，提供内部样例 CLI/fixture 但默认不启用，不连接公共 chat，不读取 Qdrant。

创新边界：Context Pack 是“可复制的开发上下文包”而不是自动 Agent。它必须解释为什么每条记忆进入包、可以回到原 Memo/insight、可被用户撤销；本阶段不做跨 Memo 自动发现、网页搜索、MCP、图数据库或后台 worker。

禁止：
- 不实现 public chunk API，不修改 `/api/ai/chat`、CitationResponse、`retrieved_count`、完整 Memo collection 或 chunk collection。
- 不修改 Memos server/store/proto/web 核心；优先只改 ai-service domain/services/tests 和 docs。
- 不把 pending/rejected insight 混入 pack，不把原始 content 当作公共来源，不加入新默认依赖。

验证顺序：
- 先写 contract fixture/tests，再实现纯函数 builder。
- cd ai-service; .\.venv\Scripts\python.exe -m pytest -q tests
- powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\verify-devmemo.ps1
- docker compose config --quiet
- git diff --check

完成条件：
- Context Pack contract/fixture、预算/排序/拒绝规则和 source traceability 有测试。
- Phase 9a AI Inbox、公共 chat、默认配置、Phase 8 pending approval 事实无回归。
- 更新 docs/PROJECT_STATUS.md、docs/CHANGELOG_AI.md、docs/HANDOFF.md、docs/roadmap.md、docs/api.md 和本 Prompt；形成清晰 commit，不自动 push。
- 最终报告真实测试结果、Context Pack 示例、未验证项、边界和下一步产品决策。
~~~
