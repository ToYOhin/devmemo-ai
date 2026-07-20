# 新窗口启动 Prompt

~~~text
继续 H:\DevMemoAI 的 DevMemo AI 项目，不要从零设计。

协作模式：单 Agent。只使用 H:\DevMemoAI 主工作树；不要启动 Terra/Luna，也不要同时操作 project4 下的其他 worktree。默认快速推进，但一次只完成一个可验证垂直切片；只有用户明确要求时才 push。

先读取最小核心上下文：
1. docs/handoffs/2026-07-20-devmemory-rollout-handoff.md
2. docs/PROJECT_STATUS.md 顶部
3. docs/HANDOFF.md 顶部
4. docs/prompts/NEXT_STAGE_PROMPT.md
5. git status --short --branch
6. git log --oneline -8

只按当前任务用 rg -n 定向读取 docs/roadmap.md、docs/structure.md、docs/DECISIONS.md、docs/api.md、docs/oss-adoption.md；不要一次加载全部历史 Phase 文档。

当前事实：
- Memos Go server/store/proto 是原始 Memo 与权限事实源；AI Service 只存 AI 派生 SQLite 状态；Web 的 AiMemoInsights/AiMemoContextPack 是当前产品入口。
- 默认保持 deterministic + memory、AI_INDEX_ON_WEBHOOK=false、AI_INDEX_MODE=memo、AI_VECTOR_STORE=memory。FastEmbed/Qdrant 只属于 adapters。
- Context Pack 是浏览器内存中的 provider-neutral 输出：只使用显式 Memo、accepted insights 与安全 title/summary/source_refs；不暴露 raw content、Webhook payload、secret 或 chunk content，不写 SQLite、不连 Qdrant、不启动 Agent/worker。
- Phase 9f 已完成 Python/Web golden parity、只读生命周期诊断、真实 Chrome/Windows 系统剪贴板验收。Markdown 与 JSON 复制均已通过，复制后无 React error boundary。
- Phase 8 public-chunk-v1 已实现但默认 AI_PUBLIC_CHUNK_RETRIEVAL=false。启用只允许可信网关签名 raw body 并提供唯一 visible_memo_ids；不修改 /api/ai/chat、memo-v1 或任何 collection/volume。

默认下一切片：执行 NEXT_STAGE_PROMPT 的 Phase 10 route B 收尾，只复用既有测试 Memo，在稳定登录态与真实参与者下记录四项简短反馈。Capture、Insight、一次 accepted Review、Context Pack 预算及 Chrome/Windows Markdown/JSON 复制均已有技术证据；没有完整权限、回滚与兼容证据时，不开启 public-chunk，不扩展浏览器客户端签名，也不新增通用 RAG/Agent/MCP/图数据库。

验证顺序：先运行相关定向测试；再按改动范围运行 ai-service pytest、scripts\verify-devmemo.ps1、docker compose config --quiet、web pnpm test/tsc/build/lint，最后 git diff --check。完成后更新状态、变更、交接、下一阶段 Prompt，提交；不自动 push。
~~~
