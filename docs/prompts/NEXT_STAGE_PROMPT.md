# 下一阶段 Prompt：Phase 12 Web strict TypeScript baseline

~~~text
Phase 11 Context Pack copy readiness is implemented: the browser-memory panel reports items, sources, and Markdown characters/max_chars; Markdown and JSON have consistent copied feedback plus format-specific aria-live status; changing the pack clears stale copied/manual/error state. Targeted tests are 7 passed, full Web tests are 33 files / 149 passed, and build/project lint pass. Real Chrome connected, but the current profile had no valid Memos login session or saved credentials, so the Phase 11 detail-page/system-clipboard recheck is explicitly unverified. Do not bypass Memos authentication or repeat Phase 10 route B. Read `docs/handoffs/2026-07-27-context-pack-copy-readiness-handoff.md`. Keep `AI_PUBLIC_CHUNK_RETRIEVAL=false`.

继续 H:\DevMemoAI 的 DevMemo AI 项目，不要从零设计。

协作模式：单 Agent。只使用 H:\DevMemoAI 主工作树；不要启动 Terra/Luna，也不要并行修改 project4 下的其他 worktree。整体推进一个完整、可验证的阶段切片；只有用户明确要求时才 push。

先读取：
1. docs/handoffs/2026-07-27-context-pack-copy-readiness-handoff.md
2. docs/PROJECT_STATUS.md 顶部
3. docs/HANDOFF.md 顶部
4. docs/roadmap.md 的 Phase 10/11
5. docs/DECISIONS.md 的 ADR-043/044/048/049/050
6. 本文件
7. git status --short --branch 与 git log --oneline -8

当前事实：
- Phase 10 route B 已完成，不再重复 Capture/Review/feedback；route A 没有真实受信任 gateway、Memos 可见范围映射与回滚条件，仍未验证。
- Phase 11 只改 Context Pack Web UI/文案/测试；没有 API、数据库、依赖、Memos 核心或公共 chat 改动。
- 项目 `pnpm lint` 使用 `tsc --noEmit --skipLibCheck` 并通过；独立 `pnpm exec tsc --noEmit` 当前报告 15 个既有第三方声明和 `src/types/view.d.ts` strict errors。
- 默认 Compose 只启动 Memos (`0.75` CPU) 与 AI Service (`0.25` CPU)；Qdrant/Ollama 只允许显式 profile。不要并行运行高负载 Web 命令。

本阶段唯一目标：Phase 12 修复 Web 独立 strict TypeScript baseline，使 `pnpm exec tsc --noEmit` 通过，同时保持运行时行为和公共契约不变。

执行边界：
- 先保存并分类当前 15 个错误，区分第三方 `.d.ts`、项目 `src/types/view.d.ts` 和真实源码错误；只修改解决根因所需的最小文件。
- 优先修正项目声明和窄范围类型兼容层；不得通过全局 `skipLibCheck`、关闭 strict、宽泛 `any`、`@ts-ignore` 或删除类型检查来制造通过。
- 本切片不升级或新增依赖。如果根因只能通过依赖升级解决，停止在可复核诊断与最小升级提案，不直接改 lockfile。
- 不修改 Context Pack contract/golden、Memos server/store/proto、AI Service API、`/api/ai/chat`、CitationResponse、memo-v1、public-chunk contract、collection 或 volume。
- 不创建/修改/删除 Memo 或 Insight，不提取 token，不绕过 Memos 认证，不把 Phase 10 剪贴板证据写成 Phase 11/12 新 pass。

验证顺序：
1. `pnpm exec tsc --noEmit`，确认错误从当前 baseline 收敛到 0；若未到 0，保留准确错误分类，不宣称完成。
2. 运行受影响模块的定向测试。
3. 串行运行 `pnpm exec vitest run --maxWorkers=1`、`pnpm build`、`pnpm lint`。
4. `docker compose config --quiet`；若没有后端代码改动，不重跑 AI Service 全量或 `verify-devmemo.ps1`。
5. `git diff --check`。

完成后更新 PROJECT_STATUS、CHANGELOG_AI、HANDOFF、roadmap、api、structure、DECISIONS、新 handoff 和本 Prompt；形成独立 commit，不自动 push。若 strict baseline 因必须升级依赖而阻塞，也提交仅包含准确诊断/提案的文档切片，不伪造通过。
~~~
