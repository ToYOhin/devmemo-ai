# 下一阶段 Prompt：发行闭环后的受控选择

~~~text
继续 H:\DevMemoAI 的 DevMemo AI 项目，不要从零设计。

协作模式：单 Agent。只使用 H:\DevMemoAI 主工作树；不要启动 Terra/Luna，也不要同时操作 project4 下的其他 worktree。每个阶段整体完成一个可验证垂直切片；只有用户明确要求时才 commit、push、打 tag 或发布。

先读取最小核心上下文：
1. docs/handoffs/2026-07-28-ghcr-public-closeout-handoff.md
2. docs/PROJECT_STATUS.md 顶部
3. docs/HANDOFF.md 顶部
4. docs/prompts/NEXT_STAGE_PROMPT.md
5. git status --short --branch
6. git log --oneline -8

只按当前任务用 rg -n 定向读取 docs/roadmap.md、docs/structure.md、docs/DECISIONS.md、docs/api.md、docs/oss-adoption.md；不要一次加载全部历史 Phase 文档。结构判断以实时源码、docs/structure.md 与上述 GHCR closeout handoff 为准；graphify-out/graph.json 停留在 2026-07-12，未覆盖近期 AI Inbox/Context Pack，只作历史索引。

当前事实：
- Memos Go server/store/proto 是原始 Memo、身份和权限事实源；AI Service 只存 AI 派生 SQLite 状态；Web 的 AiMemoInsights/AiMemoContextPack 是当前产品入口。
- 默认保持 deterministic + memory、AI_INDEX_ON_WEBHOOK=false、AI_INDEX_MODE=memo、AI_VECTOR_STORE=memory，且 AI_PUBLIC_CHUNK_RETRIEVAL=false。FastEmbed/Qdrant 只属于显式 adapters/profiles；默认 Compose 维持低 CPU 上限。
- Context Pack 是浏览器内存中的 provider-neutral 输出：只使用显式可见 Memo、accepted insights 与安全 title/summary/source_refs；不暴露 raw content、Webhook payload、secret 或 chunk content，不写 SQLite、不连 Qdrant、不启动 Agent/worker。
- Phase 10 route B、Phase 12 strict TypeScript baseline 与 Phase 13 strict lint gate 均已完成。Phase 11 自动化门禁已通过，但真实详情页与系统剪贴板复核仍需要有效 Memos 登录态；不得绕过认证或把历史证据写成新 pass。
- route A 仍必须等待真实 trusted gateway、Memos visibility mapping 和关闭 flag 的回滚条件。
- 仓库为 public，稳定 GitHub Release v0.1.0 已发布，private vulnerability reporting 已启用。独立 GHCR package `ghcr.io/toyohin/devmemo-ai` 已公开；未登录 Docker 客户端已验证 `stable` OCI index 包含 linux/amd64、linux/arm64、linux/arm/v7 manifest。

发行收尾已完成，没有默认下一切片。只有用户明确选择后才继续以下任一受控方向：
1. 在恢复正常 Memos 登录会话后，进行 Phase 11 只读详情页与系统剪贴板复核；
2. 在同时具备真实 trusted gateway、visibility mapping、关闭 flag 回滚条件后，评估 route A；
3. 提出一个新的、先有最小 proposal 与验收边界的产品目标。

不要重打 tag、重发 v0.1.0、修改产品配置或请求/保存密码或 token。仅文档改动时做 git diff --check 和最小相关检查；没有后端运行时代码改动时不重跑 AI 全量门禁。
~~~
