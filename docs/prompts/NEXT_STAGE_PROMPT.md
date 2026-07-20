# 下一阶段 Prompt：Phase 8 public-chunk-v1 controlled rollout + Phase 9f evidence

> 2026-07-20 update: shared Context Pack golden output and lifecycle-report CLI are complete (AI 179; Web 149). Phase 8 approval has produced a disabled-by-default public `public-chunk-v1` route with signed gateway visibility scope, dedupe, redaction, and flag rollback (AI full 186). Continue only gateway integration/canary evidence and remaining Phase 9f manual feedback; do not repeat the implemented route or golden/CLI work.

~~~text
继续 H:\DevMemoAI 的 DevMemo AI 项目，不要从零设计。

协作模式：单 Agent。只使用 H:\DevMemoAI 主工作树；不要启动 Terra/Luna，不要同时操作 project4 下的其他 worktree。默认快速推进；只有用户明确要求时才 push。

先读取：
1. docs/handoffs/2026-07-14-single-agent-handoff.md
2. docs/PROJECT_STATUS.md
3. docs/HANDOFF.md 顶部当前阶段
4. docs/roadmap.md 的 Phase 8/9
5. docs/DECISIONS.md 的 ADR-034/035/043
6. 本文件
7. git status --short --branch 与 git log --oneline -8

当前事实：
- Phase 9e 已完成：根目录 `contracts/context-pack-v1.json` 被 Python/Web 测试共同读取；Memo 详情页 Context Pack 从 Memos 当前用户可见列表提供显式跨 Memo 选择，默认仍只选当前 Memo。
- 只有 accepted insight 进入 pack；pending/rejected/revoke/stale 不进入。额外 Memo insight 查询失败会提示并排除；Memos deleted Webhook 会清理 AI Service 自有 `ai_notes`、`memo_templates`、`memo_insights`。
- Context Pack 仍仅在浏览器内存生成，不新增公共 HTTP、不写 Context Pack SQLite、不连接 Qdrant、不启动 Agent/worker；公共 `/api/ai/chat`、完整 Memo/chunk collection 和默认 deterministic + memory 不变。
- Phase 8 `POST /api/ai/v1/chunks/search` 已实现为 `public-chunk-v1`，但默认 `AI_PUBLIC_CHUNK_RETRIEVAL=false`。启用前必须由受信任网关配置 `AI_PUBLIC_CHUNK_SECRET`、签名 raw body，并在签名 body 中提供当前用户可见且唯一的 `visible_memo_ids`。

本阶段目标：完成受控 public-chunk-v1 rollout evidence，并继续验证 DevMemory Loop 的可解释生命周期：
1. 在真实网关/受控部署前验证 HMAC raw-body 签名、`visible_memo_ids` 权限范围、401/422/503、同 Memo 去重、metadata 脱敏和 flag rollback；不得用客户端未签名范围替代网关授权。
2. 为 Memo 删除、不可见 Memo、insight reject/revoke、stale version 和重复 webhook 保留最小可观察证据；只允许 AI 派生状态被清理，不删除原始 Memo。
3. 收集 Context Pack 的真实 UI 反馈：当前 Memo 默认路径、显式跨 Memo 选择、来源追溯、复制、截断、空态/失败态/窄屏；真实 Chrome clipboard 仅在浏览器连接可用时验收。

禁止：
- 不修改 `/api/ai/chat`、CitationResponse、其 `retrieved_count`、memo-v1 或 chunk collection；public chunk 只能使用已实现的 `public-chunk-v1`，不得扩展字段、放宽 HMAC/visible scope 或默认开启。
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
- 公共 chat、默认关闭配置、public-chunk-v1 鉴权/脱敏/去重/回滚和原始 Memo 数据无回归。
- 更新 PROJECT_STATUS、CHANGELOG_AI、HANDOFF、roadmap、api、structure、DECISIONS、handoff 和本 Prompt；形成清晰 commit，不自动 push。
- 最终报告真实测试、截图/手动路径、未验证项、当前项目问题和下一阶段产品决策。
~~~
