# 下一阶段 Prompt：Phase 10 gateway rollout evidence + DevMemory feedback

~~~text
Phase 10 next action is route B only. The participant has authorized creation of one non-sensitive test Bug Report and one Insight accept or reject action. Delete/revoke remains a separate action-time confirmation; do not perform either until it is explicitly granted. First preserve the verified low-CPU baseline in `docs/handoffs/2026-07-20-low-cpu-baseline.md`: default Compose starts Memos (`0.75` CPU) and AI Service (`0.25` CPU) only; Qdrant/Ollama require explicit profiles, and no high-load Web commands run in parallel. Then follow `docs/handoffs/2026-07-20-devmemory-real-feedback-plan.md` exactly through the available `Capture -> Insight -> Review -> Context Pack` path. Record safe source/status evidence, bounded-pack behavior, copy outcome, and four concise feedback answers. If login, an Insight, or consistent visible state is missing, stop and document the blocker; do not seed SQLite, bypass Memos authentication, or claim a pass. The local `python -m scripts.public_chunk_gateway_contract_smoke` is already complete and must not be repeated as rollout proof. Keep `AI_PUBLIC_CHUNK_RETRIEVAL=false`.

继续 H:\DevMemoAI 的 DevMemo AI 项目，不要从零设计。

协作模式：单 Agent。只使用 H:\DevMemoAI 主工作树；不要启动 Terra/Luna，也不要并行修改 project4 下的其他 worktree。一次完成一个最小、可验证的垂直切片；只有用户明确要求时才 push。

先读取：
1. docs/handoffs/2026-07-20-devmemory-rollout-handoff.md
2. docs/PROJECT_STATUS.md 顶部
3. docs/HANDOFF.md 顶部
4. docs/roadmap.md 的 Phase 8/9/10
5. docs/DECISIONS.md 的 ADR-036/041/042/043/044
6. 本文件
7. git status --short --branch 与 git log --oneline -8

当前事实：
- Phase 9a-9f 已完成 AI Inbox、Context Pack contract/UI、显式跨 Memo 选择、删除/撤销联动、Python/Web golden parity 和 SQLite 只读生命周期报告。
- 真实 Chrome/Windows 系统剪贴板验收已通过 Markdown/JSON 两种复制，且修复了复制后 React error boundary。
- Phase 8 public-chunk-v1 已实现，但 `AI_PUBLIC_CHUNK_RETRIEVAL=false` 是默认且必须保持；只有可信网关可使用 `AI_PUBLIC_CHUNK_SECRET` 对精确 raw body 签名并提供唯一 `visible_memo_ids`。
- Memos Go 仍是原始 Memo/权限事实源。AI Service 不复制用户权限系统；公共 `/api/ai/chat` 继续完整 Memo citation 语义。

本阶段唯一目标：执行 route B 的一个真实参与者反馈路径；不推进 gateway rollout。用一个真实、非敏感 Bug Report 跑可用的 `Capture -> Insight -> Review -> Context Pack`，记录安全来源、accept/reject、经同意的删除/撤销、预算截断、复制和人工反馈。所有步骤与停止条件以 `docs/handoffs/2026-07-20-devmemory-real-feedback-plan.md` 为准。

禁止：
- 不默认开启 public chunk，不修改 `/api/ai/chat`、CitationResponse、memo-v1、chunk collection 或 Memos server/store/proto 核心。
- 不引入 Redis、Celery、Neo4j、LangChain、LlamaIndex、Prometheus、常驻 worker、外部网页、MCP 或通用聊天 UI。
- 不返回 raw content、Webhook payload、secret 或 chunk content；不删除 collection/volume。

验证：先记录健康/只读 lifecycle baseline 和相关定向测试；状态变更后复核可见 UI 与 Context Pack。仅当运行时代码改动时再按改动范围运行完整 AI/Web 门禁；遵守当前用户的 CPU 节制要求，不并行运行高负载 Web build/test。最后运行 `git diff --check`。若无真实参与者反馈环境，保留不完整 evidence，明确写为未验证，不能把离线测试写成产品反馈或 rollout pass。

完成后更新 PROJECT_STATUS、CHANGELOG_AI、HANDOFF、roadmap、api、structure、DECISIONS、handoff 和本 Prompt；形成独立 commit，不自动 push。
~~~
