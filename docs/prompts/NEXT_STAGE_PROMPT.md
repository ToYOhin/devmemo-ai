# 下一阶段 Prompt：Phase 9d internal Context Pack preview/copy approval gate

~~~text
继续 H:\DevMemoAI 的 DevMemo AI 项目，不要从零设计。

协作模式：单 Agent。只使用 H:\DevMemoAI 主工作树；不要启动 Terra/Luna，不要同时操作 project4 下的其他 worktree。默认快速推进；只有用户明确要求时才 push。

先读取：
1. docs/handoffs/2026-07-14-single-agent-handoff.md
2. docs/PROJECT_STATUS.md
3. docs/HANDOFF.md 顶部当前阶段
4. docs/roadmap.md 的 Phase 8/9
5. docs/DECISIONS.md 的 ADR-035/036/037/038/039
6. 本文件
7. git status --short --branch 与 git log --oneline -8

当前事实：
- Phase 9a/9b 已完成 AI Inbox、`MemoInsight`、`context-pack-v1` builder/fixture；builder 只接受显式 Memo/accepted insight IDs，输出 bounded Markdown/JSON 与 sources。
- Phase 9c 已完成 proposal-only integration gate：推荐在 Memo 详情页 AI Inbox 内增加 `Copy Context Pack`，默认当前 Memo，跨 Memo 必须显式选择；命令面板/独立页面暂不采用。
- 当前没有收到产品入口批准。没有批准时，不修改运行时 UI/API，只补 ADR/contract tests 并记录等待条件。
- Phase 8 public chunk API implementation gate 仍 pending approval；不实现 `POST /api/ai/v1/chunks/search`，不修改 `/api/ai/chat`、完整 Memo `memo-v1` 或 chunk collection。

若用户本轮明确批准 Memo 详情页 AI Inbox 的内部 preview/copy 入口，本阶段目标才是完成一个最小 UI 垂直切片：
1. 复用 Phase 9b `build_context_pack`，默认使用当前 Memo 和其 accepted insights；跨 Memo 只能通过显式选择加入。
2. 增加 question 输入、`max_chars`/`max_items` 控件、Markdown 主复制、JSON 可选复制、sources 展示和截断提示。
3. 覆盖空态、失败态、窄屏、不可见/删除 Memo、pending/rejected/撤销/过期 insight；不显示 raw content、Webhook payload、secret 或 chunk content。
4. pack 默认只在内存中生成，不写 SQLite，不新增公共 HTTP，不连接 Qdrant，不启动 Agent/worker。

若用户没有明确批准入口：
- 保持 proposal-only，不修改 `web/` 或 AI runtime；只核对 ADR-039、Phase 9b tests 和文档事实。
- 最终报告明确指出“产品入口待批准”，不得把文档评审写成 UI 已实现。

禁止：
- 不实现 public chunk API，不修改 `/api/ai/chat`、CitationResponse、`retrieved_count`、完整 Memo/chunk collection。
- 不修改 Memos server/store/proto/web 核心，不新增 Redis/Celery/Neo4j/LangChain/LlamaIndex/Prometheus/常驻 worker。
- 不把 Context Pack 变成自动 Agent；不读取外部网页、MCP 或未显式选择的 Memo/insight。

验证顺序：
- 无批准且仅文档变更：先运行 `cd ai-service; .\.venv\Scripts\python.exe -m pytest -q tests`，再运行 verify script、Compose config 和 git diff check。
- 有批准并实现 UI：先跑相关 web tests，再运行完整 AI tests、verify script、Compose config、pnpm test、tsc、build、lint、git diff check。

完成条件：
- 没有批准：记录 proposal-only、推荐入口、权限/撤销/复制/失败边界和下一次批准条件，形成清晰 commit，不自动 push。
- 有批准：AI Inbox 内部 preview/copy 有空/失败/窄屏、来源追溯和不暴露原文测试；Phase 9a/9b、公共 chat 和 Phase 8 gate 无回归。
- 更新 docs/PROJECT_STATUS.md、docs/CHANGELOG_AI.md、docs/HANDOFF.md、docs/roadmap.md、docs/api.md、docs/DECISIONS.md 和本 Prompt。
- 最终报告真实测试结果、产品批准状态、截图/手动路径、未验证项、边界和下一步。
~~~
