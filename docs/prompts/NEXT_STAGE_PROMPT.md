# 下一阶段 Prompt：Phase 9e Context Pack product acceptance

~~~text
继续 H:\DevMemoAI 的 DevMemo AI 项目，不要从零设计。

协作模式：单 Agent。只使用 H:\DevMemoAI 主工作树；不要启动 Terra/Luna，不要同时操作 project4 下的其他 worktree。默认快速推进；只有用户明确要求时才 push。

先读取：
1. docs/handoffs/2026-07-14-single-agent-handoff.md
2. docs/PROJECT_STATUS.md
3. docs/HANDOFF.md 顶部当前阶段
4. docs/roadmap.md 的 Phase 8/9
5. docs/DECISIONS.md 的 ADR-035/038/039/040
6. 本文件
7. git status --short --branch 与 git log --oneline -8

当前事实：
- Phase 9a/9b/9c/9d 已完成：AI Inbox、MemoInsight、`context-pack-v1` Python builder、Memo 详情页内存 preview/copy UI 均已落地。
- `AiMemoContextPack` 默认当前 Memo + accepted insights，支持显式来源取消、question、预算、Markdown/JSON copy、sources、截断、empty/failure/窄屏状态。
- Web `contextPack.ts` 镜像 Python builder contract；尚未共享 fixture。当前不提供跨 Memo picker，因此没有隐式扩展；任何未来跨 Memo 必须显式选择并校验当前用户可见性。
- pack 不写 SQLite，不新增 HTTP，不连接 Qdrant，不启动 Agent/worker；公共 `/api/ai/chat`、完整 Memo/chunk collection 和默认 deterministic + memory 不变。
- Phase 8 public chunk API implementation gate 仍 pending approval；不实现 `POST /api/ai/v1/chunks/search`。

本阶段目标：只做 Context Pack 的产品验收与边界收敛，不扩大为公共 API：
1. 用共享或等价 fixture 对齐 Python/Web 的排序、预算、source 去重和脱敏语义；发现漂移先修 contract/test，不自动改公共接口。
2. 评审是否批准跨 Memo 显式选择；若没有明确产品/权限批准，保持当前仅当前 Memo UI，不读取 Memo 列表、不自动发现来源。
3. 明确 Memo 删除/不可见、insight revoke/stale version 与 AI Service SQLite 派生状态的清理/拒绝策略；优先 contract/测试和文档，不能破坏原始 Memo。
4. 若产品批准且能证明当前用户可见性，只实现一个显式、可回滚的跨 Memo选择切片；否则 proposal-only。

禁止：
- 不实现 public chunk API，不修改 `/api/ai/chat`、CitationResponse、`retrieved_count`、memo-v1 或 chunk collection。
- 不修改 Memos server/store/proto 核心；不引入 Redis/Celery/Neo4j/LangChain/LlamaIndex/Prometheus/常驻 worker。
- 不把 raw content、Webhook payload、secret 或 chunk content 放入 Context Pack；不连接外部网页、MCP、Agent 或 Qdrant。

验证顺序：
- 先跑 `cd web; pnpm vitest run tests/ai-context-pack.test.ts tests/ai-context-pack.test.tsx`。
- 如改动 fixture/contract，再跑 `cd ai-service; .\.venv\Scripts\python.exe -m pytest -q tests`。
- `powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\verify-devmemo.ps1`
- `docker compose config --quiet`
- `cd web; pnpm test; pnpm exec tsc --noEmit --skipLibCheck; pnpm build; pnpm lint`
- `git diff --check`

完成条件：
- Python/Web contract 事实一致，或明确记录为何继续等待产品/权限批准。
- 删除/不可见/撤销/过期边界有测试或真实未验证项；公共 chat、默认配置和 Phase 8 gate 无回归。
- 更新 PROJECT_STATUS、CHANGELOG_AI、HANDOFF、roadmap、api、structure、DECISIONS、handoff 和本 Prompt；形成清晰 commit，不自动 push。
- 最终报告真实测试、截图/手动路径、未验证项、当前项目问题和下一阶段产品决策。
~~~
