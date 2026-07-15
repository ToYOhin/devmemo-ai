# 下一阶段 Prompt：Phase 9f Context Pack lifecycle observation

~~~text
继续 H:\DevMemoAI 的 DevMemo AI 项目，不要从零设计。

协作模式：单 Agent。只使用 H:\DevMemoAI 主工作树；不要启动 Terra/Luna，不要同时操作 project4 下的其他 worktree。默认快速推进；只有用户明确要求时才 push。

先读取：
1. docs/handoffs/2026-07-14-single-agent-handoff.md
2. docs/PROJECT_STATUS.md
3. docs/HANDOFF.md 顶部当前阶段
4. docs/roadmap.md 的 Phase 8/9
5. docs/DECISIONS.md 的 ADR-040/041
6. 本文件
7. git status --short --branch 与 git log --oneline -8

当前事实：
- Phase 9e 已完成：根目录 `contracts/context-pack-v1.json` 被 Python/Web 测试共同读取；Memo 详情页 Context Pack 从 Memos 当前用户可见列表提供显式跨 Memo 选择，默认仍只选当前 Memo。
- 只有 accepted insight 进入 pack；pending/rejected/revoke/stale 不进入。额外 Memo insight 查询失败会提示并排除；Memos deleted Webhook 会清理 AI Service 自有 `ai_notes`、`memo_templates`、`memo_insights`。
- Context Pack 仍仅在浏览器内存生成，不新增公共 HTTP、不写 Context Pack SQLite、不连接 Qdrant、不启动 Agent/worker；公共 `/api/ai/chat`、完整 Memo/chunk collection 和默认 deterministic + memory 不变。
- Phase 8 public chunk API implementation gate 仍 pending approval；不实现 `POST /api/ai/v1/chunks/search`。

本阶段目标：验证 DevMemory Loop 的可解释生命周期，不扩大公共 API：
1. 增加跨语言 golden output 或等价 contract assertion，证明 Python/Web 的排序、预算、source dedupe、状态过滤和脱敏一致；如出现漂移先修 contract/test。
2. 为 Memo 删除、不可见 Memo、insight reject/revoke、stale version 和重复 webhook 增加最小可观察证据；只允许 AI 派生状态被清理，不删除原始 Memo。
3. 评估最小本地观测方式（测试/开发诊断即可），不得引入 Prometheus、常驻 worker、外部追踪服务或公共 telemetry API。
4. 收集 Context Pack 的真实 UI 反馈：当前 Memo 默认路径、显式跨 Memo 选择、来源追溯、复制、截断、空态/失败态/窄屏；若没有新产品需求，不继续扩大到命令面板、自动发现或 Agent。

禁止：
- 不实现 public chunk API，不修改 `/api/ai/chat`、CitationResponse、`retrieved_count`、memo-v1 或 chunk collection。
- 不修改 Memos server/store/proto 核心；不引入 Redis/Celery/Neo4j/LangChain/LlamaIndex/Prometheus/常驻 worker。
- 不把 raw content、Webhook payload、secret 或 chunk content 放入 Context Pack；不连接外部网页、MCP、Agent 或 Qdrant。

验证顺序：
- `cd ai-service; .\.venv\Scripts\python.exe -m pytest -q tests`
- `powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\verify-devmemo.ps1`
- `docker compose config --quiet`
- `cd web; pnpm test; pnpm exec tsc --noEmit --skipLibCheck; pnpm build; pnpm lint`
- 如改动 Qdrant/lifecycle，再运行 deterministic chunk smoke；默认路径仍必须 deterministic + memory。
- `git diff --check`

完成条件：
- Python/Web contract、删除/撤销/过期/权限边界有真实测试或明确未验证项。
- 公共 chat、默认配置、Phase 8 gate 和原始 Memo 数据无回归。
- 更新 PROJECT_STATUS、CHANGELOG_AI、HANDOFF、roadmap、api、structure、DECISIONS、handoff 和本 Prompt；形成清晰 commit，不自动 push。
- 最终报告真实测试、截图/手动路径、未验证项、当前项目问题和下一阶段产品决策。
~~~
