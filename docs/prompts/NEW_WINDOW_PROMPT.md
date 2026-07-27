# 新窗口启动 Prompt

~~~text
继续 H:\DevMemoAI 的 DevMemo AI 项目，不要从零设计。

协作模式：单 Agent。只使用 H:\DevMemoAI 主工作树；不要启动 Terra/Luna，也不要同时操作 project4 下的其他 worktree。每个阶段整体完成一个可验证垂直切片；只有用户明确要求时才 push。

先读取最小核心上下文：
1. docs/handoffs/2026-07-27-web-strict-typescript-handoff.md
2. docs/PROJECT_STATUS.md 顶部
3. docs/HANDOFF.md 顶部
4. docs/prompts/NEXT_STAGE_PROMPT.md
5. git status --short --branch
6. git log --oneline -8

只按当前任务用 rg -n 定向读取 docs/roadmap.md、docs/structure.md、docs/DECISIONS.md、docs/api.md、docs/oss-adoption.md；不要一次加载全部历史 Phase 文档。

当前事实：
- Memos Go server/store/proto 是原始 Memo 与权限事实源；AI Service 只存 AI 派生 SQLite 状态；Web 的 AiMemoInsights/AiMemoContextPack 是当前产品入口。
- 默认保持 deterministic + memory、AI_INDEX_ON_WEBHOOK=false、AI_INDEX_MODE=memo、AI_VECTOR_STORE=memory。FastEmbed/Qdrant 只属于显式 adapters/profiles。
- Context Pack 是浏览器内存中的 provider-neutral 输出：只使用显式可见 Memo、accepted insights 与安全 title/summary/source_refs；不暴露 raw content、Webhook payload、secret 或 chunk content，不写 SQLite、不连 Qdrant、不启动 Agent/worker。
- Phase 10 route B 已完成真实本地 Capture -> Insight -> accepted Review -> bounded Context Pack -> Chrome/Windows Markdown/JSON copy -> participant feedback，不重复该路径。
- Phase 11 已实现 copy readiness：items/sources/characters budget 摘要、两种格式一致的 copied 状态、aria-live 播报和 pack 变化后的旧状态清理。自动化 Web 门禁通过；由于当前 Chrome profile 缺少有效 Memos 登录态，本阶段真实详情页/系统剪贴板复核未验证，不能写成 pass。
- Phase 12 已把独立 strict TypeScript 从 15 个既有声明错误收敛到 0；使用明确 callback、两个精确 TypeScript-only paths 和窄范围第三方声明 bridge，没有依赖、lockfile 或运行时行为变化。
- Phase 8 public-chunk-v1 已实现但默认 AI_PUBLIC_CHUNK_RETRIEVAL=false。没有真实受信任 gateway、Memos 可见范围映射与回滚证据时，不开启、不扩展浏览器签名。
- `graphify-out/graph.json` 最后更新于 2026-07-12，没有近期 AI Inbox/Context Pack；结构判断以实时源码、docs/structure.md 和 2026-07-27 structure handoff 为准。

默认下一切片：执行 NEXT_STAGE_PROMPT 的 Phase 13 strict TypeScript lint gate promotion。只把 `pnpm lint` 的 TypeScript 子命令从 `tsc --noEmit --skipLibCheck` 提升为已验证通过的 `tsc --noEmit`；不升级依赖、不扩大 declaration bridge、不改变运行时行为。

验证顺序：先 `pnpm lint` 与显式 strict TypeScript；再串行运行 Web vitest/build；随后 docker compose config --quiet，最后 git diff --check。没有后端运行时代码改动时不重跑 AI 全量门禁。完成后更新状态、变更、交接、下一阶段 Prompt，提交；不自动 push。
~~~
