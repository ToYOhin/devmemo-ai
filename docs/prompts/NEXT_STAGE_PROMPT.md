# 下一阶段 Prompt：Phase 10 gateway rollout evidence + DevMemory feedback

~~~text
Phase 10 next action is route B only. The existing non-sensitive test Bug Report has already completed local Capture -> persisted Insight -> one authorized accepted Review through an authenticated Memos UI update and a current-user private Docker-network webhook. A fresh tab in the same authenticated Chrome profile confirms the accepted Insight, `max_chars=64` truncation, and real Chrome/Windows system-clipboard copy for both Markdown and JSON; the JSON parses as `context-pack-v1`, and safe checks found no raw payload or secret markers. The earlier host-side `memo_insights=0` observation was a wrong SQLite path; live Compose evidence must use `docker compose exec -T ai-service python -m scripts.devmemory_lifecycle_report`. Do not create another Memo, seed SQLite, bypass Memos authentication, repeat an Insight status transition, or rerun copy merely as a substitute for feedback. With a real participant, collect only four concise feedback answers about source clarity, review confidence, budget usefulness, and copy expectation; do not invent answers or delete/revoke to manufacture evidence. Keep `AI_PUBLIC_CHUNK_RETRIEVAL=false`.

继续 H:\DevMemoAI 的 DevMemo AI 项目，不要从零设计。

协作模式：单 Agent。只使用 H:\DevMemoAI 主工作树；不要启动 Terra/Luna，也不要并行修改 project4 下的其他 worktree。一次完成一个最小、可验证的垂直切片；只有用户明确要求时才 push。

先读取：
1. docs/handoffs/2026-07-20-devmemory-rollout-handoff.md
2. docs/PROJECT_STATUS.md 顶部
3. docs/HANDOFF.md 顶部
4. docs/roadmap.md 的 Phase 8/9/10
5. docs/DECISIONS.md 的 ADR-036/041/042/043/044/048
6. 本文件
7. git status --short --branch 与 git log --oneline -8

当前事实：
- Phase 9a-9f 已完成 AI Inbox、Context Pack contract/UI、显式跨 Memo 选择、删除/撤销联动、Python/Web golden parity 和 SQLite 只读生命周期报告。
- 真实 Chrome/Windows 系统剪贴板验收已通过 Markdown/JSON 两种复制，且修复了复制后 React error boundary。
- Phase 8 public-chunk-v1 已实现，但 `AI_PUBLIC_CHUNK_RETRIEVAL=false` 是默认且必须保持；只有可信网关可使用 `AI_PUBLIC_CHUNK_SECRET` 对精确 raw body 签名并提供唯一 `visible_memo_ids`。
- Memos Go 仍是原始 Memo/权限事实源。AI Service 不复制用户权限系统；公共 `/api/ai/chat` 继续完整 Memo citation 语义。

本阶段唯一目标：只完成 route B 剩余的真实参与者反馈，不推进 gateway rollout。现有非敏感 Bug Report 已有 Capture、Insight、一次 accepted Review、Context Pack 预算截断和 Chrome/Windows Markdown/JSON 复制技术证据；在稳定登录态中只记录四项人工反馈的简短安全转述。不要创建第二条 Memo，不要重复 accept/reject，也不要为了收集证据执行删除/撤销。所有步骤与停止条件以 `docs/handoffs/2026-07-20-devmemory-real-feedback-plan.md` 和最新浏览器 evidence 为准。

禁止：
- 不默认开启 public chunk，不修改 `/api/ai/chat`、CitationResponse、memo-v1、chunk collection 或 Memos server/store/proto 核心。
- 不引入 Redis、Celery、Neo4j、LangChain、LlamaIndex、Prometheus、常驻 worker、外部网页、MCP 或通用聊天 UI。
- 不返回 raw content、Webhook payload、secret 或 chunk content；不删除 collection/volume。

验证：先记录健康/只读 lifecycle baseline 和相关定向测试；状态变更后复核可见 UI 与 Context Pack。仅当运行时代码改动时再按改动范围运行完整 AI/Web 门禁；遵守当前用户的 CPU 节制要求，不并行运行高负载 Web build/test。最后运行 `git diff --check`。若无真实参与者反馈环境，保留不完整 evidence，明确写为未验证，不能把离线测试写成产品反馈或 rollout pass。

完成后更新 PROJECT_STATUS、CHANGELOG_AI、HANDOFF、roadmap、api、structure、DECISIONS、handoff 和本 Prompt；形成独立 commit，不自动 push。
~~~
